#!/usr/bin/env python
from __future__ import annotations

"""
Eval strategii mapowania kodów na zbiorze dokumentów (wariantów).

Wejście:
- Excel ze słownikiem kodów (Kod, Kategoria, Podkategoria, Usługa medyczna)
- Excel ze złotem (doc_id, gold_codes)
- Folder z plikami .txt (każdy plik = tekst jednego wariantu; doc_id = nazwa pliku bez rozszerzenia)

Wyjście:
- CSV z wynikami:
    doc_id
    gold_codes
    <strategy>_codes, <strategy>_tp, <strategy>_fp, <strategy>_fn,
    <strategy>_precision, <strategy>_recall, <strategy>_f1
"""

import argparse
from pathlib import Path
from typing import Dict, Set, List

import pandas as pd

from siwz_mapper.eval.codebook import load_service_codes_from_excel
from siwz_mapper.eval.strategies import (
    VariantWholeTextMappingStrategyV0,
    VariantWholeTextMappingStrategyV01,
    VariantWholeTextMappingStrategyV03,
    MASVariantMappingStrategyV1,
    MASVariantMappingStrategyV2,
)
from siwz_mapper.llm.gpt_client import GPTClient, estimate_cost_usd


# ---------- Helpers: wczytanie danych ----------

def read_variant_texts_from_dir(variants_dir: Path) -> Dict[str, str]:
    """
    Czyta wszystkie pliki .txt z katalogu i zwraca:
        { doc_id (stem) -> tekst }
    """
    variants_dir = variants_dir.resolve()
    texts: Dict[str, str] = {}

    for path in variants_dir.glob("*.txt"):
        doc_id = path.stem
        text = path.read_text(encoding="utf-8")
        texts[doc_id] = text

    return texts


def parse_codes_string(s: str) -> Set[str]:
    """
    Parsuje string z kodami (rozdzielone przecinkami, średnikami lub spacjami)
    do zbioru kodów.
    Np. "K01, K02;K03  K05" -> {"K01","K02","K03","K05"}
    """
    if s is None:
        return set()
    for sep in [",", ";", "|"]:
        s = s.replace(sep, " ")
    parts = [p.strip() for p in s.split() if p.strip()]
    return set(parts)


def load_gold_codes_from_excel(
    path: Path,
    doc_id_col: str = "doc_id",
    codes_col: str = "gold_codes",
) -> Dict[str, Set[str]]:
    """
    Wczytuje złote kody z Excela.
    Zakładamy kolumny:
      - doc_id_col (np. "doc_id")
      - codes_col  (np. "gold_codes") – string z listą kodów.
    """
    df = pd.read_excel(path)
    if doc_id_col not in df.columns:
        raise ValueError(f"Gold Excel missing column: {doc_id_col}")
    if codes_col not in df.columns:
        raise ValueError(f"Gold Excel missing column: {codes_col}")

    gold_by_doc: Dict[str, Set[str]] = {}
    for _, row in df.iterrows():
        doc_id = str(row[doc_id_col]).strip()
        codes_str = str(row[codes_col]) if not pd.isna(row[codes_col]) else ""
        gold_by_doc[doc_id] = parse_codes_string(codes_str)
    return gold_by_doc


# ---------- Helpers: metryki ----------

def compute_counts_and_metrics(gold: Set[str], pred: Set[str]) -> Dict[str, float]:
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def build_eval_table_wide(
    gold_by_doc: Dict[str, Set[str]],
    preds_by_strategy_and_doc: Dict[str, Dict[str, Set[str]]],
) -> pd.DataFrame:
    """
    Buduje szeroką tabelę:
      doc_id, gold_codes,
      <strategy>_codes, <strategy>_tp, <strategy>_fp, <strategy>_fn,
      <strategy>_precision, <strategy>_recall, <strategy>_f1
    """
    rows: List[Dict[str, object]] = []

    strategies = sorted(preds_by_strategy_and_doc.keys())

    for doc_id, gold_codes in gold_by_doc.items():
        row: Dict[str, object] = {}
        row["doc_id"] = doc_id
        row["gold_codes"] = " ".join(sorted(gold_codes))

        for strat in strategies:
            preds_for_doc = preds_by_strategy_and_doc.get(strat, {}).get(doc_id, set())
            metrics = compute_counts_and_metrics(gold_codes, preds_for_doc)
            codes_str = " ".join(sorted(preds_for_doc))

            prefix = strat
            row[f"{prefix}_codes"] = codes_str
            row[f"{prefix}_tp"] = metrics["tp"]
            row[f"{prefix}_fp"] = metrics["fp"]
            row[f"{prefix}_fn"] = metrics["fn"]
            row[f"{prefix}_precision"] = metrics["precision"]
            row[f"{prefix}_recall"] = metrics["recall"]
            row[f"{prefix}_f1"] = metrics["f1"]

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


