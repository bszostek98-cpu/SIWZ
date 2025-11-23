"""Tests for variant aggregator."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import SegmentClassification
from siwz_mapper.pipeline import (
    VariantAggregator,
    VariantGroup,
    aggregate_variants
)


class TestVariantGroup:
    """Tests for VariantGroup model."""
    
    def test_create_variant_group(self):
        """Test creating a variant group."""
        group = VariantGroup(
            variant_id="V1",
            header_segment=None,
            body_segments=[],
            prophylaxis_segments=[]
        )
        
        assert group.variant_id == "V1"
        assert group.header_segment is None
        assert len(group.body_segments) == 0
        assert len(group.prophylaxis_segments) == 0
    
    def test_segment_count(self):
        """Test segment count calculation."""
        header = PdfSegment(segment_id="h1", text="Header", page=1)
        body1 = PdfSegment(segment_id="b1", text="Body 1", page=1)
        body2 = PdfSegment(segment_id="b2", text="Body 2", page=1)
        proph = PdfSegment(segment_id="p1", text="Prophylaxis", page=2)
        
        group = VariantGroup(
            variant_id="V1",
            header_segment=header,
            body_segments=[body1, body2],
            prophylaxis_segments=[proph]
        )
        
        assert group.segment_count() == 4  # 1 header + 2 body + 1 prophylaxis


class TestVariantAggregator:
    """Tests for VariantAggregator class."""
    
    def test_initialization(self):
        """Test aggregator initialization."""
        aggregator = VariantAggregator()
        assert aggregator.default_variant_id == "V1"
        
        aggregator = VariantAggregator(default_variant_id="DEFAULT")
        assert aggregator.default_variant_id == "DEFAULT"
    
    def test_empty_segments(self):
        """Test aggregation with empty input."""
        aggregator = VariantAggregator()
        
        updated, variants = aggregator.aggregate([], [])
        
        assert updated == []
        assert variants == []
    
    def test_mismatched_lengths(self):
        """Test that mismatched lengths raise error."""
        aggregator = VariantAggregator()
        
        segments = [PdfSegment(segment_id="s1", text="Text", page=1)]
        classifications = []
        
        with pytest.raises(ValueError, match="must have same length"):
            aggregator.aggregate(segments, classifications)


class TestSingleVariant:
    """Tests for single variant aggregation (no headers)."""
    
    def test_no_headers_default_variant(self):
        """Test that segments without headers go to default variant."""
        segments = [
            PdfSegment(segment_id="seg_1", text="Intro text", page=1),
            PdfSegment(segment_id="seg_2", text="Body text", page=1),
            PdfSegment(segment_id="seg_3", text="More body", page=1),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="irrelevant",
                confidence=0.9,
                rationale="Intro"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_body",
                confidence=0.85,
                rationale="Body"
            ),
            SegmentClassification(
                segment_id="seg_3",
                label="variant_body",
                confidence=0.88,
                rationale="Body"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 1
        assert variants[0].variant_id == "V1"
        assert variants[0].header_segment is None
        assert len(variants[0].body_segments) == 2
        assert len(variants[0].prophylaxis_segments) == 0
        
        # Check that variant_id was assigned to body segments
        assert updated[1].variant_id == "V1"
        assert updated[2].variant_id == "V1"
        assert updated[0].variant_id is None  # irrelevant segment
    
    def test_single_variant_with_prophylaxis(self):
        """Test single variant with prophylaxis segments."""
        segments = [
            PdfSegment(segment_id="seg_1", text="Body 1", page=1),
            PdfSegment(segment_id="seg_2", text="Prophylaxis", page=2),
            PdfSegment(segment_id="seg_3", text="Body 2", page=2),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_body",
                confidence=0.9,
                rationale="Body"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="prophylaxis",
                is_prophylaxis=True,
                confidence=0.95,
                rationale="Prophylaxis"
            ),
            SegmentClassification(
                segment_id="seg_3",
                label="variant_body",
                confidence=0.88,
                rationale="Body"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 1
        assert len(variants[0].body_segments) == 2
        assert len(variants[0].prophylaxis_segments) == 1
        
        # Check variant_id assignment
        assert updated[0].variant_id == "V1"
        assert updated[1].variant_id == "V1"
        assert updated[2].variant_id == "V1"


class TestMultipleVariants:
    """Tests for multiple variant aggregation."""
    
    def test_two_variants(self):
        """Test aggregation with two variant headers."""
        segments = [
            PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
            PdfSegment(segment_id="seg_2", text="Body V1-1", page=1),
            PdfSegment(segment_id="seg_3", text="Body V1-2", page=1),
            PdfSegment(segment_id="seg_4", text="WARIANT 2", page=2),
            PdfSegment(segment_id="seg_5", text="Body V2-1", page=2),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_header",
                variant_hint="1",
                confidence=0.95,
                rationale="Header V1"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_body",
                confidence=0.9,
                rationale="Body V1"
            ),
            SegmentClassification(
                segment_id="seg_3",
                label="variant_body",
                confidence=0.88,
                rationale="Body V1"
            ),
            SegmentClassification(
                segment_id="seg_4",
                label="variant_header",
                variant_hint="2",
                confidence=0.93,
                rationale="Header V2"
            ),
            SegmentClassification(
                segment_id="seg_5",
                label="variant_body",
                confidence=0.87,
                rationale="Body V2"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 2
        
        # Variant 1
        assert variants[0].variant_id == "V1"
        assert variants[0].header_segment is not None
        assert variants[0].header_segment.segment_id == "seg_1"
        assert len(variants[0].body_segments) == 2
        assert variants[0].body_segments[0].segment_id == "seg_2"
        assert variants[0].body_segments[1].segment_id == "seg_3"
        
        # Variant 2
        assert variants[1].variant_id == "V2"
        assert variants[1].header_segment is not None
        assert variants[1].header_segment.segment_id == "seg_4"
        assert len(variants[1].body_segments) == 1
        assert variants[1].body_segments[0].segment_id == "seg_5"
        
        # Check variant_id assignment in updated segments
        assert updated[0].variant_id == "V1"  # header
        assert updated[1].variant_id == "V1"  # body
        assert updated[2].variant_id == "V1"  # body
        assert updated[3].variant_id == "V2"  # header
        assert updated[4].variant_id == "V2"  # body
    
    def test_three_variants_with_mixed_content(self):
        """Test three variants with mixed content types."""
        segments = [
            PdfSegment(segment_id="seg_1", text="Intro", page=1),
            PdfSegment(segment_id="seg_2", text="WARIANT 1", page=1),
            PdfSegment(segment_id="seg_3", text="Body V1", page=1),
            PdfSegment(segment_id="seg_4", text="WARIANT 2", page=2),
            PdfSegment(segment_id="seg_5", text="Body V2", page=2),
            PdfSegment(segment_id="seg_6", text="Prophylaxis V2", page=2),
            PdfSegment(segment_id="seg_7", text="WARIANT 3", page=3),
            PdfSegment(segment_id="seg_8", text="Body V3", page=3),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="irrelevant",
                confidence=0.9,
                rationale="Intro"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_header",
                variant_hint="1",
                confidence=0.95,
                rationale="Header V1"
            ),
            SegmentClassification(
                segment_id="seg_3",
                label="variant_body",
                confidence=0.9,
                rationale="Body V1"
            ),
            SegmentClassification(
                segment_id="seg_4",
                label="variant_header",
                variant_hint="2",
                confidence=0.93,
                rationale="Header V2"
            ),
            SegmentClassification(
                segment_id="seg_5",
                label="variant_body",
                confidence=0.88,
                rationale="Body V2"
            ),
            SegmentClassification(
                segment_id="seg_6",
                label="prophylaxis",
                is_prophylaxis=True,
                confidence=0.92,
                rationale="Prophylaxis"
            ),
            SegmentClassification(
                segment_id="seg_7",
                label="variant_header",
                variant_hint="3",
                confidence=0.94,
                rationale="Header V3"
            ),
            SegmentClassification(
                segment_id="seg_8",
                label="variant_body",
                confidence=0.87,
                rationale="Body V3"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 3
        
        # Variant 1
        assert variants[0].variant_id == "V1"
        assert len(variants[0].body_segments) == 1
        assert len(variants[0].prophylaxis_segments) == 0
        
        # Variant 2
        assert variants[1].variant_id == "V2"
        assert len(variants[1].body_segments) == 1
        assert len(variants[1].prophylaxis_segments) == 1
        
        # Variant 3
        assert variants[2].variant_id == "V3"
        assert len(variants[2].body_segments) == 1
        assert len(variants[2].prophylaxis_segments) == 0
    
    def test_variant_without_hint(self):
        """Test variant header without variant_hint (sequential numbering)."""
        segments = [
            PdfSegment(segment_id="seg_1", text="WARIANT A", page=1),
            PdfSegment(segment_id="seg_2", text="Body", page=1),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_header",
                variant_hint=None,  # No hint provided
                confidence=0.9,
                rationale="Header"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_body",
                confidence=0.85,
                rationale="Body"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 1
        # Should get sequential number V1
        assert variants[0].variant_id == "V1"


class TestConvenienceFunction:
    """Tests for aggregate_variants convenience function."""
    
    def test_convenience_function(self):
        """Test convenience function works."""
        segments = [
            PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
            PdfSegment(segment_id="seg_2", text="Body", page=1),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_header",
                variant_hint="1",
                confidence=0.95,
                rationale="Header"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_body",
                confidence=0.9,
                rationale="Body"
            ),
        ]
        
        updated, variants = aggregate_variants(segments, classifications)
        
        assert len(variants) == 1
        assert variants[0].variant_id == "V1"
    
    def test_convenience_function_custom_default(self):
        """Test convenience function with custom default variant."""
        segments = [
            PdfSegment(segment_id="seg_1", text="Body", page=1),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_body",
                confidence=0.9,
                rationale="Body"
            ),
        ]
        
        updated, variants = aggregate_variants(
            segments,
            classifications,
            default_variant_id="DEFAULT"
        )
        
        assert len(variants) == 1
        assert variants[0].variant_id == "DEFAULT"


class TestGetVariantIds:
    """Tests for get_variant_ids method."""
    
    def test_get_variant_ids(self):
        """Test extracting variant IDs."""
        variant_groups = [
            VariantGroup(variant_id="V1", body_segments=[]),
            VariantGroup(variant_id="V2", body_segments=[]),
            VariantGroup(variant_id="V3", body_segments=[]),
        ]
        
        aggregator = VariantAggregator()
        ids = aggregator.get_variant_ids(variant_groups)
        
        assert ids == ["V1", "V2", "V3"]
    
    def test_get_variant_ids_empty(self):
        """Test getting IDs from empty list."""
        aggregator = VariantAggregator()
        ids = aggregator.get_variant_ids([])
        
        assert ids == []


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_only_headers_no_bodies(self):
        """Test variants with headers but no body segments."""
        segments = [
            PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
            PdfSegment(segment_id="seg_2", text="WARIANT 2", page=2),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_header",
                variant_hint="1",
                confidence=0.95,
                rationale="Header V1"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_header",
                variant_hint="2",
                confidence=0.93,
                rationale="Header V2"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 2
        assert len(variants[0].body_segments) == 0
        assert len(variants[1].body_segments) == 0
    
    def test_only_irrelevant_segments(self):
        """Test document with only irrelevant segments (no variants)."""
        segments = [
            PdfSegment(segment_id="seg_1", text="Intro", page=1),
            PdfSegment(segment_id="seg_2", text="Legal", page=1),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="irrelevant",
                confidence=0.9,
                rationale="Intro"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="irrelevant",
                confidence=0.88,
                rationale="Legal"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        # Should create default variant with no segments
        assert len(variants) == 1
        assert variants[0].variant_id == "V1"
        assert len(variants[0].body_segments) == 0
        assert len(variants[0].prophylaxis_segments) == 0
    
    def test_pricing_table_not_included(self):
        """Test that pricing_table segments are not included in variants."""
        segments = [
            PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
            PdfSegment(segment_id="seg_2", text="Body", page=1),
            PdfSegment(segment_id="seg_3", text="Pricing table", page=2),
        ]
        
        classifications = [
            SegmentClassification(
                segment_id="seg_1",
                label="variant_header",
                variant_hint="1",
                confidence=0.95,
                rationale="Header"
            ),
            SegmentClassification(
                segment_id="seg_2",
                label="variant_body",
                confidence=0.9,
                rationale="Body"
            ),
            SegmentClassification(
                segment_id="seg_3",
                label="pricing_table",
                confidence=0.92,
                rationale="Pricing"
            ),
        ]
        
        aggregator = VariantAggregator()
        updated, variants = aggregator.aggregate(segments, classifications)
        
        assert len(variants) == 1
        assert len(variants[0].body_segments) == 1
        # Pricing table segment should not have variant_id
        assert updated[2].variant_id is None

