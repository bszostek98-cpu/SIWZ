"""
Build manual VariantServiceItem JSON from a hand-edited CSV.

Usage (from repo root):

    python -m scripts.build_manual_variant_items ^
        --input C:\Programowanie\SIWZ\data\manual\manual_services.csv ^
        --pdf C:\Programowanie\SIWZ\data\examples\OPZ_wybrane_strony.pdf ^
        --output C:\Programowanie\SIWZ\data\manual\OPZ_manual_variant_items.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, DefaultDict

from siwz_mapper.models import VariantServiceItem


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    v = str(value).strip().lower()
    if v in ("1", "true", "t", "yes", "y", "tak"):
        return True
    if v in ("0", "false", "f", "no", "n", "nie", ""):
        return False
    # cokolwiek dziwnego → ostrożnie False, ale logujemy tekst
    print(f"[WARN] Nieznana wartość bool '{value}', traktuję jako False.")
    return False


def load_manual_csv(path: Path, delimiter: str = ";") -> Dict[str, List[VariantServiceItem]]:
    """
    Wczytaj CSV z ręcznie opisanymi usługami i zwróć:
        { variant_id: [VariantServiceItem, ...], ... }
    """
    variant_items: DefaultDict[str, List[VariantServiceItem]] = defaultdict(list)

    # pamiętamy ostatni nagłówek dla (variant_id, block_no), żeby propagować
    last_heading: Dict[tuple[str, str], str] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        required_cols = ["variant_id", "block_no", "service_text", "page"]
        for col in required_cols:
            if col not in reader.fieldnames:
                raise ValueError(f"Brak wymaganej kolumny '{col}' w CSV (mam: {reader.fieldnames})")

        for row_idx, row in enumerate(reader, start=2):  # start=2, bo 1 to nagłówek
            variant_id = (row.get("variant_id") or "").strip() or "V1"
            block_no = (row.get("block_no") or "").strip()
            if not block_no:
                raise ValueError(f"Brak block_no w wierszu {row_idx}")

            key = (variant_id, block_no)

            raw_heading = (row.get("block_heading_raw") or "").strip()
            if raw_heading:
                last_heading[key] = raw_heading
            heading = raw_heading or last_heading.get(key)

            block_category = (row.get("block_category") or "").strip().lower() or "other"

            service_local_id = (row.get("service_local_id") or "").strip() or None
            service_text = (row.get("service_text") or "").strip()
            if not service_text:
                raise ValueError(f"Brak service_text w wierszu {row_idx}")

            page_str = (row.get("page") or "").strip()
            if not page_str:
                raise ValueError(f"Brak page w wierszu {row_idx}")
            try:
                page = int(page_str)
            except ValueError:
                raise ValueError(f"Niepoprawny page '{page_str}' w wierszu {row_idx}")

            source_segment_id = (row.get("source_segment_id") or "").strip()
            if not source_segment_id:
                # fallback: manual_p{page}_{local_id or block_no}_rowIdx
                suffix = service_local_id or block_no
                source_segment_id = f"manual_p{page}_{suffix}_r{row_idx}"

            # extra: próbujemy sparsować JSON, jeśli coś jest
            extra_raw = (row.get("extra") or "").strip()
            extra: Dict[str, Any] = {}
            if extra_raw:
                try:
                    extra = json.loads(extra_raw)
                    if not isinstance(extra, dict):
                        extra = {"raw_extra": extra_raw}
                except json.JSONDecodeError:
                    print(f"[WARN] Nie udało się sparsować JSON w kolumnie 'extra' (wiersz {row_idx}), zapisuję jako 'raw_extra'.")
                    extra = {"raw_extra": extra_raw}

            # dodajemy info, że to dane ręczne
            extra.setdefault("from_manual", True)
            if heading and "block_heading_raw" not in extra:
                extra["block_heading_raw"] = heading

            is_prophylaxis = _parse_bool(row.get("is_prophylaxis"))
            is_occupational_medicine = _parse_bool(row.get("is_occupational_medicine"))
            is_telemedicine = _parse_bool(row.get("is_telemedicine"))
            is_pricing_only = _parse_bool(row.get("is_pricing_only"))

            item = VariantServiceItem(
                variant_id=variant_id,
                block_no=block_no,
                block_heading_raw=heading,
                block_category=block_category,
                service_local_id=service_local_id,
                service_text=service_text,
                is_prophylaxis=is_prophylaxis,
                is_occupational_medicine=is_occupational_medicine,
                is_telemedicine=is_telemedicine,
                is_pricing_only=is_pricing_only,
                source_segment_id=source_segment_id,
                page=page,
                extra=extra,
            )

            variant_items[variant_id].append(item)

    return dict(variant_items)


def save_variant_items_json(
    variant_items_by_id: Dict[str, List[VariantServiceItem]],
    pdf_path: str,
    output_path: Path,
) -> None:
    """
    Zapisz warianty do JSON-a w formacie:

    {
      "doc_id": "nazwa_pliku_bez_ext",
      "pdf_path": "...",
      "variant_items_by_id": {
        "V1": [ {...}, ...],
        ...
      }
    }
    """
    pdf = Path(pdf_path)
    doc_id = pdf.stem

    data = {
        "doc_id": doc_id,
        "pdf_path": str(pdf),
        "variant_items_by_id": {
            vid: [it.model_dump(mode="json") for it in items]
            for vid, items in variant_items_by_id.items()
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zapisano JSON: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manual VariantServiceItem JSON from CSV.")
    parser.add_argument("--input", required=True, help="Ścieżka do CSV z ręcznie opisanymi usługami.")
    parser.add_argument("--pdf", required=True, help="Ścieżka do oryginalnego PDF (dla doc_id/pdf_path).")
    parser.add_argument("--output", required=True, help="Ścieżka wyjściowa JSON.")
    parser.add_argument("--delimiter", default=";", help="Separator w CSV (domyślnie ';').")

    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    variant_items_by_id = load_manual_csv(input_path, delimiter=args.delimiter)
    print("Wczytane warianty i liczby usług:")
    for vid, items in variant_items_by_id.items():
        print(f"  {vid}: {len(items)} usług")

    save_variant_items_json(variant_items_by_id, pdf_path=args.pdf, output_path=output_path)


if __name__ == "__main__":
    main()
