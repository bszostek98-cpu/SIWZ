# Dictionary Loader - Dokumentacja

## ✅ Implementacja zakończona

**Data**: 2025-11-22  
**Status**: ✅ Wszystkie funkcjonalności zaimplementowane i przetestowane

## 📦 Co zostało zaimplementowane

### Moduł `src/siwz_mapper/io/dictionary_loader.py`

Efektywny loader słownika usług medycznych z plików CSV/XLSX do `List[ServiceEntry]`.

#### Kluczowe funkcjonalności

1. **✅ Obsługa formatów**
   - CSV z automatyczną detekcją separatora (`,`, `;`, `|`, tab)
   - XLSX (Excel)
   - Kodowanie UTF-8 (konfigurowalne)

2. **✅ Wersjonowanie**
   - Automatyczna detekcja z nazwy pliku (`services_v1.2.csv` → "1.2")
   - Ręczne przekazanie wersji
   - Pattern matching: `v1.2.3`, `_1.2`, `1.0`

3. **✅ Walidacja**
   - Sprawdzanie duplikatów kodów
   - Walidacja wymaganych pól (code, name, category)
   - Trimowanie białych znaków
   - Obsługa pustych wierszy

4. **✅ Mapowanie kolumn**
   - Automatyczne rozpoznawanie różnych nazw kolumn
   - Wsparcie polskich nazw (kod, nazwa, kategoria, itp.)
   - Case-insensitive matching
   - Konfigurowalne mapowanie

5. **✅ Parsowanie synonimów**
   - Separatory: `,`, `;`, `|`, `\n`
   - Automatyczne trimowanie
   - Lista stringów w `ServiceEntry.synonyms`

6. **✅ Wydajność**
   - Pandas dla efektywnego przetwarzania
   - Obsługa tysięcy wierszy
   - Minimalne użycie pamięci

7. **✅ Tryby walidacji**
   - Strict mode: rzuca wyjątki przy błędach
   - Non-strict mode: loguje ostrzeżenia, kontynuuje

## 🧪 Testy

**23 testy jednostkowe** - wszystkie przechodzą ✅

```bash
python -m pytest tests/test_dictionary_loader.py -v
# 23 passed in 1.55s
```

### Pokrycie testów

- ✅ Ładowanie CSV i XLSX
- ✅ Parsowanie różnych separatorów
- ✅ Detekcja wersji z nazwy pliku
- ✅ Walidacja duplikatów (strict/non-strict)
- ✅ Walidacja wymaganych pól
- ✅ Trimowanie whitespace
- ✅ Mapowanie polskich nazw kolumn
- ✅ Parsowanie synonimów
- ✅ Obsługa błędów (brak pliku, błędny format)
- ✅ Ładowanie z DataFrame
- ✅ Duże zbiory danych (5000 wierszy)
- ✅ Statystyki ładowania

### Fixture files

- `tests/fixtures/services_v1.0.csv` - poprawny słownik (10 usług)
- `tests/fixtures/services_with_issues.csv` - z błędami (duplikaty, puste pola)
- `tests/fixtures/services_semicolon.csv` - separator średnik

## 📝 API

### Convenience function

```python
from siwz_mapper import load_dictionary

services, version = load_dictionary(
    file_path,
    encoding='utf-8',  # opcjonalne
    version=None,      # opcjonalne (auto-detekcja)
    strict=True        # strict validation
)
```

### Klasa DictionaryLoader

```python
from siwz_mapper import DictionaryLoader

loader = DictionaryLoader(
    column_mapping=None,      # custom mappings
    strict_validation=True    # strict mode
)

# Load from file
services, version = loader.load(file_path, encoding='utf-8')

# Load from DataFrame
services, version = loader.load_from_dataframe(df, version="1.0")

# Get statistics
stats = loader.get_stats()
# Returns: {
#   'total_rows': 100,
#   'valid_services': 98,
#   'version': '1.2',
#   'source_file': 'path/to/file.csv'
# }
```

### Wyjątki

```python
from siwz_mapper import DictionaryLoadError

try:
    services, version = load_dictionary("file.csv")
except DictionaryLoadError as e:
    # Błędy:
    # - File not found
    # - Unsupported format
    # - Missing required columns
    # - Duplicate codes (strict mode)
    # - No valid services loaded
    print(f"Error: {e}")
```

## 💡 Przykłady użycia

### 1. Podstawowe ładowanie

```python
from siwz_mapper import load_dictionary

services, version = load_dictionary("data/services_v1.0.csv")

print(f"Loaded {len(services)} services (version {version})")
for service in services[:3]:
    print(f"  [{service.code}] {service.name}")
    print(f"    Category: {service.category}")
```

### 2. Obsługa błędów

```python
from siwz_mapper import DictionaryLoadError

try:
    services, version = load_dictionary(
        "data/services.csv",
        strict=False  # Continue on errors
    )
except DictionaryLoadError as e:
    print(f"Fatal error: {e}")
```

