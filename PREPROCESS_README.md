# Text Preprocessing for SIWZ Mapper

Moduł preprocessingu zapewnia normalizację i segmentację tekstu wyekstrahowanego z PDFów.

## 📦 Komponenty

### 1. `TextNormalizer` - Normalizacja tekstu

Czysci i ujednolica tekst wyekstrahowany z PDF:

#### Funkcje

- ✨ **Unicode normalization** (NFC)
- 🧹 **Whitespace cleanup** (wielokrotne spacje, tabulatory)
- 🔗 **Hyphenation fixes** (usuwanie dzielenia wyrazów na końcu linii)
- 📝 **Smart quotes** → straight quotes
- 🚫 **Zero-width characters** (usuwanie niewidocznych znaków)
- 🎯 **Bullet point detection**

#### Przykład użycia

```python
from siwz_mapper.preprocess import TextNormalizer, normalize_text

# Convenience function
text = "tekst  z    błędami\npodzielo-\nny"
normalized = normalize_text(text)
# Output: "tekst z błędami\npodzielony"

# Lub z większą kontrolą
normalizer = TextNormalizer(
    normalize_unicode=True,
    fix_whitespace=True,
    fix_hyphenation=True,
    normalize_quotes=True
)

normalized = normalizer.normalize(text)
```

#### Detekcja bullet points

```python
normalizer = TextNormalizer()

normalizer.is_bullet_point("• Pierwszy punkt")  # True
normalizer.is_bullet_point("1. Punkt")          # True
normalizer.is_bullet_point("- Lista")           # True
normalizer.is_bullet_point("Zwykły tekst")      # False
```

### 2. `Segmenter` - Segmentacja tekstu

Dzieli długie bloki tekstu na mniejsze segmenty:

#### Strategia segmentacji

1. **Blank-line paragraphs** - dzieli po pustych liniach
2. **Bullet lists** - każdy punkt osobno
3. **Table rows** - wykrywa tabele (heurystyka)
4. **Long paragraphs** - dzieli długie paragrafy na granicach zdań

#### Soft limits

- **Soft min**: 800 znaków (domyślnie)
- **Soft max**: 1200 znaków (domyślnie)
- Segmenty nie są sztywno ograniczone - priorytet to granice zdań

#### Zachowywane metadane

- ✅ Numer strony (`page`)
- ✅ Bounding box (`bbox`)
- ✅ Character offsets (`start_char`, `end_char`)
- ✅ Section labels

#### Przykład użycia

```python
from siwz_mapper.preprocess import Segmenter, segment_pdf_blocks
from siwz_mapper.io import load_pdf

# Load PDF blocks
blocks = load_pdf("document.pdf")

# Convenience function
segments = segment_pdf_blocks(
    blocks,
    soft_min_chars=800,
    soft_max_chars=1200,
    normalize=True
)

# Lub z większą kontrolą
segmenter = Segmenter(
    soft_min_chars=800,
    soft_max_chars=1200,
    normalize_text=True,
    detect_bullets=True,
    detect_tables=True
)

segments = segmenter.segment(blocks)

# Każdy segment to PdfSegment z metadanymi
for seg in segments:
    print(f"Page {seg.page}, {len(seg.text)} chars")
    print(f"Text: {seg.text[:100]}...")
```

## 🔄 Pełny pipeline

```python
from siwz_mapper.io import load_pdf
from siwz_mapper.preprocess import segment_pdf_blocks

# 1. Load PDF (with bboxes and offsets)
blocks = load_pdf("siwz_document.pdf", extract_bboxes=True)

# 2. Segment and normalize
segments = segment_pdf_blocks(
    blocks,
    soft_max_chars=1200,
    normalize=True
)

# 3. Use for further processing (entity detection, mapping, etc.)
for segment in segments:
    # Each segment is ready for LLM processing
    # - Clean, normalized text
    # - Reasonable length
    # - Preserved metadata for citation
    pass
```

## 🎯 Dlaczego segmentacja?

### Bez segmentacji

- ❌ Całe strony PDFów (tysiące znaków) → zbyt długie dla LLM context
- ❌ Brak granularności dla cytowania
- ❌ Trudne debugowanie i audyt

### Z segmentacją

