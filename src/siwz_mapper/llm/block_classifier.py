"""
Block-level classification using GPT.

Classifies SemanticBlock objects into the same label space as segment-level
classification, but on larger semantic units.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Dict

from pydantic import ValidationError

from ..models import SemanticBlock, BlockClassification
from .gpt_client import GPTClientProtocol
from .classify_segments import (
    SegmentClassification,
    VALID_LABELS,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_BLOCK = """Jesteś ekspertem w analizie dokumentów SIWZ/SWZ dla ubezpieczeń medycznych OPZ w Polsce.

Twoim zadaniem jest klasyfikacja WIĘKSZYCH BLOKÓW tekstu (sekcji) do DOKŁADNIE JEDNEJ z następujących kategorii:

DOZWOLONE ETYKIETY:
- "irrelevant"       - tekst wprowadzający, prawny, metainformacje (nie opisuje usług ani wariantów)
- "general"          - ogólny opis zakresu, ale nie konkretny wariant ani lista usług
- "variant_header"   - nagłówki wprowadzające konkretne warianty medyczne, np. "Załącznik nr 2 A – WARIANT 1", "WARIANT 2", "Pakiet Rodzina"
- "variant_body"     - listy usług i opisy należące do konkretnego wariantu medycznego (cały zakres świadczeń dla pakietu/wariantu)
- "prophylaxis"      - fragmenty opisujące program profilaktyczny (np. "profilaktyczny przegląd stanu zdrowia")
- "pricing_table"    - tabele/formularze gdzie "Wariant 1-4" to TYLKO kolumny cenowe w ofercie, NIE definicje pakietów medycznych

WAŻNE:
- Pojęcie "blok" oznacza tutaj większą sekcję (często kilka akapitów lub tabelę), a nie pojedynczą linijkę.
- Ten blok może zawierać nagłówek, listę punktów, wiersze tabeli itp.

KLUCZOWE ZASADY DOMENOWE:
1. Słowo "Wariant" / "Pakiet" może występować w dwóch kontekstach:
   a) W OPZ jako rzeczywisty wariant medyczny → "variant_header" lub "variant_body"
   b) W edytowalnych załącznikach/formularzach ofertowych jako etykiety kolumn cenowych → "pricing_table"

2. Sekcje profilaktyki często wyglądają jak zwykłe listy usług, ale semantycznie są częścią "programu profilaktycznego" → muszą mieć etykietę "prophylaxis"

3. Używaj kontekstu (poprzedni i następny blok) do rozróżnienia niejednoznacznych przypadków.

FORMAT WYJŚCIOWY:
MUSISZ zwrócić odpowiedź w ŚCISŁYM formacie JSON:
{
  "block_id": "id_bloku",
  "label": "jedna_z_dozwolonych_etykiet",
  "variant_hint": "numer_lub_nazwa_wariantu_lub_null",
  "is_prophylaxis": true_lub_false,
  "confidence": 0.0_do_1.0,
  "rationale": "krótkie_uzasadnienie_po_polsku"
}

ANTY-HALUCYNACJA:
- Używaj TYLKO tekstu z dostarczonego bloku i kontekstu
- NIE wymyślaj ani nie dodawaj tekstu spoza bloku
- Jeśli nie jesteś pewien, wybierz najlepsze dopasowanie i obniż confidence

