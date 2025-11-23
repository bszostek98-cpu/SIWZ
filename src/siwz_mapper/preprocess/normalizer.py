"""
Text normalization utilities.

Provides light text cleaning:
- Unicode normalization
- Whitespace cleanup
- Hyphenation fixes (Polish/English)
"""

import re
import unicodedata
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TextNormalizer:
    """
    Text normalizer for PDF-extracted text.
    
    Handles:
    - Unicode normalization (NFC)
    - Whitespace cleanup (multiple spaces, tabs, etc.)
    - Line-end hyphenation removal
    - Smart quotes conversion
    - Zero-width characters removal
    """
    
    # Common bullet point characters
    BULLET_CHARS = ['•', '◦', '▪', '▫', '●', '○', '■', '□', '–', '—', '-', '*']
    
    # Hyphenation patterns (Polish/English)
    HYPHENATION_PATTERN = re.compile(r'(\w+)-\s*\n\s*(\w+)')
    
    def __init__(
        self,
        normalize_unicode: bool = True,
        fix_whitespace: bool = True,
        fix_hyphenation: bool = True,
        normalize_quotes: bool = True,
        preserve_bullets: bool = True
    ):
        """
        Initialize text normalizer.
        
        Args:
            normalize_unicode: Apply Unicode NFC normalization
            fix_whitespace: Clean up multiple spaces/tabs
            fix_hyphenation: Remove line-end hyphens
            normalize_quotes: Convert smart quotes to straight
            preserve_bullets: Keep bullet characters
        """
        self.normalize_unicode = normalize_unicode
        self.fix_whitespace = fix_whitespace
        self.fix_hyphenation = fix_hyphenation
        self.normalize_quotes = normalize_quotes
        self.preserve_bullets = preserve_bullets
    
    def normalize(self, text: str) -> str:
        """
        Normalize text.
        
        Args:
            text: Input text
            
        Returns:
            Normalized text
        """
        if not text:
            return text
        
        # Unicode normalization (NFC - composed form)
        if self.normalize_unicode:
            text = unicodedata.normalize('NFC', text)
        
        # Remove zero-width and invisible characters
        text = self._remove_invisible_chars(text)
        
        # Fix line-end hyphenation
        if self.fix_hyphenation:
            text = self._fix_hyphenation(text)
        
        # Normalize quotes
        if self.normalize_quotes:
            text = self._normalize_quotes(text)
        
        # Whitespace cleanup
        if self.fix_whitespace:
            text = self._fix_whitespace(text)
        
        return text
    
    def _remove_invisible_chars(self, text: str) -> str:
        """Remove zero-width and other invisible characters."""
        # Zero-width characters
        invisible_chars = [
            '\u200b',  # Zero-width space
            '\u200c',  # Zero-width non-joiner
            '\u200d',  # Zero-width joiner
            '\ufeff',  # Zero-width no-break space (BOM)
            '\u00ad',  # Soft hyphen
        ]
        
        for char in invisible_chars:
            text = text.replace(char, '')
        
        return text
    
    def _fix_hyphenation(self, text: str) -> str:
        """
        Remove line-end hyphens for split words.
        
        Example: "dodat-\nkowy" -> "dodatkowy"
        """
        # Match: word-\nword
        text = self.HYPHENATION_PATTERN.sub(r'\1\2', text)
        
        return text
    
    def _normalize_quotes(self, text: str) -> str:
        """Convert smart quotes to straight quotes."""
        # Double quotes (using Unicode escapes to avoid encoding issues)
        text = text.replace('\u201c', '"').replace('\u201d', '"')  # Smart double quotes ""
        text = text.replace('\u201e', '"').replace('\u201f', '"')  # Polish quotes „‟
        
        # Single quotes
        text = text.replace('\u2018', "'").replace('\u2019', "'")  # Smart single quotes ''
        text = text.replace('\u201a', "'").replace('\u201b', "'")  # Additional quotes ‚‛
        
        return text
    
    def _fix_whitespace(self, text: str) -> str:
        """Clean up whitespace."""
        # Replace tabs with spaces
        text = text.replace('\t', ' ')
        
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        
        # Clean up spaces around newlines
        text = re.sub(r' *\n *', '\n', text)
        
        # Remove trailing/leading whitespace per line
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)
        
        # Remove multiple consecutive newlines (keep max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text
    
    def is_bullet_point(self, text: str) -> bool:
        """
        Check if text starts with a bullet point.
        
        Args:
            text: Text to check
            
        Returns:
            True if starts with bullet character
        """
        text = text.lstrip()
        if not text:
            return False
        
        # Check for bullet characters
        if text[0] in self.BULLET_CHARS:
            return True
        
        # Check for numbered bullets (1., 2), a), etc.)
        if re.match(r'^(\d+|[a-z])[.)][\s]', text):
            return True
        
        return False


def normalize_text(
    text: str,
    normalize_unicode: bool = True,
    fix_whitespace: bool = True,
    fix_hyphenation: bool = True
) -> str:
    """
    Convenience function for text normalization.
    
    Args:
        text: Input text
        normalize_unicode: Apply Unicode normalization
        fix_whitespace: Clean up whitespace
        fix_hyphenation: Fix line-end hyphens
        
    Returns:
        Normalized text
        
    Example:
        >>> text = "przykładowy  tekst\\n\\nz    błędami"
        >>> normalize_text(text)
        'przykładowy tekst\\n\\nz błędami'
    """
    normalizer = TextNormalizer(
        normalize_unicode=normalize_unicode,
        fix_whitespace=fix_whitespace,
        fix_hyphenation=fix_hyphenation
    )
    return normalizer.normalize(text)

