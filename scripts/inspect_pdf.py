"""
Inspect a SIWZ PDF end-to-end (block-first version).

Kroki:
1) io.load_pdf -> surowe bloki z PDF (PdfSegment)
2) BlockSegmenter.group_blocks -> semantic blocks (SemanticBlock)
3) classify_blocks (GPT lub FakeGPTClient) -> BlockClassification
4) project_block_classes_to_segments -> SegmentClassification per PdfSegment
5) VariantAggregator -> warianty

Wynik:
- krótki podgląd w konsoli
- pełny raport w JSON obok PDF:
  "<nazwa_pliku>.full_report.json"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from siwz_mapper.io import load_pdf
from siwz_mapper.models import PdfSegment, SemanticBlock, BlockClassification
from siwz_mapper.preprocess.block_segmenter import BlockSegmenter
from siwz_mapper.llm.classify_segments import SegmentClassification
from siwz_mapper.llm.block_classifier import (
    classify_blocks,
    project_block_classes_to_segments,
)
from siwz_mapper.llm.gpt_client import GPTClient, FakeGPTClient
from siwz_mapper.pipeline.variant_aggregator import (
    VariantAggregator,
    VariantGroup,
)

logger = logging.getLogger(__name__)


def run_inspection(pdf_path: Path, use_real_gpt: bool = False) -> Dict[str, Any]:
    """
    Uruchom pełny pipeline na pojedynczym PDF-ie w trybie block-first.

    Zwraca słownik gotowy do zapisania jako JSON:
    {
      "pdf": ...,
      "use_real_gpt": true/false,
      "num_blocks_raw": ...,
      "num_semantic_blocks": ...,
      "num_segments_for_aggregation": ...,
      "label_counts": {...},
      "variants": [...],
      "blocks": [...],                # raw PdfSegment
      "semantic_blocks": [...],       # SemanticBlock
      "block_classifications": [...],
      "segment_classifications": [...],
      "segments_with_variant_id": [...]
    }
    """
    # 1) Surowe bloki z PDF (PdfSegment)
    blocks: List[PdfSegment] = load_pdf(pdf_path)
    logger.info("Loaded %d raw blocks from %s", len(blocks), pdf_path)

    # 2) Grupowanie w semantic blocks
    block_segmenter = BlockSegmenter()
    semantic_blocks: List[SemanticBlock] = block_segmenter.group_blocks(blocks)
    logger.info("Grouped into %d semantic blocks", len(semantic_blocks))

    # Spłaszczona lista segmentów w kolejności dla agregatora
    segments_for_aggregation: List[PdfSegment] = [
        seg for blk in semantic_blocks for seg in blk.segments
    ]

    # 3) Wybór klienta GPT: prawdziwy albo Fake
    if use_real_gpt:
        try:
            client = GPTClient(model="gpt-4o-mini", temperature=0.0)
            real_used = True
            logger.info("Using REAL GPTClient (gpt-4o-mini)")
        except Exception as e:
            logger.warning(
                "Failed to initialize GPTClient (%s), falling back to FakeGPTClient", e
            )
            client = FakeGPTClient()
            real_used = False
    else:
        client = FakeGPTClient()
        real_used = False
        logger.info("Using FakeGPTClient (no real API calls)")

    # 4) Klasyfikacja bloków
    block_classifications: List[BlockClassification] = classify_blocks(
        semantic_blocks,
        client=client,
        show_progress=False,
    )

    # 5) Projekcja na klasyfikacje per-segment (dla VariantAggregator)
    segment_classifications: List[SegmentClassification] = (
        project_block_classes_to_segments(semantic_blocks, block_classifications)
    )

    # policz etykiety po stronie segmentów
    label_counts: Dict[str, int] = {}
    for cls in segment_classifications:
        label_counts[cls.label] = label_counts.get(cls.label, 0) + 1

    # 6) Agregacja w warianty
    aggregator = VariantAggregator()
    updated_segments, variant_groups = aggregator.aggregate(
        segments_for_aggregation,
        segment_classifications,
    )

    # 7) Zbuduj czytelne podsumowanie wariantów
    variants_summary: List[Dict[str, Any]] = []
    for vg in variant_groups:
        variants_summary.append(
            {
                "variant_id": vg.variant_id,
                "has_header": vg.header_segment is not None,
                "num_body": len(vg.body_segments),
                "num_prophylaxis": len(vg.prophylaxis_segments),
                "header_preview": (
                    vg.header_segment.text[:200] if vg.header_segment else None
                ),
            }
        )

    # 8) Złóż pełny raport
    report: Dict[str, Any] = {
        "pdf": str(pdf_path),
        "use_real_gpt": real_used,
        "num_blocks_raw": len(blocks),
        "num_semantic_blocks": len(semantic_blocks),
        "num_segments_for_aggregation": len(segments_for_aggregation),
        "label_counts": label_counts,
        "variants": variants_summary,
        # pełne dane do debugowania:
        "blocks": [b.model_dump() for b in blocks],
        "semantic_blocks": [b.model_dump() for b in semantic_blocks],
        "block_classifications": [c.model_dump() for c in block_classifications],
        "segment_classifications": [c.model_dump() for c in segment_classifications],
        # zaktualizowane segmenty z variant_id:
        "segments_with_variant_id": [s.model_dump() for s in updated_segments],
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pełna inspekcja pojedynczego PDF-a SIWZ (block-first)."
    )
    parser.add_argument("pdf", type=str, help="Ścieżka do pliku PDF")
    parser.add_argument(
        "--real",
        action="store_true",
        help=(
            "Użyj prawdziwego GPT (wymaga OPENAI_API_KEY); "
            "bez tej flagi używany jest FakeGPTClient."
        ),
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)

    report = run_inspection(pdf_path, use_real_gpt=args.real)

    # krótki podgląd w konsoli
    print(f"PDF: {report['pdf']}")
    print(f"Use real GPT: {report['use_real_gpt']}")
    print(f"Raw blocks: {report['num_blocks_raw']}")
    print(f"Semantic blocks: {report['num_semantic_blocks']}")
    print(f"Segments for aggregation: {report['num_segments_for_aggregation']}")
    print(f"Label counts (segment level): {report['label_counts']}")
    print("Variants:")
    for v in report["variants"]:
        print(
            f"  {v['variant_id']}: header={v['has_header']}, "
            f"body={v['num_body']}, prophylaxis={v['num_prophylaxis']}"
        )

    # zapis pełnego raportu
    out_path = pdf_path.with_suffix(pdf_path.suffix + ".full_report.json")
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote full report: {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