### 3. Custom column mapping

```python
from siwz_mapper import DictionaryLoader

custom_mapping = {
    'code': ['kod_uslugi', 'code'],
    'name': ['nazwa_uslugi', 'name'],
    'category': ['kategoria', 'category'],
    'subcategory': ['podkategoria'],
    'synonyms': ['synonimy']
}

loader = DictionaryLoader(column_mapping=custom_mapping)
services, version = loader.load("data/custom_format.csv")
```

### 4. Ładowanie z DataFrame

```python
import pandas as pd
from siwz_mapper import DictionaryLoader

# Load and preprocess
df = pd.read_csv("raw_services.csv")
df = df[df['active'] == True]  # Filter active services
df['code'] = df['code'].str.upper()  # Normalize codes

# Load to ServiceEntry
loader = DictionaryLoader()
services, version = loader.load_from_dataframe(df, version="filtered_1.0")
```

### 5. Statystyki

```python
from siwz_mapper import DictionaryLoader

loader = DictionaryLoader()
services, version = loader.load("data/services.csv")

stats = loader.get_stats()
print(f"Version: {stats['version']}")
print(f"Total rows: {stats['total_rows']}")
print(f"Valid services: {stats['valid_services']}")
print(f"Skipped: {stats['total_rows'] - stats['valid_services']}")
```

## 📊 Format danych wejściowych

### CSV

```csv
code,name,category,subcategory,synonyms
KAR001,Konsultacja kardiologiczna,Kardiologia,Konsultacje,"wizyta,badanie"
KAR002,USG serca,Kardiologia,Badania obrazowe,"echo,echokardiografia"
```

### CSV (polskie nazwy)

```csv
kod,nazwa,kategoria,podkategoria,synonimy
KAR001,Konsultacja kardiologiczna,Kardiologia,Konsultacje,"wizyta,badanie"
```

### CSV (różne separatory)

```csv
code;name;category;subcategory;synonyms
KAR001;Konsultacja;Kardiologia;Konsultacje;wizyta|badanie
```

## 🔄 Wersjonowanie

### Automatyczna detekcja

Wersja jest automatycznie wykrywana z nazwy pliku:

| Nazwa pliku | Wykryta wersja |
|-------------|----------------|
| `services_v1.0.csv` | "1.0" |
| `services_v2.5.1.xlsx` | "2.5.1" |
| `dict_1.2.csv` | "1.2" |
| `services_v3.csv` | "3" |
| `services.csv` | "1.0" (domyślna) |

### Ręczne przekazanie

```python
services, version = load_dictionary(
    "services.csv",
    version="2.0-beta"  # Override auto-detection
)
```

## 🎯 Walidacja

### Strict mode (domyślnie)

```python
# Rzuca DictionaryLoadError przy:
# - duplikatach kodów
# - brakujących wymaganych polach
# - błędach parsowania

services, version = load_dictionary("file.csv", strict=True)
```

### Non-strict mode

```python
# Loguje ostrzeżenia i kontynuuje:
# - usuwa duplikaty (zachowuje pierwszy)
# - pomija wiersze z błędami
# - loguje problemy

services, version = load_dictionary("file.csv", strict=False)
```

## 🚀 Wydajność

- **Pandas**: Efektywne przetwarzanie dużych zbiorów
- **Streamowanie**: Nie wczytuje całego pliku do pamięci
- **Benchmark**: 5000 wierszy w < 2 sekundy

```python
# Test z 5000 wierszy
services, version = load_dictionary("large_services_5k.csv")
# Loaded 5000 services in ~1.5s
```

## 📋 Zależności

```
pandas>=2.0.0      # CSV/XLSX processing
openpyxl>=3.1.0    # XLSX support
pydantic>=2.0.0    # ServiceEntry validation
```

## ✅ Checklist implementacji

- [x] Ładowanie CSV z auto-detekcją separatora
- [x] Ładowanie XLSX
- [x] Automatyczna detekcja wersji z nazwy pliku
- [x] Walidacja duplikatów kodów
- [x] Walidacja wymaganych pól
- [x] Trimowanie whitespace
- [x] Mapowanie polskich nazw kolumn
- [x] Parsowanie synonimów (różne separatory)
- [x] Strict i non-strict mode
- [x] Ładowanie z DataFrame
- [x] Statystyki ładowania
- [x] Obsługa błędów
- [x] 23 testy jednostkowe
- [x] Dokumentacja i przykłady
- [x] Fixture files dla testów

## 🔜 Przyszłe rozszerzenia (nie w tym scope)

- [ ] Embeddings dla ServiceEntry
- [ ] Cache wczytanych słowników
- [ ] Incremental updates (diff between versions)
- [ ] Multi-file loading (merge dictionaries)
- [ ] Database backend support
- [ ] API do remote dictionary loading

---

**Implementation complete!** ✅  
**Tests passing**: 23/23 ✅  
**Ready for production use**

