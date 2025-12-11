Jasne, to teraz dam Ci **cały zaktualizowany plik** `siwz_pipeline_context.md` do wklejenia – już:

* **bez** FakegptClient w pipeline (tylko `gptClient`),
* z doprecyzowaniem, że `gptClient` jest w module `siwz_mapper.llm.gpt_client`,
* z poprawionym opisem `inspect_pdf.py` (bez `--real`, bez `use_real_gpt` w raporcie).

Wklej to jako całość zamiast starej wersji:

````markdown
---
format:
  html:
    theme: darkly
---
Poniżej masz „czysty” plik `siwz_pipeline_context.md`, oparty **tylko** na realnym kodzie

# SIWZ Mapper – Pipeline Context

This document describes the **current state** of the SIWZ Mapper pipeline based on the existing code in:

- `src/siwz_mapper/pipeline/`
- `src/siwz_mapper/io/pdf_loader.py`
- `src/siwz_mapper/preprocess/segmenter.py`
- `src/siwz_mapper/pipeline/variant_aggregator.py`
- `src/siwz_mapper/pipeline/service_mapper.py`
- `scripts/inspect_pdf.py`

and outlines the main **extension points** for future development.

---

## 0. Scope

This document is meant as a **living context file**. It should:

- capture how data flows through the current pipeline,
- highlight the responsibilities of each module,
- explicitly list current limitations,
- point to realistic next steps (where to plug in new logic).

The goal is to make it easy to open this project in a few months and immediately understand:
> *Where do I change PDF parsing / segmentation / LLM classification / variant aggregation / service mapping?*

---

## 1. High-level pipeline (today vs. target)

### 1.1. Conceptual target pipeline

Conceptually, the pipeline we are aiming for looks like this:

