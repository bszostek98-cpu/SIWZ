# src/siwz_mapper/eval/manual_items.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import json 
from pydantic import BaseModel


class ServiceCandidate(BaseModel):
    """
    Single candidate service for a given item (one-to-many mapping).
    """
    code: str
    label: Optional[str] = None      # Human-readable label (from ServiceEntry)
    score: Optional[float] = None    # Confidence / similarity
    source: Optional[str] = None     # e.g. "heuristic", "single_llm", "mas", "vector_llm"
    rank: Optional[int] = None       # 1 = best


class VariantItemExtra(BaseModel):
    from_manual: bool = False
    block_heading_raw: Optional[str] = None


class VariantItem(BaseModel):
    """
    One manually defined 'service item' inside a variant.
    This matches your JSON structure.
    """
    variant_id: str
    block_no: str
    block_heading_raw: Optional[str] = None
    block_category: str
    service_local_id: str
    service_text: str

    is_prophylaxis: bool = False
    is_occupational_medicine: bool = False
    is_telemedicine: bool = False
    is_pricing_only: bool = False

    source_segment_id: Optional[str] = None
    page: Optional[int] = None
    extra: Optional[VariantItemExtra] = None

    # GOLD labels - optional (you will fill them later)
    expected_codes: Optional[List[str]] = None

    # Predicted services per item (one-to-many), filled by mapping strategies
    predicted_services: Optional[List[ServiceCandidate]] = None

    # Final codes selected/confirmed by human in GUI
    final_codes: Optional[List[str]] = None


class ManualDocVariantItems(BaseModel):
    """
    Container for all items for a single document.
    This matches the top-level JSON structure.
    """
    doc_id: str
    pdf_path: str
    variant_items_by_id: Dict[str, List[VariantItem]]

    @staticmethod
    def load(path: str | Path) -> "ManualDocVariantItems":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return ManualDocVariantItems.model_validate(data)

    def save(self, path: str | Path) -> None:
        """
        Save to JSON file with nice indentation and UTF-8 (Polish chars).
        Compatible with Pydantic v2.
        """
        path = Path(path)
        data = self.model_dump()  # python-serializable dict
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(json_str, encoding="utf-8")