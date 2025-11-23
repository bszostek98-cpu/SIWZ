# Architektura SIWZ Mapper

## Przegląd systemu

System składa się z pipeline'u przetwarzającego dokumenty SIWZ w trzech głównych krokach:

```
PDF → [1. Ekstrakcja] → [2. Detekcja wariantów] → [3. Mapowanie usług] → Wynik JSON
```

## Komponenty

### 1. Modele danych (`models/`)

#### document.py
```python
PDFDocument
  ├── TextSpan (text + pozycja)
  │   └── BoundingBox (współrzędne)
  └── Variant (wykryty wariant)
```

**Odpowiedzialność**: Reprezentacja struktury dokumentu PDF z informacją o pozycji tekstu.

**Kluczowe klasy**:
- `TextSpan`: Fragment tekstu z numerem strony, offsetami znaków, bounding box
- `Variant`: Wykryty wariant z przypisanymi fragmentami tekstu
- `PDFDocument`: Kompletny dokument z wszystkimi fragmentami i wariantami

#### service.py
```python
Service
  ├── code (unikalny kod)
  ├── name (nazwa usługi)
  ├── category_info (kategoria/podkategoria)
  └── synonyms (alternatywne nazwy)
```

**Odpowiedzialność**: Reprezentacja słownika usług medycznych.

**Kluczowe metody**:
- `to_search_text()`: Generuje tekst do semantic search

#### mapping.py
```python
MappingResult
  └── VariantMapping[]
      ├── core_services (zmapowane kody)
      ├── core_audit_trails (ścieżki audytu)
      │   └── AuditTrail
      │       ├── source_spans (źródłowe fragmenty)
      │       ├── quoted_text (dokładny cytat)
      │       └── confidence (pewność)
      └── core_candidates (alternatywy)
          └── ServiceCandidate
              ├── service (kandydat)
              └── score (wynik)
```

**Odpowiedzialność**: Wyniki mapowania z pełną ścieżką audytu.

**Kluczowe typy**:
- `MappingType`: Enum (1:1, 1:N, N:1, 1:0)
- `AuditTrail`: Dokładna dokumentacja każdej decyzji mapowania
- `ServiceCandidate`: Alternatywne dopasowanie z wynikiem

#### config.py
```python
Config
  ├── LLMConfig (API, model, temperatura)
  └── PipelineConfig (top_k, thresholdy)
```

**Odpowiedzialność**: Konfiguracja systemu z obsługą zmiennych środowiskowych.

### 2. Pipeline (`pipeline/`)

#### pdf_extractor.py
```python
PDFExtractor
  └── extract(pdf_path) → PDFDocument
```

**Odpowiedzialność**: Ekstrakcja tekstu z PDFa z informacją o pozycji.

**Technologie**: PyMuPDF (fitz) lub pdfplumber

**Output**:
- Pełny tekst dokumentu
- Lista `TextSpan` z pozycjami (strona, offsety, bbox)
- Metadata PDFa

**Implementacja (TODO)**:
```python
import fitz  # PyMuPDF

def extract(self, pdf_path):
    doc = fitz.open(pdf_path)
    spans = []
    
    for page_num, page in enumerate(doc, 1):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            # Extract text with positions
            ...
    
    return PDFDocument(...)
```

#### variant_detector.py
```python
VariantDetector
  └── detect(document) → PDFDocument (with variants)
```

**Odpowiedzialność**: Wykrycie wariantów i sekcji profilaktycznych za pomocą LLM.

**Flow**:
1. Chunk długiego dokumentu na sekcje
2. Dla każdego chunka: wywołaj LLM z promptem detekcji wariantów
3. Sklej wyniki i usuń duplikaty
4. Przypisz `TextSpan`y do wariantów

**Prompt strategy**:
```
Znalezione sekcje:
- "Wariant 1: ..." → Variant(id="v1", name="Wariant 1")
- "Program profilaktyczny..." → Variant(is_prophylaxis=True)
```

**Implementacja (TODO)**:
```python
def detect(self, document):
    chunks = self._chunk_document(document)
    
    variants = []
    for chunk in chunks:
        response = self.llm_client.call(
            prompt=PromptTemplates.VARIANT_DETECTION,
            source_snippet=chunk.text,
            json_schema=VARIANT_SCHEMA
        )
        variants.extend(self._parse_variants(response))
    
    return self._merge_variants(variants)
```

#### service_mapper.py
```python
ServiceMapper
  └── map_variants(variants) → MappingResult
      ├── _extract_service_mentions()
      ├── _find_candidate_services()
      └── _create_audit_trail()
```

