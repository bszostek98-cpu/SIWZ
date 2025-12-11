# src/siwz_mapper/eval/runner.py
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import time

from .manual_items import ManualDocVariantItems
from .strategies import ServiceItemMappingStrategy

@dataclass
class RunStats:
    processed_items: int
    elapsed_seconds: float
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def pretty(self) -> str:
        return (
            f"Processed items : {self.processed_items}\n"
            f"Elapsed time    : {self.elapsed_seconds:.2f} s\n"
            f"Prompt tokens   : {self.total_prompt_tokens}\n"
            f"Completion tok. : {self.total_completion_tokens}\n"
            f"Total tokens    : {self.total_tokens}\n"
            f"Est. cost (USD) : {self.estimated_cost_usd:.4f}\n"
        )


def run_strategy_on_manual_doc(
    manual_doc: ManualDocVariantItems,
    strategy: ServiceItemMappingStrategy,
    max_items: int | None = None,
    show_progress: bool = False,
) -> tuple[ManualDocVariantItems, RunStats]:
    """
    Runs given strategy on all items in a manual document.
    Modifies manual_doc in-place (fills predicted_services).

    :param max_items: if given, process only first N items across all variants.
    :param show_progress: if True, print simple progress info.
    :return: (updated_manual_doc, RunStats)
    """
    # >>> NOWE: przygotowanie strategii (np. budowa kontekstu dla V3)
    prepare = getattr(strategy, "prepare", None)
    if callable(prepare):
        prepare(manual_doc)
    # Spłaszczamy listę pozycji do jednej listy (variant_id, item)
    all_items: list[tuple[str, object]] = []
    for variant_id, items in manual_doc.variant_items_by_id.items():
        for item in items:
            all_items.append((variant_id, item))

    if max_items is not None:
        all_items = all_items[:max_items]

    total = len(all_items)
    start_time = time.perf_counter()

    for idx, (variant_id, item) in enumerate(all_items, start=1):
        result = strategy.map_item(item)
        item.predicted_services = result.candidates

        if show_progress:
            print(
                f"[{idx}/{total}] "
                f"variant={variant_id}, service_local_id={item.service_local_id}"
            )

    elapsed = time.perf_counter() - start_time

    # Spróbujmy odczytać statystyki z klienta LLM, jeśli istnieją
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    estimated_cost = 0.0

    client = getattr(strategy, "client", None)
    if client is not None and hasattr(client, "usage_stats"):
        usage = client.usage_stats
        total_prompt_tokens = usage.total_prompt_tokens
        total_completion_tokens = usage.total_completion_tokens
        total_tokens = usage.total_tokens

        # jeżeli masz helper estimate_cost_usd
        try:
            from siwz_mapper.llm.gpt_client import estimate_cost_usd
            estimated_cost = estimate_cost_usd(client.model, usage)
        except Exception:
            estimated_cost = 0.0

    stats = RunStats(
        processed_items=total,
        elapsed_seconds=elapsed,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost,
    )

    return manual_doc, stats



def run_strategy_on_json_path(
    json_path: str | Path,
    strategy: ServiceItemMappingStrategy,
    output_path: str | Path | None = None,
    max_items: int | None = None,
    show_progress: bool = False,
) -> tuple[ManualDocVariantItems, RunStats]:
    """
    Convenience helper:
    - loads JSON into ManualDocVariantItems,
    - runs strategy,
    - optionally saves updated JSON with predictions.
    - returns (updated_doc, RunStats)
    """
    manual_doc = ManualDocVariantItems.load(json_path)
    updated_doc, stats = run_strategy_on_manual_doc(
        manual_doc=manual_doc,
        strategy=strategy,
        max_items=max_items,
        show_progress=show_progress,
    )

    if output_path is not None:
        updated_doc.save(output_path)

    return updated_doc, stats

