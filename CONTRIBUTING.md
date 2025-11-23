# Contributing to SIWZ Mapper

Dziękujemy za zainteresowanie rozwojem SIWZ Mapper! 🎉

## Jak zacząć

### 1. Fork i clone

```bash
# Fork repozytorium na GitHubie
# Następnie:
git clone https://github.com/YOUR-USERNAME/siwz-mapper.git
cd siwz-mapper
```

### 2. Setup środowiska developerskiego

```bash
# Utwórz venv
python -m venv venv
source venv/bin/activate  # lub venv\Scripts\activate na Windows

# Zainstaluj w trybie edycji z narzędziami dev
pip install -e .
pip install -e ".[dev]"
```

### 3. Uruchom testy

```bash
pytest tests/ -v
```

## Struktura projektu

```
src/siwz_mapper/
├── models/          # Modele danych - dodawaj nowe modele tutaj
├── pipeline/        # Komponenty pipeline - logika przetwarzania
├── llm/             # Integracja z LLM - prompty i API calls
└── utils/           # Narzędzia pomocnicze
```

## Obszary do implementacji

### 🔴 Priorytet wysoki

1. **PDFExtractor** (`pipeline/pdf_extractor.py`)
   - Rzeczywista ekstrakcja z PyMuPDF/pdfplumber
   - Wydobywanie bounding boxes
   - Obsługa różnych formatów PDF

2. **LLMClient** (`llm/client.py`)
   - Implementacja wywołań OpenAI API
   - Parsowanie odpowiedzi JSON
   - Obsługa błędów i retry logic
   - Rate limiting

3. **VariantDetector** (`pipeline/variant_detector.py`)
   - Prompt engineering dla detekcji wariantów
   - Klasyfikacja sekcji profilaktycznych
   - Chunking długich dokumentów

4. **ServiceMapper** (`pipeline/service_mapper.py`)
   - Ekstrakcja wzmianek o usługach
   - Dopasowanie do słownika (semantic search)
   - Generowanie top-k kandydatów

### 🟡 Priorytet średni

5. **Prompt Templates** (`llm/prompts.py`)
   - Optymalizacja istniejących promptów
   - Dodanie przykładów few-shot
   - Testy A/B różnych promptów

6. **Config Loading** (`models/config.py`)
   - Wczytywanie z YAML
   - Walidacja konfiguracji
   - Profile dla różnych środowisk

7. **Evaluation Metrics**
   - Dodatkowe metryki (MRR, NDCG)
   - Analiza per-kategoria
   - Wizualizacja wyników

### 🟢 Nice to have

8. **Web UI**
   - Interface do przeglądania wyników
   - Możliwość korekt eksperckich
   - Wizualizacja PDF z podświetleniem

9. **Semantic Search**
   - Embeddingi dla usług
   - Wektorowa baza danych (Chroma, Qdrant)
   - Hybrid search (keyword + semantic)

10. **Pipeline Optimizations**
    - Równoległe wywołania LLM
    - Caching wyników
    - Batch processing

## Guidelines

### Code Style

```bash
# Format przed commitem
black src/ tests/
ruff check src/ tests/ --fix
mypy src/
```

Używamy:
- **Black** dla formatowania (line length: 100)
- **Ruff** dla lintingu
- **MyPy** dla type checking (opcjonalnie)

### Konwencje

- **Docstringi**: Google style dla wszystkich publicznych funkcji/klas
- **Type hints**: Używaj gdzie możliwe
- **Języki**: Polski w promptach i docs użytkownika, angielski w kodzie
- **Testy**: Co najmniej jeden test dla każdej nowej funkcjonalności

### Przykład dobrego pull requesta

```python
class ServiceMapper:
    def find_candidates(
        self,
        mention: str,
        services: List[Service],
        top_k: int = 5
    ) -> List[ServiceCandidate]:
        """
        Find top-k candidate services for a mention.
        
        Args:
            mention: Extracted service mention text
            services: Available services to search
            top_k: Number of candidates to return
            
        Returns:
            List of ServiceCandidate objects sorted by score
            
        Example:
            >>> mapper.find_candidates("USG serca", services, top_k=3)
            [ServiceCandidate(service=..., score=0.95), ...]
        """
        # Implementation
        ...
```

### Commit messages

```
feat: Add semantic search for service matching
fix: Handle empty PDF pages in extractor
docs: Update README with new config options
test: Add tests for VariantDetector
refactor: Simplify LLM prompt construction
```

Prefiksy: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`

## Proces review

1. **Stwórz branch** z opisową nazwą: `feature/semantic-search`
2. **Napisz testy** dla nowej funkcjonalności
3. **Uruchom wszystkie testy** przed PR: `pytest tests/ -v`
4. **Sprawdź coverage**: `pytest --cov=src/siwz_mapper`
5. **Format code**: `black src/ tests/`
6. **Utwórz PR** z opisem zmian i przykładami

## Testowanie

### Uruchom testy

```bash
# Wszystkie testy
pytest tests/ -v

# Konkretny plik
pytest tests/test_models.py -v

# Z coverage
pytest --cov=src/siwz_mapper --cov-report=html

# Tylko szybkie testy (bez integracyjnych)
pytest -m "not slow"
```

### Dodaj nowe testy

```python
# tests/test_new_feature.py
import pytest
from siwz_mapper.your_module import YourClass

class TestYourFeature:
    def test_basic_functionality(self):
        """Test basic use case."""
        obj = YourClass()
        result = obj.method()
        assert result == expected
    
    def test_edge_case(self):
        """Test edge case."""
        obj = YourClass()
        with pytest.raises(ValueError):
            obj.method(invalid_input)
```

## Zgłaszanie bugów

Użyj template:

```markdown
**Opis buga**
Krótki opis problemu

**Kroki do reprodukcji**
1. Uruchom `python scripts/run_pipeline.py ...`
2. Zobacz błąd...

**Oczekiwane zachowanie**
Co powinno się stać

**Aktualne zachowanie**
Co się dzieje

**Środowisko**
- OS: Windows 10 / Ubuntu 22.04
- Python: 3.11
- Wersja: 0.1.0

**Logi**
```
[Paste relevant logs]
```
```

## Feature requests

Jeśli masz pomysł na nową funkcjonalność:

1. **Sprawdź issues** - może ktoś już to zaproponował
2. **Otwórz issue** z tagiem `enhancement`
3. **Opisz use case** - jak to będzie używane?
4. **Zaproponuj API** - jak powinien wyglądać interface?

## Pytania?

- Otwórz issue z tagiem `question`
- Sprawdź [README.md](README.md) i [QUICKSTART.md](QUICKSTART.md)
- Zobacz istniejące issues i PRs

## Kod of Conduct

- Bądź uprzejmy i pomocny
- Szanuj różne punkty widzenia
- Przyjmuj konstruktywną krytykę
- Skoncentruj się na tym co najlepsze dla projektu

---

**Happy coding!** 🚀