```text
PDF
  └─> PDFLoader (io.pdf_loader)
        └─ raw blocks: List[PdfSegment]

      └─> Segmenter (preprocess.segmenter)
            └─ segments: List[PdfSegment]  (smaller, normalized text units)

          └─> classify_segments (llm.classify_segments + gptClient)
                └─ classifications: List[SegmentClassification]

              └─> VariantAggregator (pipeline.variant_aggregator)
                    └─ updated_segments (with variant_id)
                    └─ variant_groups: List[VariantGroup]

                └─> ServiceMapper (pipeline.service_mapper, stub)
                      └─ mapped variants / entities (future)

                  └─> DocumentResult (models.DocumentResult)
````

### 1.2. What actually runs in code today

There are **two main entry points**:

1. `scripts/inspect_pdf.py` – *debug / inspection script* doing **almost full pipeline** (except service mapping):

   * `io.load_pdf` → raw `PdfSegment` blocks,
   * `Segmenter` → segmented `PdfSegment`,
   * `classify_segments` (with `gptClient`),
   * `VariantAggregator` → variants,
   * writes a detailed `*.full_report.json`.

2. `Pipeline` (`src/siwz_mapper/pipeline/pipeline.py`) – *high-level orchestrator*, but currently **Stage B stub**:

   * uses `PDFExtractor` to get segments,
   * creates an empty `DocumentResult` with some metadata,
   * **does not yet** call LLM, VariantAggregator, or ServiceMapper.

So, **the “real logic” currently lives in `scripts/inspect_pdf.py`**, while `Pipeline` is the placeholder that will eventually orchestrate everything for production use.

---

## 2. Module overview

### 2.1. `io.pdf_loader.PDFLoader`

Responsible for:

* opening PDFs via PyMuPDF (`fitz`),
* extracting text as **blocks** with position info,
* converting each block into a `PdfSegment` with:

  * `segment_id` (e.g. `seg_p1_b0`),
  * `text`,
  * `page` (1-indexed),
  * `bbox` (`BBox` with x0, y0, x1, y1, page),
  * `start_char`, `end_char` (global character offsets in the document).

Key points:

* Uses `page.get_text("blocks")`.
* Each **fitz block** becomes one `PdfSegment` (after `strip()` and length check).
* There is an optional `_merge_blocks_on_line` that can merge consecutive blocks on (approximately) the same y-coordinate, but it is controlled by `merge_consecutive_blocks` (currently default = `False`).

Helper:

* `load_pdf(path, extract_bboxes=True)` creates a `PDFLoader` and returns `loader.load(path)`.

### 2.2. `preprocess.segmenter.Segmenter`

Responsible for:

* taking **raw `PdfSegment` blocks** from `PDFLoader`,
* normalizing text (`TextNormalizer`),
* splitting each block into **smaller segments** based on:

  * blank lines (paragraphs),
  * bullet list detection,
  * table row heuristics,
  * long paragraph splitting at sentence boundaries.

Important details:

* Soft limits for segments: `SOFT_MIN = 800`, `SOFT_MAX = 1200` characters.
* The segmenter works **per block**, not across blocks:

  * It never merges blocks together,
  * It only splits a given block into smaller pieces.

Heuristics:

* **Bullet lists**:

  * `TextNormalizer.is_bullet_point(line)` detects bullets by characters (`•`, `-`, `*`, numbers `1.` etc.).
  * `_segment_bullet_list` splits block text into separate segments per bullet.

* **Tables**:

  * `_is_table_block` checks for multiple spaces / tabs in lines:

    * if ≥50% of lines match `TABLE_ROW_PATTERN` (`\s{3,}|\t`), block is treated as a table.
  * `_segment_table` splits into one segment per line (row).

* **Paragraphs**:

  * `_split_by_blank_lines` splits on double newlines → paragraphs.
  * `_create_paragraph_segments` creates segments for each paragraph, optionally using `_split_long_paragraph` if paragraph is too long.

* **Long paragraphs**:

  * `_split_long_paragraph` uses `_split_into_sentences` and tries to keep segments between `soft_min_chars` and `soft_max_chars`.

Output:

* Each new segment is a fresh `PdfSegment` created via `_create_segment_from_block`:

  * `segment_id` is derived from original (e.g. `seg_p1_b0_p0`, `seg_p1_b0_bullet3`, `seg_p1_b0_row2`, `seg_p1_b0_split0`),
  * `page`, `bbox` are copied from the original block,
  * `start_char`, `end_char` are adjusted based on `char_offset` within the block,
  * `section_label`, `variant_id` are inherited.

Helper:

* `segment_pdf_blocks(blocks, ...)` = convenience wrapper creating a `Segmenter` and calling `.segment`.

### 2.3. `llm.classify_segments` (used by `inspect_pdf.py`)

Not included here in full, but from usage we know:

* It exposes `classify_segments(segments, client, show_progress=False)`.
* It returns a list of `SegmentClassification` objects, one per segment.
* At minimum, `SegmentClassification` has:

  * `label` (e.g. `"general"`, `"irrelevant"`, `"variant_header"`, `"variant_body"`, `"prophylaxis"`),
  * `variant_hint` (optional, used by `VariantAggregator` to derive `variant_id` like `V1`, `V2`).

LLM client:

* Implementations live in module `siwz_mapper.llm.gpt_client`:

  * `gptClient` – main wrapper around the OpenAI API (e.g. `gpt-4o-mini`),
    used in the actual pipeline and in `inspect_pdf.py`.

* `gptClient` implements a small protocol (sometimes referred to as `gptClientProtocol` in type hints):

  * `chat(system_prompt: str, user_prompt: str) -> str` – low-level chat completion,
  * in some places also `ask_structured(system_prompt: str, user_prompt: str, response_model: type[T]) -> T`
    – helper that parses JSON into a Pydantic model.

`classify_segments(segments, client, show_progress=False)` expects `client`
compatible with this protocol (typowo `gptClient` z `siwz_mapper.llm.gpt_client`).

### 2.4. `pipeline.variant_aggregator.VariantAggregator`

Responsible for:

* taking `segments: List[PdfSegment]` and `classifications: List[SegmentClassification]`,
* assigning `variant_id` to segments (where appropriate),
* grouping them into `VariantGroup` objects.

`VariantGroup` (Pydantic model):

* `variant_id: str` (e.g. `"V1"`, `"V2"`),
* `header_segment: Optional[PdfSegment]` – the header that started this variant (if any),
* `body_segments: List[PdfSegment]`,
* `prophylaxis_segments: List[PdfSegment]`,
* `segment_count()` – convenience method.

Main logic:

1. `_extract_variant_headers`:

   * scans all segments / classifications,
   * each `cls.label == "variant_header"` becomes a new header,
   * `variant_id`:

     * if `cls.variant_hint` exists → `f"V{cls.variant_hint}"`,
     * otherwise sequential: `V1`, `V2`, ...

2. If **no headers** are found:

   * `_aggregate_single_variant`:

     * assumes a single variant `default_variant_id` (default `"V1"`),
     * segments with `label == "variant_body"` or `"prophylaxis"` get `variant_id="V1"`,
     * creates one `VariantGroup` with no `header_segment`.

3. If **headers exist**:

   * `_aggregate_multiple_variants`:

     * for each header at index `header_idx`, define the variant range `[header_idx, next_header_idx)` (or end of list),
     * header segment gets `variant_id`,
     * `variant_body` and `prophylaxis` inside this range get the same `variant_id`,
     * other labels (`general`, `irrelevant`, maybe `pricing_table` if added later) do **not** get `variant_id`.

Helper:

* `aggregate_variants(segments, classifications, default_variant_id="V1")` is a convenience wrapper around `VariantAggregator.aggregate`.

### 2.5. `pipeline.service_mapper.ServiceMapper` (stub)

Currently a **stub** for future mapping logic.

* Holds a list of `ServiceEntry` (from `models.py`) and `top_k` parameter.
* Provides:

  * `service_index` property (dict `code -> ServiceEntry`),
  * `map_entities(entities: List[DetectedEntity]) -> List[EntityMapping]` – currently returns empty list,
  * `map_variants(variants: List[VariantResult]) -> List[VariantResult]` – currently returns variants unchanged.

This is where **mapping to internal service codes** will eventually live:

* mapping textual mentions / detected entities to `ServiceEntry` codes,
* annotating `VariantResult` with `core_codes`, `prophylaxis_codes`, etc.

### 2.6. `pipeline.pdf_extractor.PDFExtractor`

A thin wrapper used by `Pipeline`:

* In `__init__`:

  * creates a `PDFLoader` with `extract_bboxes` flag,
  * creates a `Segmenter`.

* In `extract(self, pdf_path: Path) -> List[PdfSegment]`:

  * tries `self.loader.load(pdf_path)`:

    * on `PDFLoadError`, returns a **stub** segment with:

      * `segment_id="stub_seg_001"`,
      * `text="[STUB] PDF missing, fallback text"`,
      * other fields set minimally.
  * otherwise, always calls `self.segmenter.segment(blocks)` to produce **segmented** `PdfSegment`.

So for existing PDFs:

```text
PDF → PDFLoader.load → blocks (PdfSegment)
    → Segmenter.segment → segments (PdfSegment)
