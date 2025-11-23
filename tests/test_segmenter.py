"""Tests for text segmenter."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import PdfSegment, BBox
from siwz_mapper.preprocess import Segmenter, segment_pdf_blocks


class TestSegmenter:
    """Tests for Segmenter class."""
    
    def test_initialization(self):
        """Test segmenter initialization."""
        segmenter = Segmenter()
        assert segmenter.soft_min_chars == 800
        assert segmenter.soft_max_chars == 1200
        assert segmenter.normalize_text_enabled is True
    
    def test_initialization_custom(self):
        """Test segmenter with custom parameters."""
        segmenter = Segmenter(
            soft_min_chars=500,
            soft_max_chars=1000,
            normalize_text=False
        )
        
        assert segmenter.soft_min_chars == 500
        assert segmenter.soft_max_chars == 1000
        assert segmenter.normalize_text_enabled is False
    
    def test_segment_short_block(self):
        """Test segmenting a short block (no splitting needed)."""
        block = PdfSegment(
            segment_id="seg_1",
            text="Short paragraph text.",
            page=1,
            start_char=0,
            end_char=21
        )
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        assert len(segments) == 1
        assert segments[0].text == "Short paragraph text."
    
    def test_segment_by_blank_lines(self):
        """Test segmenting by blank lines (paragraphs)."""
        text = """First paragraph text.

Second paragraph text.

Third paragraph text."""
        
        block = PdfSegment(
            segment_id="seg_1",
            text=text,
            page=1,
            start_char=0,
            end_char=len(text)
        )
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        # Should create 3 segments
        assert len(segments) >= 3
        assert "First" in segments[0].text
        assert "Second" in segments[1].text
        assert "Third" in segments[2].text
    
    def test_segment_bullet_list(self):
        """Test segmenting bullet list."""
        text = """• First bullet point
• Second bullet point
• Third bullet point"""
        
        block = PdfSegment(
            segment_id="seg_1",
            text=text,
            page=1
        )
        
        segmenter = Segmenter(detect_bullets=True)
        segments = segmenter.segment([block])
        
        # Should create 3 segments (one per bullet)
        assert len(segments) == 3
        assert "First" in segments[0].text
        assert "Second" in segments[1].text
        assert "Third" in segments[2].text
    
    def test_segment_numbered_list(self):
        """Test segmenting numbered list."""
        text = """1. First item
2. Second item
3. Third item"""
        
        block = PdfSegment(
            segment_id="seg_1",
            text=text,
            page=1
        )
        
        segmenter = Segmenter(detect_bullets=True)
        segments = segmenter.segment([block])
        
        assert len(segments) == 3
    
    def test_split_long_paragraph(self):
        """Test splitting a long paragraph at sentence boundaries."""
        # Create a long paragraph (>1200 chars)
        sentence = "This is a sentence about medical services. "
        long_text = sentence * 30  # ~1260 chars
        
        block = PdfSegment(
            segment_id="seg_1",
            text=long_text,
            page=1,
            start_char=0,
            end_char=len(long_text)
        )
        
        segmenter = Segmenter(soft_max_chars=1200)
        segments = segmenter.segment([block])
        
        # Should be split into multiple segments
        assert len(segments) > 1
        
        # Each segment should be roughly within limits
        for seg in segments:
            # Allow some flexibility
            assert len(seg.text) <= segmenter.soft_max_chars + 200
    
    def test_preserve_page_numbers(self):
        """Test that page numbers are preserved."""
        blocks = [
            PdfSegment(segment_id="seg_1", text="Page 1 text", page=1),
            PdfSegment(segment_id="seg_2", text="Page 2 text", page=2),
        ]
        
        segmenter = Segmenter()
        segments = segmenter.segment(blocks)
        
        assert segments[0].page == 1
        assert segments[1].page == 2
    
    def test_preserve_bboxes(self):
        """Test that bounding boxes are preserved."""
        bbox = BBox(page=1, x0=50, y0=100, x1=400, y1=120)
        block = PdfSegment(
            segment_id="seg_1",
            text="Text with bbox",
            page=1,
            bbox=bbox
        )
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        assert segments[0].bbox is not None
        assert segments[0].bbox.page == 1
        assert segments[0].bbox.x0 == 50
    
    def test_preserve_char_offsets(self):
        """Test that character offsets are updated correctly."""
        text = """First paragraph.

Second paragraph."""
        
        block = PdfSegment(
            segment_id="seg_1",
            text=text,
            page=1,
            start_char=100,
            end_char=100 + len(text)
        )
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        # Offsets should be incremental
        assert segments[0].start_char == 100
        assert segments[1].start_char > segments[0].end_char
    
    def test_table_detection(self):
        """Test table row detection."""
        # Use tabs instead of spaces (more reliable for table detection after normalization)
        text = "Col1\tCol2\tCol3\nVal1\tVal2\tVal3\nVal4\tVal5\tVal6"
        
        block = PdfSegment(
            segment_id="seg_1",
            text=text,
            page=1
        )
        
        segmenter = Segmenter(detect_tables=True, normalize_text=False)
        segments = segmenter.segment([block])
        
        # Should detect as table and split into rows
        assert len(segments) >= 2
    
    def test_skip_empty_blocks(self):
        """Test that empty blocks are skipped."""
        blocks = [
            PdfSegment(segment_id="seg_1", text="", page=1),
            PdfSegment(segment_id="seg_2", text="   ", page=1),
            PdfSegment(segment_id="seg_3", text="Real text", page=1),
        ]
        
        segmenter = Segmenter()
        segments = segmenter.segment(blocks)
        
        # Should only keep non-empty
        assert len(segments) == 1
        assert "Real text" in segments[0].text
    
    def test_segment_id_generation(self):
        """Test segment ID generation."""
        text = """First paragraph.

