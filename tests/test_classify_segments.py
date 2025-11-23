"""Tests for segment classification."""

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import (
    classify_segment,
    classify_segments,
    SegmentClassification,
    FakeGPTClient,
    VALID_LABELS
)


class TestSegmentClassification:
    """Tests for SegmentClassification model."""
    
    def test_valid_classification(self):
        """Test creating valid classification."""
        classification = SegmentClassification(
            segment_id="seg_1",
            label="variant_header",
            variant_hint="1",
            is_prophylaxis=False,
            confidence=0.95,
            rationale="Nagłówek wariantu"
        )
        
        assert classification.segment_id == "seg_1"
        assert classification.label == "variant_header"
        assert classification.variant_hint == "1"
        assert classification.confidence == 0.95
    
    def test_invalid_label(self):
        """Test that invalid label raises error."""
        with pytest.raises(ValueError, match="Invalid label"):
            SegmentClassification(
                segment_id="seg_1",
                label="invalid_label",
                variant_hint=None,
                is_prophylaxis=False,
                confidence=0.8,
                rationale="Test"
            )
    
    def test_prophylaxis_consistency_auto_fix(self):
        """Test that prophylaxis label auto-sets is_prophylaxis."""
        classification = SegmentClassification(
            segment_id="seg_1",
            label="prophylaxis",
            variant_hint=None,
            is_prophylaxis=False,  # Wrong, should be auto-fixed
            confidence=0.9,
            rationale="Program profilaktyczny"
        )
        
        # Should be auto-corrected to True
        assert classification.is_prophylaxis is True
    
    def test_json_roundtrip(self):
        """Test JSON serialization and deserialization."""
        original = SegmentClassification(
            segment_id="seg_1",
            label="variant_body",
            variant_hint="2",
            is_prophylaxis=False,
            confidence=0.88,
            rationale="Lista usług"
        )
        
        json_str = original.model_dump_json()
        loaded = SegmentClassification.model_validate_json(json_str)
        
        assert loaded.segment_id == original.segment_id
        assert loaded.label == original.label
        assert loaded.confidence == original.confidence


class TestFakeGPTClient:
    """Tests for FakeGPTClient."""
    
    def test_fake_client_basic(self):
        """Test basic fake client functionality."""
        client = FakeGPTClient()
        
        response = client.chat("system", "user")
        
        assert isinstance(response, str)
        assert client.call_count == 1
        assert client.last_system_prompt == "system"
        assert client.last_user_prompt == "user"
    
    def test_fake_client_variant_header(self):
        """Test fake client recognizes variant headers."""
        client = FakeGPTClient()
        
        response = client.chat("system", "Załącznik nr 2 A – WARIANT 1")
        data = json.loads(response)
        
        assert data["label"] == "variant_header"
        assert data["variant_hint"] == "1"
        assert data["is_prophylaxis"] is False
    
    def test_fake_client_prophylaxis(self):
        """Test fake client recognizes prophylaxis."""
        client = FakeGPTClient()
        
        response = client.chat("system", "Profilaktyczny przegląd stanu zdrowia")
        data = json.loads(response)
        
        assert data["label"] == "prophylaxis"
        assert data["is_prophylaxis"] is True
    
    def test_fake_client_pricing_table(self):
        """Test fake client recognizes pricing tables."""
        client = FakeGPTClient()
        
        response = client.chat(
            "system",
            "Tabela cenowa z kolumnami: Wariant 1, Wariant 2, Wariant 3"
        )
        data = json.loads(response)
        
        assert data["label"] == "pricing_table"
    
    def test_fake_client_custom_responses(self):
        """Test fake client with custom responses."""
        custom_responses = {
            "test_keyword": json.dumps({
                "segment_id": "custom",
                "label": "general",
                "variant_hint": None,
                "is_prophylaxis": False,
                "confidence": 1.0,
                "rationale": "Custom response"
            })
        }
        
        client = FakeGPTClient(responses=custom_responses)
        response = client.chat("system", "This contains test_keyword")
        data = json.loads(response)
        
        assert data["rationale"] == "Custom response"


