"""Tests for core data models (models.py)."""

import pytest
from pydantic import ValidationError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import (
    ServiceEntry,
    BBox,
    PdfSegment,
    DetectedEntity,
    CandidateService,
    EntityMapping,
    VariantResult,
    DocumentResult,
    ValidationHelper,
)


class TestServiceEntry:
    """Tests for ServiceEntry model."""
    
    def test_create_service_entry(self):
        """Test basic ServiceEntry creation."""
        service = ServiceEntry(
            code="KAR001",
            name="Konsultacja kardiologiczna",
            category="Kardiologia",
            subcategory="Konsultacje"
        )
        
        assert service.code == "KAR001"
        assert service.name == "Konsultacja kardiologiczna"
        assert service.category == "Kardiologia"
        assert service.subcategory == "Konsultacje"
        assert service.synonyms == []
    
    def test_service_entry_with_synonyms(self):
        """Test ServiceEntry with synonyms."""
        service = ServiceEntry(
            code="KAR001",
            name="Konsultacja kardiologiczna",
            category="Kardiologia",
            synonyms=["wizyta kardiologiczna", "badanie"]
        )
        
        assert len(service.synonyms) == 2
        assert "wizyta kardiologiczna" in service.synonyms
    
    def test_service_entry_to_search_text(self):
        """Test to_search_text method."""
        service = ServiceEntry(
            code="KAR001",
            name="Konsultacja",
            category="Kardiologia",
            subcategory="Konsultacje",
            synonyms=["wizyta"]
        )
        
        search_text = service.to_search_text()
        assert "KAR001" in search_text
        assert "Konsultacja" in search_text
        assert "Kardiologia" in search_text
        assert "wizyta" in search_text
    
    def test_service_entry_json_roundtrip(self):
        """Test JSON serialization/deserialization."""
        service = ServiceEntry(
            code="KAR001",
            name="Test",
            category="Cat"
        )
        
        json_data = service.model_dump()
        service2 = ServiceEntry(**json_data)
        
        assert service2.code == service.code
        assert service2.name == service.name


class TestBBoxAndPdfSegment:
    """Tests for BBox and PdfSegment models."""
    
    def test_create_bbox(self):
        """Test BBox creation."""
        bbox = BBox(page=1, x0=50.0, y0=200.0, x1=400.0, y1=220.0)
        
        assert bbox.page == 1
        assert bbox.x0 == 50.0
        assert bbox.y1 == 220.0
    
    def test_create_pdf_segment_minimal(self):
        """Test PdfSegment with minimal fields."""
        segment = PdfSegment(
            segment_id="seg_001",
            text="Test text",
            page=1
        )
        
        assert segment.segment_id == "seg_001"
        assert segment.text == "Test text"
        assert segment.page == 1
        assert segment.bbox is None
    
    def test_create_pdf_segment_full(self):
        """Test PdfSegment with all fields."""
        bbox = BBox(page=5, x0=50, y0=200, x1=400, y1=220)
        segment = PdfSegment(
            segment_id="seg_001",
            text="Konsultacja kardiologiczna",
            page=5,
            bbox=bbox,
            start_char=1250,
            end_char=1276,
            section_label="Wariant 1",
            variant_id="variant_1"
        )
        
        assert segment.segment_id == "seg_001"
        assert segment.page == 5
        assert segment.bbox is not None
        assert segment.bbox.page == 5
        assert segment.start_char == 1250
        assert segment.section_label == "Wariant 1"
    
    def test_pdf_segment_page_validation(self):
        """Test page number validation."""
        with pytest.raises(ValidationError):
            PdfSegment(
                segment_id="seg_001",
                text="Test",
                page=0  # Invalid: must be >= 1
            )
    
    def test_pdf_segment_char_offset_validation(self):
        """Test character offset validation."""
        with pytest.raises(ValidationError):
            PdfSegment(
                segment_id="seg_001",
                text="Test",
                page=1,
                start_char=-1  # Invalid: must be >= 0
            )


