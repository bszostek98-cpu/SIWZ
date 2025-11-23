# Variant Aggregator

Moduł agregacji wariantów z sklasyfikowanych segmentów dokumentów SIWZ.

## 📋 Przegląd

`VariantAggregator` grupuje sklasyfikowane segmenty w warianty medyczne na podstawie:
- **variant_header** - rozpoczyna nowy wariant
- **variant_body** - przypisywany do bieżącego wariantu
- **prophylaxis** - śledzona osobno na wariant

## 🎯 Zasady działania

### 1. Wykrywanie wariantów

- **variant_header** rozpoczyna nowy wariant
- Następne **variant_body** dziedziczą `variant_id` z nagłówka
- Przypisywanie trwa do następnego nagłówka lub końca dokumentu

### 2. Domyślny wariant

- Jeśli brak nagłówków → pojedynczy wariant "V1"
- Wszystkie **variant_body** trafiają do tego wariantu

### 3. Obsługa profilaktyki

- **prophylaxis** segmenty są śledzone osobno per wariant
- Przypisywane do wariantu w którym się znajdują
- Nie są częścią `body_segments`

### 4. Inne etykiety

- **irrelevant**, **general**, **pricing_table** → **NIE** dostają `variant_id`
- Są w `updated_segments` ale bez przypisania do wariantu

## 📊 Modele danych

### `VariantGroup`

Reprezentuje zgrupowany wariant z jego segmentami.

```python
from siwz_mapper.pipeline import VariantGroup

group = VariantGroup(
    variant_id="V1",                        # Unique ID
    header_segment=header_seg,              # Optional header
    body_segments=[seg1, seg2],             # Body segments
    prophylaxis_segments=[proph_seg]        # Prophylaxis segments
)

print(group.segment_count())  # Total segments (header + body + prophylaxis)
```

**Pola:**
- `variant_id`: str - Identyfikator wariantu (np. "V1", "V2")
- `header_segment`: Optional[PdfSegment] - Segment nagłówkowy
- `body_segments`: List[PdfSegment] - Segmenty ciała wariantu
- `prophylaxis_segments`: List[PdfSegment] - Segmenty profilaktyki

**Metody:**
- `segment_count()` - Zwraca całkowitą liczbę segmentów

## 🔧 Użycie

### Podstawowe użycie

```python
from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import classify_segments, FakeGPTClient
from siwz_mapper.pipeline import aggregate_variants

# 1. Masz segmenty
segments = [
    PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
    PdfSegment(segment_id="seg_2", text="Body text", page=1),
]

# 2. Klasyfikuj (z GPT lub FakeGPTClient)
client = FakeGPTClient()
classifications = classify_segments(segments, client)

# 3. Agreguj w warianty
updated_segments, variants = aggregate_variants(segments, classifications)

# 4. Użyj wyników
print(f"Found {len(variants)} variants")
for variant in variants:
    print(f"{variant.variant_id}: {variant.segment_count()} segments")
```

### Użycie klasy `VariantAggregator`

```python
from siwz_mapper.pipeline import VariantAggregator

# Custom default variant ID
aggregator = VariantAggregator(default_variant_id="DEFAULT")

# Aggregate
updated_segments, variants = aggregator.aggregate(segments, classifications)

# Extract variant IDs
variant_ids = aggregator.get_variant_ids(variants)
print(f"Variant IDs: {variant_ids}")
```

## 📝 Przykłady

### Przykład 1: Dwa warianty

```python
segments = [
    PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
    PdfSegment(segment_id="seg_2", text="• Usługa 1\n• Usługa 2", page=1),
    PdfSegment(segment_id="seg_3", text="WARIANT 2", page=2),
    PdfSegment(segment_id="seg_4", text="• Usługa 3", page=2),
]

# After classification and aggregation:
# variants[0]: V1 with seg_2
# variants[1]: V2 with seg_4
```

### Przykład 2: Brak nagłówków (single variant)

```python
segments = [
    PdfSegment(segment_id="seg_1", text="• Usługa 1", page=1),
    PdfSegment(segment_id="seg_2", text="• Usługa 2", page=1),
]

# After aggregation:
# variants[0]: V1 (default) with seg_1, seg_2
```

### Przykład 3: Z profilaktyką

```python
segments = [
    PdfSegment(segment_id="seg_1", text="WARIANT 1", page=1),
    PdfSegment(segment_id="seg_2", text="• Konsultacja", page=1),
    PdfSegment(segment_id="seg_3", text="Program profilaktyczny", page=2),
]

# After aggregation:
# variants[0].body_segments: [seg_2]
# variants[0].prophylaxis_segments: [seg_3]
```

## 🔄 Przepływ danych

```
Input:
  - List[PdfSegment]
  - List[SegmentClassification]

        ↓

  VariantAggregator
    1. Extract variant headers
    2. Group segments by variant
    3. Assign variant_id
    4. Separate prophylaxis

        ↓

Output:
  - List[PdfSegment] (with variant_id assigned)
  - List[VariantGroup]
```

## 📐 Algorytm

### Przypadek: Multiple variants