class TestClassifySegment:
    """Tests for classify_segment function."""
    
    def test_classify_variant_header(self):
        """Test classifying a variant header."""
        client = FakeGPTClient()
        
        segment = PdfSegment(
            segment_id="seg_1",
            text="Załącznik nr 2 A – WARIANT 1\nZakres świadczeń medycznych",
            page=5
        )
        
        result = classify_segment(client, segment)
        
        assert result.segment_id == "seg_1"
        assert result.label == "variant_header"
        assert result.variant_hint == "1"
        assert result.confidence > 0.0
    
    def test_classify_variant_body(self):
        """Test classifying variant body with services."""
        client = FakeGPTClient()
        
        segment = PdfSegment(
            segment_id="seg_2",
            text="• Konsultacja kardiologiczna\n• Badanie EKG\n• USG serca",
            page=6
        )
        
        result = classify_segment(client, segment)
        
        assert result.segment_id == "seg_2"
        assert result.label == "variant_body"
        assert not result.is_prophylaxis
    
    def test_classify_prophylaxis(self):
        """Test classifying prophylaxis section."""
        client = FakeGPTClient()
        
        segment = PdfSegment(
            segment_id="seg_3",
            text="Profilaktyczny przegląd stanu zdrowia obejmuje:\n• Morfologia\n• Badanie ogólne moczu",
            page=10
        )
        
        result = classify_segment(client, segment)
        
        assert result.segment_id == "seg_3"
        assert result.label == "prophylaxis"
        assert result.is_prophylaxis is True
    
    def test_classify_pricing_table(self):
        """Test classifying pricing table."""
        client = FakeGPTClient()
        
        segment = PdfSegment(
            segment_id="seg_4",
            text="Tabela ofertowa:\nCena za Wariant 1: ____\nCena za Wariant 2: ____",
            page=15
        )
        
        result = classify_segment(client, segment)
        
        assert result.segment_id == "seg_4"
        assert result.label == "pricing_table"
    
    def test_classify_with_context(self):
        """Test classification with previous/next context."""
        client = FakeGPTClient()
        
        segment = PdfSegment(
            segment_id="seg_5",
            text="Lista badań:",
            page=7
        )
        
        prev_text = "WARIANT 1 - Podstawowy"
        next_text = "• Badanie 1\n• Badanie 2"
        
        result = classify_segment(client, segment, prev_text, next_text)
        
        assert result.segment_id == "seg_5"
        assert isinstance(result.label, str)
        assert result.label in VALID_LABELS


class TestClassifySegments:
    """Tests for classify_segments function."""
    
    def test_classify_multiple_segments(self):
        """Test classifying multiple segments."""
        client = FakeGPTClient()
        
        segments = [
            PdfSegment(
                segment_id="seg_1",
                text="Ogłoszenie o zamówieniu publicznym",
                page=1
            ),
            PdfSegment(
                segment_id="seg_2",
                text="WARIANT 1 - Pakiet podstawowy",
                page=5
            ),
            PdfSegment(
                segment_id="seg_3",
                text="• Konsultacja lekarska\n• Badania laboratoryjne",
                page=6
            ),
        ]
        
        results = classify_segments(segments, client, show_progress=False)
        
        assert len(results) == 3
        assert all(isinstance(r, SegmentClassification) for r in results)
        assert results[0].segment_id == "seg_1"
        assert results[1].segment_id == "seg_2"
        assert results[2].segment_id == "seg_3"
    
    def test_classify_empty_list(self):
        """Test classifying empty segment list."""
        client = FakeGPTClient()
        
        results = classify_segments([], client)
        
        assert results == []
    
    def test_context_propagation(self):
        """Test that context is properly passed between segments."""
        client = FakeGPTClient()
        
        segments = [
            PdfSegment(segment_id="seg_1", text="Text 1", page=1),
            PdfSegment(segment_id="seg_2", text="Text 2", page=1),
            PdfSegment(segment_id="seg_3", text="Text 3", page=1),
        ]
        
        results = classify_segments(segments, client, show_progress=False)
        
        # All segments should be classified
        assert len(results) == 3
        
        # FakeGPTClient should have been called 3 times
        assert client.call_count == 3