class TestDetectedEntity:
    """Tests for DetectedEntity model."""
    
    def test_create_detected_entity(self):
        """Test DetectedEntity creation."""
        entity = DetectedEntity(
            entity_id="ent_001",
            segment_id="seg_001",
            text="konsultacja kardiologiczna",
            quote="Konsultacja kardiologiczna",
            page=5,
            confidence=0.95
        )
        
        assert entity.entity_id == "ent_001"
        assert entity.segment_id == "seg_001"
        assert entity.text == "konsultacja kardiologiczna"
        assert entity.quote == "Konsultacja kardiologiczna"
        assert entity.confidence == 0.95
    
    def test_detected_entity_with_offsets(self):
        """Test DetectedEntity with character offsets."""
        entity = DetectedEntity(
            entity_id="ent_001",
            segment_id="seg_001",
            text="test",
            quote="Test",
            page=1,
            start_char=100,
            end_char=104,
            confidence=0.9
        )
        
        assert entity.start_char == 100
        assert entity.end_char == 104
    
    def test_detected_entity_confidence_validation(self):
        """Test confidence validation."""
        # Valid confidence
        entity = DetectedEntity(
            entity_id="ent_001",
            segment_id="seg_001",
            text="test",
            quote="Test",
            page=1,
            confidence=0.5
        )
        assert entity.confidence == 0.5
        
        # Invalid confidence > 1
        with pytest.raises(ValidationError):
            DetectedEntity(
                entity_id="ent_001",
                segment_id="seg_001",
                text="test",
                quote="Test",
                page=1,
                confidence=1.5
            )
        
        # Invalid confidence < 0
        with pytest.raises(ValidationError):
            DetectedEntity(
                entity_id="ent_001",
                segment_id="seg_001",
                text="test",
                quote="Test",
                page=1,
                confidence=-0.1
            )


class TestCandidateService:
    """Tests for CandidateService model."""
    
    def test_create_candidate_service(self):
        """Test CandidateService creation."""
        candidate = CandidateService(
            code="KAR001",
            name="Konsultacja kardiologiczna",
            score=0.95,
            reason="Dokładne dopasowanie"
        )
        
        assert candidate.code == "KAR001"
        assert candidate.score == 0.95
        assert candidate.reason == "Dokładne dopasowanie"
    
    def test_candidate_service_score_validation(self):
        """Test score validation."""
        # Valid score
        candidate = CandidateService(
            code="KAR001",
            name="Test",
            score=0.5,
            reason="Test"
        )
        assert candidate.score == 0.5
        
        # Invalid score > 1
        with pytest.raises(ValidationError):
            CandidateService(
                code="KAR001",
                name="Test",
                score=1.5,
                reason="Test"
            )


