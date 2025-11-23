"""
Segment classification using GPT.

Classifies PdfSegments into categories for Polish SIWZ/SWZ medical documents.
"""

import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from ..models import PdfSegment
from .gpt_client import GPTClientProtocol

logger = logging.getLogger(__name__)


# Valid classification labels
VALID_LABELS = {
    "irrelevant",       # introductory/legal/meta info
    "general",          # general scope description
    "variant_header",   # variant headers like "WARIANT 1"
    "variant_body",     # service lists belonging to a variant
    "prophylaxis",      # prophylactic program sections
    "pricing_table"     # pricing tables (not medical variants)
}


class SegmentClassification(BaseModel):
    """
    Classification result for a single segment.
    
    Attributes:
        segment_id: ID of the classified segment
        label: Classification label (one of VALID_LABELS)
        variant_hint: Optional variant number ("1", "2", etc.) if applicable
        is_prophylaxis: True if this is part of prophylaxis program
        confidence: Confidence score 0.0-1.0
        rationale: Brief explanation of the classification
    """
    
    segment_id: str = Field(..., description="Segment identifier")
    label: str = Field(..., description="Classification label")
    variant_hint: Optional[str] = Field(None, description="Variant number if applicable")
    is_prophylaxis: bool = Field(False, description="Is prophylaxis section")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    rationale: str = Field(..., description="Classification rationale")
    
    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str) -> str:
        """Validate that label is one of the allowed values."""
        if v not in VALID_LABELS:
            raise ValueError(
                f"Invalid label '{v}'. Must be one of: {', '.join(sorted(VALID_LABELS))}"
            )
        return v
    
    @field_validator("is_prophylaxis")
    @classmethod
    def validate_prophylaxis_consistency(cls, v: bool, info) -> bool:
        """Ensure is_prophylaxis is consistent with label."""
        if info.data.get("label") == "prophylaxis" and not v:
            logger.warning("Prophylaxis label but is_prophylaxis=False, fixing")
            return True
        if info.data.get("label") != "prophylaxis" and v:
            logger.warning("is_prophylaxis=True but label is not prophylaxis, fixing")
            return False
        return v


# System prompt for GPT
SYSTEM_PROMPT = """Jesteś ekspertem w analizie dokumentów SIWZ/SWZ dla ubezpieczeń medycznych OPZ w Polsce.

Twoim zadaniem jest klasyfikacja segmentów tekstu do DOKŁADNIE JEDNEJ z następujących kategorii:

DOZWOLONE ETYKIETY:
- "irrelevant"       - tekst wprowadzający, prawny, metainformacje (nie opisuje usług ani wariantów)
- "general"          - ogólny opis zakresu, ale nie konkretny wariant ani lista usług
- "variant_header"   - nagłówki wprowadzające konkretne warianty medyczne, np. "Załącznik nr 2 A – WARIANT 1", "WARIANT 2"
- "variant_body"     - listy usług i opisy należące do konkretnego wariantu medycznego
- "prophylaxis"      - fragmenty opisujące program profilaktyczny (np. "profilaktyczny przegląd stanu zdrowia")
- "pricing_table"    - tabele/formularze gdzie "Wariant 1-4" to TYLKO kolumny cenowe w ofercie, NIE definicje pakietów medycznych

KLUCZOWE ZASADY DOMENOWE:
1. Słowo "Wariant" może występować w dwóch kontekstach:
   a) W OPZ jako rzeczywisty wariant medyczny → "variant_header" lub "variant_body"
   b) W edytowalnych załącznikach/formularzach ofertowych jako etykiety kolumn cenowych → "pricing_table"

2. Sekcje profilaktyki często wyglądają jak zwykłe listy usług, ale semantycznie są częścią "programu profilaktycznego" → muszą mieć etykietę "prophylaxis"

3. Używaj kontekstu (poprzedni i następny segment) do rozróżnienia niejednoznacznych przypadków

4. Później w pipeline "variant_header" + "variant_body" zostaną zgrupowane w warianty (V1, V2, ...). Segmenty "pricing_table" będą ignorowane przy liczeniu wariantów.

FORMAT WYJŚCIOWY:
MUSISZ zwrócić odpowiedź w ŚCISŁYM formacie JSON:
{
  "segment_id": "id_segmentu",
  "label": "jedna_z_dozwolonych_etykiet",
  "variant_hint": "numer_wariantu_lub_null",
  "is_prophylaxis": true_lub_false,
  "confidence": 0.0_do_1.0,
  "rationale": "krótkie_uzasadnienie_po_polsku"
}

ANTY-HALUCYNACJA:
- Używaj TYLKO tekstu z dostarczonych segmentów
- NIE wymyślaj ani nie dodawaj tekstu spoza segmentów
- Jeśli nie jesteś pewien, wybierz najlepsze dopasowanie i obniż confidence

Zawsze zwracaj poprawny JSON bez dodatkowego tekstu."""


def build_user_prompt(
    segment: PdfSegment,
    prev_text: str,
    next_text: str
) -> str:
    """
    Build user prompt for segment classification.
    
    Args:
        segment: Segment to classify
        prev_text: Text of previous segment (empty string if none)
        next_text: Text of next segment (empty string if none)
        
    Returns:
        Formatted user prompt
    """
    parts = ["Sklasyfikuj poniższy segment tekstu z dokumentu SIWZ.\n"]
    
    # Previous segment context
    if prev_text:
        parts.append(f"POPRZEDNI SEGMENT (kontekst):\n{prev_text[:300]}\n")
    
    # Current segment
    parts.append(f"AKTUALNY SEGMENT (do klasyfikacji):")
    parts.append(f"ID: {segment.segment_id}")
    parts.append(f"Strona: {segment.page}")
    if segment.section_label:
        parts.append(f"Sekcja: {segment.section_label}")
    parts.append(f"Tekst:\n{segment.text}\n")
    
    # Next segment context
    if next_text:
        parts.append(f"NASTĘPNY SEGMENT (kontekst):\n{next_text[:300]}\n")
    
    parts.append(
        "\nWybierz DOKŁADNIE JEDNĄ etykietę z listy: "
        "irrelevant, general, variant_header, variant_body, prophylaxis, pricing_table"
    )
    parts.append("\nZwróć odpowiedź jako JSON zgodnie ze schematem opisanym w instrukcjach systemowych.")
    
    return "\n".join(parts)


