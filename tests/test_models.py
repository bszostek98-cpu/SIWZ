import pytest
from pydantic import ValidationError

from siwz_mapper.models import (
    ServiceEntry, BBox, PdfSegment,
    CandidateService, EntityMapping,
    VariantResult, DocumentResult
)


class TestCurrentModels:
    def test_bbox_creation(self):
        bbox = BBox(page=1, x0=0, y0=0, x1=100, y1=20)
        assert bbox.page == 1

    def test_pdfsegment_creation(self):
        seg = PdfSegment(
            segment_id="seg1",
            text="Test",
            page=1,
            bbox=None
        )
        assert seg.segment_id == "seg1"

    def test_serviceentry_creation(self):
        svc = ServiceEntry(
            code="SVC001",
            name="Konsultacja",
            category="Kardiologia",
            subcategory=None,
            synonyms=["wizyta"]
        )
        assert "SVC001" in svc.to_search_text()

    def test_candidate_service_validation(self):
        cand = CandidateService(
            code="SVC001",
            name="Test",
            score=0.8,
            reason="ok"
        )
        assert cand.score == 0.8
        with pytest.raises(ValidationError):
            CandidateService(code="SVC001", name="Test", score=1.5, reason="bad")

    def test_entity_mapping_creation(self):
        m = EntityMapping(
            entity_id="e1",
            mapping_type="1-1",
            primary_codes=["SVC001"],
            alt_candidates=[],
            rationale="exact",
            confidence=0.9
        )
        assert m.mapping_type == "1-1"

    def test_document_result_creation(self):
        vr = VariantResult(variant_id="V1")
        doc = DocumentResult(doc_id="doc1", variants=[vr])
        assert doc.variants[0].variant_id == "V1"