- ✅ Segmenty 800-1200 znaków → optymalne dla LLM
- ✅ Precyzyjne cytowanie (page + char offset + bbox)
- ✅ Łatwe podświetlanie w UI
- ✅ Lepsze mapowanie encji → usług

## 📊 Przykładowe wyniki

### Input block

```
Block 1 (page 1, 2500 chars):
"Rozdział I. Zakres usług medycznych.
Wykonawca zobowiązuje się do świadczenia następujących usług:
• Konsultacje specjalistyczne...
[długi tekst]"
```

### Output segments

```
Segment 1.1 (page 1, 180 chars):
"Rozdział I. Zakres usług medycznych.
Wykonawca zobowiązuje się do świadczenia następujących usług:"

Segment 1.2_bullet0 (page 1, 45 chars):
"• Konsultacje specjalistyczne"

Segment 1.2_bullet1 (page 1, 38 chars):
"• Badania diagnostyczne"

[...]
```

## 🧪 Testy

```bash
# Run tests
pytest tests/test_normalizer.py tests/test_segmenter.py -v

# Example output
38 passed
```

### Test coverage

- **TextNormalizer**: 16 testów
  - Unicode normalization
  - Whitespace cleanup
  - Hyphenation fixes
  - Smart quotes
  - Bullet detection
  - Polish characters

- **Segmenter**: 22 testy
  - Short blocks (no split)
  - Blank-line paragraphs
  - Bullet lists
  - Long paragraph splitting
  - Table detection
  - Metadata preservation
  - Edge cases

## ⚙️ Konfiguracja

### Normalization options

```python
normalizer = TextNormalizer(
    normalize_unicode=True,    # Unicode NFC
    fix_whitespace=True,       # Clean spaces/tabs
    fix_hyphenation=True,      # Fix word splits
    normalize_quotes=True,     # Smart → straight
    preserve_bullets=True      # Keep bullet chars
)
```

### Segmentation options

```python
segmenter = Segmenter(
    soft_min_chars=800,       # Min segment length
    soft_max_chars=1200,      # Max segment length
    normalize_text=True,      # Apply normalization
    detect_bullets=True,      # Separate bullets
    detect_tables=True        # Separate table rows
)
```

## 🚀 Performance

- **Normalization**: < 1ms per 1000 chars
- **Segmentation**: < 5ms per block
- **Full pipeline**: ~10ms per PDF page

Skaluje liniowo z ilością tekstu.

## 📝 Notatki

### Bullet detection

Wykrywane znaki:
- `•`, `◦`, `▪`, `▫`, `●`, `○`, `■`, `□`
- `-`, `–`, `—`, `*`
- Numerowane: `1.`, `2)`, `a)`, etc.

### Hyphenation

Usuwa dzielenie wyrazów typu:
```
medycz-
nych
```
→ `medycznych`

Działa dla polskich i angielskich wyrazów.

### Table detection

Heurystyka bazująca na:
- Wielokrotnych spacjach lub tabulatorach
- Konsystencji w wielu liniach
- >50% linii z cechami tabeli

**Best-effort** - nie jest 100% dokładna.

## 🔗 Integracja

### Z PDF Loader

```python
from siwz_mapper.io import load_pdf
from siwz_mapper.preprocess import segment_pdf_blocks

blocks = load_pdf("doc.pdf")
segments = segment_pdf_blocks(blocks)
```

### Z dalszymi etapami pipeline

```python
# Segments → Entity Detection
for segment in segments:
    entities = detect_entities(segment)
    
    # Each entity has:
    # - quote (exact text from segment)
    # - page, char offsets (from segment metadata)
    # - segment_id (for traceability)
```

## 📚 API Reference

### `normalize_text()`

```python
def normalize_text(
    text: str,
    normalize_unicode: bool = True,
    fix_whitespace: bool = True,
    fix_hyphenation: bool = True
) -> str
```

### `segment_pdf_blocks()`

```python
def segment_pdf_blocks(
    blocks: List[PdfSegment],
    soft_min_chars: int = 800,
    soft_max_chars: int = 1200,
    normalize: bool = True
) -> List[PdfSegment]
```

---

**Część ekosystemu SIWZ Mapper** 🏥

