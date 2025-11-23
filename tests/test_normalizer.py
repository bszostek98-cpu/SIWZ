"""Tests for text normalizer."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.preprocess import TextNormalizer, normalize_text


class TestTextNormalizer:
    """Tests for TextNormalizer class."""
    
    def test_initialization(self):
        """Test normalizer initialization."""
        normalizer = TextNormalizer()
        assert normalizer.normalize_unicode is True
        assert normalizer.fix_whitespace is True
        assert normalizer.fix_hyphenation is True
    
    def test_unicode_normalization(self):
        """Test Unicode NFC normalization."""
        normalizer = TextNormalizer()
        
        # Composed vs decomposed forms
        text = "café"  # May be decomposed
        normalized = normalizer.normalize(text)
        assert normalized == "café"
    
    def test_whitespace_cleanup(self):
        """Test whitespace cleanup."""
        normalizer = TextNormalizer()
        
        text = "tekst  z    wieloma     spacjami"
        normalized = normalizer.normalize(text)
        assert normalized == "tekst z wieloma spacjami"
    
    def test_multiple_newlines(self):
        """Test multiple newlines cleanup."""
        normalizer = TextNormalizer()
        
        text = "linia 1\n\n\n\nlinia 2"
        normalized = normalizer.normalize(text)
        assert normalized == "linia 1\n\nlinia 2"
    
    def test_tab_replacement(self):
        """Test tab to space conversion."""
        normalizer = TextNormalizer()
        
        text = "kolumna1\tkolumna2\tkolumna3"
        normalized = normalizer.normalize(text)
        assert "\t" not in normalized
        assert "kolumna1" in normalized
    
    def test_hyphenation_fix(self):
        """Test line-end hyphenation removal."""
        normalizer = TextNormalizer()
        
        text = "dodat-\nkowy"
        normalized = normalizer.normalize(text)
        assert normalized == "dodatkowy"
        
        text = "konsul-\ntacja"
        normalized = normalizer.normalize(text)
        assert normalized == "konsultacja"
    
    def test_smart_quotes_normalization(self):
        """Test smart quotes conversion."""
        normalizer = TextNormalizer()
        
        # Smart quotes (using Unicode escapes to avoid syntax errors)
        text = "\u201ccytat\u201d i \u2018inny\u2019"  # "cytat" i 'inny'
        normalized = normalizer.normalize(text)
        # Check that smart quotes are replaced with straight quotes
        assert '\u201c' not in normalized  # No left smart double quote
        assert '\u201d' not in normalized  # No right smart double quote
        assert '\u2018' not in normalized  # No left smart single quote
        assert '\u2019' not in normalized  # No right smart single quote
        assert 'cytat' in normalized
        assert 'inny' in normalized
        # Verify straight quotes are present
        assert normalized.count('"') == 2  # Two straight double quotes
        assert normalized.count("'") == 2  # Two straight single quotes
        
        # Polish quotes
        text = "\u201epolski cytat\u201d"  # „polski cytat"
        normalized = normalizer.normalize(text)
        assert '\u201e' not in normalized  # No Polish opening quote
        assert 'polski cytat' in normalized
    
    def test_invisible_chars_removal(self):
        """Test removal of invisible characters."""
        normalizer = TextNormalizer()
        
        # Zero-width space
        text = "tekst\u200bz\u200binwizybilnymi"
        normalized = normalizer.normalize(text)
        assert '\u200b' not in normalized
        assert normalized == "tekstzinwizybilnymi"
    
    def test_leading_trailing_whitespace(self):
        """Test removal of leading/trailing whitespace."""
        normalizer = TextNormalizer()
        
        text = "  tekst  \n  druga linia  "
        normalized = normalizer.normalize(text)
        assert normalized == "tekst\ndruga linia"
    
    def test_bullet_detection(self):
        """Test bullet point detection."""
        normalizer = TextNormalizer()
        
        # Various bullet characters
        assert normalizer.is_bullet_point("• Pierwszy punkt")
        assert normalizer.is_bullet_point("- drugi punkt")
        assert normalizer.is_bullet_point("* trzeci punkt")
        
        # Numbered bullets
        assert normalizer.is_bullet_point("1. pierwszy")
        assert normalizer.is_bullet_point("2) drugi")
        assert normalizer.is_bullet_point("a) litera")
        
        # Not bullets
        assert not normalizer.is_bullet_point("Zwykły tekst")
        assert not normalizer.is_bullet_point("")
    
    def test_disable_options(self):
        """Test disabling normalization options."""
        normalizer = TextNormalizer(
            normalize_unicode=False,
            fix_whitespace=False,
            fix_hyphenation=False,
            normalize_quotes=False
        )
        
        text = "tekst  z    błędami\nz-\ndzieleniem"
        normalized = normalizer.normalize(text)
        # Should be mostly unchanged (only invisible chars removed)
        assert "  " in normalized  # Multiple spaces preserved
    
    def test_empty_text(self):
        """Test normalization of empty text."""
        normalizer = TextNormalizer()
        
        assert normalizer.normalize("") == ""
        assert normalizer.normalize(None) == None


class TestConvenienceFunction:
    """Tests for normalize_text convenience function."""
    
    def test_normalize_text(self):
        """Test convenience function."""
        text = "przykład  z    błędami\n\n\nwielokrotne"
        normalized = normalize_text(text)
        
        assert "  " not in normalized
        assert "\n\n\n" not in normalized
    
    def test_normalize_text_options(self):
        """Test convenience function with options."""
        text = "tekst  z    spacjami"
        
        # With whitespace fix
        normalized = normalize_text(text, fix_whitespace=True)
        assert normalized == "tekst z spacjami"
        
        # Without whitespace fix
        normalized = normalize_text(text, fix_whitespace=False)
        assert "  " in normalized


class TestPolishText:
    """Tests for Polish-specific text."""
    
    def test_polish_characters(self):
        """Test Polish characters are preserved."""
        normalizer = TextNormalizer()
        
        text = "ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ"
        normalized = normalizer.normalize(text)
        assert normalized == text
    
    def test_polish_hyphenation(self):
        """Test Polish word hyphenation."""
        normalizer = TextNormalizer()
        
        text = "medycz-\nnych"
        normalized = normalizer.normalize(text)
        assert normalized == "medycznych"
        
        # Test with another Polish word
        text = "dodatko-\nwy"
        normalized = normalizer.normalize(text)
        assert normalized == "dodatkowy"