```

### 2.7. `pipeline.pipeline.Pipeline`

High-level orchestrator (currently **Stage B stub**).

* Holds:

  * `config: Config` (e.g. `config.pipeline.extract_bboxes`, `config.pipeline.top_k_candidates`),
  * `services: List[ServiceEntry]` (for future mapping),
  * `pdf_extractor: PDFExtractor`,
  * `service_mapper: ServiceMapper`,
  * `variant_aggregator: VariantAggregator`.

* `process(self, pdf_path: Path, output_path: Optional[Path] = None) -> DocumentResult`:

  1. Calls `segments = self.pdf_extractor.extract(pdf_path)` (but **does nothing** with these segments yet).
  2. Constructs `DocumentResult` with:

     * `doc_id = pdf_path.stem`,
     * `variants = []` (empty),
     * `metadata = {"pipeline_version": "0.1.0-stub", "num_segments": len(segments)}`.
  3. Optionally writes this result as JSON to `output_path`.
  4. Returns the `DocumentResult`.

* `run(self, pdf_path: str) -> DocumentResult`:

  * thin wrapper that converts `pdf_path` to `Path` and calls `process`.

**Important:** currently, `Pipeline` does not:

* call `classify_segments`,
* use `VariantAggregator`,
* use `ServiceMapper`.

All of that logic is used only in `scripts/inspect_pdf.py` for now.

### 2.8. `scripts/inspect_pdf.py`

Debug / development script that runs almost the full pipeline on a single PDF:

Steps in `run_inspection(pdf_path)`:

1. `blocks: List[PdfSegment] = load_pdf(pdf_path)`

   * uses `siwz_mapper.io.load_pdf` → `PDFLoader.load`.

2. `segmenter = Segmenter()`

   * `segments = segmenter.segment(blocks)`.

3. Create gpt client:

   * `client = gptClient(model="gpt-4o-mini", temperature=0.0)`
     imported from module `siwz_mapper.llm.gpt_client`.
   * This client is passed into `classify_segments`.

4. `classifications = classify_segments(segments, client, show_progress=False)`.

5. `aggregator = VariantAggregator()`

   * `updated_segments, variant_groups = aggregator.aggregate(segments, classifications)`.

6. Build summary:

   * `label_counts` – histogram of classification labels,
   * `variants_summary` – list with:

     * `variant_id`,
     * `has_header`,
     * `num_body`,
     * `num_prophylaxis`,
     * `header_preview`.

7. Build `report` dict containing:

   * basic info: `pdf`, `num_blocks`, `num_segments`, `label_counts`, `variants`,
   * debug info:

     * `"blocks"` – `blocks` converted via `.model_dump()`,
     * `"segments"` – same for `segments`,
     * `"classifications"` – same for `classifications`,
     * `"segments_with_variant_id"` – same for `updated_segments`.

8. `main()`:

   * parses CLI args (expects at least path to `pdf`),
   * runs `run_inspection`,
   * prints a short summary to stdout,
   * writes full JSON to `<pdf>.full_report.json`.

---

## 3. Current behaviour and limitations (critical view)

### 3.1. PDF blocks vs. semantic units

* `PDFLoader` relies on `page.get_text("blocks")`.
* PyMuPDF “blocks” are mostly **layout blocks**:

  * they may correspond to small visual chunks, not necessarily semantic units (e.g. line fragments, cells in a table, parts split by columns).
* `merge_consecutive_blocks` is currently **disabled** by default:

  * we do **not** merge blocks that are on the same line or close in y-axis,
  * we accept PyMuPDF’s block fragmentation as-is.

Effect in SIWZ-like documents:

* large logical sections (e.g. full description of “WYMAGANY ZAKRES ŚWIADCZEŃ”) can be broken into **many small blocks**, especially when laid out as tables or bullet lists.

### 3.2. Segmenter: only splits, never merges

* `Segmenter` always operates **inside a single `PdfSegment` block**.
* It:

  * normalizes text,
  * optionally splits by bullets, tables, blank lines, sentence boundaries.
* It **never merges multiple `PdfSegment` blocks together** (e.g. continuation lines on next row, multi-row descriptions).

Implications:

* If the PDF produces one block per line or per table cell, `Segmenter` will **not** reconstruct multi-line semantic units.
* For many SIWZ documents, this leads to:

  * a large number of small segments,
  * segments that represent only a slice of the semantic meaning (e.g. only one cell of a row, or one continuation line without context).

### 3.3. LLM classification at “too fine” granularity

* `classify_segments` sees one segment at a time (with whatever context the prompt provides, but the core text is that segment).
* When segments are excessively small:

  * the model has less context to infer:

    * whether a fragment belongs to a particular variant,
    * whether it is a header or just part of a list,
    * how it relates to neighbouring lines.
* This increases:

  * number of LLM calls,
  * risk of **misclassification** due to lack of context.

### 3.4. VariantAggregator assumptions

* Assumes a fairly **linear structure**:

  * `variant_header` → subsequent `variant_body`/`prophylaxis` segments belong to this variant until the next header.
* Edge cases not handled yet:

  * “Variant 2 includes everything from Variant 1 except X and adds Y”,
  * cross-references between variants,
  * non-standard variant names (e.g. “Pakiet Rodzina”, “MAX”, “Komfort”) without explicit numeric labels.
* At present, this is acceptable for a first iteration, but will need extensions for real SIWZ complexity.

### 3.5. Pipeline vs. inspect script

* `Pipeline.process` is currently a **stub**:

  * obtains segments via `PDFExtractor`,
  * returns an empty `DocumentResult` (no variants, no mapping).
* The “real” processing chain is in `scripts/inspect_pdf.py`, not inside `Pipeline`.
* This means:

  * there is **duplicated logic** (choice of Segmenter, LLM client, VariantAggregator),
  * real integrations (e.g. mapping to services, storage) cannot rely on `Pipeline` yet.

### 3.6. Service mapping missing

* `ServiceMapper` is a placeholder with no real logic.
* There is no current mechanism to:

  * detect medical services / procedures in variant bodies,
  * map them to `ServiceEntry` codes,
  * produce a rich `DocumentResult` (with mapped core / prophylaxis services per variant).

---

## 4. Extension points and suggested next steps

This section does **not** define any new classes yet, but points to where and how the pipeline can be extended.

### 4.1. Make `Pipeline` the real orchestrator

Goal:

* Move the “real work” (currently in `scripts/inspect_pdf.py`) into `Pipeline.process`, so that:

```text
Pipeline.process(pdf_path) 
  └─> PDFExtractor.extract → segments
  └─> classify_segments
  └─> VariantAggregator
  └─> ServiceMapper
  └─> DocumentResult (with variants and mappings)
