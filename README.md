# SIWZ Medical Service Mapper

System do automatycznego mapowania wzmianek o usługach medycznych w dokumentach SIWZ na wewnętrzne kody usług, wykorzystujący GPT API.

## 📋 Opis

System przetwarza długie, nieformalne dokumenty SIWZ (Specyfikacja Istotnych Warunków Zamówienia) w języku polskim i:

1. **Wykrywa warianty** - identyfikuje różne warianty oraz sekcje programu profilaktycznego
2. **Ekstrahuje usługi** - wydobywa wzmianki o usługach medycznych z tekstu
3. **Mapuje na kody** - dopasowuje wzmianki do słownika wewnętrznych kodów usług
4. **Tworzy ścieżkę audytu** - dla każdego mapowania zapisuje dokładny cytat z PDF, numer strony i pozycję
5. **Generuje kandydatów** - zwraca top-k alternatywnych dopasowań z wynikami pewności

## 🎯 Funkcjonalności

### Typy mapowań
- **1→1**: Jedna wzmianka → jeden kod usługi
- **1→N**: Jedna wzmianka → wiele kodów (np. "pakiet kardiologiczny")
- **N→1**: Wiele wzmianek → jeden kod (duplikaty)
- **1→0**: Niezmapowane wzmianki

### Ścieżka audytu
Każde mapowanie zawiera:
- Dokładny cytat z PDF (bez halucynacji!)
- Numer strony
- Przesunięcia znaków (character offsets)
- Bounding box (jeśli dostępny)
- Uzasadnienie decyzji
- Współczynnik pewności

### Przygotowanie pod UI
- Top-k kandydatów z wynikami
- Struktura do przechowywania korekt eksperckich
- Kompletny JSON z wszystkimi danymi do wizualizacji

## 📊 Modele danych

System używa **Pydantic** do walidacji i serializacji danych. Wszystkie modele są zdefiniowane w `src/siwz_mapper/models.py`.

### ServiceEntry - Słownik usług

```python
from siwz_mapper import ServiceEntry

service = ServiceEntry(
    code="KAR001",
    name="Konsultacja kardiologiczna",
    category="Kardiologia",
    subcategory="Konsultacje",  # opcjonalne
    synonyms=["wizyta kardiologiczna", "badanie kardiologiczne"]  # opcjonalne
)
```

**JSON Example**:
```json
{
  "code": "KAR001",
  "name": "Konsultacja kardiologiczna",
  "category": "Kardiologia",
  "subcategory": "Konsultacje",
  "synonyms": ["wizyta kardiologiczna", "badanie kardiologiczne"]
}
```

### PdfSegment - Fragment tekstu z PDF

```python
from siwz_mapper import PdfSegment, BBox

segment = PdfSegment(
    segment_id="seg_001",
    text="Konsultacja kardiologiczna oraz USG serca",
    page=5,
    bbox=BBox(page=5, x0=50, y0=200, x1=400, y1=220),  # opcjonalne
    start_char=1250,  # opcjonalne
    end_char=1292,    # opcjonalne
    section_label="Wariant podstawowy",  # opcjonalne
    variant_id="variant_1"  # opcjonalne
)
```

**JSON Example**:
```json
{
  "segment_id": "seg_001",
  "text": "Konsultacja kardiologiczna oraz USG serca",
  "page": 5,
  "bbox": {
    "page": 5,
    "x0": 50.0,
    "y0": 200.0,
    "x1": 400.0,
    "y1": 220.0
  },
  "start_char": 1250,
  "end_char": 1292,
  "section_label": "Wariant podstawowy",
  "variant_id": "variant_1"
}
```

### DetectedEntity - Wykryta encja

```python
from siwz_mapper import DetectedEntity

entity = DetectedEntity(
    entity_id="ent_001",
    segment_id="seg_001",
    text="konsultacja kardiologiczna",  # znormalizowany tekst
    quote="Konsultacja kardiologiczna",  # dokładny cytat z PDF
    page=5,
    start_char=1250,  # opcjonalne
    end_char=1276,    # opcjonalne
    confidence=0.95
)
```

