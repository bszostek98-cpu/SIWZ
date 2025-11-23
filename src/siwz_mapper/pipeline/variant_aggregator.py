"""
Variant aggregation from classified segments.

Takes classified segments and groups them into variants based on:
- variant_header labels (start new variant)
- variant_body labels (belong to current variant)
- prophylaxis labels (tracked separately per variant)
"""

import logging
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from ..models import PdfSegment
from ..llm.classify_segments import SegmentClassification

logger = logging.getLogger(__name__)


class VariantGroup(BaseModel):
    """
    A grouped variant with its segments.
    
    Attributes:
        variant_id: Unique variant identifier (e.g., "V1", "V2", "V3")
        header_segment: Optional header segment that started this variant
        body_segments: List of segments belonging to this variant's body
        prophylaxis_segments: List of prophylaxis segments associated with this variant
    """
    
    variant_id: str = Field(..., description="Variant identifier")
    header_segment: Optional[PdfSegment] = Field(None, description="Header segment")
    body_segments: List[PdfSegment] = Field(default_factory=list, description="Body segments")
    prophylaxis_segments: List[PdfSegment] = Field(default_factory=list, description="Prophylaxis segments")
    
    def segment_count(self) -> int:
        """Total number of segments in this variant."""
        count = len(self.body_segments) + len(self.prophylaxis_segments)
        if self.header_segment:
            count += 1
        return count