```

Steps:

1. Reuse the same flow as `run_inspection`:

   * consider factoring out a shared helper (e.g. a function that performs the 4 steps on a list of segments).
2. Keep `scripts/inspect_pdf.py` as a **debugging wrapper**, but make it call into `Pipeline` or a shared helper, to avoid divergence.

### 4.2. Introduce a “semantic block” layer (block-first approach)

Problem:

* Current granularity is often too fine (blocks/segments ≈ lines, table cells).
* LLM classification would be more robust on **larger, semantically coherent blocks**.

Idea:

* Introduce a new layer between `PDFLoader` and `Segmenter` / LLM:

```text
PDFLoader.load → raw_blocks: List[PdfSegment]

  └─> (NEW) SemanticBlockGrouper / SectionDetector
        └─ logical_blocks: List[PdfSegment or new type]

      └─> LLM classification at block level
           (e.g. classify whole sections as variant body / pricing / irrelevant)

      └─> fine-grained splitting (Segmenter or similar) only where needed
           (e.g. inside variant body blocks for service mapping)
```

Where to plug in:

* This new grouping logic can live in a new module, e.g.:

  * `siwz_mapper.preprocess.block_grouper.py` or
  * `siwz_mapper.preprocess.sections.py`.
* It would take the **raw blocks** from `PDFLoader` and:

  * merge vertically related blocks (same column, close x bounds),
  * merge continuation lines,
  * group table rows into logical service entries where possible.

Important:

* The new layer should **preserve links to original `PdfSegment`s**:

  * either by:

    * creating a new model that holds `List[PdfSegment]` as children, or
    * creating “higher-level” segments with references / ranges.
* This will allow:

  * using larger context for LLM decisions,
  * still tracing back to page/bbox for highlighting.

### 4.3. Use LLM more “block-wise” instead of per tiny segment

Once we have larger semantic blocks, we can:

* call `classify_segments` (or a new function) on **blocks** instead of very small segments:

  * classify whole **sections** as:

    * “general description / introduction”,
    * “variant header”,
    * “variant body including all services of Variant X”,
    * “prophylaxis description”,
    * “pricing / irrelevant tables”, etc.
* inside blocks that are identified as **variant body**, optionally:

  * apply a **fine-grained segmenter** (maybe the existing `Segmenter`, reused or slightly adapted),
  * use those fine segments for **service detection & mapping**.

This is a conceptual change:

* From:

  > PDFLoader → Segmenter (fine) → classify every small segment → aggregate.

* To:

  > PDFLoader → *BlockGrouper* (coarse) → classify coarse blocks → (then fine segmentation only where needed).

### 4.4. Evolve VariantAggregator as SIWZ semantics grow

Later steps (not immediate, but good to have in mind):

* Support non-numeric variant names:

  * “Pakiet Rodzina”, “Komfort”, “Senior”, “MAX”, etc.
  * LLM classification could expose a normalized `variant_id` and a human readable name.
* Handle relationships between variants:

  * “Variant 2 includes everything from Variant 1 except X and adds Y”.
* Store variant relationships and dependencies in a richer model (extended `VariantGroup` / `VariantResult`).

### 4.5. Implement ServiceMapper (real logic)

Once we have:

* meaningful variants,
* body/prophylaxis segments with enough context,

we can:

* detect **service entities** (with LLM or rule-based),
* map them to `ServiceEntry` codes via:

  * fuzzy matching,
  * embeddings,
  * or explicit dictionary matching.

The `ServiceMapper` class is already the right place to centralize this logic; the only missing piece is the implementation.

---

## 5. Repository hygiene (what is noise)

In the current file list there are several `__pycache__` and `.pyc` files, e.g.:

* `src/siwz_mapper/io/__pycache__/...`
* `src/siwz_mapper/llm/__pycache__/...`
* `src/siwz_mapper/pipeline/__pycache__/...`
* `src/siwz_mapper/preprocess/__pycache__/...`
* `src/siwz_mapper/__pycache__/...`

These are **Python bytecode artifacts** and:

* should **not** be versioned in git,
* should be ignored via `.gitignore`.

They are not part of the logical architecture and can be safely deleted from the repository (they will be recreated by Python at runtime).

---

## 6. Summary

* **PDFLoader**: converts PDF into raw `PdfSegment` blocks based on PyMuPDF layout.
* **Segmenter**: splits those blocks into smaller segments using heuristics (bullets, tables, paragraphs, sentences).
* **LLM classification** (via `classify_segments`) works on these segments, assigning labels like `variant_header`, `variant_body`, etc.
* **VariantAggregator**: groups classified segments into variants (`VariantGroup`), assigning `variant_id`s.
* **ServiceMapper**: stub – future place for mapping detected entities / segments to internal service codes.
* **Pipeline**: orchestrator stub – currently only runs PDF extraction and returns an empty `DocumentResult`.
* **inspect_pdf.py**: full inspection pipeline (PDF → blocks → segments → LLM → variants → JSON report), currently the richest integration point.

The main architectural debt is that we:

* operate at a **too fine granularity** for LLM classification (line-like segments),
* lack an intermediate layer for **semantic block grouping**,
* keep full orchestration in the debug script instead of the `Pipeline` class,
* do not yet implement real **service mapping**.

This document should be the reference when designing:

* a new “semantic block / section” layer,
* a block-first LLM classification strategy,
* migration of the logic from `scripts/inspect_pdf.py` into `Pipeline.process`,
* and finally, a real `ServiceMapper` implementation.

```

Jeśli po spojrzeniu na aktualny `inspect_pdf.py` / `gpt_client.py` zobaczysz, że jednak coś jeszcze się rozjeżdża (np. nazwa modułu, parametry konstruktora), daj znać, a doprecyzujemy ten fragment pod dokładny kod.
```