**Odpowiedzialność**: Mapowanie wzmianek o usługach na kody z top-k kandydatami.

**Flow**:
1. **Ekstrakcja**: Wywołaj LLM aby wydobyć wzmianki o usługach z tekstu
2. **Matching**: Dla każdej wzmianki znajdź top-k kandydatów ze słownika
3. **Ranking**: Posortuj kandydatów według score
4. **Audit**: Stwórz `AuditTrail` z dokładnym cytatem i uzasadnieniem

**Matching strategies**:
- **Exact match**: Dokładne dopasowanie nazwy
- **Fuzzy match**: Levenshtein distance
- **Semantic search**: Embeddingi + cosine similarity (TODO)
- **LLM ranking**: GPT ocenia dopasowanie (dla top-k)

**Implementacja (TODO)**:
```python
def _find_candidate_services(self, mention):
    # 1. Quick filtering
    candidates = self._fuzzy_search(mention, self.services, top_k=20)
    
    # 2. LLM reranking
    response = self.llm_client.call(
        prompt=PromptTemplates.SERVICE_MAPPING.format(
            mention=mention,
            services_list=candidates
        ),
        source_snippet=mention,
        json_schema=RANKING_SCHEMA
    )
    
    # 3. Return top-k
    return self._parse_candidates(response, top_k=self.top_k)
```

#### pipeline.py
```python
Pipeline
  └── process(pdf_path) → MappingResult
      1. pdf_extractor.extract()
      2. variant_detector.detect()
      3. service_mapper.map_variants()
```

**Odpowiedzialność**: Orkiestracja całego procesu.

**Flow**:
```
PDF 
  → PDFExtractor.extract() 
  → PDFDocument 
  → VariantDetector.detect() 
  → PDFDocument + Variants 
  → ServiceMapper.map_variants() 
  → MappingResult
  → JSON output
```

### 3. LLM Integration (`llm/`)

#### client.py
```python
LLMClient
  └── call(prompt, source_snippet, json_schema) → dict
      ├── _build_constrained_prompt()
      └── _validate_response()
```

**Odpowiedzialność**: Wrapper dla API LLM z wymuszeniem ograniczeń.

**Wymuszane ograniczenia**:
1. Zawsze dołącz `source_snippet` w prompcie
2. Instrukcja: "Cytuj TYLKO z dostarczonego fragmentu"
3. Wymagaj JSON output zgodny ze schematem
4. Wymagaj współczynnika `confidence` w odpowiedzi

**Przykład prompta**:
```
KRYTYCZNE ZASADY:
1. Cytuj TYLKO tekst z dostarczonego fragmentu źródłowego
2. NIE WYMYŚLAJ ani nie dodawaj tekstu spoza fragmentu
3. Zwróć odpowiedź w formacie JSON
4. Dołącz confidence (0-1)

SCHEMAT JSON: {...}

FRAGMENT ŹRÓDŁOWY:
{source_snippet}

ZADANIE:
{prompt}
```

**Implementacja (TODO)**:
```python
def call(self, prompt, source_snippet, json_schema):
    full_prompt = self._build_constrained_prompt(...)
    
    response = openai.ChatCompletion.create(
        model=self.config.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt}
        ],
        temperature=self.config.temperature,
        response_format={"type": "json_object"}
    )
    
    return self._validate_response(response, json_schema)
```

#### prompts.py
```python
PromptTemplates
  ├── VARIANT_DETECTION
  ├── SERVICE_EXTRACTION
  ├── SERVICE_MAPPING
  └── PROPHYLAXIS_CLASSIFICATION
```

**Odpowiedzialność**: Centralne repozytorium promptów.

**Podejście**:
- Szablony z placeholderami: `{mention}`, `{services_list}`
- Jasne instrukcje w języku polskim
- Przykłady few-shot (TODO: dodać)
- Konsystentny format JSON output

## Przepływ danych

### Szczegółowy flow