```python
1. Znajdź wszystkie variant_header
2. Dla każdego nagłówka:
   a. Utwórz VariantGroup z ID z hint lub sekwencyjny
   b. Określ range segmentów (do następnego header lub końca)
   c. Dla każdego segmentu w range:
      - variant_header → dodaj do updated z variant_id
      - variant_body → dodaj do body_segments z variant_id
      - prophylaxis → dodaj do prophylaxis_segments z variant_id
      - inne → dodaj do updated BEZ variant_id
```

### Przypadek: Single variant (no headers)

```python
1. Utwórz VariantGroup z default_variant_id
2. Dla każdego segmentu:
   - variant_body → dodaj do body_segments z variant_id
   - prophylaxis → dodaj do prophylaxis_segments z variant_id
   - inne → dodaj do updated BEZ variant_id
```

## 🧪 Testy

System ma 17 testów pokrywających wszystkie scenariusze:

```bash
pytest tests/test_variant_aggregator.py -v

# 17 passed
```

**Test coverage:**
- ✅ Tworzenie VariantGroup
- ✅ Inicjalizacja aggregator
- ✅ Empty segments
- ✅ Mismatched lengths error
- ✅ Single variant (no headers)
- ✅ Single variant with prophylaxis
- ✅ Two variants
- ✅ Three variants with mixed content
- ✅ Variant without hint (sequential numbering)
- ✅ Convenience function
- ✅ Custom default variant
- ✅ get_variant_ids()
- ✅ Only headers, no bodies
- ✅ Only irrelevant segments
- ✅ Pricing table not included

## 🎯 Kluczowe właściwości

### 1. Przypisywanie variant_id

**Dostają variant_id:**
- ✅ variant_header
- ✅ variant_body
- ✅ prophylaxis (w ramach wariantu)

**NIE dostają variant_id:**
- ❌ irrelevant
- ❌ general
- ❌ pricing_table

### 2. Numeracja wariantów

- Jeśli `variant_hint` w classification → używany jako numer (np. "1" → "V1")
- Jeśli brak hint → sekwencyjna numeracja ("V1", "V2", "V3", ...)

### 3. Prophylaxis assignment

- Profilaktyka w zakresie wariantu → przypisana do tego wariantu
- Śledzona oddzielnie w `prophylaxis_segments`
- Ma ustawiony `variant_id`

## 📊 Output structure

### Updated segments

```python
# PdfSegment with variant_id assigned
updated_segments = [
    PdfSegment(..., variant_id="V1"),  # header
    PdfSegment(..., variant_id="V1"),  # body
    PdfSegment(..., variant_id="V1"),  # prophylaxis
    PdfSegment(..., variant_id=None),  # irrelevant
]
```

### Variant groups

```python
variants = [
    VariantGroup(
        variant_id="V1",
        header_segment=PdfSegment(...),
        body_segments=[...],
        prophylaxis_segments=[...]
    ),
    VariantGroup(
        variant_id="V2",
        header_segment=PdfSegment(...),
        body_segments=[...],
        prophylaxis_segments=[]
    ),
]
```

## 🔗 Integracja z pipeline

```python
from siwz_mapper.io import load_pdf
from siwz_mapper.preprocess import segment_pdf_blocks
from siwz_mapper.llm import GPTClient, classify_segments
from siwz_mapper.pipeline import aggregate_variants

# Full pipeline
blocks = load_pdf("siwz.pdf")
segments = segment_pdf_blocks(blocks)
client = GPTClient()
classifications = classify_segments(segments, client)

# Aggregate variants (C2)
updated_segments, variants = aggregate_variants(segments, classifications)

# Next: Entity detection per variant (C3)
for variant in variants:
    print(f"Processing {variant.variant_id}")
    for body_seg in variant.body_segments:
        # Extract service mentions from body_seg
        pass
```

## ⚙️ Konfiguracja

```python
# Default configuration
aggregator = VariantAggregator()
# default_variant_id = "V1"

# Custom default
aggregator = VariantAggregator(default_variant_id="DEFAULT")
```

## 🐛 Error handling

```python
# Mismatched lengths
try:
    aggregator.aggregate(segments, classifications)
except ValueError as e:
    print(f"Length mismatch: {e}")

# Empty input
updated, variants = aggregator.aggregate([], [])
# Returns: ([], [])
```

## 💡 Best practices

1. **Zawsze klasyfikuj przed agregacją**:
   ```python
   classifications = classify_segments(segments, client)
   updated, variants = aggregate_variants(segments, classifications)
   ```

2. **Sprawdź czy są warianty**:
   ```python
   if not variants:
       logger.warning("No variants found")
   ```

3. **Iteruj po wariantach**:
   ```python
   for variant in variants:
       print(f"Processing {variant.variant_id}")
       # Process body_segments
       # Process prophylaxis_segments separately
   ```

4. **Użyj segment_count() dla statystyk**:
   ```python
   for variant in variants:
       print(f"{variant.variant_id}: {variant.segment_count()} total segments")
   ```

## 📈 Performance

- **Complexity**: O(n) gdzie n = liczba segmentów
- **Memory**: O(n) dla kopii segmentów z variant_id
- **Typical speed**: <1ms dla 100 segmentów

---

**Status: ✅ Kompletny i przetestowany**  
**Część ekosystemu SIWZ Mapper** 🏥

