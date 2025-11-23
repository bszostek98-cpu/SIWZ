"""LLM integration components."""

from .client import LLMClient
from .prompts import PromptTemplates
from .gpt_client import GPTClient, FakeGPTClient, GPTClientProtocol
from .classify_segments import (
    classify_segment,
    classify_segments,
    SegmentClassification,
    VALID_LABELS
)

__all__ = [
    "LLMClient",
    "PromptTemplates",
    "GPTClient",
    "FakeGPTClient",
    "GPTClientProtocol",
    "classify_segment",
    "classify_segments",
    "SegmentClassification",
    "VALID_LABELS",
]