```
┌─────────────┐
│  PDF File   │
└──────┬──────┘
       │
       v
┌─────────────────────────────────────┐
│  PDFExtractor                       │
│  - PyMuPDF/pdfplumber               │
│  - Extract text + positions         │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────────────────────────────┐
│  PDFDocument                        │
│  - full_text: str                   │
│  - spans: List[TextSpan]            │
│    - text, page, char_start/end     │
│    - bbox (optional)                │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────────────────────────────┐
│  VariantDetector + LLM              │
│  1. Chunk document                  │
│  2. LLM: identify variants          │
│  3. Classify prophylaxis sections   │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────────────────────────────┐
│  PDFDocument + Variants             │
│  - variants: List[Variant]          │
│    - variant_id, name               │
│    - is_prophylaxis: bool           │
│    - spans: List[TextSpan]          │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────────────────────────────┐
│  ServiceMapper + LLM                │
│  For each Variant:                  │
│    1. LLM: extract service mentions │
│    2. Match to service dict         │
│    3. Generate top-k candidates     │
│    4. Create audit trails           │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────────────────────────────┐
│  MappingResult                      │
│  - variants: List[VariantMapping]   │
│    - core_services: List[str]       │
│    - core_audit_trails: [...]       │
│    - core_candidates: [...]         │
│    - user_overrides: dict           │
└──────┬──────────────────────────────┘
       │
       v
┌─────────────┐
│  JSON File  │
└─────────────┘
```

## Przykład końcowego JSON

```json
{
  "document_name": "siwz_2025_kardiologia.pdf",
  "mapping_type": "1:N",
  "variants": [
    {
      "variant_id": "variant_1",
      "variant_name": "Wariant podstawowy",
      "is_prophylaxis": false,
      "core_services": ["KAR001", "KAR002", "KAR003"],
      "core_audit_trails": [
        {
          "source_spans": [
            {
              "text": "konsultacja kardiologiczna oraz USG serca",
              "page": 5,
              "char_start": 1250,
              "char_end": 1292,
              "bbox": {"page": 5, "x0": 50, "y0": 200, "x1": 400, "y1": 220}
            }
          ],
          "quoted_text": "konsultacja kardiologiczna",
          "reasoning": "Dokładne dopasowanie nazwy usługi z słownika",
          "confidence": 0.95,
          "llm_response": {"raw": "..."}
        }
      ],
      "core_candidates": [
        {
          "service": {
            "code": "KAR001",
            "name": "Konsultacja kardiologiczna",
            "category_info": {"category": "Kardiologia", "subcategory": "Konsultacje"}
          },
          "score": 0.95,
          "reasoning": "Dokładne dopasowanie"
        },
        {
          "service": {
            "code": "KAR005",
            "name": "Konsultacja kardiologiczna kontrolna"
          },
          "score": 0.72,
          "reasoning": "Podobna nazwa, ale kontrolna"
        }
      ],
      "user_overrides": {}
    }
  ],
  "unmapped_spans": [],
  "metadata": {
    "processed_at": "2025-11-22T10:30:00",
    "pipeline_version": "0.1.0",
    "num_variants": 1
  }
}
```

## Rozszerzalność

### Dodanie nowego źródła danych

Stwórz nowy extractor implementujący interfejs:

```python
class CustomExtractor:
    def extract(self, input_path: Path) -> PDFDocument:
        # Your logic
        return PDFDocument(...)
```

### Dodanie nowej strategii matchowania

Rozszerz `ServiceMapper`:

```python
class ServiceMapper:
    def _find_candidate_services_v2(self, mention):
        # New matching logic
        # e.g. embedding-based search
        embeddings = self.embedding_model.encode(mention)
        candidates = self.vector_store.search(embeddings)
        return candidates
```

### Dodanie metryk ewaluacji

Rozszerz `Evaluator` w `scripts/evaluate.py`:

```python
class Evaluator:
    def calculate_mrr(self, predictions, ground_truth):
        # Mean Reciprocal Rank
        ...
```

## Best Practices

1. **Zawsze zachowuj pełną ścieżkę audytu**
   - Zapisuj dokładne cytaty z PDF
   - Dołączaj pozycję (strona, offsety, bbox)
   - Loguj reasoning decyzji

2. **Waliduj output LLM**
   - Sprawdź czy cytaty pochodzą z source snippet
   - Waliduj format JSON względem schematu
   - Obsłuż błędy i retry

3. **Testuj na małych fragmentach**
   - Zacznij od 1-2 stron PDF
   - Sprawdź każdy krok pipeline osobno
   - Używaj fixtures w testach

4. **Optymalizuj koszty LLM**
   - Cache wyników dla identycznych inputów
   - Rozważ batch processing
   - Monitoruj token usage

5. **Przygotuj pod UI**
   - Generuj top-k kandydatów, nie tylko best match
   - Zapisuj wszystkie dane potrzebne do wizualizacji
   - Strukturyzuj user_overrides dla przyszłych korekt

---

**Wersja**: 0.1.0  
**Ostatnia aktualizacja**: 2025-11-22

