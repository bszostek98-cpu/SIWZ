"""
GPT Client for OpenAI API integration.

Provides a simple, testable wrapper around OpenAI's chat completion API.
"""

import os
import logging
from typing import Optional, Protocol, List
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)



@dataclass
class LLMUsageStats:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_calls += 1

@dataclass
class LLMCallRecord:
    """
    Jeden zapis wywołania LLM do debugowania.
    """
    model: str
    call_type: str               # "chat" lub "ask_structured"
    prompt_tokens: int
    completion_tokens: int
    system_prompt: str
    user_prompt: str


class GPTClientProtocol(Protocol):
    """Protocol for GPT client (enables easy mocking in tests)."""
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat completion request.
        
        Args:
            system_prompt: System message (context, instructions)
            user_prompt: User message (actual query/task)
            
        Returns:
            Assistant's response as string
        """
        ...


class GPTClient:
    """
    Central GPT client wrapper for OpenAI API.
    
    Features:
    - Reads OPENAI_API_KEY from environment
    - Configurable model and temperature
    - Optional configurable timeout (only if explicitly set)
    - Simple chat interface
    - Easy to mock for testing
    """
    
    def __init__(
        self,
        model: str = "gpt-5-mini",
        temperature: float = 0.0,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize GPT client.
        
        Args:
            model: OpenAI model name (default: gpt-5-mini)
            temperature: Sampling temperature 0.0-2.0 (default: 0.0 for deterministic)
            api_key: OpenAI API key (if None, reads from OPENAI_API_KEY env var)
            timeout: Optional request timeout in seconds.
                     - If None (default): use OpenAI client's default timeout.
                     - If set (e.g. 1800.0): all requests will use this timeout.
            
        Raises:
            ValueError: If API key is not provided and not in environment
        """
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.usage_stats = LLMUsageStats()
        self.call_history: List[LLMCallRecord] = []
        
        # Get API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Please set OPENAI_API_KEY environment variable "
                "or pass api_key parameter.\n\n"
                "Example (Windows PowerShell):\n"
                "  $env:OPENAI_API_KEY = 'your-api-key-here'\n\n"
                "Example (Linux/Mac):\n"
                "  export OPENAI_API_KEY='your-api-key-here'"
            )
        
        # Import OpenAI client (lazy import to avoid dependency if not using GPT)
        try:
            from openai import OpenAI
            # Jeśli timeout nie jest podany -> użyj domyślnego zachowania klienta OpenAI
            if self.timeout is None:
                self.client = OpenAI(api_key=self.api_key)
            else:
                self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        logger.info(
            f"Initialized GPTClient (model={model}, temperature={temperature}, timeout={self.timeout})"
        )
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat completion request.

        Zbiera też informacje debugowe:
        - liczba tokenów wejścia/wyjścia
        - pełne prompty w call_history
        """
        try:
            logger.debug(f"Sending chat request to {self.model}")

            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            usage = getattr(response, "usage", None)
            prompt_tokens = 0
            completion_tokens = 0

            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                self.usage_stats.add(prompt_tokens, completion_tokens)

            content = response.choices[0].message.content
            logger.debug(f"Received response ({len(content)} chars)")

            # zapisujemy do historii
            self.call_history.append(
                LLMCallRecord(
                    model=self.model,
                    call_type="chat",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            )

            return content

        except Exception as e:
            logger.error(f"GPT API call failed: {e}")
            raise

    def print_debug_report(self, max_prompt_chars: int = 300) -> None:
        """
        Drukuje raport wszystkich wywołań LLM:
        - typ wywołania
        - liczba tokenów
        - ucięte prompty (system + user)

        max_prompt_chars – ile znaków promptu pokazać (żeby nie zalać terminala).
        """
        print("\n=== LLM DEBUG REPORT ===")
        print(f"Total calls: {len(self.call_history)}\n")

        for i, rec in enumerate(self.call_history, start=1):
            print(f"--- CALL #{i} ---")
            print(f"Type: {rec.call_type}, model: {rec.model}")
            print(f"Prompt tokens: {rec.prompt_tokens}, completion tokens: {rec.completion_tokens}")
            print("\n[SYSTEM PROMPT] (truncated)")
            print(rec.system_prompt[:max_prompt_chars])
            if len(rec.system_prompt) > max_prompt_chars:
                print("... [truncated]")
            print("\n[USER PROMPT] (truncated)")
            print(rec.user_prompt[:max_prompt_chars])
            if len(rec.user_prompt) > max_prompt_chars:
                print("... [truncated]")
            print()




def estimate_cost_usd(model: str, usage: LLMUsageStats) -> float:
    """
    Szacuje koszt na podstawie liczby tokenów i cennika za 1M tokenów.
    WYPEŁNIJ ceny odpowiednio do swojego konta.
    """
    # PRZYKŁAD – wpisz swoje realne ceny:
    PRICING_PER_MILLION = {
        # "model_name": (input_per_million, output_per_million)
        # liczby poniżej są PRZYKŁADOWE, podmień na swoje:
        "gpt-5-mini": (0.25, 2.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1-mini": (0.15, 0.60),
        "gpt-5-nano": (0.05, 0.40),
    }

    input_price, output_price = PRICING_PER_MILLION.get(model, (0.0, 0.0))

    cost_input = usage.total_prompt_tokens * (input_price / 1_000_000)
    cost_output = usage.total_completion_tokens * (output_price / 1_000_000)

    return cost_input + cost_output


def print_llm_usage_summary(client: GPTClient) -> None:
    """
    Wypisuje podsumowanie użycia LLM i szacowany koszt.
    """
    usage = client.usage_stats
    model = client.model

    total_prompt = usage.total_prompt_tokens
    total_completion = usage.total_completion_tokens
    total_tokens = total_prompt + total_completion
    cost = estimate_cost_usd(model, usage)

    print("\n=== LLM USAGE SUMMARY ===")
    print(f"Model              : {model}")
    print(f"Prompt tokens      : {total_prompt}")
    print(f"Completion tokens  : {total_completion}")
    print(f"Total tokens       : {total_tokens}")
    print(f"Estimated cost (USD): {cost:.6f}")


class FakeGPTClient:
    """
    Fake GPT client for testing (no API calls).
    
    Returns deterministic responses based on simple keyword matching.
    """
    
    def __init__(self, responses: Optional[dict] = None):
        """
        Initialize fake client.
        
        Args:
            responses: Optional dict mapping keywords to responses
        """
        self.responses = responses or {}
        self.call_count = 0
        self.last_system_prompt = None
        self.last_user_prompt = None
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Return fake response based on keywords in user_prompt.
        
        Args:
            system_prompt: System prompt (stored but not used)
            user_prompt: User prompt (analyzed for keywords)
            
        Returns:
            Fake JSON response
        """
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        
        # Check for custom responses
        for keyword, response in self.responses.items():
            if keyword.lower() in user_prompt.lower():
                return response
        
        # Extract the current segment (between "AKTUALNY SEGMENT" and "NASTĘPNY SEGMENT" or end)
        current_segment_text = user_prompt
        if "AKTUALNY SEGMENT" in user_prompt:
            # Extract only the current segment part
            start = user_prompt.find("AKTUALNY SEGMENT")
            end = user_prompt.find("NASTĘPNY SEGMENT")
            if end == -1:
                end = len(user_prompt)
            current_segment_text = user_prompt[start:end]
        
        # Default keyword-based classification
        user_lower = current_segment_text.lower()
        
        # Variant headers (check first before general irrelevant)
        if "wariant 1" in user_lower or ("załącznik" in user_lower and "wariant" in user_lower):
            if "tabela" in user_lower or "cenowa" in user_lower or ("oferta" in user_lower and "cena" in user_lower):
                # Pricing table
                return json.dumps({
                    "segment_id": "test",
                    "label": "pricing_table",
                    "variant_hint": None,
                    "is_prophylaxis": False,
                    "confidence": 0.9,
                    "rationale": "Tabela cenowa z kolumnami wariantów"
                }, ensure_ascii=False)
            else:
                # Real variant header
                return json.dumps({
                    "segment_id": "test",
                    "label": "variant_header",
                    "variant_hint": "1",
                    "is_prophylaxis": False,
                    "confidence": 0.95,
                    "rationale": "Nagłówek wariantu medycznego"
                }, ensure_ascii=False)
        
        # General or irrelevant
        if ("ogłoszenie" in user_lower or "zamówien" in user_lower or 
            "rozdział i" in user_lower or "postępowanie" in user_lower):
            return json.dumps({
                "segment_id": "test",
                "label": "irrelevant",
                "variant_hint": None,
                "is_prophylaxis": False,
                "confidence": 0.8,
                "rationale": "Tekst wprowadzający lub prawny"
            }, ensure_ascii=False)
        
        # Prophylaxis
        if "profilakt" in user_lower or "przegląd stanu zdrowia" in user_lower:
            return json.dumps({
                "segment_id": "test",
                "label": "prophylaxis",
                "variant_hint": None,
                "is_prophylaxis": True,
                "confidence": 0.92,
                "rationale": "Program profilaktyczny"
            }, ensure_ascii=False)
        
        # Variant body (service lists)
        if ("•" in user_prompt or "konsultacja" in user_lower or "badanie" in user_lower):
            return json.dumps({
                "segment_id": "test",
                "label": "variant_body",
                "variant_hint": None,
                "is_prophylaxis": False,
                "confidence": 0.85,
                "rationale": "Lista usług w wariancie"
            }, ensure_ascii=False)
        
        # Default
        return json.dumps({
            "segment_id": "test",
            "label": "general",
            "variant_hint": None,
            "is_prophylaxis": False,
            "confidence": 0.7,
            "rationale": "Ogólny opis zakresu"
        }, ensure_ascii=False)

