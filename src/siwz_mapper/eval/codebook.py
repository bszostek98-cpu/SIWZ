# src/siwz_mapper/eval/codebook.py
from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd
from pydantic import BaseModel


class ServiceCode(BaseModel):
    """
    Single service code definition loaded from an Excel file.
    """
    code: str
    category: str
    subcategory: str
    name: str

    def as_prompt_line(self) -> str:
        """
        Human-readable single-line representation used in LLM prompt.
        """
        cat = self.category or "-"
        sub = self.subcategory or "-"
        return f"{self.code}: [{cat} / {sub}] {self.name}"


def load_service_codes_from_excel(path: str | Path) -> List[ServiceCode]:
    """
    Load service codes from an Excel file with columns:
    'Kod', 'Kategoria', 'Podkategoria', 'Usługa medyczna'.
    """
    path = Path(path)
    df = pd.read_excel(path)

    # Normalize column names (just in case of minor differences)
    rename_map = {
        "Kod": "code",
        "Kategoria": "category",
        "Podkategoria": "subcategory",
        "Usługa medyczna": "name",
    }
    df = df.rename(columns=rename_map)

    required = ["code", "category", "subcategory", "name"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in {path}")

    codes: list[ServiceCode] = []
    for _, row in df.iterrows():
        code = str(row["code"]).strip()
        if not code:
            continue

        category = str(row.get("category", "") or "").strip()
        subcategory = str(row.get("subcategory", "") or "").strip()
        name = str(row.get("name", "") or "").strip()

        codes.append(
            ServiceCode(
                code=code,
                category=category,
                subcategory=subcategory,
                name=name,
            )
        )

    # Optional: deduplicate by code
    unique_by_code: dict[str, ServiceCode] = {}
    for c in codes:
        unique_by_code[c.code] = c

    return list(unique_by_code.values())
