"""Configuration models."""

from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMConfig(BaseModel):
    """LLM API configuration."""
    
    provider: str = Field("openai", description="LLM provider (openai, azure, etc.)")
    model: str = Field("gpt-4o", description="Model name")
    api_key: Optional[str] = Field(None, description="API key (can be set via env)")
    temperature: float = Field(0.1, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(4000, description="Max tokens per response")
    timeout: int = Field(60, description="Request timeout in seconds")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.1,
                "max_tokens": 4000,
                "timeout": 60
            }
        }
    }


class PipelineConfig(BaseModel):
    """Pipeline execution configuration."""
    
    top_k_candidates: int = Field(5, ge=1, description="Number of alternative candidates to return")
    min_confidence_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum confidence for auto-mapping")
    extract_bboxes: bool = Field(True, description="Whether to extract bounding boxes from PDF")
    parallel_llm_calls: bool = Field(False, description="Whether to parallelize LLM calls")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "top_k_candidates": 5,
                "min_confidence_threshold": 0.5,
                "extract_bboxes": True,
                "parallel_llm_calls": False
            }
        }
    }


class Config(BaseSettings):
    """Main application configuration."""
    
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    
    # File paths
    services_dict_path: Optional[str] = Field(None, description="Path to services dictionary JSON")
    output_dir: str = Field("output", description="Output directory for results")
    
    model_config = {
        "env_prefix": "SIWZ_",
        "env_nested_delimiter": "__",
        "json_schema_extra": {
            "example": {
                "llm": {"provider": "openai", "model": "gpt-4o"},
                "pipeline": {"top_k_candidates": 5},
                "services_dict_path": "data/services.json",
                "output_dir": "output"
            }
        }
    }

