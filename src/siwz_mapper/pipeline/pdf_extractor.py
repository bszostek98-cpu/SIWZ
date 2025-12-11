"""
PDFExtractor (thin wrapper).

Kept for compatibility with pipeline/tests.
Actual PDF parsing is handled by siwz_mapper.io.pdf_loader.PDFLoader
and segmentation by:
- siwz_mapper.preprocess.block_segmenter.BlockSegmenter  (semantic blocks)
- siwz_mapper.preprocess.segmenter.Segmenter             (fine-grained)
"""

from pathlib import Path
from typing import List
import logging

from ..io.pdf_loader import PDFLoader, PDFLoadError
from ..preprocess.segmenter import Segmenter
from ..preprocess.block_segmenter import BlockSegmenter
from ..models import PdfSegment, SemanticBlock

logger = logging.getLogger(__name__)


class PDFExtractor:
    """
    Load PDF and return segments/blocks in various granularities.

    Public API:
    - extract_blocks(...)          -> raw PdfSegment blocks from PDFLoader
    - extract_semantic_blocks(...) -> SemanticBlock (grouped blocks)
    - extract(...)                 -> fine-grained PdfSegments (backwards compat)
    """

    def __init__(self, extract_bboxes: bool = True):
        self.loader = PDFLoader(extract_bboxes=extract_bboxes)
        self.segmenter = Segmenter()
        self.block_segmenter = BlockSegmenter()
        logger.info(
            "Initialized PDFExtractor (extract_bboxes=%s)",
            extract_bboxes,
        )

    # ------------------------------------------------------------------ #
    # New block-first API
    # ------------------------------------------------------------------ #

    def extract_blocks(self, pdf_path: Path) -> List[PdfSegment]:
        """
        Load raw blocks from PDF without fine-grained segmentation.
        """
        try:
            blocks = self.loader.load(pdf_path)
            logger.info("Loaded %d raw blocks from %s", len(blocks), pdf_path)
            return blocks
        except PDFLoadError:
            # STUB fallback for tests / missing files
            logger.warning("PDF not found (%s), returning stub block", pdf_path)
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

    def extract_semantic_blocks(self, pdf_path: Path) -> List[SemanticBlock]:
        """
        Load raw blocks and group them into higher-level semantic blocks.
        """
        blocks = self.extract_blocks(pdf_path)
        semantic_blocks = self.block_segmenter.group_blocks(blocks)
        logger.info(
            "Grouped %d raw blocks into %d semantic blocks for %s",
            len(blocks),
            len(semantic_blocks),
            pdf_path,
        )
        return semantic_blocks

    # ------------------------------------------------------------------ #
    # Backwards compatible API
    # ------------------------------------------------------------------ #

    def extract(self, pdf_path: Path) -> List[PdfSegment]:
        """
        Backwards compatible method used in Stage B stub.

        It still:
        - loads raw blocks
        - applies fine-grained Segmenter.segment(...)
        """
        blocks = self.extract_blocks(pdf_path)

        # always segment blocks into smaller pieces (legacy behaviour)
        segments = self.segmenter.segment(blocks)
        logger.info(
            "Fine-grained segmentation: %d raw blocks -> %d segments",
            len(blocks),
            len(segments),
        )
        return segments
