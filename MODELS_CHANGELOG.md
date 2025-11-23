# Models Implementation - Changelog

## 2025-11-22 - Core Models Implementation

### ✅ Zaimplementowano

#### Nowe modele (src/siwz_mapper/models.py)

1. **ServiceEntry** - Słownik usług medycznych
   - `code`, `name`, `category`, `subcategory`, `synonyms`
   - Metoda `to_search_text()` dla wyszukiwania

2. **PdfSegment** - Fragment tekstu z PDF
   - `segment_id`, `text`, `page`
   - Opcjonalne: `bbox`, `start_char`, `end_char`, `section_label`, `variant_id`
   - Walidacja: page >= 1, char offsets >= 0

3. **DetectedEntity** - Wykryta encja (wzmianka o usłudze)
   - `entity_id`, `segment_id`, `text`, `quote`, `page`
   - Opcjonalne: `start_char`, `end_char`
   - `confidence` (0-1) z walidacją

4. **CandidateService** - Kandydat dopasowania
   - `code`, `name`, `score`, `reason`
   - `score` (0-1) z walidacją

5. **EntityMapping** - Mapowanie encji na kody
   - `entity_id`, `mapping_type`, `primary_codes`, `alt_candidates`
   - `rationale`, `confidence`
   - `mapping_type`: "1-1" | "1-m" | "m-1" | "1-0"

6. **VariantResult** - Wyniki dla wariantu
   - `variant_id`, `core_codes`, `prophylaxis_codes`, `mappings`

7. **DocumentResult** - Kompletny wynik
   - `doc_id`, `variants`, `metadata`

8. **ValidationHelper** - Narzędzia walidacji
   - `validate_document_result()` - walidacja całego dokumentu
   - `validate_*()` - walidacja poszczególnych modeli
   - `get_json_schema()` - pobieranie JSON schema
   - `validate_mapping_type_consistency()` - sprawdzanie spójności

#### Testy (tests/test_core_models.py)

- **34 testy jednostkowe** - wszystkie przechodzą ✓
- Pokrycie wszystkich modeli i walidatorów
- Testy edge cases i walidacji

#### Dokumentacja

- **README.md** - dodano szczegółową sekcję o modelach:
  - Przykłady Python dla każdego modelu
  - Przykłady JSON dla każdego modelu
  - Dokumentacja ValidationHelper
  - Opis typów mapowań

#### Przykłady (examples/)

- **example_output.json** - kompletny przykład outputu
  - 2 warianty
  - 5 mapowań z różnymi typami
  - Alternatywne kandydaty
  - Metadata

- **validate_output.py** - skrypt walidacji
  - Walidacja struktury JSON
  - Sprawdzanie spójności
  - Generowanie JSON schema

### 🔄 Zmiany struktury

#### Usunięto
- `src/siwz_mapper/models/` (stary folder z legacy modelami)
  - `document.py` (zastąpiony przez PdfSegment)
  - `service.py` (zastąpiony przez ServiceEntry)
  - `mapping.py` (zastąpiony przez EntityMapping/VariantResult)
  - `config.py` (przeniesiony do src/siwz_mapper/config.py)

#### Dodano
- `src/siwz_mapper/models.py` - nowe core modele (Pydantic V2)
- `src/siwz_mapper/config.py` - konfiguracja (przeniesiona z models/)
- `examples/example_output.json` - przykładowy output
- `examples/validate_output.py` - skrypt walidacji
- `tests/test_core_models.py` - testy nowych modeli

#### Zaktualizowano
- `src/siwz_mapper/__init__.py` - eksport nowych modeli
- `src/siwz_mapper/pipeline/*.py` - zaktualizowane importy
- `src/siwz_mapper/llm/client.py` - zaktualizowane importy
- `tests/test_pipeline.py` - zaktualizowane do nowych modeli
- `README.md` - dodana sekcja o modelach z przykładami

### 📊 Statystyki

- **Modele**: 8 głównych klas
- **Testy**: 34 (wszystkie przechodzą)
- **Linie kodu modeli**: ~470
- **Linie kodu testów**: ~580
- **Przykłady JSON**: 2 kompleksowe
- **Skrypty**: 1 walidacyjny

### 🎯 Najważniejsze funkcjonalności

1. **Pełna walidacja** - Pydantic waliduje wszystkie dane
2. **JSON Schema** - automatyczne generowanie schema
3. **Typy mapowań** - 4 typy: 1-1, 1-m, m-1, 1-0
4. **Audit trail** - dokładne cytaty, pozycje, confidence
5. **Top-k kandidaci** - alternatywne dopasowania
6. **Consistency checks** - automatyczne sprawdzanie spójności
7. **Helper walidacyjny** - łatwa walidacja outputów

### 💡 Przykład użycia

```python
from siwz_mapper import (
    ServiceEntry, PdfSegment, DetectedEntity,
    EntityMapping, VariantResult, DocumentResult,
    ValidationHelper
)

# Tworzenie modeli
service = ServiceEntry(
    code="KAR001",
    name="Konsultacja kardiologiczna",
    category="Kardiologia"
)

segment = PdfSegment(
    segment_id="seg_001",
    text="Konsultacja kardiologiczna",
    page=5
)

entity = DetectedEntity(
    entity_id="ent_001",
    segment_id="seg_001",
    text="konsultacja kardiologiczna",
    quote="Konsultacja kardiologiczna",
    page=5,
    confidence=0.95
)

mapping = EntityMapping(
    entity_id="ent_001",
    mapping_type="1-1",
    primary_codes=["KAR001"],
    rationale="Dokładne dopasowanie",
    confidence=0.95
)

variant = VariantResult(
    variant_id="variant_1",
    core_codes=["KAR001"],
    prophylaxis_codes=[],
    mappings=[mapping]
)

result = DocumentResult(
    doc_id="siwz_2025",
    variants=[variant],
    metadata={"version": "0.1.0"}
)

# Walidacja
warnings = ValidationHelper.validate_mapping_type_consistency(variant)
if not warnings:
    print("✓ Wszystko OK")

# JSON export
json_data = result.model_dump()
```

### 🧪 Uruchomienie testów

```bash
# Wszystkie testy modeli
python -m pytest tests/test_core_models.py -v

# Walidacja przykładu
python examples/validate_output.py examples/example_output.json

# Pobierz JSON schema
python examples/validate_output.py --schema
```

### ✅ Status

**Implementacja zakończona** - wszystkie modele działają, testy przechodzą, dokumentacja kompletna.

### 🔜 Następne kroki

1. Dostosować pipeline do nowych modeli
2. Zaimplementować rzeczywistą ekstrakcję PDF → PdfSegment
3. Zaimplementować detekcję encji → DetectedEntity
4. Zaimplementować mapowanie → EntityMapping
5. Zaktualizować skrypty run_pipeline.py i evaluate.py

---

**Data**: 2025-11-22  
**Autor**: AI Assistant  
**Status**: ✅ Completed

