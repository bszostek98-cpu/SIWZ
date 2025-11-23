from typing import List, Optional

from ..models import PdfSegment
from ..llm.classify_segments import SegmentClassification
from ..llm.client import LLMClient
from .variant_aggregator import VariantAggregator, VariantGroup


class VariantDetector:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
        self.aggregator = VariantAggregator()

    def detect(self, classifications: List[SegmentClassification]) -> List[VariantGroup]:
        # tworzymy „puste” segmenty tylko po to, żeby użyć istniejącej logiki agregatora
        dummy_segments = [
            PdfSegment(segment_id=c.segment_id, text="", page=1)
            for c in classifications
        ]
        _, variant_groups = self.aggregator.aggregate(dummy_segments, classifications)
        return variant_groups