def classify_segment(
    client: GPTClientProtocol,
    segment: PdfSegment,
    prev_text: str = "",
    next_text: str = "",
    retry_on_error: bool = True
) -> SegmentClassification:
    """
    Classify a single segment using GPT.
    
    Args:
        client: GPT client (or mock)
        segment: Segment to classify
        prev_text: Previous segment text for context
        next_text: Next segment text for context
        retry_on_error: Whether to retry once on parse error
        
    Returns:
        Classification result
        
    Raises:
        ValueError: If response is invalid after retries
    """
    user_prompt = build_user_prompt(segment, prev_text, next_text)
    
    try:
        # First attempt
        response = client.chat(SYSTEM_PROMPT, user_prompt)
        result = _parse_classification_response(response, segment.segment_id)
        
        logger.debug(
            f"Classified {segment.segment_id} as '{result.label}' "
            f"(confidence={result.confidence:.2f})"
        )
        
        return result
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Parse error on first attempt: {e}")
        logger.debug(f"Raw response: {response[:200]}")
        
        if retry_on_error:
            # Retry with stricter instruction
            retry_prompt = user_prompt + (
                "\n\n⚠️  UWAGA: Poprzednia odpowiedź była niepoprawna. "
                "Musisz zwrócić TYLKO poprawny JSON, bez dodatkowego tekstu, "
                "markdown ani komentarzy. Zacznij od { i zakończ na }."
            )
            
            try:
                response = client.chat(SYSTEM_PROMPT, retry_prompt)
                result = _parse_classification_response(response, segment.segment_id)
                
                logger.info(f"Retry successful for {segment.segment_id}")
                return result
                
            except Exception as retry_error:
                logger.error(f"Retry also failed: {retry_error}")
        
        # Fallback: return low-confidence "irrelevant"
        logger.error(
            f"Could not parse GPT response for {segment.segment_id}, "
            f"falling back to 'irrelevant'"
        )
        
        return SegmentClassification(
            segment_id=segment.segment_id,
            label="irrelevant",
            variant_hint=None,
            is_prophylaxis=False,
            confidence=0.1,
            rationale=f"[FALLBACK] Nie udało się sparsować odpowiedzi GPT: {str(e)[:100]}"
        )


def _parse_classification_response(
    response: str,
    segment_id: str
) -> SegmentClassification:
    """
    Parse GPT response into SegmentClassification.
    
    Args:
        response: Raw GPT response (should be JSON)
        segment_id: Expected segment ID
        
    Returns:
        Parsed classification
        
    Raises:
        json.JSONDecodeError: If response is not valid JSON
        ValueError: If required fields missing or invalid
    """
    # Try to extract JSON if response has markdown formatting
    response = response.strip()
    
    # Remove markdown code blocks if present
    if response.startswith("```"):
        lines = response.split("\n")
        # Find first line that's not a markdown fence
        start_idx = 1 if lines[0].startswith("```") else 0
        # Find last line that's not a markdown fence
        end_idx = len(lines) - 1
        if lines[end_idx].startswith("```"):
            end_idx -= 1
        response = "\n".join(lines[start_idx:end_idx + 1]).strip()
    
    # Parse JSON
    data = json.loads(response)
    
    # Override segment_id with the correct one (GPT might hallucinate this)
    data["segment_id"] = segment_id
    
    # Create and validate using Pydantic
    classification = SegmentClassification(**data)
    
    return classification


def classify_segments(
    segments: List[PdfSegment],
    client: GPTClientProtocol,
    show_progress: bool = True
) -> List[SegmentClassification]:
    """
    Classify multiple segments.
    
    Args:
        segments: List of segments to classify
        client: GPT client (or mock for testing)
        show_progress: Whether to log progress
        
    Returns:
        List of classifications aligned with input segments
    """
    if not segments:
        logger.warning("No segments to classify")
        return []
    
    logger.info(f"Classifying {len(segments)} segments")
    
    classifications = []
    
    for i, segment in enumerate(segments):
        if show_progress and (i + 1) % 10 == 0:
            logger.info(f"Progress: {i + 1}/{len(segments)} segments classified")
        
        # Get context (previous and next segment text)
        prev_text = segments[i - 1].text if i > 0 else ""
        next_text = segments[i + 1].text if i < len(segments) - 1 else ""
        
        # Classify
        try:
            classification = classify_segment(
                client=client,
                segment=segment,
                prev_text=prev_text,
                next_text=next_text
            )
            classifications.append(classification)
            
        except Exception as e:
            logger.error(f"Error classifying segment {segment.segment_id}: {e}")
            # Add fallback classification
            classifications.append(
                SegmentClassification(
                    segment_id=segment.segment_id,
                    label="irrelevant",
                    variant_hint=None,
                    is_prophylaxis=False,
                    confidence=0.0,
                    rationale=f"[ERROR] {str(e)[:100]}"
                )
            )
    
    logger.info(f"Classification complete: {len(classifications)} results")
    
    # Log summary
    label_counts = {}
    for c in classifications:
        label_counts[c.label] = label_counts.get(c.label, 0) + 1
    
    logger.info(f"Label distribution: {label_counts}")
    
    return classifications

