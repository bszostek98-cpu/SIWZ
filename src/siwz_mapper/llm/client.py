"""LLM API client wrapper."""

from typing import Dict, Any, Optional
import logging
import json

from ..config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Wrapper for LLM API calls.
    
    Enforces constraints:
    - Always include source snippet in prompt
    - Strict instruction to quote only from snippet
    - Request JSON output with schema
    - Include confidence scores
    """
    
    def __init__(self, config: LLMConfig):
        """
        Initialize LLM client.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        logger.info(f"Initialized LLMClient (provider={config.provider}, model={config.model})")
    
    def call(
        self,
        prompt: str,
        source_snippet: str,
        json_schema: Dict[str, Any],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Make LLM API call with enforced constraints.
        
        Args:
            prompt: Main prompt/instruction
            source_snippet: Source text snippet (must be included)
            json_schema: Expected JSON output schema
            system_prompt: Optional system prompt
            
        Returns:
            Parsed JSON response
            
        Note:
            This is a STUB. Real implementation would:
            1. Construct prompt with source snippet
            2. Add instructions to quote only from snippet
            3. Request JSON output matching schema
            4. Call OpenAI/Azure API
            5. Parse and validate response
        """
        logger.info("Making LLM call")
        
        # Construct full prompt with constraints
        full_prompt = self._build_constrained_prompt(
            prompt=prompt,
            source_snippet=source_snippet,
            json_schema=json_schema
        )
        
        # STUB: Return empty response
        stub_response = {
            "result": [],
            "confidence": 0.0,
            "reasoning": "[STUB] Brak implementacji LLM"
        }
        
        logger.info("LLM call complete (stub)")
        return stub_response
    
    def _build_constrained_prompt(
        self,
        prompt: str,
        source_snippet: str,
        json_schema: Dict[str, Any]
    ) -> str:
        """
        Build prompt with all required constraints.
        
        Args:
            prompt: Base prompt
            source_snippet: Source text
            json_schema: Expected schema
            
        Returns:
            Full prompt with constraints
        """
        constraints = [
            "KRYTYCZNE ZASADY:",
            "1. Cytuj TYLKO tekst z dostarczonego fragmentu źródłowego",
            "2. NIE WYMYŚLAJ ani nie dodawaj tekstu spoza fragmentu",
            "3. Zwróć odpowiedź w formacie JSON zgodnym ze schematem",
            "4. Dołącz współczynnik pewności (confidence) dla każdego wyniku"
        ]
        
        schema_str = json.dumps(json_schema, indent=2, ensure_ascii=False)
        
        full_prompt = f"""
{chr(10).join(constraints)}

SCHEMAT JSON:
{schema_str}

FRAGMENT ŹRÓDŁOWY:
{source_snippet}

ZADANIE:
{prompt}

Odpowiedz w formacie JSON:
"""
        
        return full_prompt
    
    def call_streaming(
        self,
        prompt: str,
        source_snippet: str,
        json_schema: Dict[str, Any]
    ):
        """
        Make streaming LLM call (for future UI).
        
        Args:
            prompt: Main prompt
            source_snippet: Source text
            json_schema: Expected schema
            
        Yields:
            Response chunks
        """
        # STUB: Not implemented yet
        raise NotImplementedError("Streaming not yet implemented")

