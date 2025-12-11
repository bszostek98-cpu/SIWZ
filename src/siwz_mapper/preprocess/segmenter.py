"""
Text segmentation for PDF blocks.

Segments raw PDF blocks into smaller, more manageable PdfSegment objects:
- Paragraph separation (blank lines)
- Bullet list items (each bullet separate)
- Table rows (best-effort detection)
- Long paragraph splitting at sentence boundaries
"""

import re
from typing import List, Tuple, Optional
import logging

from ..models import PdfSegment
from .normalizer import TextNormalizer

logger = logging.getLogger(__name__)


class Segmenter:
    """
    Segments PDF blocks into smaller segments.
    
    Handles:
    - Blank-line paragraph separation
    - Bullet list detection
    - Table row detection (heuristic)
    - Long paragraph splitting (soft cap 800-1200 chars)
    - Preserves page/bbox/char offsets
    """
    
    # Soft character limits for segments
    SOFT_MIN = 800
    SOFT_MAX = 1200
    
    # Sentence ending patterns (Polish/English)
    SENTENCE_END = re.compile(r'[.!?…]+[\s\n"]')
    
    # Table detection pattern (heuristic)
    TABLE_ROW_PATTERN = re.compile(r'\s{3,}|\t')  # Multiple spaces or tab
    
    def __init__(
        self,
        soft_min_chars: int = SOFT_MIN,
        soft_max_chars: int = SOFT_MAX,
        normalize_text: bool = True,
        detect_bullets: bool = True,
        detect_tables: bool = True
    ):
        """
        Initialize segmenter.
        
        Args:
            soft_min_chars: Soft minimum segment length
            soft_max_chars: Soft maximum segment length
            normalize_text: Apply text normalization
            detect_bullets: Detect and separate bullet lists
            detect_tables: Detect and separate table rows
        """
        self.soft_min_chars = soft_min_chars
        self.soft_max_chars = soft_max_chars
        self.normalize_text_enabled = normalize_text
        self.detect_bullets = detect_bullets
        self.detect_tables = detect_tables
        
        if normalize_text:
            self.normalizer = TextNormalizer()
        else:
            self.normalizer = None
        
        logger.info(
            f"Initialized Segmenter (min={soft_min_chars}, max={soft_max_chars}, "
            f"normalize={normalize_text})"
        )
    
    def segment(self, blocks: List[PdfSegment]) -> List[PdfSegment]:
        """
        Segment PDF blocks into smaller segments.
        
        Args:
            blocks: List of raw PDF blocks from pdf_loader
            
        Returns:
            List of segmented PdfSegment objects
        """
        segments = []
        
        for block in blocks:
            # Normalize text if enabled
            text = block.text
            if self.normalizer:
                text = self.normalizer.normalize(text)
            
            # Skip empty blocks
            if not text.strip():
                continue
            
            # Segment this block
            block_segments = self._segment_block(block, text)
            segments.extend(block_segments)
        
        logger.info(f"Segmented {len(blocks)} blocks into {len(segments)} segments")
        
        return segments
    
    def _segment_block(self, block: PdfSegment, text: str) -> List[PdfSegment]:
        """
        Segment a single block into multiple segments.
        
        Args:
            block: Original block
            text: Normalized text
            
        Returns:
            List of segments
        """
        # Try bullet list detection
        if self.detect_bullets and self.normalizer and self.normalizer.is_bullet_point(text):
            return self._segment_bullet_list(block, text)
        
        # Try table detection
        if self.detect_tables and self._is_table_block(text):
            return self._segment_table(block, text)
        
        # Check for blank-line separated paragraphs
        paragraphs = self._split_by_blank_lines(text)
        if len(paragraphs) > 1:
            return self._create_paragraph_segments(block, paragraphs)
        
        # Single paragraph - check if too long
        if len(text) > self.soft_max_chars:
            return self._split_long_paragraph(block, text)
        
        # Short enough - return as-is
        return [self._create_segment_from_block(block, text, 0)]
    
    def _split_by_blank_lines(self, text: str) -> List[str]:
        """Split text by blank lines (paragraph separator)."""
        # Split on double newline or more
        paragraphs = re.split(r'\n\s*\n+', text)
        # Filter empty
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return paragraphs
    
    def _segment_bullet_list(self, block: PdfSegment, text: str) -> List[PdfSegment]:
        """
        Segment bullet list into individual items.
        
        Args:
            block: Original block
            text: Text content
            
        Returns:
            List of segments, one per bullet
        """
        lines = text.split('\n')
        bullets = []
        current_bullet = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts a new bullet
            if self.normalizer and self.normalizer.is_bullet_point(line):
                # Save previous bullet if any
                if current_bullet:
                    bullets.append('\n'.join(current_bullet))
                current_bullet = [line]
            else:
                # Continuation of current bullet
                if current_bullet:
                    current_bullet.append(line)
                else:
                    # First line, not a bullet - treat as regular text
                    bullets.append(line)
        
        # Save last bullet
        if current_bullet:
            bullets.append('\n'.join(current_bullet))
        
        # Create segments
        segments = []
        char_offset = 0
        
        for i, bullet_text in enumerate(bullets):
            segment = self._create_segment_from_block(
                block,
                bullet_text,
                char_offset,
                suffix=f"_bullet{i}"
            )
            segments.append(segment)
            char_offset += len(bullet_text) + 1  # +1 for newline
        
        return segments
    
    def _is_table_block(self, text: str) -> bool:
        """
        Heuristic to detect if block is a table.
        
        Checks for:
        - Multiple columns (aligned spaces/tabs)
        - Multiple rows
        """
        lines = text.split('\n')
        if len(lines) < 2:
            return False
        
        # Count lines with table-like spacing
        table_lines = 0
        for line in lines:
            if self.TABLE_ROW_PATTERN.search(line):
                table_lines += 1
        
        # If >50% of lines have table-like spacing, consider it a table
        return table_lines >= len(lines) * 0.5
    
    def _segment_table(self, block: PdfSegment, text: str) -> List[PdfSegment]:
        """
        Segment table into rows.
        
        Args:
            block: Original block
            text: Text content
            
        Returns:
            List of segments, one per table row
        """
        lines = text.split('\n')
        segments = []
        char_offset = 0
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            segment = self._create_segment_from_block(
                block,
                line,
                char_offset,
                suffix=f"_row{i}"
            )
            segments.append(segment)
            char_offset += len(line) + 1
        
        return segments
    
    def _create_paragraph_segments(
        self,
        block: PdfSegment,
        paragraphs: List[str]
    ) -> List[PdfSegment]:
        """
        Create segments from paragraphs.
        
        Args:
            block: Original block
            paragraphs: List of paragraph texts
            
        Returns:
            List of segments
        """
        segments = []
        char_offset = 0
        
        for i, para_text in enumerate(paragraphs):
            # Check if paragraph is too long
            if len(para_text) > self.soft_max_chars:
                # Split further
                para_segments = self._split_long_paragraph(block, para_text, char_offset)
                segments.extend(para_segments)
                char_offset += len(para_text) + 2  # +2 for double newline
            else:
                segment = self._create_segment_from_block(
                    block,
                    para_text,
                    char_offset,
                    suffix=f"_p{i}"
                )
                segments.append(segment)
                char_offset += len(para_text) + 2
        
        return segments
    
    def _split_long_paragraph(
        self,
        block: PdfSegment,
        text: str,
        base_offset: int = 0
    ) -> List[PdfSegment]:
        """
        Split long paragraph at sentence boundaries.
        
        Tries to keep segments between soft_min and soft_max.
        
        Args:
            block: Original block
            text: Paragraph text
            base_offset: Character offset from block start
            
        Returns:
            List of segments
        """
        sentences = self._split_into_sentences(text)
        segments = []
        
        current_chunk = []
        current_length = 0
        char_offset = base_offset
        chunk_start_offset = base_offset
        
        for sentence in sentences:
            sentence_len = len(sentence)
            
            # Would adding this sentence exceed soft_max?
            if current_length + sentence_len > self.soft_max_chars and current_chunk:
                # Save current chunk if it's not too small
                if current_length >= self.soft_min_chars:
                    chunk_text = ' '.join(current_chunk)
                    segment = self._create_segment_from_block(
                        block,
                        chunk_text,
                        chunk_start_offset,
                        suffix=f"_split{len(segments)}"
                    )
                    segments.append(segment)
                    
                    current_chunk = [sentence]
                    current_length = sentence_len
                    chunk_start_offset = char_offset
                    char_offset += len(chunk_text) + 1
                else:
                    # Too small, add sentence anyway
                    current_chunk.append(sentence)
                    current_length += sentence_len + 1
            else:
                current_chunk.append(sentence)
                current_length += sentence_len + 1 if current_chunk else sentence_len
        
        # Save last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            segment = self._create_segment_from_block(
                block,
                chunk_text,
                chunk_start_offset,
                suffix=f"_split{len(segments)}"
            )
            segments.append(segment)
        
        return segments
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences.
        
        Args:
            text: Input text
            
        Returns:
            List of sentences
        """
        # Find sentence boundaries
        sentences = []
        last_end = 0
        
        for match in self.SENTENCE_END.finditer(text):
            end = match.start() + 1  # Include ending punctuation
            sentence = text[last_end:end].strip()
            if sentence:
                sentences.append(sentence)
            last_end = end
        
        # Add remaining text
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                sentences.append(remaining)
        
        return sentences if sentences else [text]
    
    def _create_segment_from_block(
        self,
        block: PdfSegment,
        text: str,
        char_offset: int,
        suffix: str = ""
    ) -> PdfSegment:
        """
        Create a new segment based on original block.
        
        Preserves page, bbox (approximated), and char offsets.
        
        Args:
            block: Original block
            text: Segment text
            char_offset: Character offset from block start
            suffix: Suffix for segment_id
            
        Returns:
            New PdfSegment
        """
        # Create new segment ID
        new_id = f"{block.segment_id}{suffix}"
        
        # Calculate char offsets
        start_char = None
        end_char = None
        if block.start_char is not None:
            start_char = block.start_char + char_offset
            end_char = start_char + len(text)
        
        # Approximate bbox (keep same for now - could be refined)
        bbox = block.bbox
        
        return PdfSegment(
            segment_id=new_id,
            text=text,
            page=block.page,
            bbox=bbox,
            start_char=start_char,
            end_char=end_char,
            section_label=block.section_label,
            variant_id=block.variant_id
        )


def segment_pdf_blocks(
    blocks: List[PdfSegment],
    soft_min_chars: int = 800,
    soft_max_chars: int = 1200,
    normalize: bool = True
) -> List[PdfSegment]:
    """
    Convenience function to segment PDF blocks.
    
    Args:
        blocks: List of PDF blocks from pdf_loader
        soft_min_chars: Soft minimum segment length
        soft_max_chars: Soft maximum segment length
        normalize: Apply text normalization
        
    Returns:
        List of segmented PdfSegment objects
        
    Example:
        >>> from siwz_mapper import load_pdf
        >>> from siwz_mapper.preprocess import segment_pdf_blocks
        >>> 
        >>> blocks = load_pdf("document.pdf")
        >>> segments = segment_pdf_blocks(blocks)
        >>> print(f"Created {len(segments)} segments from {len(blocks)} blocks")
    """
    segmenter = Segmenter(
        soft_min_chars=soft_min_chars,
        soft_max_chars=soft_max_chars,
        normalize_text=normalize
    )
    return segmenter.segment(blocks)