**JSON Example**:
```json
{
  "entity_id": "ent_001",
  "segment_id": "seg_001",
  "text": "konsultacja kardiologiczna",
  "quote": "Konsultacja kardiologiczna",
  "page": 5,
  "start_char": 1250,
  "end_char": 1276,
  "confidence": 0.95
}
```

### EntityMapping - Mapowanie encji na kody

```python
from siwz_mapper import EntityMapping, CandidateService

mapping = EntityMapping(
    entity_id="ent_001",
    mapping_type="1-1",  # "1-1" | "1-m" | "m-1" | "1-0"
    primary_codes=["KAR001"],
    alt_candidates=[
        CandidateService(
            code="KAR005",
            name="Konsultacja kardiologiczna kontrolna",
            score=0.72,
            reason="Podobna nazwa, ale konsultacja kontrolna"
        )
    ],
    rationale="Dokładne dopasowanie nazwy z wysoką pewnością",
    confidence=0.95
)
```

**JSON Example**:
```json
{
  "entity_id": "ent_001",
  "mapping_type": "1-1",
  "primary_codes": ["KAR001"],
  "alt_candidates": [
    {
      "code": "KAR005",
      "name": "Konsultacja kardiologiczna kontrolna",
      "score": 0.72,
      "reason": "Podobna nazwa, ale konsultacja kontrolna"
    }
  ],
  "rationale": "Dokładne dopasowanie nazwy z wysoką pewnością",
  "confidence": 0.95
}
```

### VariantResult - Wyniki dla wariantu

```python
from siwz_mapper import VariantResult

variant = VariantResult(
    variant_id="variant_1",
    core_codes=["KAR001", "KAR002", "KAR003"],
    prophylaxis_codes=["PROF001"],
    mappings=[...]  # lista EntityMapping
)
```

**JSON Example**:
```json
{
  "variant_id": "variant_1",
  "core_codes": ["KAR001", "KAR002", "KAR003"],
  "prophylaxis_codes": ["PROF001"],
  "mappings": [
    {
      "entity_id": "ent_001",
      "mapping_type": "1-1",
      "primary_codes": ["KAR001"],
      "alt_candidates": [],
      "rationale": "Dokładne dopasowanie",
      "confidence": 0.95
    }
  ]
}
```

### DocumentResult - Kompletny wynik

```python
from siwz_mapper import DocumentResult

result = DocumentResult(
    doc_id="siwz_2025_kardiologia",
    variants=[...],  # lista VariantResult
    metadata={
        "processed_at": "2025-11-22T10:30:00",
        "pipeline_version": "0.1.0",
        "num_segments": 150,
        "num_entities_detected": 45
    }
)
```

**Kompletny JSON Example**:
```json
{
  "doc_id": "siwz_2025_kardiologia",
  "variants": [
    {
      "variant_id": "variant_1",
      "core_codes": ["KAR001", "KAR002"],
      "prophylaxis_codes": [],
      "mappings": [
        {
          "entity_id": "ent_001",
          "mapping_type": "1-1",
          "primary_codes": ["KAR001"],
          "alt_candidates": [
            {
              "code": "KAR005",
              "name": "Konsultacja kardiologiczna kontrolna",
              "score": 0.72,
              "reason": "Podobna nazwa"
            }
          ],
          "rationale": "Dokładne dopasowanie",
          "confidence": 0.95
        }
      ]
    }
  ],
  "metadata": {
    "processed_at": "2025-11-22T10:30:00",
    "pipeline_version": "0.1.0",
    "num_segments": 150,
    "num_entities_detected": 45,
    "num_variants": 1
  }
}
```

### ValidationHelper - Walidacja outputów