Second paragraph."""
        
        block = PdfSegment(segment_id="seg_1", text=text, page=1)
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        # IDs should be based on original + suffix
        assert segments[0].segment_id.startswith("seg_1")
        assert segments[1].segment_id.startswith("seg_1")
        assert segments[0].segment_id != segments[1].segment_id
    
    def test_sentence_splitting(self):
        """Test splitting at sentence boundaries."""
        text = ("This is sentence one. This is sentence two. "
                "This is sentence three. This is sentence four.")
        
        segmenter = Segmenter()
        sentences = segmenter._split_into_sentences(text)
        
        assert len(sentences) == 4
        assert "sentence one" in sentences[0]
        assert "sentence two" in sentences[1]
    
    def test_multiple_blocks(self):
        """Test segmenting multiple blocks."""
        blocks = [
            PdfSegment(segment_id="seg_1", text="Block 1 text", page=1),
            PdfSegment(segment_id="seg_2", text="Block 2 text", page=1),
            PdfSegment(segment_id="seg_3", text="Block 3 text", page=2),
        ]
        
        segmenter = Segmenter()
        segments = segmenter.segment(blocks)
        
        assert len(segments) >= 3


class TestConvenienceFunction:
    """Tests for segment_pdf_blocks convenience function."""
    
    def test_segment_pdf_blocks(self):
        """Test convenience function."""
        blocks = [
            PdfSegment(segment_id="seg_1", text="Text 1", page=1),
            PdfSegment(segment_id="seg_2", text="Text 2", page=1),
        ]
        
        segments = segment_pdf_blocks(blocks)
        
        assert len(segments) >= 2
        assert isinstance(segments[0], PdfSegment)
    
    def test_segment_pdf_blocks_options(self):
        """Test convenience function with custom options."""
        # Create text with actual sentences so it can be split
        sentence = "This is a test sentence. "
        blocks = [
            PdfSegment(segment_id="seg_1", text=sentence * 50, page=1),  # ~1250 chars
        ]
        
        segments = segment_pdf_blocks(
            blocks,
            soft_max_chars=500,
            normalize=False
        )
        
        # Should be split due to length
        assert len(segments) > 1


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_very_long_sentence(self):
        """Test handling of very long sentences (>soft_max)."""
        # Single sentence longer than soft_max
        long_sentence = "This is a very long sentence " * 50 + "."
        
        block = PdfSegment(
            segment_id="seg_1",
            text=long_sentence,
            page=1
        )
        
        segmenter = Segmenter(soft_max_chars=500)
        segments = segmenter.segment([block])
        
        # Should still create segments even if sentence is too long
        assert len(segments) >= 1
    
    def test_no_sentence_endings(self):
        """Test text without clear sentence endings."""
        text = "text without clear endings and lots of content " * 30
        
        block = PdfSegment(segment_id="seg_1", text=text, page=1)
        
        segmenter = Segmenter(soft_max_chars=1000)
        segments = segmenter.segment([block])
        
        # Should handle gracefully
        assert len(segments) >= 1
    
    def test_mixed_content(self):
        """Test mixed content (paragraphs + bullets)."""
        text = """Regular paragraph text.

• Bullet one
• Bullet two

Another paragraph."""
        
        block = PdfSegment(segment_id="seg_1", text=text, page=1)
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        # Should handle mixed content
        assert len(segments) >= 2
    
    def test_unicode_text(self):
        """Test handling of Unicode text."""
        text = "Tekst po polsku z ąćęłńóśźż i konsultacja medyczna."
        
        block = PdfSegment(segment_id="seg_1", text=text, page=1)
        
        segmenter = Segmenter()
        segments = segmenter.segment([block])
        
        assert len(segments) == 1
        assert "ąćęłńóśźż" in segments[0].text


class TestIntegration:
    """Integration tests with normalizer."""
    
    def test_normalization_in_segmentation(self):
        """Test that normalization is applied during segmentation."""
        text = "tekst  z    wieloma     spacjami"
        
        block = PdfSegment(segment_id="seg_1", text=text, page=1)
        
        # With normalization
        segmenter = Segmenter(normalize_text=True)
        segments = segmenter.segment([block])
        
        # Multiple spaces should be cleaned
        assert "  " not in segments[0].text
        
        # Without normalization
        segmenter_no_norm = Segmenter(normalize_text=False)
        segments_no_norm = segmenter_no_norm.segment([block])
        
        # Spaces preserved
        assert "  " in segments_no_norm[0].text

