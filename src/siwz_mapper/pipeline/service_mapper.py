"""
ServiceMapper (stub).

Compatibility layer for pipeline/tests.
Real mapping will be implemented later.
"""

from typing import List, Optional
import logging

from ..models import ServiceEntry, DetectedEntity, EntityMapping, VariantResult

logger = logging.getLogger(__name__)


class ServiceMapper:
    """
    Stub for service mapping.

    Docelowo:
    - map_entities: DetectedEntity -> EntityMapping (top_k kandydatów)
    - map_variants: uzupełnia VariantResult o core_codes/prophylaxis_codes/mappings
    """

    def __init__(
        self,
        services: Optional[List[ServiceEntry]] = None,
        top_k: int = 10,
    ):
        self.services = services or []
        self.top_k = top_k

    @property
    def service_index(self):
        """Słownik code -> ServiceEntry, liczony na bieżąco."""
        return {s.code: s for s in self.services}

    def map_entities(self, entities: List[DetectedEntity]) -> List[EntityMapping]:
        # STUB: brak mapowania
        return []

    def map_variants(self, variants: List[VariantResult]) -> List[VariantResult]:
        # STUB: zwracamy warianty bez zmian
        return variants
