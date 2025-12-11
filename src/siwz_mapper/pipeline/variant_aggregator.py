"""
Variant aggregation from classified segments.

Takes classified segments and groups them into variants based on:
- variant_header labels (start new variant)
- variant_body labels (belong to current variant)
- prophylaxis labels (tracked separately per variant)

This version uses light heuristics to avoid treating nagłówki pojedynczych usług
(np. "Ambulatoryjna opieka pielęgniarska", "Badania moczu") jako osobne warianty.

Dodatkowo:
- wewnątrz wariantu trzymamy też segmenty z innymi etykietami (general,
  pricing_table, itp.) w polu `other_segments`, żeby np. blokowe nagłówki typu
  "Badania moczu (...)" były dostępne podczas ekstrakcji usług.
"""

import logging
import re
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from ..models import PdfSegment
from ..llm.classify_segments import SegmentClassification

logger = logging.getLogger(__name__)


class VariantGroup(BaseModel):
    """
    A grouped variant with its segments.

    Attributes:
        variant_id: Unique variant identifier (e.g., "V1", "V2", "V_STD")
        header_segment: Optional header segment that started this variant
        body_segments: List of segments belonging to this variant's body
        prophylaxis_segments: List of prophylaxis segments associated with this variant
        other_segments: Other segments inside variant range (general, pricing_table, itp.)
    """

    variant_id: str = Field(..., description="Variant identifier")
    header_segment: Optional[PdfSegment] = Field(None, description="Header segment")

    body_segments: List[PdfSegment] = Field(
        default_factory=list, description="Body segments"
    )
    prophylaxis_segments: List[PdfSegment] = Field(
        default_factory=list, description="Prophylaxis segments"
    )
    other_segments: List[PdfSegment] = Field(
        default_factory=list,
        description="Inne segmenty wewnątrz zakresu wariantu (general, pricing_table, itp.)",
    )

    def segment_count(self) -> int:
        """Total number of segments in this variant."""
        count = len(self.body_segments) + len(self.prophylaxis_segments) + len(
            self.other_segments
        )
        if self.header_segment:
            count += 1
        return count


