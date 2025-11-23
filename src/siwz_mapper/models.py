"""
Core data models for SIWZ Mapper.

All models use Pydantic for validation and JSON serialization.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ============================================================================
# Service Dictionary Models
# ============================================================================

class ServiceEntry(BaseModel):
    """Entry in the medical services dictionary."""
    
    code: str = Field(..., description="Unique service code")
    name: str = Field(..., description="Service name")
    category: str = Field(..., description="Main category")
    subcategory: Optional[str] = Field(None, description="Subcategory (optional)")
    synonyms: List[str] = Field(default_factory=list, description="Alternative names")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "KAR001",
                "name": "Konsultacja kardiologiczna",
                "category": "Kardiologia",
                "subcategory": "Konsultacje",
                "synonyms": ["wizyta kardiologiczna", "badanie kardiologiczne"]
            }
        }
    
    def to_search_text(self) -> str:
        """Generate concatenated text for search."""
        parts = [self.code, self.name, self.category]
        if self.subcategory:
            parts.append(self.subcategory)
        parts.extend(self.synonyms)
        return " | ".join(parts)


# ============================================================================
# PDF Segment Models
# ============================================================================

class BBox(BaseModel):
    """Bounding box coordinates in PDF."""
    
    page: int = Field(..., description="Page number (1-indexed)")
    x0: float = Field(..., description="Left coordinate")
    y0: float = Field(..., description="Bottom coordinate")
    x1: float = Field(..., description="Right coordinate")
    y1: float = Field(..., description="Top coordinate")
    
    class Config:
        json_schema_extra = {
            "example": {
                "page": 1,
                "x0": 50.0,
                "y0": 200.0,
                "x1": 400.0,
                "y1": 220.0
            }
        }


class PdfSegment(BaseModel):
    """A segment of text extracted from PDF with position info."""
    
    segment_id: str = Field(..., description="Unique segment identifier")
    text: str = Field(..., description="Extracted text content")
    page: int = Field(..., description="Page number (1-indexed)")
    bbox: Optional[BBox] = Field(None, description="Bounding box coordinates")
    start_char: Optional[int] = Field(None, description="Character offset start in document")
    end_char: Optional[int] = Field(None, description="Character offset end in document")
    section_label: Optional[str] = Field(None, description="Section label (e.g., 'Wariant 1')")
    variant_id: Optional[str] = Field(None, description="Associated variant ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "segment_id": "seg_001",
                "text": "Konsultacja kardiologiczna oraz USG serca",
                "page": 5,
                "bbox": {"page": 5, "x0": 50, "y0": 200, "x1": 400, "y1": 220},
                "start_char": 1250,
                "end_char": 1292,
                "section_label": "Wariant podstawowy",
                "variant_id": "variant_1"
            }
        }
    
    @field_validator('page')
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError('Page number must be >= 1')
        return v
    
    @field_validator('start_char', 'end_char')
    @classmethod
    def validate_char_offsets(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError('Character offsets must be >= 0')
        return v


# ============================================================================
# Entity Detection Models
# ============================================================================

class DetectedEntity(BaseModel):
    """A detected service mention entity in the text."""
    
    entity_id: str = Field(..., description="Unique entity identifier")
    segment_id: str = Field(..., description="Source segment ID")
    text: str = Field(..., description="Entity text (normalized)")
    quote: str = Field(..., description="Exact quote from PDF (as extracted)")
    page: int = Field(..., description="Page number")
    start_char: Optional[int] = Field(None, description="Character offset start")
    end_char: Optional[int] = Field(None, description="Character offset end")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Detection confidence")
    
    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "ent_001",
                "segment_id": "seg_001",
                "text": "konsultacja kardiologiczna",
                "quote": "Konsultacja kardiologiczna",
                "page": 5,
                "start_char": 1250,
                "end_char": 1276,
                "confidence": 0.95
            }
        }
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0 and 1')
        return v


# ============================================================================
# Service Mapping Models
# ============================================================================

class CandidateService(BaseModel):
    """A candidate service match for an entity."""
    
    code: str = Field(..., description="Service code")
    name: str = Field(..., description="Service name")
    score: float = Field(..., ge=0.0, le=1.0, description="Match score")
    reason: str = Field(..., description="Reasoning for this match")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "KAR001",
                "name": "Konsultacja kardiologiczna",
                "score": 0.95,
                "reason": "Dokładne dopasowanie nazwy usługi"
            }
        }
    
    @field_validator('score')
    @classmethod
    def validate_score(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('Score must be between 0 and 1')
        return v


MappingType = Literal["1-1", "1-m", "m-1", "1-0"]


class EntityMapping(BaseModel):
    """Mapping of a detected entity to service codes."""
    
    entity_id: str = Field(..., description="Entity being mapped")
    mapping_type: MappingType = Field(..., description="Type of mapping relationship")
    primary_codes: List[str] = Field(default_factory=list, description="Primary mapped service codes")
    alt_candidates: List[CandidateService] = Field(
        default_factory=list,
        description="Alternative candidate services (top-k)"
    )
    rationale: str = Field(..., description="Explanation of mapping decision")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Mapping confidence")
    
    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "ent_001",
                "mapping_type": "1-1",
                "primary_codes": ["KAR001"],
                "alt_candidates": [
                    {
                        "code": "KAR005",
                        "name": "Konsultacja kardiologiczna kontrolna",
                        "score": 0.72,
                        "reason": "Podobna nazwa, ale konsultacja kontrolna"
                    }
                ],
                "rationale": "Dokładne dopasowanie nazwy z wysoką pewnością",
                "confidence": 0.95
            }
        }
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError('Confidence must be between 0 and 1')
        return v
    
    @field_validator('mapping_type')
    @classmethod
    def validate_mapping_type(cls, v: str) -> str:
        valid_types = ["1-1", "1-m", "m-1", "1-0"]
        if v not in valid_types:
            raise ValueError(f'mapping_type must be one of {valid_types}')
        return v


# ============================================================================
# Variant Result Models
# ============================================================================

class VariantResult(BaseModel):
    """Mapping results for a single variant."""
    
    variant_id: str = Field(..., description="Variant identifier")
    core_codes: List[str] = Field(default_factory=list, description="Core service codes")
    prophylaxis_codes: List[str] = Field(
        default_factory=list,
        description="Prophylaxis program service codes"
    )
    mappings: List[EntityMapping] = Field(
        default_factory=list,
        description="Detailed entity mappings"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "variant_id": "variant_1",
                "core_codes": ["KAR001", "KAR002", "KAR003"],
                "prophylaxis_codes": [],
                "mappings": [
                    {
                        "entity_id": "ent_001",
                        "mapping_type": "1-1",
                        "primary_codes": ["KAR001"],
                        "alt_candidates": [],
                        "rationale": "Dokładne dopasowanie",
                        "confidence": 0.95
                    }
                ]
            }
        }


# ============================================================================
# Document Result Models
# ============================================================================

class DocumentResult(BaseModel):
    """Complete mapping result for a SIWZ document."""
    
    doc_id: str = Field(..., description="Document identifier")
    variants: List[VariantResult] = Field(default_factory=list, description="Results per variant")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (timestamps, versions, etc.)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "siwz_2025_kardiologia",
                "variants": [
                    {
                        "variant_id": "variant_1",
                        "core_codes": ["KAR001", "KAR002"],
                        "prophylaxis_codes": [],
                        "mappings": []
                    }
                ],
                "metadata": {
                    "processed_at": "2025-11-22T10:30:00",
                    "pipeline_version": "0.1.0",
                    "num_segments": 150,
                    "num_entities_detected": 45,
                    "num_variants": 2
                }
            }
        }


# ============================================================================
# Validation Helpers
# ============================================================================

class ValidationHelper:
    """Helper class for validating outputs."""
    
    @staticmethod
    def validate_document_result(data: Dict[str, Any]) -> DocumentResult:
        """
        Validate a document result dictionary.
        
        Args:
            data: Dictionary to validate
            
        Returns:
            Validated DocumentResult instance
            
        Raises:
            ValidationError: If data is invalid
        """
        return DocumentResult(**data)
    
    @staticmethod
    def validate_variant_result(data: Dict[str, Any]) -> VariantResult:
        """Validate a variant result dictionary."""
        return VariantResult(**data)
    
    @staticmethod
    def validate_entity_mapping(data: Dict[str, Any]) -> EntityMapping:
        """Validate an entity mapping dictionary."""
        return EntityMapping(**data)
    
    @staticmethod
    def validate_service_entry(data: Dict[str, Any]) -> ServiceEntry:
        """Validate a service entry dictionary."""
        return ServiceEntry(**data)
    
    @staticmethod
    def validate_pdf_segment(data: Dict[str, Any]) -> PdfSegment:
        """Validate a PDF segment dictionary."""
        return PdfSegment(**data)
    
    @staticmethod
    def validate_detected_entity(data: Dict[str, Any]) -> DetectedEntity:
        """Validate a detected entity dictionary."""
        return DetectedEntity(**data)
    
    @staticmethod
    def get_json_schema(model_class) -> Dict[str, Any]:
        """
        Get JSON schema for a model class.
        
        Args:
            model_class: Pydantic model class
            
        Returns:
            JSON schema dictionary
        """
        return model_class.model_json_schema()
    
    @staticmethod
    def validate_mapping_type_consistency(variant: VariantResult) -> List[str]:
        """
        Check consistency of mapping types within a variant.
        
        Args:
            variant: VariantResult to check
            
        Returns:
            List of warning messages (empty if all OK)
        """
        warnings = []
        
        # Check that core_codes matches mappings
        mapped_codes = set()
        for mapping in variant.mappings:
            mapped_codes.update(mapping.primary_codes)
        
        core_set = set(variant.core_codes)
        prophylaxis_set = set(variant.prophylaxis_codes)
        
        # Check for unmapped codes in core_codes
        unmapped_in_core = core_set - mapped_codes
        if unmapped_in_core:
            warnings.append(
                f"Core codes without mappings: {unmapped_in_core}"
            )
        
        # Check for codes in both core and prophylaxis
        overlap = core_set & prophylaxis_set
        if overlap:
            warnings.append(
                f"Codes in both core and prophylaxis: {overlap}"
            )
        
        # Check for 1-0 mappings with primary codes
        for mapping in variant.mappings:
            if mapping.mapping_type == "1-0" and mapping.primary_codes:
                warnings.append(
                    f"Mapping {mapping.entity_id} has type '1-0' but has primary_codes"
                )
        
        return warnings


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "ServiceEntry",
    "BBox",
    "PdfSegment",
    "DetectedEntity",
    "CandidateService",
    "MappingType",
    "EntityMapping",
    "VariantResult",
    "DocumentResult",
    "ValidationHelper",
]