class TestParseResponse:
    """Tests for response parsing."""
    
    def test_parse_plain_json(self):
        """Test parsing plain JSON response."""
        from siwz_mapper.llm.classify_segments import _parse_classification_response
        
        response = json.dumps({
            "segment_id": "will_be_overridden",
            "label": "general",
            "variant_hint": None,
            "is_prophylaxis": False,
            "confidence": 0.85,
            "rationale": "Test"
        })
        
        result = _parse_classification_response(response, "seg_123")
        
        assert result.segment_id == "seg_123"  # Overridden
        assert result.label == "general"
    
    def test_parse_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        from siwz_mapper.llm.classify_segments import _parse_classification_response
        
        response = """```json
{
  "segment_id": "test",
  "label": "variant_header",
  "variant_hint": "2",
  "is_prophylaxis": false,
  "confidence": 0.9,
  "rationale": "Test"
}
```"""
        
        result = _parse_classification_response(response, "seg_456")
        
        assert result.segment_id == "seg_456"
        assert result.label == "variant_header"
        assert result.variant_hint == "2"
    
    def test_parse_invalid_json_raises(self):
        """Test that invalid JSON raises error."""
        from siwz_mapper.llm.classify_segments import _parse_classification_response
        
        with pytest.raises(json.JSONDecodeError):
            _parse_classification_response("Not valid JSON", "seg_789")


class TestIntegration:
    """Integration tests with realistic examples."""
    
    def test_realistic_siwz_flow(self):
        """Test classification of realistic SIWZ segments."""
        client = FakeGPTClient()
        
        segments = [
            # Intro
            PdfSegment(
                segment_id="seg_1",
                text="OGŁOSZENIE O ZAMÓWIENIU PUBLICZNYM\nZamówienie na ochronę zdrowia pracowników",
                page=1
            ),
            # Variant header
            PdfSegment(
                segment_id="seg_2",
                text="Załącznik nr 2 A – WARIANT 1\nPakiet opieki zdrowotnej podstawowej",
                page=5
            ),
            # Variant body
            PdfSegment(
                segment_id="seg_3",
                text="Zakres usług:\n• Konsultacje specjalistyczne\n• Badania diagnostyczne",
                page=6
            ),
            # Prophylaxis
            PdfSegment(
                segment_id="seg_4",
                text="Program profilaktyczny obejmuje przegląd stanu zdrowia:\n• Morfologia krwi\n• Badanie ogólne moczu",
                page=10
            ),
            # Pricing table
            PdfSegment(
                segment_id="seg_5",
                text="Tabela cenowa:\nCena za Wariant 1: ___zł\nCena za Wariant 2: ___zł",
                page=15
            ),
        ]
        
        results = classify_segments(segments, client, show_progress=False)
        
        assert len(results) == 5
        
        # Check labels
        assert results[0].label == "irrelevant"  # intro
        assert results[1].label == "variant_header"  # variant header
        assert results[2].label == "variant_body"  # services
        assert results[3].label == "prophylaxis"  # prophylaxis
        assert results[4].label == "pricing_table"  # pricing
        
        # Check prophylaxis flag
        assert not results[0].is_prophylaxis
        assert not results[1].is_prophylaxis
        assert not results[2].is_prophylaxis
        assert results[3].is_prophylaxis
        assert not results[4].is_prophylaxis


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_fallback_on_invalid_response(self):
        """Test fallback when GPT returns invalid response."""
        # Create client that returns invalid JSON
        client = FakeGPTClient(responses={
            "invalid": "This is not JSON at all"
        })
        
        segment = PdfSegment(
            segment_id="seg_err",
            text="This will trigger invalid response",
            page=1
        )
        
        result = classify_segment(client, segment)
        
        # Should fallback to "irrelevant" with low confidence
        assert result.segment_id == "seg_err"
        assert result.label == "irrelevant"
        assert result.confidence < 0.5
        assert "FALLBACK" in result.rationale or "ERROR" in result.rationale