class TestEntityMapping:
    """Tests for EntityMapping model."""
    
    def test_create_entity_mapping_1_to_1(self):
        """Test EntityMapping with 1-1 type."""
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-1",
            primary_codes=["KAR001"],
            rationale="Dokładne dopasowanie",
            confidence=0.95
        )
        
        assert mapping.entity_id == "ent_001"
        assert mapping.mapping_type == "1-1"
        assert len(mapping.primary_codes) == 1
        assert mapping.confidence == 0.95
    
    def test_create_entity_mapping_1_to_many(self):
        """Test EntityMapping with 1-m type."""
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-m",
            primary_codes=["KAR001", "KAR002", "KAR003"],
            rationale="Pakiet usług",
            confidence=0.85
        )
        
        assert mapping.mapping_type == "1-m"
        assert len(mapping.primary_codes) == 3
    
    def test_create_entity_mapping_unmapped(self):
        """Test EntityMapping with 1-0 (unmapped) type."""
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-0",
            primary_codes=[],
            rationale="Nie znaleziono dopasowania",
            confidence=0.3
        )
        
        assert mapping.mapping_type == "1-0"
        assert len(mapping.primary_codes) == 0
    
    def test_entity_mapping_with_candidates(self):
        """Test EntityMapping with alternative candidates."""
        candidates = [
            CandidateService(
                code="KAR005",
                name="Konsultacja kontrolna",
                score=0.72,
                reason="Podobna nazwa"
            )
        ]
        
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-1",
            primary_codes=["KAR001"],
            alt_candidates=candidates,
            rationale="Best match",
            confidence=0.95
        )
        
        assert len(mapping.alt_candidates) == 1
        assert mapping.alt_candidates[0].code == "KAR005"
    
    def test_entity_mapping_type_validation(self):
        """Test mapping type validation."""
        # Valid types
        for mt in ["1-1", "1-m", "m-1", "1-0"]:
            mapping = EntityMapping(
                entity_id="ent_001",
                mapping_type=mt,
                primary_codes=[],
                rationale="Test",
                confidence=0.5
            )
            assert mapping.mapping_type == mt
        
        # Invalid type
        with pytest.raises(ValidationError):
            EntityMapping(
                entity_id="ent_001",
                mapping_type="invalid",
                primary_codes=[],
                rationale="Test",
                confidence=0.5
            )


class TestVariantResult:
    """Tests for VariantResult model."""
    
    def test_create_variant_result(self):
        """Test VariantResult creation."""
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001", "KAR002"],
            prophylaxis_codes=[],
            mappings=[]
        )
        
        assert variant.variant_id == "variant_1"
        assert len(variant.core_codes) == 2
        assert len(variant.prophylaxis_codes) == 0
    
    def test_variant_result_with_mappings(self):
        """Test VariantResult with mappings."""
        mapping1 = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-1",
            primary_codes=["KAR001"],
            rationale="Match",
            confidence=0.95
        )
        
        mapping2 = EntityMapping(
            entity_id="ent_002",
            mapping_type="1-1",
            primary_codes=["KAR002"],
            rationale="Match",
            confidence=0.90
        )
        
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001", "KAR002"],
            prophylaxis_codes=[],
            mappings=[mapping1, mapping2]
        )
        
        assert len(variant.mappings) == 2
        assert variant.mappings[0].entity_id == "ent_001"
    
    def test_variant_result_with_prophylaxis(self):
        """Test VariantResult with prophylaxis codes."""
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001"],
            prophylaxis_codes=["PROF001", "PROF002"],
            mappings=[]
        )
        
        assert len(variant.prophylaxis_codes) == 2
        assert "PROF001" in variant.prophylaxis_codes


class TestDocumentResult:
    """Tests for DocumentResult model."""
    
    def test_create_document_result(self):
        """Test DocumentResult creation."""
        doc = DocumentResult(
            doc_id="siwz_2025_test",
            variants=[],
            metadata={}
        )
        
        assert doc.doc_id == "siwz_2025_test"
        assert len(doc.variants) == 0
    
    def test_document_result_with_variants(self):
        """Test DocumentResult with variants."""
        variant1 = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001"],
            prophylaxis_codes=[],
            mappings=[]
        )
        
        variant2 = VariantResult(
            variant_id="variant_2",
            core_codes=["KAR001", "KAR002"],
            prophylaxis_codes=[],
            mappings=[]
        )
        
        doc = DocumentResult(
            doc_id="siwz_2025_test",
            variants=[variant1, variant2],
            metadata={}
        )
        
        assert len(doc.variants) == 2
        assert doc.variants[0].variant_id == "variant_1"
        assert doc.variants[1].variant_id == "variant_2"
    
    def test_document_result_with_metadata(self):
        """Test DocumentResult with metadata."""
        doc = DocumentResult(
            doc_id="siwz_2025_test",
            variants=[],
            metadata={
                "processed_at": "2025-11-22T10:30:00",
                "pipeline_version": "0.1.0",
                "num_segments": 150
            }
        )
        
        assert doc.metadata["processed_at"] == "2025-11-22T10:30:00"
        assert doc.metadata["pipeline_version"] == "0.1.0"
    
    def test_document_result_json_roundtrip(self):
        """Test full JSON serialization/deserialization."""
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001"],
            prophylaxis_codes=[],
            mappings=[]
        )
        
        doc = DocumentResult(
            doc_id="test_doc",
            variants=[variant],
            metadata={"version": "0.1.0"}
        )
        
        # Serialize
        json_data = doc.model_dump()
        
        # Deserialize
        doc2 = DocumentResult(**json_data)
        
        assert doc2.doc_id == doc.doc_id
        assert len(doc2.variants) == len(doc.variants)
        assert doc2.variants[0].variant_id == doc.variants[0].variant_id