```python
from siwz_mapper import ValidationHelper
import json

# Waliduj JSON z pliku
with open("output/result.json") as f:
    data = json.load(f)

try:
    # Waliduj cały dokument
    result = ValidationHelper.validate_document_result(data)
    print(f"✓ Dokument {result.doc_id} jest poprawny")
    
    # Sprawdź spójność mapowań
    for variant in result.variants:
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        if warnings:
            print(f"⚠ Ostrzeżenia dla {variant.variant_id}:")
            for w in warnings:
                print(f"  - {w}")
    
    # Pobierz JSON schema
    schema = ValidationHelper.get_json_schema(DocumentResult)
    print(f"JSON Schema: {schema}")
    
except ValidationError as e:
    print(f"✗ Błąd walidacji: {e}")
```

**Typy mapowań**:
- `"1-1"` - jedna encja → jeden kod (standard)
- `"1-m"` - jedna encja → wiele kodów (pakiet usług)
- `"m-1"` - wiele encji → jeden kod (duplikaty)
- `"1-0"` - niezmapowana encja (brak dopasowania)

## 🏗️ Architektura

```
src/siwz_mapper/
├── models.py         # Modele danych (Pydantic)
├── models/           # Legacy modele (deprecated)
├── pipeline/         # Komponenty pipeline
│   ├── pdf_extractor.py      # Ekstrakcja tekstu z pozycjami
│   ├── variant_detector.py   # Detekcja wariantów (LLM)
│   ├── service_mapper.py     # Mapowanie usług (LLM)
│   └── pipeline.py           # Orkiestracja
├── llm/             # Integracja z LLM
│   ├── client.py    # Wrapper API z ograniczeniami
│   └── prompts.py   # Szablony promptów
└── utils/           # Narzędzia
    └── logging.py   # Konfiguracja logowania
```

## 📥 Ładowanie słownika usług

System zawiera narzędzia do efektywnego ładowania słownika usług medycznych z plików CSV/XLSX.

### Szybkie użycie

```python
from siwz_mapper import load_dictionary

# Załaduj słownik z CSV lub XLSX
services, version = load_dictionary("data/services_v1.2.csv")

print(f"Załadowano {len(services)} usług (wersja {version})")
for service in services[:3]:
    print(f"  [{service.code}] {service.name}")
```

### Obsługiwane formaty

- **CSV**: różne separatory (`,`, `;`, `|`, tab), automatyczne wykrywanie
- **XLSX**: pliki Excel
- **Wersjonowanie**: automatyczna detekcja z nazwy pliku (np. `services_v1.2.csv`)
- **Kodowanie**: UTF-8 (domyślnie), konfigurowalne

### Nazwy kolumn

System automatycznie rozpoznaje różne nazwy kolumn (również polskie):

| Pole | Rozpoznawane nazwy |
|------|-------------------|
| `code` | code, service_code, kod, kod_uslugi |
| `name` | name, service_name, nazwa, nazwa_uslugi |
| `category` | category, kategoria, cat |
| `subcategory` | subcategory, podkategoria, subcat (opcjonalne) |
| `synonyms` | synonyms, synonimy, aliases (opcjonalne) |

### Walidacja

Automatyczna walidacja przy ładowaniu:
- ✅ Brak duplikatów kodów
- ✅ Wszystkie wymagane pola obecne
- ✅ Trimowanie białych znaków
- ✅ Parsowanie synonimów (separatory: `,`, `;`, `|`, `\n`)

### Przykłady użycia

#### Podstawowe ładowanie

```python
from siwz_mapper import DictionaryLoader

loader = DictionaryLoader(strict_validation=True)
services, version = loader.load("data/services.xlsx")

# Pobierz statystyki
stats = loader.get_stats()
print(f"Wiersze: {stats['total_rows']}, Poprawne: {stats['valid_services']}")
```

#### Non-strict mode (pomiń błędy)