# ---------- Główna logika: odpalanie strategii ----------

def run_all_strategies_for_docs(
    texts_by_doc: Dict[str, str],
    service_codes,
    model: str,
    temperature: float,
    timeout: float | None,
) -> Dict[str, Dict[str, Set[str]]]:
    """
    Odpala wszystkie strategie na wszystkich dokumentach.

    Zwraca:
        {
          "v0":     { doc_id -> set(kodów) },
          "v0_1":   { doc_id -> set(kodów) },
          "v0_3":   { doc_id -> set(kodów) },
          "mas_v1": { doc_id -> set(kodów) },
          "mas_v2": { doc_id -> set(kodów) },
        }
    """
    client = GPTClient(
        model=model,
        temperature=temperature,
        timeout=timeout,
    )

    # --- Inicjalizacja strategii ---

    # V0 – cały tekst wariantu -> lista kodów
    strat_v0 = VariantWholeTextMappingStrategyV0(
        client=client,
        service_codes=service_codes,
        batch_size_codes=150,         # możesz zmienić
        debug_log_prompts=False,
    )

    # V0.1 – chunk -> kody, końcowo union kodów
    strat_v01 = VariantWholeTextMappingStrategyV01(
        client=client,
        service_codes=service_codes,
        debug_log_prompts=False,
    )

    # V0.3 – chunk -> kody, num_code_batches (liczba batchy kodów)
    strat_v03 = VariantWholeTextMappingStrategyV03(
        client=client,
        service_codes=service_codes,
        num_code_batches=3,
        debug_log_prompts=False,
    )

    # MAS v1 – router kategorii (bez limitu kategorii), union kodów
    strat_mas_v1 = MASVariantMappingStrategyV1(
        client=client,
        service_codes=service_codes,
        max_chunk_chars=800,
        router_max_categories_per_chunk=None,   # brak twardego limitu
        router_examples_per_category=3,
        debug_log_prompts_router=False,
        debug_log_prompts_agents=False,
    )

    # MAS v2 – planner (variant-level), union kodów
    strat_mas_v2 = MASVariantMappingStrategyV2(
        client=client,
        service_codes=service_codes,
        planner_max_examples_per_category=5,
        planner_max_examples_per_subcategory=3,
        debug_log_prompts_planner=False,
        debug_log_prompts_agents=False,
    )

    strategy_objects = {
        "v0": strat_v0,
        "v0_1": strat_v01,
        "v0_3": strat_v03,
        "mas_v1": strat_mas_v1,
        "mas_v2": strat_mas_v2,
    }

    preds_by_strategy_and_doc: Dict[str, Dict[str, Set[str]]] = {
        key: {} for key in strategy_objects.keys()
    }

    doc_ids = list(texts_by_doc.keys())
    total_docs = len(doc_ids)

    for idx, doc_id in enumerate(doc_ids, start=1):
        text = texts_by_doc[doc_id]
        print(f"\n=== Dokument {idx}/{total_docs}: {doc_id} (len={len(text)} znaków) ===")

        for strat_key, strat in strategy_objects.items():
            print(f"[{strat_key}] Running {getattr(strat, 'name', strat_key)}...")
            try:
                # wszystkie pięć strategii tutaj zwraca ServiceItemMappingResult
                res = strat.map_variant(text)
                codes = set(res.predicted_codes)

                preds_by_strategy_and_doc[strat_key][doc_id] = codes
                print(f"[{strat_key}]  -> {len(codes)} kodów")
            except Exception as e:
                print(f"[{strat_key}]  BŁĄD: {e}")
                preds_by_strategy_and_doc[strat_key][doc_id] = set()

    # Podsumowanie tokenów / kosztu
    usage = client.usage_stats
    total_prompt_tokens = usage.total_prompt_tokens
    total_completion_tokens = usage.total_completion_tokens

    try:
        total_cost = estimate_cost_usd(model, usage)
    except Exception:
        total_cost = 0.0

    print("\n=== LLM usage summary ===")
    print("Prompt tokens    :", total_prompt_tokens)
    print("Completion tokens:", total_completion_tokens)
    print("Total tokens     :", total_prompt_tokens + total_completion_tokens)
    print(f"Estimated cost   : {total_cost:.4f} USD (model={model})")

    if hasattr(client, "print_debug_report"):
        print("\n(Jeśli chcesz pełny raport promptów, wywołaj client.print_debug_report() w notatniku.)")

    return preds_by_strategy_and_doc