class TestValidationHelper:
    """Tests for ValidationHelper."""
    
    def test_validate_document_result(self):
        """Test validate_document_result."""
        data = {
            "doc_id": "test",
            "variants": [],
            "metadata": {}
        }
        
        result = ValidationHelper.validate_document_result(data)
        assert isinstance(result, DocumentResult)
        assert result.doc_id == "test"
    
    def test_validate_document_result_invalid(self):
        """Test validate_document_result with invalid data."""
        data = {
            # Missing required field 'doc_id'
            "variants": [],
            "metadata": {}
        }
        
        with pytest.raises(ValidationError):
            ValidationHelper.validate_document_result(data)
    
    def test_validate_service_entry(self):
        """Test validate_service_entry."""
        data = {
            "code": "KAR001",
            "name": "Test",
            "category": "Cat"
        }
        
        result = ValidationHelper.validate_service_entry(data)
        assert isinstance(result, ServiceEntry)
    
    def test_get_json_schema(self):
        """Test get_json_schema."""
        schema = ValidationHelper.get_json_schema(ServiceEntry)
        
        assert "properties" in schema
        assert "code" in schema["properties"]
        assert "name" in schema["properties"]
    
    def test_validate_mapping_type_consistency(self):
        """Test validate_mapping_type_consistency."""
        # Valid variant
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-1",
            primary_codes=["KAR001"],
            rationale="Test",
            confidence=0.9
        )
        
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001"],
            prophylaxis_codes=[],
            mappings=[mapping]
        )
        
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        assert len(warnings) == 0
    
    def test_validate_mapping_type_consistency_warnings(self):
        """Test validate_mapping_type_consistency with warnings."""
        # Variant with code not in mappings
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001", "KAR999"],  # KAR999 not mapped
            prophylaxis_codes=[],
            mappings=[
                EntityMapping(
                    entity_id="ent_001",
                    mapping_type="1-1",
                    primary_codes=["KAR001"],
                    rationale="Test",
                    confidence=0.9
                )
            ]
        )
        
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        assert len(warnings) > 0
        assert "KAR999" in warnings[0]
    
    def test_validate_mapping_type_consistency_overlap(self):
        """Test detecting codes in both core and prophylaxis."""
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=["KAR001"],
            prophylaxis_codes=["KAR001"],  # Overlap!
            mappings=[]
        )
        
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        assert any("both core and prophylaxis" in w for w in warnings)
    
    def test_validate_mapping_type_consistency_1_0_with_codes(self):
        """Test detecting 1-0 mapping with primary codes."""
        mapping = EntityMapping(
            entity_id="ent_001",
            mapping_type="1-0",
            primary_codes=["KAR001"],  # Invalid for 1-0!
            rationale="Test",
            confidence=0.5
        )
        
        variant = VariantResult(
            variant_id="variant_1",
            core_codes=[],
            prophylaxis_codes=[],
            mappings=[mapping]
        )
        
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        assert any("type '1-0' but has primary_codes" in w for w in warnings)

