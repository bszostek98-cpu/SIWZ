"""
PDF text extraction with position information.

Uses PyMuPDF (fitz) to extract text blocks with:
- Page numbers
- Paragraph/bullet separation
- Bounding boxes
- Character offsets

Output is suitable for citation and highlighting.
"""

from pathlib import Path
from typing import List, Optional, Tuple
import logging

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from ..models import PdfSegment, BBox

logger = logging.getLogger(__name__)


class PDFLoadError(Exception):
    """Exception raised when PDF loading fails."""
    pass


class PDFLoader:
    """
    PDF text extractor with position preservation.
    
    Extracts text blocks from PDF preserving:
    - Page numbers (1-indexed)
    - Paragraph/block separation
    - Bounding boxes for each text block
    - Character offsets in document
    
    Suitable for later citation and highlighting.
    """
    
    def __init__(
        self,
        extract_bboxes: bool = True,
        merge_consecutive_blocks: bool = False,
        min_block_length: int = 1
    ):
        """
        Initialize PDF loader.
        
        Args:
            extract_bboxes: Whether to extract bounding box coordinates
            merge_consecutive_blocks: Whether to merge blocks on same line
            min_block_length: Minimum characters in block to keep
        """
        if fitz is None:
            raise ImportError(
                "PyMuPDF (fitz) is required for PDF loading. "
                "Install with: pip install PyMuPDF"
            )
        
        self.extract_bboxes = extract_bboxes
        self.merge_consecutive_blocks = merge_consecutive_blocks
        self.min_block_length = min_block_length
        
        logger.info(
            f"Initialized PDFLoader (bboxes={extract_bboxes}, "
            f"merge={merge_consecutive_blocks})"
        )
    
    def load(self, pdf_path: Path) -> List[PdfSegment]:
        """
        Load PDF and extract text segments with positions.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of PdfSegment objects with text and position info
            
        Raises:
            PDFLoadError: If PDF cannot be loaded or processed
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise PDFLoadError(f"PDF file not found: {pdf_path}")
        
        logger.info(f"Loading PDF: {pdf_path}")
        
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            raise PDFLoadError(f"Failed to open PDF: {e}")
        
        segments = []
        char_offset = 0
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_segments = self._extract_page_segments(
                    page,
                    page_num + 1,  # 1-indexed
                    char_offset
                )
                segments.extend(page_segments)
                
                # Update char offset
                if page_segments:
                    last_segment = page_segments[-1]
                    if last_segment.end_char is not None:
                        char_offset = last_segment.end_char
        
        finally:
            doc.close()
        
        logger.info(f"Extracted {len(segments)} text segments from {len(doc)} pages")
        
        return segments
    
    def load_from_bytes(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf"
    ) -> List[PdfSegment]:
        """
        Load PDF from bytes.
        
        Args:
            pdf_bytes: PDF file bytes
            filename: Filename for reference
            
        Returns:
            List of PdfSegment objects
        """
        logger.info(f"Loading PDF from bytes: {filename}")
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise PDFLoadError(f"Failed to open PDF from bytes: {e}")
        
        segments = []
        char_offset = 0
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_segments = self._extract_page_segments(
                    page,
                    page_num + 1,
                    char_offset
                )
                segments.extend(page_segments)
                
                if page_segments:
                    last_segment = page_segments[-1]
                    if last_segment.end_char is not None:
                        char_offset = last_segment.end_char
        
        finally:
            doc.close()
        
        logger.info(f"Extracted {len(segments)} segments")
        
        return segments
    
    def _extract_page_segments(
        self,
        page,
        page_num: int,
        start_char_offset: int
    ) -> List[PdfSegment]:
        """
        Extract text segments from a single page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            start_char_offset: Starting character offset for this page
            
        Returns:
            List of PdfSegment objects for this page
        """
        segments = []
        
        # Extract text blocks with position information
        # blocks format: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        
        char_offset = start_char_offset
        
        for block_idx, block in enumerate(blocks):
            # Extract block info
            x0, y0, x1, y1, text, block_no, block_type = block
            
            # Skip empty blocks
            text = text.strip()
            if len(text) < self.min_block_length:
                continue
            
            # Create bounding box if requested
            bbox = None
            if self.extract_bboxes:
                bbox = BBox(
                    page=page_num,
                    x0=float(x0),
                    y0=float(y0),
                    x1=float(x1),
                    y1=float(y1)
                )
            
            # Calculate character offsets
            start_char = char_offset
            end_char = char_offset + len(text)
            char_offset = end_char + 1  # +1 for implicit newline between blocks
            
            # Create segment
            segment_id = f"seg_p{page_num}_b{block_idx}"
            segment = PdfSegment(
                segment_id=segment_id,
                text=text,
                page=page_num,
                bbox=bbox,
                start_char=start_char,
                end_char=end_char
            )
            
            segments.append(segment)
        
        logger.debug(f"Page {page_num}: extracted {len(segments)} segments")
        
        return segments
    
    def _merge_blocks_on_line(
        self,
        segments: List[PdfSegment]
    ) -> List[PdfSegment]:
        """
        Merge consecutive text blocks that appear on the same line.
        
        Args:
            segments: List of segments to merge
            
        Returns:
            List of merged segments
        """
        if not segments or not self.merge_consecutive_blocks:
            return segments
        
        merged = []
        current = segments[0]
        
        for next_seg in segments[1:]:
            # Check if on same line (similar y0)
            if (current.bbox and next_seg.bbox and
                abs(current.bbox.y0 - next_seg.bbox.y0) < 5):  # 5pt tolerance
                
                # Merge text
                current.text = current.text + " " + next_seg.text
                
                # Update bbox
                if current.bbox:
                    current.bbox.x1 = max(current.bbox.x1, next_seg.bbox.x1)
                    current.bbox.y1 = max(current.bbox.y1, next_seg.bbox.y1)
                
                # Update char offsets
                if current.end_char and next_seg.end_char:
                    current.end_char = next_seg.end_char
            else:
                merged.append(current)
                current = next_seg
        
        merged.append(current)
        return merged
    
    def get_page_count(self, pdf_path: Path) -> int:
        """
        Get number of pages in PDF without full extraction.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Number of pages
        """
        try:
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
            return page_count
        except Exception as e:
            raise PDFLoadError(f"Failed to get page count: {e}")
    
    def extract_page_text(self, pdf_path: Path, page_num: int) -> str:
        """
        Extract raw text from a single page.
        
        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            
        Returns:
            Text content of the page
        """
        try:
            doc = fitz.open(pdf_path)
            
            if page_num < 1 or page_num > len(doc):
                raise PDFLoadError(
                    f"Invalid page number {page_num} (PDF has {len(doc)} pages)"
                )
            
            page = doc[page_num - 1]  # Convert to 0-indexed
            text = page.get_text()
            doc.close()
            
            return text
        
        except Exception as e:
            raise PDFLoadError(f"Failed to extract page {page_num}: {e}")


def load_pdf(
    pdf_path: Path,
    extract_bboxes: bool = True
) -> List[PdfSegment]:
    """
    Convenience function to load PDF and extract segments.
    
    Args:
        pdf_path: Path to PDF file
        extract_bboxes: Whether to extract bounding boxes
        
    Returns:
        List of PdfSegment objects
        
    Example:
        >>> segments = load_pdf("document.pdf")
        >>> for seg in segments[:3]:
        ...     print(f"Page {seg.page}: {seg.text[:50]}")
    """
    loader = PDFLoader(extract_bboxes=extract_bboxes)
    return loader.load(pdf_path)

