"""Tests for PDF loader."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.io import PDFLoader, PDFLoadError
from siwz_mapper.io.pdf_loader import load_pdf
from siwz_mapper.models import PdfSegment, BBox


# Mock fitz module for all tests
@pytest.fixture(autouse=True)
def mock_fitz_module():
    """Mock PyMuPDF module globally."""
    # Create a mock fitz module
    mock_fitz_mod = MagicMock()
    
    # Patch it into sys.modules so imports work
    with patch.dict('sys.modules', {'fitz': mock_fitz_mod}):
        yield mock_fitz_mod


class TestPDFLoader:
    """Tests for PDFLoader class."""
    
    def test_initialization(self):
        """Test PDFLoader initialization."""
        loader = PDFLoader(extract_bboxes=True)
        assert loader.extract_bboxes is True
        assert loader.merge_consecutive_blocks is False
        assert loader.min_block_length == 1
    
    def test_initialization_custom_params(self):
        """Test PDFLoader with custom parameters."""
        loader = PDFLoader(
            extract_bboxes=False,
            merge_consecutive_blocks=True,
            min_block_length=5
        )
        
        assert loader.extract_bboxes is False
        assert loader.merge_consecutive_blocks is True
        assert loader.min_block_length == 5
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    @patch('pathlib.Path.exists')
    def test_load_pdf_mock(self, mock_exists, mock_fitz):
        """Test loading PDF with mocked fitz."""
        # Mock file existence
        mock_exists.return_value = True
        
        # Create mock page with text blocks
        mock_page = Mock()
        mock_page.get_text.return_value = [
            # (x0, y0, x1, y1, text, block_no, block_type)
            (50, 100, 400, 120, "First paragraph text.\n", 0, 0),
            (50, 140, 400, 160, "Second paragraph text.\n", 1, 0),
        ]
        
        # Create mock document with proper __len__ support
        mock_doc = Mock()
        mock_doc.__len__ = Mock(return_value=1)
        mock_doc.configure_mock(**{'__len__.return_value': 1})
        mock_doc.__getitem__ = Mock(return_value=mock_page)
        mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
        mock_doc.close = Mock()
        
        # Setup fitz.open to return mock document
        mock_fitz.open.return_value = mock_doc
        
        # Create loader and load
        loader = PDFLoader()
        
        # Create a temporary file path (doesn't need to exist with mock)
        segments = loader.load(Path("dummy.pdf"))
        
        # Verify segments were created
        assert len(segments) == 2
        assert all(isinstance(seg, PdfSegment) for seg in segments)
        assert segments[0].page == 1
        assert "First paragraph" in segments[0].text
    
    def test_extract_page_segments(self):
        """Test extracting segments from a page."""
        # Create mock page
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 400, 120, "Text block 1\n", 0, 0),
            (50, 140, 400, 160, "Text block 2\n", 1, 0),
            (50, 180, 400, 200, "   \n", 2, 0),  # Empty (whitespace only)
        ]
        
        loader = PDFLoader(extract_bboxes=True)
        segments = loader._extract_page_segments(mock_page, 1, 0)
        
        # Should skip empty block
        assert len(segments) == 2
        assert segments[0].segment_id == "seg_p1_b0"
        assert segments[0].page == 1
        assert segments[0].text == "Text block 1"
        assert segments[0].bbox is not None
    
    def test_min_block_length_filter(self):
        """Test filtering blocks by minimum length."""
        loader = PDFLoader(min_block_length=10)
        
        # Mock page with short and long blocks
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 100, 120, "Hi", 0, 0),  # Too short
            (50, 140, 400, 160, "This is a longer text block", 1, 0),  # OK
        ]
        
        segments = loader._extract_page_segments(mock_page, 1, 0)
        
        assert len(segments) == 1
        assert "longer text" in segments[0].text
    
    def test_bbox_extraction(self):
        """Test bounding box extraction."""
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50.5, 100.2, 400.8, 120.9, "Test text", 0, 0),
        ]
        
        # With bboxes
        loader = PDFLoader(extract_bboxes=True)
        segments = loader._extract_page_segments(mock_page, 1, 0)
        
        assert segments[0].bbox is not None
        assert segments[0].bbox.x0 == 50.5
        assert segments[0].bbox.y0 == 100.2
        assert segments[0].bbox.x1 == 400.8
        assert segments[0].bbox.y1 == 120.9
        assert segments[0].bbox.page == 1
        
        # Without bboxes
        loader_no_bbox = PDFLoader(extract_bboxes=False)
        segments_no_bbox = loader_no_bbox._extract_page_segments(mock_page, 1, 0)
        
        assert segments_no_bbox[0].bbox is None
    
    def test_character_offsets(self):
        """Test character offset calculation."""
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 400, 120, "First block", 0, 0),   # 11 chars
            (50, 140, 400, 160, "Second block", 1, 0),  # 12 chars
        ]
        
        loader = PDFLoader()
        segments = loader._extract_page_segments(mock_page, 1, 0)
        
        # First block
        assert segments[0].start_char == 0
        assert segments[0].end_char == 11
        
        # Second block (starts after first + 1 for newline)
        assert segments[1].start_char == 12
        assert segments[1].end_char == 24
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_file_not_found(self, mock_fitz):
        """Test error when PDF file doesn't exist."""
        loader = PDFLoader()
        
        with pytest.raises(PDFLoadError) as exc_info:
            loader.load(Path("nonexistent.pdf"))
        
        assert "not found" in str(exc_info.value).lower()
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_invalid_pdf(self, mock_fitz):
        """Test error when PDF cannot be opened."""
        mock_fitz.open.side_effect = Exception("Invalid PDF")
        
        loader = PDFLoader()
        
        with pytest.raises(PDFLoadError) as exc_info:
            loader.load(Path(__file__))  # Use existing file
        
        assert "failed to open" in str(exc_info.value).lower()
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_load_from_bytes(self, mock_fitz):
        """Test loading PDF from bytes."""
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 400, 120, "Test text", 0, 0),
        ]
        
        # Create mock document with __len__ support
        class MockDoc:
            def __len__(self):
                return 1
            def __getitem__(self, idx):
                return mock_page
            def __iter__(self):
                return iter([mock_page])
            def close(self):
                pass
        
        mock_doc = MockDoc()
        mock_fitz.open.return_value = mock_doc
        
        loader = PDFLoader()
        pdf_bytes = b"fake pdf content"
        
        segments = loader.load_from_bytes(pdf_bytes, filename="test.pdf")
        
        assert len(segments) == 1
        assert segments[0].text == "Test text"
        
        # Verify fitz.open was called with stream
        mock_fitz.open.assert_called_once()
        call_kwargs = mock_fitz.open.call_args[1]
        assert call_kwargs['filetype'] == 'pdf'
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_get_page_count(self, mock_fitz):
        """Test getting page count."""
        class MockDoc:
            def __len__(self):
                return 5
            def close(self):
                pass
        
        mock_fitz.open.return_value = MockDoc()
        
        loader = PDFLoader()
        count = loader.get_page_count(Path("dummy.pdf"))
        
        assert count == 5
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_extract_page_text(self, mock_fitz):
        """Test extracting text from single page."""
        mock_page = Mock()
        mock_page.get_text.return_value = "Page text content"
        
        class MockDoc:
            def __len__(self):
                return 3
            def __getitem__(self, idx):
                return mock_page
            def close(self):
                pass
        
        mock_doc = MockDoc()
        mock_fitz.open.return_value = mock_doc
        
        loader = PDFLoader()
        text = loader.extract_page_text(Path("dummy.pdf"), page_num=2)
        
        assert text == "Page text content"
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    def test_extract_page_text_invalid_page(self, mock_fitz):
        """Test error for invalid page number."""
        class MockDoc:
            def __len__(self):
                return 3
            def close(self):
                pass
        
        mock_fitz.open.return_value = MockDoc()
        
        loader = PDFLoader()
        
        with pytest.raises(PDFLoadError) as exc_info:
            loader.extract_page_text(Path("dummy.pdf"), page_num=5)
        
        assert "invalid page" in str(exc_info.value).lower()
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    @patch('pathlib.Path.exists')
    def test_multiple_pages(self, mock_exists, mock_fitz):
        """Test loading PDF with multiple pages."""
        mock_exists.return_value = True
        
        # Create mock pages
        mock_page1 = Mock()
        mock_page1.get_text.return_value = [
            (50, 100, 400, 120, "Page 1 text", 0, 0),
        ]
        
        mock_page2 = Mock()
        mock_page2.get_text.return_value = [
            (50, 100, 400, 120, "Page 2 text", 0, 0),
        ]
        
        class MockDoc:
            def __len__(self):
                return 2
            def __iter__(self):
                return iter([mock_page1, mock_page2])
            def __getitem__(self, idx):
                return [mock_page1, mock_page2][idx]
            def close(self):
                pass
        
        mock_fitz.open.return_value = MockDoc()
        
        loader = PDFLoader()
        segments = loader.load(Path("dummy.pdf"))
        
        assert len(segments) == 2
        assert segments[0].page == 1
        assert segments[1].page == 2
        assert "Page 1" in segments[0].text
        assert "Page 2" in segments[1].text