class VariantAggregator:
    """
    Aggregates classified segments into variants.
    
    Rules:
    1. variant_header starts a new variant
    2. variant_body segments following a header inherit that variant_id
    3. If no headers found, assume single variant "V1"
    4. prophylaxis segments are kept in a separate list per variant
    """
    
    def __init__(self, default_variant_id: str = "V1"):
        """
        Initialize aggregator.
        
        Args:
            default_variant_id: Default variant ID if no headers found
        """
        self.default_variant_id = default_variant_id
        logger.info(f"Initialized VariantAggregator (default={default_variant_id})")
    
    def aggregate(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification]
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate segments into variants.
        
        Args:
            segments: List of PdfSegment objects
            classifications: Corresponding classifications for each segment
            
        Returns:
            Tuple of:
            - Updated segments with variant_id assigned
            - List of VariantGroup objects
            
        Raises:
            ValueError: If segments and classifications lengths don't match
        """
        if len(segments) != len(classifications):
            raise ValueError(
                f"Segments ({len(segments)}) and classifications ({len(classifications)}) "
                f"must have same length"
            )
        
        if not segments:
            logger.warning("No segments to aggregate")
            return [], []
        
        logger.info(f"Aggregating {len(segments)} segments into variants")
        
        # Extract variant headers
        variant_headers = self._extract_variant_headers(segments, classifications)
        
        if not variant_headers:
            logger.info("No variant headers found, using default single variant")
            # Single variant case
            return self._aggregate_single_variant(segments, classifications)
        
        # Multiple variants case
        return self._aggregate_multiple_variants(
            segments,
            classifications,
            variant_headers
        )
    
    def _extract_variant_headers(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification]
    ) -> List[Tuple[int, str, PdfSegment, SegmentClassification]]:
        """
        Extract variant headers with their positions.
        
        Returns:
            List of tuples: (index, variant_id, segment, classification)
        """
        headers = []
        
        for i, (seg, cls) in enumerate(zip(segments, classifications)):
            if cls.label == "variant_header":
                # Generate variant_id from variant_hint or sequential number
                if cls.variant_hint:
                    variant_id = f"V{cls.variant_hint}"
                else:
                    variant_id = f"V{len(headers) + 1}"
                
                headers.append((i, variant_id, seg, cls))
                logger.debug(f"Found variant header at index {i}: {variant_id}")
        
        return headers
    
    def _aggregate_single_variant(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification]
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate all segments into a single default variant.
        
        Args:
            segments: All segments
            classifications: All classifications
            
        Returns:
            Updated segments and single VariantGroup
        """
        variant_id = self.default_variant_id
        
        # Create updated segments with variant_id
        updated_segments = []
        body_segments = []
        prophylaxis_segments = []
        
        for seg, cls in zip(segments, classifications):
            # Create copy with variant_id
            updated_seg = seg.model_copy(deep=True)
            
            if cls.label == "variant_body":
                updated_seg.variant_id = variant_id
                body_segments.append(updated_seg)
            elif cls.label == "prophylaxis":
                updated_seg.variant_id = variant_id
                prophylaxis_segments.append(updated_seg)
            # Other labels don't get variant_id assigned
            
            updated_segments.append(updated_seg)
        
        # Create single variant group
        variant_group = VariantGroup(
            variant_id=variant_id,
            header_segment=None,
            body_segments=body_segments,
            prophylaxis_segments=prophylaxis_segments
        )
        
        logger.info(
            f"Created single variant {variant_id}: "
            f"{len(body_segments)} body, {len(prophylaxis_segments)} prophylaxis"
        )
        
        return updated_segments, [variant_group]
    
    def _aggregate_multiple_variants(
        self,
        segments: List[PdfSegment],
        classifications: List[SegmentClassification],
        variant_headers: List[Tuple[int, str, PdfSegment, SegmentClassification]]
    ) -> Tuple[List[PdfSegment], List[VariantGroup]]:
        """
        Aggregate segments into multiple variants.
        
        Args:
            segments: All segments
            classifications: All classifications
            variant_headers: Extracted headers with positions
            
        Returns:
            Updated segments and list of VariantGroups
        """
        updated_segments = []
        variant_groups = []
        
        # Process each variant
        for i, (header_idx, variant_id, header_seg, header_cls) in enumerate(variant_headers):
            # Determine range of segments for this variant
            start_idx = header_idx
            end_idx = variant_headers[i + 1][0] if i + 1 < len(variant_headers) else len(segments)
            
            # Create variant group with header
            header_copy = header_seg.model_copy(deep=True)
            header_copy.variant_id = variant_id
            
            variant_group = VariantGroup(
                variant_id=variant_id,
                header_segment=header_copy
            )
            
            # Collect body and prophylaxis segments for this variant
            for j in range(start_idx, end_idx):
                seg = segments[j]
                cls = classifications[j]
                
                updated_seg = seg.model_copy(deep=True)
                
                if cls.label == "variant_header" and j == start_idx:
                    # This is the header itself - set variant_id and add to updated
                    updated_seg.variant_id = variant_id
                    updated_segments.append(updated_seg)
                elif cls.label == "variant_body":
                    updated_seg.variant_id = variant_id
                    variant_group.body_segments.append(updated_seg)
                    updated_segments.append(updated_seg)
                elif cls.label == "prophylaxis":
                    # Assign to current variant if within range
                    updated_seg.variant_id = variant_id
                    variant_group.prophylaxis_segments.append(updated_seg)
                    updated_segments.append(updated_seg)
                else:
                    # Other labels (irrelevant, general, pricing_table) don't get variant_id
                    updated_segments.append(updated_seg)
            
            variant_groups.append(variant_group)
            
            logger.info(
                f"Created variant {variant_id}: "
                f"{len(variant_group.body_segments)} body, "
                f"{len(variant_group.prophylaxis_segments)} prophylaxis"
            )
        
        return updated_segments, variant_groups
    
    def get_variant_ids(self, variant_groups: List[VariantGroup]) -> List[str]:
        """
        Extract list of variant IDs from variant groups.
        
        Args:
            variant_groups: List of variant groups
            
        Returns:
            List of variant IDs
        """
        return [vg.variant_id for vg in variant_groups]


def aggregate_variants(
    segments: List[PdfSegment],
    classifications: List[SegmentClassification],
    default_variant_id: str = "V1"
) -> Tuple[List[PdfSegment], List[VariantGroup]]:
    """
    Convenience function to aggregate variants.
    
    Args:
        segments: List of segments
        classifications: Corresponding classifications
        default_variant_id: Default variant ID if no headers found
        
    Returns:
        Tuple of (updated_segments, variant_groups)
        
    Example:
        >>> from siwz_mapper.llm import classify_segments, FakeGPTClient
        >>> from siwz_mapper.pipeline import aggregate_variants
        >>> 
        >>> # Classify segments
        >>> client = FakeGPTClient()
        >>> classifications = classify_segments(segments, client)
        >>> 
        >>> # Aggregate into variants
        >>> updated_segments, variants = aggregate_variants(segments, classifications)
        >>> 
        >>> print(f"Found {len(variants)} variants")
        >>> for variant in variants:
        ...     print(f"{variant.variant_id}: {variant.segment_count()} segments")
    """
    aggregator = VariantAggregator(default_variant_id=default_variant_id)
    return aggregator.aggregate(segments, classifications)

