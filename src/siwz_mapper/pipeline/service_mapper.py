"""
ServiceMapper (stub).

Compatibility layer for tests.
Real mapping will be implemented later.
"""

from typing import List, Optional
import logging

from ..llm.client import LLMClient
from ..models import ServiceEntry, DetectedEntity, EntityMapping, VariantResult

logger = logging.getLogger(__name__)



class ServiceMapper:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        services: Optional[List[ServiceEntry]] = None,
        top_k: int = 10,
    ):
        self.llm_client = llm_client
        self.services = services or []
        self.top_k = top_k
        self.service_index = {s.code: s for s in self.services}
    def map_entities(
        self,
        entities: List[DetectedEntity],
    ) -> List[EntityMapping]:
        # STUB: no mapping yet
        return []

    def map_variants(
        self,
        variants: List[VariantResult],
    ) -> List[VariantResult]:
        # STUB: return variants unchanged
        return variants