class TestConvenienceFunction:
    """Tests for load_pdf convenience function."""
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    @patch('pathlib.Path.exists')
    def test_load_pdf(self, mock_exists, mock_fitz):
        """Test convenience function."""
        mock_exists.return_value = True
        
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 400, 120, "Test content", 0, 0),
        ]
        
        class MockDoc:
            def __len__(self):
                return 1
            def __getitem__(self, idx):
                return mock_page
            def __iter__(self):
                return iter([mock_page])
            def close(self):
                pass
        
        mock_fitz.open.return_value = MockDoc()
        
        segments = load_pdf(Path("dummy.pdf"))
        
        assert len(segments) == 1
        assert isinstance(segments[0], PdfSegment)


class TestSegmentStructure:
    """Tests for PdfSegment structure suitability."""
    
    @patch('siwz_mapper.io.pdf_loader.fitz')
    @patch('pathlib.Path.exists')
    def test_segment_has_citation_info(self, mock_exists, mock_fitz):
        """Test that segments contain all info needed for citation."""
        mock_exists.return_value = True
        
        mock_page = Mock()
        mock_page.get_text.return_value = [
            (50, 100, 400, 120, "Cited text block", 0, 0),
        ]
        
        class MockDoc:
            def __len__(self):
                return 1
            def __iter__(self):
                return iter([mock_page])
            def __getitem__(self, idx):
                return mock_page
            def close(self):
                pass
        
        mock_fitz.open.return_value = MockDoc()
        
        loader = PDFLoader(extract_bboxes=True)
        segments = loader.load(Path("dummy.pdf"))
        
        segment = segments[0]
        
        # Check all citation requirements
        assert segment.text is not None  # The actual text
        assert segment.page == 1  # Page number
        assert segment.start_char is not None  # Character offset
        assert segment.end_char is not None
        assert segment.bbox is not None  # Bounding box for highlighting
        assert segment.segment_id is not None  # Unique identifier
        
        # Verify bbox structure
        assert segment.bbox.page == 1
        assert segment.bbox.x0 >= 0
        assert segment.bbox.y0 >= 0
    
    def test_segment_suitable_for_highlighting(self):
        """Test that PdfSegment structure supports highlighting."""
        # Create a segment
        segment = PdfSegment(
            segment_id="seg_p1_b0",
            text="Highlighted text",
            page=1,
            bbox=BBox(page=1, x0=50, y0=100, x1=400, y1=120),
            start_char=0,
            end_char=16
        )
        
        # Verify we can extract highlight coordinates
        highlight_coords = {
            'page': segment.bbox.page,
            'x0': segment.bbox.x0,
            'y0': segment.bbox.y0,
            'x1': segment.bbox.x1,
            'y1': segment.bbox.y1,
        }
        
        assert highlight_coords['page'] == 1
        assert highlight_coords['x0'] == 50
        
        # Verify we can create citation
        citation = f'"{segment.text}" (page {segment.page}, chars {segment.start_char}-{segment.end_char})'
        assert 'page 1' in citation
        assert 'chars 0-16' in citation

