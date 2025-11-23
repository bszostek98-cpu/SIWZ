# Szybki start z SIWZ Mapper

Ten dokument przeprowadzi Cię przez pierwsze kroki z systemem SIWZ Mapper.

## 1. Instalacja (5 minut)

```bash
# Klonuj repozytorium
git clone <repository-url>
cd SIWZ

# Utwórz środowisko wirtualne
python -m venv venv

# Aktywuj środowisko
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Zainstaluj zależności
pip install -r requirements.txt
```

## 2. Konfiguracja API (2 minuty)

Ustaw klucz API OpenAI:

```bash
# Windows PowerShell
$env:SIWZ_LLM__API_KEY="sk-your-api-key-here"

# Linux/Mac
export SIWZ_LLM__API_KEY="sk-your-api-key-here"
```

## 3. Przygotuj dane (10 minut)

### Słownik usług

Utwórz plik `data/services.json` z listą usług:

```json
[
  {
    "code": "KAR001",
    "name": "Konsultacja kardiologiczna",
    "category_info": {
      "category": "Kardiologia",
      "subcategory": "Konsultacje"
    },
    "description": "Wizyta u lekarza kardiologa",
    "synonyms": ["wizyta kardiologiczna", "badanie kardiologiczne"]
  },
  {
    "code": "KAR002",
    "name": "USG serca",
    "category_info": {
      "category": "Kardiologia",
      "subcategory": "Badania obrazowe"
    },
    "description": "Ultrasonografia serca (echokardiografia)",
    "synonyms": ["echokardiografia", "echo serca", "USG kardiologiczne"]
  }
]
```

Możesz użyć przykładowego pliku:
```bash
cp tests/fixtures/sample_services.json data/services.json
```

### PDF SIWZ

Umieść swój plik PDF w katalogu `data/`:

```bash
# Przykład
cp /path/to/your/siwz.pdf data/siwz_przyklad.pdf
```

## 4. Uruchom pipeline (1 minuta)

```bash
python scripts/run_pipeline.py \
  --pdf data/siwz_przyklad.pdf \
  --services data/services.json \
  --log-level INFO
```

Wynik zostanie zapisany w `output/siwz_przyklad_mapping.json`

## 5. Sprawdź wyniki

Otwórz plik `output/siwz_przyklad_mapping.json`:

```json
{
  "document_name": "siwz_przyklad.pdf",
  "mapping_type": "1:N",
  "variants": [
    {
      "variant_id": "variant_1",
      "variant_name": "Wariant podstawowy",
      "core_services": ["KAR001", "KAR002"],
      "core_audit_trails": [
        {
          "quoted_text": "konsultacja kardiologiczna",
          "reasoning": "Dokładne dopasowanie nazwy usługi",
          "confidence": 0.95,
          "source_spans": [...]
        }
      ],
      "core_candidates": [...]
    }
  ]
}
```

## 6. Uruchom testy (opcjonalnie)

```bash
# Wszystkie testy
pytest tests/ -v

# Z pokryciem
pytest tests/ --cov=src/siwz_mapper
```

## 7. Ewaluacja (opcjonalnie)

Jeśli masz ground truth annotations:

```bash
python scripts/evaluate.py \
  --predictions output/siwz_przyklad_mapping.json \
  --ground-truth data/ground_truth.json
```

Wyświetli metryki precision, recall, F1.

## Struktura projektu

```
SIWZ/
├── src/siwz_mapper/     # Kod źródłowy
│   ├── models/          # Modele danych (Pydantic)
│   ├── pipeline/        # Komponenty pipeline
│   ├── llm/             # Integracja z GPT
│   └── utils/           # Narzędzia
├── scripts/             # Skrypty uruchamiające
├── tests/               # Testy jednostkowe
├── config/              # Konfiguracja
├── data/                # Twoje dane (PDFs, services.json)
└── output/              # Wyniki mapowania
```

## Najczęstsze problemy

### Błąd: "PDF file not found"
- Sprawdź, czy plik PDF istnieje w podanej ścieżce
- Użyj pełnej ścieżki: `--pdf C:\path\to\file.pdf`

### Błąd: "API key not set"
- Upewnij się, że zmienna środowiskowa jest ustawiona
- Sprawdź nazwę: `SIWZ_LLM__API_KEY` (dwa podkreślniki!)

### Błąd: "Services file not found"
- Utwórz `data/services.json` zgodnie z przykładem powyżej
- Lub użyj: `cp tests/fixtures/sample_services.json data/services.json`

### System zwraca puste wyniki
- ⚠️ To normalne w wersji STUB
- Obecna wersja zawiera tylko szkielet implementacji
- Rzeczywista implementacja LLM będzie dodana w następnych wersjach

## Następne kroki

1. **Dostosuj słownik usług** - dodaj wszystkie swoje usługi do `data/services.json`
2. **Przetestuj na małym PDFie** - zacznij od 2-3 stronicowego dokumentu
3. **Sprawdź logi** - użyj `--log-level DEBUG` aby zobaczyć szczegóły
4. **Stwórz ground truth** - przygotuj adnotacje dla ewaluacji
5. **Zaczekaj na pełną implementację** - lub przyczyń się do rozwoju!

## Pomoc

- Przeczytaj [README.md](README.md) dla pełnej dokumentacji
- Sprawdź [testy](tests/) dla przykładów użycia
- Zobacz [przykłady danych](tests/fixtures/)

---

**Czas setupu**: ~20 minut  
**Poziom**: Początkujący  
**Python**: 3.10+

