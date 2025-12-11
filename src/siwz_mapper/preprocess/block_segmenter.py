from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

from ..models import PdfSegment, SemanticBlock


_HEADING_RE = re.compile(
    r"^\s*(rozdział|§|\d+\.\s|[ivxlcdm]+\.\s)", re.IGNORECASE
)


class BlockSegmenter:
    """
    Groups raw PdfSegment blocks into larger semantic blocks (SemanticBlock).

    The goal is to:
    - keep headings as separate blocks,
    - merge consecutive blocks that belong to the same logical section,
    - keep tables as whole blocks (instead of row-by-row segments),
    - enforce a soft character limit per block (for LLM prompts).

    This class does NOT change PdfSegment objects – it only groups them.
    """

    def __init__(
        self,
        max_chars_per_block: int = 2500,
        y_gap_threshold: float = 8.0,
        x_shift_threshold: float = 40.0,
    ) -> None:
        """
        :param max_chars_per_block: soft limit of characters per SemanticBlock.
        :param y_gap_threshold: vertical gap (in PDF units) that indicates a new block.
        :param x_shift_threshold: horizontal shift that indicates a new column / region.
        """
        self.max_chars_per_block = max_chars_per_block
        self.y_gap_threshold = y_gap_threshold
        self.x_shift_threshold = x_shift_threshold

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def group_blocks(self, blocks: List[PdfSegment]) -> List[SemanticBlock]:
        """
        Group raw PdfSegment blocks into larger SemanticBlock units.

        The input should be the raw blocks straight from PDFLoader
        (before fine-grained Segmenter). The result is a list of
        SemanticBlock objects in reading order.

        This function:
        - sorts blocks by (page, y0, x0),
        - starts a new SemanticBlock at headings,
        - starts a new SemanticBlock when there is a big vertical gap
          or strong horizontal shift,
        - merges consecutive blocks otherwise, until max_chars_per_block
          is reached.
        """
        if not blocks:
            return []

        sorted_blocks = sorted(
            blocks,
            key=lambda s: (
                s.page,
                getattr(s.bbox, "y0", 0.0),
                getattr(s.bbox, "x0", 0.0),
            ),
        )

        semantic_blocks: List[SemanticBlock] = []
        current_segments: List[PdfSegment] = []
        current_text_parts: List[str] = []

        def flush_current() -> None:
            """Finalize the current group and create a SemanticBlock."""
            nonlocal current_segments, current_text_parts

            if not current_segments:
                current_text_parts = []
                return

            text = "\n".join(current_text_parts).strip()
            if not text:
                current_segments = []
                current_text_parts = []
                return

            page_start = current_segments[0].page
            page_end = current_segments[-1].page

            bbox = self._union_bbox(
                [seg.bbox for seg in current_segments if seg.bbox is not None]
            )

            block_id = f"blk_{len(semantic_blocks):04d}"

            semantic_blocks.append(
                SemanticBlock(
                    block_id=block_id,
                    text=text,
                    segments=list(current_segments),
                    page_start=page_start,
                    page_end=page_end,
                    bbox=bbox,
                    type_hint=self._infer_block_type(text, current_segments),
                )
            )

            current_segments = []
            current_text_parts = []

        for seg in sorted_blocks:
            raw_text = seg.text or ""
            text = raw_text.strip()
            if not text:
                # skip empty / whitespace-only segments
                continue

            is_heading = self._is_heading(text)

            if not current_segments:
                # First segment in a new block
                current_segments.append(seg)
                current_text_parts.append(text)
                continue

            prev = current_segments[-1]

            # Headings always start a new block (after flushing current)
            if is_heading:
                flush_current()
                current_segments.append(seg)
                current_text_parts.append(text)
                continue

            # Decide whether we should start a new block based on layout and length
            if self._should_start_new_block(prev, seg, current_text_parts):
                flush_current()
                current_segments.append(seg)
                current_text_parts.append(text)
            else:
                current_segments.append(seg)
                current_text_parts.append(text)

        # Flush the last group
        flush_current()

        return semantic_blocks

    # ------------------------------------------------------------------ #
    # Heuristics
    # ------------------------------------------------------------------ #

    def _is_heading(self, text: str) -> bool:
        """
        Very simple heading heuristic suited for Polish SIWZ-style docs:
        - short UPPERCASE lines,
        - lines ending with ':' (section titles),
        - lines starting with 'ROZDZIAŁ', '§', '1.', 'I.', etc.
        """
        stripped = text.strip()

        if len(stripped) <= 80 and stripped.isupper():
            return True

        if stripped.endswith(":") and len(stripped) <= 120:
            return True

        if _HEADING_RE.match(stripped):
            return True

        return False

    def _is_table_like(self, text: str) -> bool:
        """
        Heuristic: consider a text as 'table-like' if it contains
        multiple groups of 3+ spaces or tab characters – similar to
        how Segmenter detects table rows.
        """
        # multiple chunks of wide spacing or tabs -> likely a table row
        return bool(re.search(r"(\s{3,}|\t).*?(\s{3,}|\t)", text))

    def _infer_block_type(
        self,
        text: str,
        segments: List[PdfSegment],
    ) -> Optional[str]:
        """
        Try to infer a coarse block type: 'heading', 'table', 'list', etc.
        This is just a hint – LLM is still the main semantic source of truth.
        """
        if self._is_heading(text):
            return "heading"

        if self._is_table_like(text):
            return "table"

        # TODO: optionally detect bullet lists here (many lines starting with '-' or '•')
        return None

    def _should_start_new_block(
        self,
        prev: PdfSegment,
        current: PdfSegment,
        current_text_parts: List[str],
    ) -> bool:
        """
        Decide whether 'current' should start a new SemanticBlock
        instead of being merged into the existing one.
        """
        # Different pages always start a new block
        if prev.page != current.page:
            return True

        # Enforce soft character limit per block
        current_len = sum(len(t) for t in current_text_parts)
        # + 1 for a newline
        if current_len + 1 + len((current.text or "")) >= self.max_chars_per_block:
            return True

        # Layout-based cues: big vertical gap or strong horizontal shift
        prev_bbox = prev.bbox
        curr_bbox = current.bbox

        if prev_bbox is not None and curr_bbox is not None:
            y_gap = getattr(curr_bbox, "y0", 0.0) - getattr(prev_bbox, "y1", 0.0)
            x_shift = abs(
                getattr(curr_bbox, "x0", 0.0) - getattr(prev_bbox, "x0", 0.0)
            )

            if y_gap > self.y_gap_threshold:
                return True

            if x_shift > self.x_shift_threshold:
                # Most likely a new column or different region on the page
                return True

        return False

    def _union_bbox(self, bboxes: Iterable[Any]) -> Any:
        """
        Compute a union bounding box over the given bbox objects.

        We intentionally avoid importing BBox directly here and instead
        construct a new instance using the type of the first bbox. This
        keeps the code robust even if the BBox model lives in a different
        module or has been subclassed.

        If bboxes is empty, returns None.
        """
        boxes = [b for b in bboxes if b is not None]
        if not boxes:
            return None

        # Assume bbox has attributes x0, y0, x1, y1, and optionally page
        x0 = min(getattr(b, "x0", 0.0) for b in boxes)
        y0 = min(getattr(b, "y0", 0.0) for b in boxes)
        x1 = max(getattr(b, "x1", 0.0) for b in boxes)
        y1 = max(getattr(b, "y1", 0.0) for b in boxes)

        page = getattr(boxes[0], "page", getattr(boxes[0], "page_number", 1))

        BBoxType = type(boxes[0])
        try:
            return BBoxType(x0=x0, y0=y0, x1=x1, y1=y1, page=page)
        except TypeError:
            # Fallback – if the constructor signature is different,
            # just return the first bbox (better than failing hard).
            return boxes[0]