```python
from siwz_mapper import load_dictionary

# Załaduj nawet jeśli są duplikaty - zachowaj pierwszy
services, version = load_dictionary(
    "data/services_with_issues.csv",
    strict=False  # Pomiń błędy walidacji
)
```

#### Ładowanie z DataFrame

```python
import pandas as pd
from siwz_mapper import DictionaryLoader

df = pd.read_csv("services.csv")
# ... przetwarzanie DataFrame ...

loader = DictionaryLoader()
services, version = loader.load_from_dataframe(df, version="custom_1.0")
```

#### Duże zbiory danych

```python
# Efektywne ładowanie tysięcy wierszy
services, version = load_dictionary("data/large_services_10k_rows.csv")
# System używa pandas dla wydajności
```

### Format CSV

```csv
code,name,category,subcategory,synonyms
KAR001,Konsultacja kardiologiczna,Kardiologia,Konsultacje,"wizyta,badanie"
KAR002,USG serca,Kardiologia,Badania obrazowe,"echo,echokardiografia"
```

Lub z polskimi nazwami kolumn:

```csv
kod,nazwa,kategoria,podkategoria,synonimy
KAR001,Konsultacja kardiologiczna,Kardiologia,Konsultacje,"wizyta,badanie"
```

### Obsługa błędów

```python
from siwz_mapper import DictionaryLoadError

try:
    services, version = load_dictionary("services.csv")
except DictionaryLoadError as e:
    print(f"Błąd ładowania: {e}")
    # Błędy: brak pliku, duplikaty, brakujące kolumny, itp.
```

## 🚀 Instalacja

### 1. Klonowanie repozytorium

```bash
git clone <repository-url>
cd SIWZ
```

### 2. Utworzenie środowiska wirtualnego

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Instalacja zależności

```bash
pip install -r requirements.txt
```

### 4. Konfiguracja

Ustaw klucz API OpenAI:

```bash
# Windows PowerShell
$env:SIWZ_LLM__API_KEY="your-api-key-here"

# Linux/Mac
export SIWZ_LLM__API_KEY="your-api-key-here"

# Lub w pliku .env
echo "SIWZ_LLM__API_KEY=your-api-key-here" > .env
```

Opcjonalnie edytuj `config/default_config.yaml` aby zmienić domyślne ustawienia.

## 📖 Użycie

### Uruchomienie pipeline

```bash
python scripts/run_pipeline.py \
  --pdf data/siwz_example.pdf \
  --services data/services.json \
  --output output/results.json
```

Parametry:
- `--pdf`: Ścieżka do pliku PDF SIWZ (wymagane)
- `--services`: Ścieżka do słownika usług JSON (wymagane)
- `--output`: Ścieżka wyjściowa JSON (opcjonalne, domyślnie `output/<nazwa>.json`)
- `--config`: Ścieżka do pliku konfiguracyjnego YAML (opcjonalne)
- `--log-level`: Poziom logowania: DEBUG, INFO, WARNING, ERROR (domyślnie INFO)

### Format słownika usług

Plik `services.json` powinien zawierać listę usług:

```json
[
  {
    "code": "SVC001",
    "name": "Konsultacja kardiologiczna",
    "category_info": {
      "category": "Kardiologia",
      "subcategory": "Konsultacje"
    },
    "description": "Wizyta u kardiologa",
    "synonyms": ["wizyta kardiologiczna", "badanie kardiologiczne"]
  }
]
```

### Format wyniku

Pipeline generuje JSON z pełną strukturą mapowań:

```json
{
  "document_name": "siwz_example.pdf",
  "mapping_type": "1:N",
  "variants": [
    {
      "variant_id": "variant_1",
      "variant_name": "Wariant podstawowy",
      "core_services": ["SVC001", "SVC002"],
      "core_audit_trails": [
        {
          "source_spans": [...],
          "quoted_text": "konsultacja kardiologiczna",
          "reasoning": "Dokładne dopasowanie nazwy",
          "confidence": 0.95
        }
      ],
      "core_candidates": [
        {
          "service": {...},
          "score": 0.92,
          "reasoning": "Wysokie podobieństwo semantyczne"
        }
      ]
    }
  ]
}
```

