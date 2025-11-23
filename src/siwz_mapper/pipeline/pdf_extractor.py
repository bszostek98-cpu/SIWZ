"""
PDFExtractor (thin wrapper).

Kept for compatibility with pipeline/tests.
Actual PDF parsing is handled by siwz_mapper.io.pdf_loader.PDFLoader
and segmentation by siwz_mapper.preprocess.segmenter.Segmenter.
"""

from pathlib import Path
from typing import List
import logging

from ..io.pdf_loader import PDFLoader, PDFLoadError
from ..preprocess.segmenter import Segmenter
from ..models import PdfSegment

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Load PDF and return PdfSegments."""

    def __init__(self, extract_bboxes: bool = True):
        self.extract_bboxes = extract_bboxes
        self.loader = PDFLoader(extract_bboxes=extract_bboxes)
        self.segmenter = Segmenter()
        logger.info(f"Initialized PDFExtractor (extract_bboxes={extract_bboxes})")

    def extract(self, pdf_path: Path) -> List[PdfSegment]:
        try:
            raw = self.loader.load(str(pdf_path))
        except PDFLoadError:
            # STUB fallback for tests / missing files
            logger.warning(f"PDF not found ({pdf_path}), returning stub segment")
            return [
                PdfSegment(
                    segment_id="stub_seg_001",
                    text="[STUB] PDF missing, fallback text",
                    page=1,
                    bbox=None,
                    start_char=0,
                    end_char=0,
                    section_label=None,
                    variant_id=None,
                )
            ]

        if raw and hasattr(raw[0], "segment_id"):
            return raw

        return self.segmenter.segment(raw)
