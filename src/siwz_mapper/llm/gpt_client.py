"""
GPT Client for OpenAI API integration.

Provides a simple, testable wrapper around OpenAI's chat completion API.
"""

import os
import logging
from typing import Optional, Protocol
import json

logger = logging.getLogger(__name__)


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
    - Simple chat interface
    - Easy to mock for testing
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        api_key: Optional[str] = None,
        timeout: int = 60
    ):
        """
        Initialize GPT client.
        
        Args:
            model: OpenAI model name (default: gpt-4o-mini)
            temperature: Sampling temperature 0.0-2.0 (default: 0.0 for deterministic)
            api_key: OpenAI API key (if None, reads from OPENAI_API_KEY env var)
            timeout: Request timeout in seconds
            
        Raises:
            ValueError: If API key is not provided and not in environment
        """
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        
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
            self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )
        
        logger.info(
            f"Initialized GPTClient (model={model}, temperature={temperature})"
        )
    
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a chat completion request.
        
        Args:
            system_prompt: System message (context, instructions)
            user_prompt: User message (actual query/task)
            
        Returns:
            Assistant's response as string
            
        Raises:
            Exception: If API call fails
        """
        try:
            logger.debug(f"Sending chat request to {self.model}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            content = response.choices[0].message.content
            
            logger.debug(f"Received response ({len(content)} chars)")
            
            return content
            
        except Exception as e:
            logger.error(f"GPT API call failed: {e}")
            raise


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

