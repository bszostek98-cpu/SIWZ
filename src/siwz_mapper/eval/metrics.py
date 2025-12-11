from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Set

import pandas as pd


def parse_codes_from_string(raw: str | None) -> Set[str]:
    """
    Zamienia string typu:
        "KOD1, KOD2; KOD3  KOD4"
    na zbiór:
        {"KOD1", "KOD2", "KOD3", "KOD4"}

    - separatorami mogą być: przecinek, średnik, spacja, nowa linia
    - puste elementy są ignorowane
    - kody są przycinane z whitespace'ów
    """
    if not raw:
        return set()

    # zamieniamy różne separatory na przecinek
    tmp = (
        raw.replace(";", ",")
        .replace("\n", ",")
        .replace("\t", ",")
    )
    parts = [p.strip() for p in tmp.split(",")]
    return {p for p in parts if p}


@dataclass
class PRF:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def compute_prf(true_codes: Set[str], pred_codes: Set[str]) -> PRF:
    """
    Liczy TP/FP/FN oraz precision/recall/F1 dla dwóch zbiorów kodów.
    """
    tp_set = true_codes & pred_codes
    fp_set = pred_codes - true_codes
    fn_set = true_codes - pred_codes

    tp = len(tp_set)
    fp = len(fp_set)
    fn = len(fn_set)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return PRF(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def load_gold_codes_from_excel(
    excel_path: str | Path,
    doc_id_col: str = "doc_id",
    codes_col: str = "gold_codes",
) -> Dict[str, Set[str]]:
    """
    Wczytuje plik Excel z referencyjnymi kodami per dokument.

    Oczekiwany format Excela (przykład):

        doc_id        | gold_codes
        --------------+------------------------------
        OPZ_001.pdf   | KOD1, KOD2; KOD3
        OPZ_002.pdf   | K01; K02 K03

    doc_id_col  – nazwa kolumny z identyfikatorem dokumentu
    codes_col   – nazwa kolumny z listą kodów (string)
    """
    excel_path = Path(excel_path)
    df = pd.read_excel(excel_path)

    gold: Dict[str, Set[str]] = {}

    for _, row in df.iterrows():
        doc_id = str(row[doc_id_col]).strip()
        codes_raw = str(row[codes_col]) if not pd.isna(row[codes_col]) else ""
        gold[doc_id] = parse_codes_from_string(codes_raw)

    return gold


def build_eval_table_wide(
    gold_by_doc: Dict[str, Set[str]],
    preds_by_strategy_and_doc: Dict[str, Dict[str, Set[str]]],
) -> pd.DataFrame:
    """
    Buduje tabelę "wide":

        doc_id | gold_codes | v0_codes | v0_precision | v0_recall | v0_f1 | v01_codes | ...

    gold_by_doc:
        { doc_id -> zbiór kodów referencyjnych }

    preds_by_strategy_and_doc:
        {
          "v0":    { doc_id -> zbiór kodów przewidzianych przez V0 },
          "v0_1":  { doc_id -> zbiór kodów przewidzianych przez V0.1 },
          "mas_v0_1": { ... },
          ...
        }

    Zwraca DataFrame, który możesz zapisać do CSV.
    """
    rows: list[dict] = []

    # lista strategii – nazwy kolumn będą oparte na kluczach
    strategies = list(preds_by_strategy_and_doc.keys())

    for doc_id, true_codes in gold_by_doc.items():
        row: dict = {
            "doc_id": doc_id,
            "gold_codes": ";".join(sorted(true_codes)),
        }

        for strat in strategies:
            pred_for_doc = preds_by_strategy_and_doc.get(strat, {}).get(doc_id, set())
            prf = compute_prf(true_codes, pred_for_doc)

            codes_str = ";".join(sorted(pred_for_doc))

            row[f"{strat}_codes"] = codes_str
            row[f"{strat}_tp"] = prf.tp
            row[f"{strat}_fp"] = prf.fp
            row[f"{strat}_fn"] = prf.fn
            row[f"{strat}_precision"] = prf.precision
            row[f"{strat}_recall"] = prf.recall
            row[f"{strat}_f1"] = prf.f1

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def save_eval_table_to_csv(df: pd.DataFrame, path: str | Path) -> None:
    """
    Zapisuje tabelę oceny do CSV (UTF-8).
    """
    path = Path(path)
    df.to_csv(path, index=False, encoding="utf-8")