class VariantAggregator:
    """
    Aggregates classified segments into variants.

    High-level rules:
    1. Only wybrane segmenty z etykietą 'variant_header' są traktowane jako
       prawdziwe nagłówki wariantów (używamy heurystyk tekstowych).
    2. Dla każdego nagłówka wariantu zbieramy kolejne segmenty jako 'body',
       'prophylaxis' lub 'other' aż do następnego nagłówka wariantu.
    3. Jeśli nie znaleziono żadnych nagłówków, zakładamy pojedynczy wariant
       default_variant_id.
    """

    def __init__(
        self,
        default_variant_id: str = "V1",
        min_header_confidence: float = 0.6,
        use_header_heuristics: bool = True,
        header_keywords: Optional[List[str]] = None,
    ):
        """
        Initialize aggregator.

        Args:
            default_variant_id: Default variant ID if no headers found
            min_header_confidence: Minimal confidence for a segment to be
                                   accepted as a variant header
            use_header_heuristics: Whether to apply text heuristics when
                                   deciding if a segment is a true header
            header_keywords: Optional custom list of substrings that suggest
                             "this is a variant/package header"
        """
        self.default_variant_id = default_variant_id
        self.min_header_confidence = min_header_confidence
        self.use_header_heuristics = use_header_heuristics

        # Słowa-klucze sugerujące, że dany nagłówek opisuje wariant/pakiet,
        # a nie pojedynczą usługę.
        if header_keywords is not None:
            self.header_keywords = [kw.lower() for kw in header_keywords]
        else:
            self.header_keywords = [
                "wariant",  # WARIANT 1, WARIANT 2...
                "pakiet",  # Pakiet Standard, Pakiet Max
                "zestaw",
                "plan",
                "program",
                "grupa",
                "opcja",  # Opcja Standard / Plus
                "standard",
                "rozszerzon",  # rozszerzony / rozszerzona
                "max",
                "maks",
                "plus",
                "rodzina",
                "dzieci",
            ]

        # Wzorzec dla typowych "ponumerowanych usług": "11. coś tam"
        self._numbered_item_pattern = re.compile(r"^\s*\d{1,3}\.\s")

        logger.info(
            "Initialized VariantAggregator "
            f"(default={default_variant_id}, "
            f"min_header_confidence={min_header_confidence}, "
            f"use_header_heuristics={use_header_heuristics})"
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def aggregate(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification],
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate segments into variants.

        Args:
            segments: List of PdfSegment objects
            classifications: Corresponding classifications for each segment

        Returns:
            Tuple of:
            - Updated segments with variant_id assigned (tam gdzie ma sens)
            - List of VariantGroup objects
        """
        if len(segments) != len(classifications):
            raise ValueError(
                f"Segments ({len(segments)}) and classifications "
                f"({len(classifications)}) must have same length"
            )

        if not segments:
            logger.warning("No segments to aggregate")
            return [], []

        logger.info(f"Aggregating {len(segments)} segments into variants")

        # 1) Wyciągnij kandydatów na nagłówki wariantów
        variant_headers = self._extract_variant_headers(segments, classifications)

        if not variant_headers:
            logger.info(
                "No variant headers found after heuristics, "
                f"using single default variant {self.default_variant_id}"
            )
            # Single variant case
            return self._aggregate_single_variant(segments, classifications)

        # 2) Standardowy przypadek: wiele wariantów
        return self._aggregate_multiple_variants(
            segments,
            classifications,
            variant_headers,
        )

    def get_variant_ids(self, variant_groups: List[VariantGroup]) -> List[str]:
        """
        Extract list of variant IDs from variant groups.
        """
        return [vg.variant_id for vg in variant_groups]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _is_valid_header_candidate(
        self,
        segment: PdfSegment,
        cls: SegmentClassification,
    ) -> bool:
        """
        Decide whether a given (segment, classification) should be treated
        as a real variant header.
        """
        if cls.label != "variant_header":
            return False

        text = (segment.text or "").strip()
        if not text:
            return False

        lowered = text.lower()

        # 1) Minimalny confidence
        if cls.confidence is not None and cls.confidence < self.min_header_confidence:
            logger.debug(
                "Skipping header candidate %s (low confidence %.2f)",
                segment.segment_id,
                cls.confidence,
            )
            return False

        if not self.use_header_heuristics:
            return True

        first_line = lowered.splitlines()[0].strip()

        # 2) Wygląda jak typowa ponumerowana usługa: "11. Coś tam"
        if self._numbered_item_pattern.match(first_line):
            has_keyword = any(kw in lowered for kw in self.header_keywords)
            if not has_keyword:
                logger.debug(
                    "Skipping header candidate %s (looks like numbered service, "
                    "no header keyword)",
                    segment.segment_id,
                )
                return False

        # 3) Nagłówki "Załącznik nr 2 A..." traktujemy jako meta-info
        if "załącznik" in lowered:
            has_keyword = any(kw in lowered for kw in self.header_keywords)
            if not has_keyword:
                logger.debug(
                    "Skipping header candidate %s (looks like attachment heading, "
                    "no header keyword)",
                    segment.segment_id,
                )
                return False

        # 4) Ogólna logika: jeśli zawiera słowo-kluczowe → sensowny nagłówek wariantu
        has_any_keyword = any(kw in lowered for kw in self.header_keywords)
        if has_any_keyword:
            return True

        logger.debug(
            "Skipping header candidate %s (no strong header signal: '%s')",
            segment.segment_id,
            first_line,
        )
        return False

    def _extract_variant_headers(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification],
    ) -> List[Tuple[int, str, PdfSegment, SegmentClassification]]:
        """
        Extract variant headers with their positions.

        Returns:
            List of tuples: (index, variant_id, segment, classification)
        """
        headers: List[Tuple[int, str, PdfSegment, SegmentClassification]] = []

        for i, (seg, cls) in enumerate(zip(segments, classifications)):
            if not self._is_valid_header_candidate(seg, cls):
                continue

            if cls.variant_hint:
                variant_id = f"V{cls.variant_hint}"
            else:
                variant_id = f"V{len(headers) + 1}"

            headers.append((i, variant_id, seg, cls))
            logger.debug(
                "Accepted variant header at index %d: %s (segment_id=%s)",
                i,
                variant_id,
                seg.segment_id,
            )

        logger.info("Extracted %d variant headers after heuristics", len(headers))
        return headers

    def _aggregate_single_variant(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification],
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate all segments into a single default variant.
        """
        variant_id = self.default_variant_id

        updated_segments: List[PdfSegment] = []
        body_segments: List[PdfSegment] = []
        prophylaxis_segments: List[PdfSegment] = []
        other_segments: List[PdfSegment] = []

        for seg, cls in zip(segments, classifications):
            updated_seg = seg.model_copy(deep=True)
            updated_seg.variant_id = variant_id

            if cls.label == "variant_body":
                body_segments.append(updated_seg)
            elif cls.label == "prophylaxis":
                prophylaxis_segments.append(updated_seg)
            else:
                other_segments.append(updated_seg)

            updated_segments.append(updated_seg)

        variant_group = VariantGroup(
            variant_id=variant_id,
            header_segment=None,
            body_segments=body_segments,
            prophylaxis_segments=prophylaxis_segments,
            other_segments=other_segments,
        )

        logger.info(
            "Created single variant %s: %d body, %d prophylaxis, %d other",
            variant_id,
            len(body_segments),
            len(prophylaxis_segments),
            len(other_segments),
        )

        return updated_segments, [variant_group]

    def _aggregate_multiple_variants(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification],
        variant_headers: List[Tuple[int, str, PdfSegment, SegmentClassification]],
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate segments into multiple variants.
        """
        updated_segments: List[PdfSegment] = []
        variant_groups: List[VariantGroup] = []

        for i, (header_idx, variant_id, header_seg, header_cls) in enumerate(
            variant_headers
        ):
            start_idx = header_idx
            end_idx = variant_headers[i + 1][0] if i + 1 < len(variant_headers) else len(segments)

            header_copy = header_seg.model_copy(deep=True)
            header_copy.variant_id = variant_id

            variant_group = VariantGroup(
                variant_id=variant_id,
                header_segment=header_copy,
            )

            body_segments: List[PdfSegment] = []
            prophylaxis_segments: List[PdfSegment] = []
            other_segments: List[PdfSegment] = []

            for j in range(start_idx, end_idx):
                seg = segments[j]
                cls = classifications[j]
                updated_seg = seg.model_copy(deep=True)

                # wszystko w zakresie wariantu dostaje variant_id
                updated_seg.variant_id = variant_id

                if cls.label == "variant_header" and j == start_idx:
                    # to jest nagłówek wariantu – zapisany wyżej
                    updated_segments.append(updated_seg)
                elif cls.label == "variant_body":
                    body_segments.append(updated_seg)
                    updated_segments.append(updated_seg)
                elif cls.label == "prophylaxis":
                    prophylaxis_segments.append(updated_seg)
                    updated_segments.append(updated_seg)
                else:
                    # general, pricing_table, irrelevant, dodatkowe nagłówki, itd.
                    other_segments.append(updated_seg)
                    updated_segments.append(updated_seg)

            variant_group.body_segments = body_segments
            variant_group.prophylaxis_segments = prophylaxis_segments
            variant_group.other_segments = other_segments
            variant_groups.append(variant_group)

            logger.info(
                "Created variant %s: %d body, %d prophylaxis, %d other",
                variant_id,
                len(body_segments),
                len(prophylaxis_segments),
                len(other_segments),
            )

        return updated_segments, variant_groups


def aggregate_variants(
    segments: List[PdfSegment],
    classifications: List[SegmentClassification],
    default_variant_id: str = "V1",
) -> Tuple[List[PdfSegment], List[VariantGroup]]:
    """
    Convenience function to aggregate variants.
    """
    aggregator = VariantAggregator(default_variant_id=default_variant_id)
    return aggregator.aggregate(segments, classifications)