### Ewaluacja

Porównaj wyniki z ground truth:

```bash
python scripts/evaluate.py \
  --predictions output/results.json \
  --ground-truth data/ground_truth.json \
  --output output/metrics.json
```

Wyświetli metryki:
- Precision, Recall, F1 (ogólne i per-wariant)
- Liczba zmapowanych/niezmapowanych usług

## 🧪 Testy

### Uruchomienie wszystkich testów

```bash
pytest tests/ -v
```

### Testy z pokryciem

```bash
pytest tests/ --cov=src/siwz_mapper --cov-report=html
```

### Testy konkretnego modułu

```bash
pytest tests/test_models.py -v
pytest tests/test_pipeline.py -v
```

## ⚙️ Konfiguracja

### Zmienne środowiskowe

System używa prefiksu `SIWZ_` dla zmiennych środowiskowych:

```bash
SIWZ_LLM__API_KEY=your-key           # Klucz API
SIWZ_LLM__MODEL=gpt-4o               # Model LLM
SIWZ_LLM__TEMPERATURE=0.1            # Temperatura
SIWZ_PIPELINE__TOP_K_CANDIDATES=5    # Liczba kandydatów
SIWZ_SERVICES_DICT_PATH=data/services.json
SIWZ_OUTPUT_DIR=output
```

### Plik konfiguracyjny

`config/default_config.yaml`:

```yaml
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.1
  max_tokens: 4000

pipeline:
  top_k_candidates: 5
  min_confidence_threshold: 0.5
  extract_bboxes: true
  parallel_llm_calls: false
```

## 🛠️ Development

### Code style

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Type checking
mypy src/
```

### Struktura testów

```
tests/
├── test_models.py        # Testy modeli danych
├── test_pipeline.py      # Testy komponentów pipeline
└── fixtures/
    └── sample_services.json
```

## 📊 Status implementacji

### ✅ Zaimplementowane komponenty

- ✅ **Modele danych** (Pydantic) - kompletne z walidacją
- ✅ **PDF Loader** (PyMuPDF) - ekstrakcja z metadanymi (page, bbox, offsets)
- ✅ **Text Normalizer** - czyszczenie tekstu (unicode, whitespace, hyphenation)
- ✅ **Segmenter** - segmentacja na chunks 800-1200 chars
- ✅ **GPT Client** - wrapper dla OpenAI API
- ✅ **Segment Classification** (C1) - klasyfikacja na 6 kategorii z GPT
- ✅ **FakeGPTClient** - mock dla testów bez API
- ✅ **Dictionary Loader** - wczytywanie słownika usług z CSV/XLSX
- ✅ **Testy jednostkowe** - 60+ testów, wszystkie przechodzą
- ✅ **Dokumentacja** - szczegółowe README dla każdego komponentu

### 🚧 W kolejce do implementacji

1. **Variant Grouping** (C2) - grupowanie segmentów w warianty
2. **Entity Detection** (C3) - wydobywanie wzmianek o usługach z GPT
3. **Service Mapping** (C4) - mapowanie encji na kody słownika
4. **Embedding search** - semantyczne wyszukiwanie kandydatów
5. **Pipeline orchestration** - połączenie wszystkich kroków

## 📄 Licencja

[Określ licencję projektu]

## 👥 Autorzy

[Określ autorów]

## 🤝 Contributing

1. Fork repozytorium
2. Utwórz branch (`git checkout -b feature/amazing-feature`)
3. Commit zmian (`git commit -m 'Add amazing feature'`)
4. Push do brancha (`git push origin feature/amazing-feature`)
5. Otwórz Pull Request

---

**Status projektu**: 🚧 W fazie rozwoju (stub implementation)