# ---------- CLI ----------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark strategii mapowania kodów na zbiorze dokumentów."
    )

    parser.add_argument(
        "--codes-excel",
        type=Path,
        required=True,
        help="Ścieżka do Excela ze słownikiem kodów (Kod, Kategoria, Podkategoria, Usługa medyczna)",
    )
    parser.add_argument(
        "--gold-excel",
        type=Path,
        required=True,
        help="Ścieżka do Excela ze złotem (doc_id, gold_codes)",
    )
    parser.add_argument(
        "--variants-dir",
        type=Path,
        required=True,
        help="Katalog z plikami .txt – każdy plik to tekst jednego wariantu; nazwa pliku = doc_id",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        required=True,
        help="Ścieżka do pliku CSV z wynikami",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5-mini",
        help="Nazwa modelu OpenAI (domyślnie: gpt-5-mini)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperatura próbkowania (domyślnie: 0.0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Timeout w sekundach dla zapytań do LLM (domyślnie: None – domyślny timeout klienta OpenAI)",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    codes_excel_path: Path = args.codes_excel
    gold_excel_path: Path = args.gold_excel
    variants_dir: Path = args.variants_dir
    output_csv_path: Path = args.output_csv

    model: str = args.model
    temperature: float = args.temperature
    timeout: float | None = args.timeout

    print("=== Konfiguracja ===")
    print("Słownik kodów Excel :", codes_excel_path)
    print("Złoto Excel         :", gold_excel_path)
    print("Folder wariantów    :", variants_dir)
    print("Output CSV          :", output_csv_path)
    print("Model               :", model)
    print("Temperature         :", temperature)
    print("Timeout             :", timeout)

    # 1. Wczytanie słownika kodów
    print("\n[1/4] Wczytuję słownik kodów z Excela...")
    service_codes = load_service_codes_from_excel(codes_excel_path)
    print(f"Załadowano {len(service_codes)} kodów.")

    # 2. Wczytanie złota
    print("\n[2/4] Wczytuję złote kody per dokument...")
    gold_by_doc = load_gold_codes_from_excel(gold_excel_path)
    print(f"Załadowano złoto dla {len(gold_by_doc)} dokumentów.")

    # 3. Wczytanie tekstów wariantów
    print("\n[3/4] Wczytuję teksty wariantów z katalogu...")
    texts_by_doc = read_variant_texts_from_dir(variants_dir)
    print(f"Znaleziono {len(texts_by_doc)} plików .txt z wariantami.")

    missing_docs = [doc_id for doc_id in gold_by_doc.keys() if doc_id not in texts_by_doc]
    if missing_docs:
        print("\n[UWAGA] Następujące doc_id są w złocie, ale brak ich pliku .txt w katalogu:")
        for d in missing_docs:
            print("  -", d)
        print("Zostaną pominięte w ewaluacji.\n")

    common_doc_ids = set(texts_by_doc.keys()) & set(gold_by_doc.keys())
    if not common_doc_ids:
        print("Brak wspólnych doc_id między złotem a plikami .txt. Kończę.")
        return

    texts_by_doc_filtered = {doc_id: texts_by_doc[doc_id] for doc_id in common_doc_ids}
    gold_by_doc_filtered = {doc_id: gold_by_doc[doc_id] for doc_id in common_doc_ids}

    print(f"\nDo ewaluacji użyję {len(common_doc_ids)} dokumentów (przecięcie złota i txt).")

    # 4. Odpalenie wszystkich strategii
    print("\n[4/4] Uruchamiam strategie na wszystkich dokumentach...")
    preds_by_strategy_and_doc = run_all_strategies_for_docs(
        texts_by_doc=texts_by_doc_filtered,
        service_codes=service_codes,
        model=model,
        temperature=temperature,
        timeout=timeout,
    )

    print("\nBuduję tabelę z metrykami...")
    df_eval = build_eval_table_wide(
        gold_by_doc=gold_by_doc_filtered,
        preds_by_strategy_and_doc=preds_by_strategy_and_doc,
    )

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    df_eval.to_csv(output_csv_path, index=False, encoding="utf-8-sig")

    print("\n=== GOTOWE ===")
    print("Zapisano wyniki ewaluacji do:", output_csv_path)


if __name__ == "__main__":
    main()