Zawsze zwracaj poprawny JSON bez dodatkowego tekstu."""


def build_block_user_prompt(
    block: SemanticBlock,
    prev_text: str,
    next_text: str,
) -> str:
    """
    Build user prompt for block-level classification.

    Args:
        block: Semantic block to classify
        prev_text: Text of previous block (empty string if none)
        next_text: Text of next block (empty string if none)
    """
    parts = ["Sklasyfikuj poniższy BLOK tekstu z dokumentu SIWZ.\n"]

    if prev_text:
        parts.append("POPRZEDNI BLOK (kontekst):\n")
        parts.append(prev_text[:800] + "\n")

    parts.append("AKTUALNY BLOK (do klasyfikacji):\n")
    parts.append(f"ID bloku: {block.block_id}\n")
    parts.append(f"Zakres stron: {block.page_start}–{block.page_end}\n")
    if block.type_hint:
        parts.append(f"Hint typu bloku (layout): {block.type_hint}\n")
    parts.append("Tekst bloku:\n")
    parts.append(block.text)
    parts.append("\n")

    if next_text:
        parts.append("NASTĘPNY BLOK (kontekst):\n")
        parts.append(next_text[:800] + "\n")

    parts.append(
        "\nWybierz DOKŁADNIE JEDNĄ etykietę z listy: "
        "irrelevant, general, variant_header, variant_body, prophylaxis, pricing_table"
    )
    parts.append(
        "\nZwróć odpowiedź jako JSON zgodnie ze schematem opisanym w instrukcjach systemowych."
    )

    return "\n".join(parts)


def _parse_block_classification_response(
    response: str,
    block_id: str,
) -> BlockClassification:
    """
    Parse GPT response into BlockClassification.

    Raises:
        json.JSONDecodeError, ValueError, ValidationError
    """
    response = response.strip()

    # Remove markdown code fences if present
    if response.startswith("```"):
        lines = response.split("\n")
        start_idx = 1 if lines[0].startswith("```") else 0
        end_idx = len(lines) - 1
        if lines[end_idx].startswith("```"):
            end_idx -= 1
        response = "\n".join(lines[start_idx : end_idx + 1]).strip()

    data = json.loads(response)

    # Force the correct block_id (GPT may hallucinate it)
    data["block_id"] = block_id

    # Default sanity for label / fields
    if "label" not in data:
        raise ValueError("Missing 'label' in block classification response")

    label = data["label"]
    if label not in VALID_LABELS:
        raise ValueError(
            f"Invalid block label '{label}'. Must be one of: {', '.join(sorted(VALID_LABELS))}"
        )

    # Provide safe defaults if missing
    data.setdefault("variant_hint", None)
    data.setdefault("is_prophylaxis", label == "prophylaxis")
    data.setdefault("confidence", 0.5)
    data.setdefault("rationale", "Brak szczegółowego uzasadnienia (domyślne).")

    return BlockClassification(**data)


def classify_block(
    client: GPTClientProtocol,
    block: SemanticBlock,
    prev_text: str = "",
    next_text: str = "",
    retry_on_error: bool = True,
) -> BlockClassification:
    """
    Classify a single semantic block using GPT.
    """
    user_prompt = build_block_user_prompt(block, prev_text, next_text)

    try:
        response = client.chat(SYSTEM_PROMPT_BLOCK, user_prompt)
        result = _parse_block_classification_response(response, block.block_id)

        logger.debug(
            "Classified block %s as '%s' (confidence=%.2f)",
            block.block_id,
            result.label,
            result.confidence,
        )
        return result

    except (json.JSONDecodeError, ValueError, KeyError, ValidationError) as e:
        logger.warning("Block parse error on first attempt (%s)", e)
        logger.debug("Raw block response: %s", response[:200] if "response" in locals() else "")

        if retry_on_error:
            retry_prompt = user_prompt + (
                "\n\n⚠️  UWAGA: Poprzednia odpowiedź była niepoprawna. "
                "Musisz zwrócić TYLKO poprawny JSON, bez dodatkowego tekstu, "
                "markdown ani komentarzy. Zacznij od { i zakończ na }."
            )
            try:
                response = client.chat(SYSTEM_PROMPT_BLOCK, retry_prompt)
                result = _parse_block_classification_response(response, block.block_id)
                logger.info("Retry successful for block %s", block.block_id)
                return result
            except Exception as retry_error:
                logger.error(
                    "Retry for block %s also failed: %s",
                    block.block_id,
                    retry_error,
                )

        logger.error(
            "Could not parse GPT response for block %s, falling back to 'irrelevant'",
            block.block_id,
        )

        return BlockClassification(
            block_id=block.block_id,
            label="irrelevant",
            variant_hint=None,
            is_prophylaxis=False,
            confidence=0.1,
            rationale=f"[FALLBACK] Nie udało się sparsować odpowiedzi GPT: {str(e)[:100]}",
        )


def classify_blocks(
    blocks: List[SemanticBlock],
    client: GPTClientProtocol,
    show_progress: bool = True,
) -> List[BlockClassification]:
    """
    Classify multiple semantic blocks.

    Returns:
        List of BlockClassification aligned with input blocks.
    """
    if not blocks:
        logger.warning("No blocks to classify")
        return []

    logger.info("Classifying %d semantic blocks", len(blocks))

    classifications: List[BlockClassification] = []

    for i, block in enumerate(blocks):
        if show_progress and (i + 1) % 10 == 0:
            logger.info(
                "Progress: %d/%d blocks classified",
                i + 1,
                len(blocks),
            )

        prev_text = blocks[i - 1].text if i > 0 else ""
        next_text = blocks[i + 1].text if i < len(blocks) - 1 else ""

        try:
            cls = classify_block(
                client=client,
                block=block,
                prev_text=prev_text,
                next_text=next_text,
            )
            classifications.append(cls)
        except Exception as e:
            logger.error("Error classifying block %s: %s", block.block_id, e)
            classifications.append(
                BlockClassification(
                    block_id=block.block_id,
                    label="irrelevant",
                    variant_hint=None,
                    is_prophylaxis=False,
                    confidence=0.0,
                    rationale=f"[ERROR] {str(e)[:100]}",
                )
            )

    logger.info("Block classification complete: %d results", len(classifications))

    # Log summary
    label_counts: Dict[str, int] = {}
    for c in classifications:
        label_counts[c.label] = label_counts.get(c.label, 0) + 1

    logger.info("Block label distribution: %s", label_counts)

    return classifications


def project_block_classes_to_segments(
    blocks: List[SemanticBlock],
    block_classes: List[BlockClassification],
) -> List[SegmentClassification]:
    """
    Project block-level classifications onto underlying PdfSegments.

    For each SemanticBlock and its BlockClassification, all underlying
    PdfSegments receive the same label, variant_hint, is_prophylaxis,
    confidence and rationale.

    Returned list is in the same order as flattening:
        for block in blocks:
            for seg in block.segments:
                ...

    This makes it easy to feed into VariantAggregator, which expects
    SegmentClassification aligned with a list of PdfSegment objects.
    """
    if len(blocks) != len(block_classes):
        raise ValueError(
            f"blocks ({len(blocks)}) and block_classes ({len(block_classes)}) "
            f"must have the same length"
        )

    per_segment: List[SegmentClassification] = []

    for block, cls in zip(blocks, block_classes):
        for seg in block.segments:
            per_segment.append(
                SegmentClassification(
                    segment_id=seg.segment_id,
                    label=cls.label,
                    variant_hint=cls.variant_hint,
                    is_prophylaxis=cls.is_prophylaxis,
                    confidence=cls.confidence,
                    rationale=cls.rationale,
                )
            )

    return per_segment
