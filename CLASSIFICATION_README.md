# Segment Classification with GPT

Moduł klasyfikacji segmentów dla polskich dokumentów SIWZ/SWZ z użyciem GPT API.

## 📋 Przegląd

System klasyfikuje segmenty tekstu (PdfSegment) do kategorii, które są później używane w pipeline do:
- Wykrywania wariantów medycznych
- Identyfikacji programu profilaktycznego
- Odróżniania tabel cenowych od rzeczywistych wariantów
- Ignorowania tekstów wprowadzających/prawnych

## 🏷️ Etykiety klasyfikacji

System przypisuje **DOKŁADNIE JEDNĄ** z poniższych etykiet do każdego segmentu:

### `irrelevant`
**Opis:** Tekst wprowadzający, prawny, metainformacje  
**Przykłady:**
- "OGŁOSZENIE O ZAMÓWIENIU PUBLICZNYM"
- "Rozdział I. Postanowienia ogólne"
- "Zamawiający zaprasza do składania ofert"

### `general`
**Opis:** Ogólny opis zakresu, ale nie konkretny wariant  
**Przykłady:**
- "Przedmiotem zamówienia jest opieka medyczna nad pracownikami"
- "Zakres usług obejmuje konsultacje i badania"

### `variant_header`
**Opis:** Nagłówki wprowadzające konkretne warianty medyczne  
**Przykłady:**
- "Załącznik nr 2 A – WARIANT 1"
- "WARIANT 2 - Pakiet rozszerzony"
- "Wariant III – opieka specjalistyczna"

**Uwaga:** Zawiera `variant_hint` (np. "1", "2", "III")

### `variant_body`
**Opis:** Listy usług i opisy należące do konkretnego wariantu  
**Przykłady:**
- "• Konsultacja kardiologiczna\n• Badanie EKG\n• USG serca"
- "Zakres badań obejmuje: morfologię, biochemię, RTG"

### `prophylaxis`
**Opis:** Fragmenty opisujące program profilaktyczny  
**Przykłady:**
- "Program profilaktyczny obejmuje przegląd stanu zdrowia"
- "Profilaktyczny przegląd stanu zdrowia:\n• Morfologia\n• Badanie moczu"

**Uwaga:** `is_prophylaxis=True`

### `pricing_table`
**Opis:** Tabele/formularze gdzie "Wariant 1-4" to kolumny cenowe, NIE definicje pakietów  
**Przykłady:**
- "Tabela cenowa:\nCena za Wariant 1: ___\nCena za Wariant 2: ___"
- "Formularz oferty: Wariant 1 | Wariant 2 | Wariant 3"

**Uwaga:** Te segmenty są ignorowane przy grupowaniu wariantów medycznych

## 🧠 Zasady domenowe

### Rozróżnianie "Wariantu"

Słowo "Wariant" występuje w dwóch kontekstach:

1. **Rzeczywisty wariant medyczny** (OPZ, załączniki):
   ```
   Załącznik nr 2 A – WARIANT 1
   Pakiet opieki podstawowej obejmuje:
   • Konsultacje lekarskie
   • Badania laboratoryjne
   ```
   → Etykiety: `variant_header`, `variant_body`

2. **Kolumna cenowa** (edytowalne formularze ofertowe):
   ```
   Tabela cenowa:
   Wariant 1: ___ zł
   Wariant 2: ___ zł
   ```
   → Etykieta: `pricing_table`

### Kontekst ma znaczenie

System używa kontekstu (poprzedni i następny segment) do rozróżnienia:
- GPT otrzymuje `prev_text`, `current_text`, `next_text`
- Pozwala to rozróżnić "Wariant" w różnych kontekstach

## 🔧 Użycie

### Podstawowe użycie

```python
from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import GPTClient, classify_segments

# 1. Utwórz klienta GPT
client = GPTClient(
    model="gpt-4o-mini",
    temperature=0.0
)

# 2. Przygotuj segmenty (np. z pdf_loader + segmenter)
segments = [
    PdfSegment(segment_id="seg_1", text="...", page=1),
    PdfSegment(segment_id="seg_2", text="...", page=2),
]

# 3. Klasyfikuj
results = classify_segments(segments, client)

# 4. Użyj wyników
for result in results:
    print(f"Segment {result.segment_id}: {result.label}")
    if result.is_prophylaxis:
        print("  → Part of prophylaxis program")
    if result.variant_hint:
        print(f"  → Variant number: {result.variant_hint}")
```

### Testowanie bez API (FakeGPTClient)

```python
from siwz_mapper.llm import FakeGPTClient, classify_segments

# Użyj FakeGPTClient do testów
fake_client = FakeGPTClient()

results = classify_segments(segments, fake_client)
# Działa bez wywołań API, deterministyczne wyniki
```

### Klasyfikacja pojedynczego segmentu

```python
from siwz_mapper.llm import classify_segment

# Z kontekstem
result = classify_segment(
    client=client,
    segment=my_segment,
    prev_text="Text from previous segment",
    next_text="Text from next segment"
)

print(f"Label: {result.label}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Rationale: {result.rationale}")
```

## 📊 Model danych

### `SegmentClassification`

```python
from siwz_mapper.llm import SegmentClassification

classification = SegmentClassification(
    segment_id="seg_123",
    label="variant_header",           # Jedna z VALID_LABELS
    variant_hint="1",                  # Optional[str]
    is_prophylaxis=False,              # bool
    confidence=0.95,                   # float 0.0-1.0
    rationale="Nagłówek wariantu..."  # str
)

# JSON export
json_str = classification.model_dump_json()
```

**Pola:**
- `segment_id`: ID segmentu (zawsze ustawiane z PdfSegment.segment_id)
- `label`: Etykieta (walidowana, musi być w VALID_LABELS)
- `variant_hint`: Numer wariantu jeśli dotyczy (np. "1", "2", "III")
- `is_prophylaxis`: Flaga programu profilaktycznego (auto-sync z label)
- `confidence`: Pewność GPT 0.0-1.0
- `rationale`: Krótkie uzasadnienie po polsku

## 🔐 Konfiguracja API Key

### Windows PowerShell
```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### Linux/Mac Bash
```bash
export OPENAI_API_KEY="sk-..."
```

### W kodzie (niezalecane dla produkcji)
```python
client = GPTClient(api_key="sk-...", model="gpt-4o-mini")
```

## 🎯 GPT Client API

### `GPTClient`

```python
from siwz_mapper.llm import GPTClient

client = GPTClient(
    model="gpt-4o-mini",     # Model OpenAI
    temperature=0.0,          # 0.0-2.0 (0.0 = deterministyczny)
    api_key=None,             # Optional, reads from env
    timeout=60                # Request timeout in seconds
)

# Simple chat interface
response = client.chat(
    system_prompt="You are a classifier...",
    user_prompt="Classify this text..."
)
# Returns: string (assistant's response)
```

### `FakeGPTClient`

```python
from siwz_mapper.llm import FakeGPTClient

# Dla testów - bez wywołań API
fake = FakeGPTClient()

# Custom responses dla specific keywords
fake = FakeGPTClient(responses={
    "specific_keyword": '{"segment_id":"test","label":"general",...}'
})

# Tracking
print(fake.call_count)              # Liczba wywołań
print(fake.last_user_prompt)        # Ostatni prompt
```

## 🧪 Testowanie

System ma kompletne testy z FakeGPTClient:

```bash
# Run tests
pytest tests/test_classify_segments.py -v

# Wszystkie testy działają bez API
# 22 testy, 100% coverage podstawowej funkcjonalności
```

**Testy obejmują:**
- ✅ Walidację modelu Pydantic
- ✅ FakeGPTClient logic
- ✅ Klasyfikację wszystkich typów segmentów
- ✅ Propagację kontekstu
- ✅ Parsing JSON (plain, markdown-wrapped)
- ✅ Error handling (fallback)
- ✅ Realistyczny flow SIWZ

## ⚙️ System Prompt

GPT otrzymuje szczegółowy system prompt w języku polskim, który:
- Opisuje 6 kategorii szczegółowo
- Wyjaśnia zasady domenowe (wariant vs. kolumna cenowa)
- Wymaga strict JSON output
- Zapewnia anti-halucynację (tylko tekst z segmentów)
- Instruuje użycie kontekstu

System prompt zdefiniowany w `src/siwz_mapper/llm/classify_segments.py::SYSTEM_PROMPT`

## 🔄 User Prompt

Dla każdego segmentu budowany jest prompt zawierający:

```
POPRZEDNI SEGMENT (kontekst):
[text preview]

AKTUALNY SEGMENT (do klasyfikacji):
ID: seg_123
Strona: 5
Sekcja: Załącznik nr 2 A
Tekst:
[full segment text]

NASTĘPNY SEGMENT (kontekst):
[text preview]

Wybierz DOKŁADNIE JEDNĄ etykietę...
Zwróć JSON zgodnie ze schematem...
```

## 📈 Integracja z Pipeline

```python
from siwz_mapper.io import load_pdf
from siwz_mapper.preprocess import segment_pdf_blocks
from siwz_mapper.llm import GPTClient, classify_segments

# 1. Load PDF
blocks = load_pdf("siwz.pdf")

# 2. Segment
segments = segment_pdf_blocks(blocks)

# 3. Classify
client = GPTClient()
classifications = classify_segments(segments, client)

# 4. Group by label for further processing
by_label = {}
for seg, cls in zip(segments, classifications):
    by_label.setdefault(cls.label, []).append((seg, cls))

# 5. Process variants
variant_headers = by_label.get("variant_header", [])
variant_bodies = by_label.get("variant_body", [])
prophylaxis = by_label.get("prophylaxis", [])
# ...
```

## ⚠️ Error Handling

System ma robust error handling:

1. **Invalid JSON from GPT**:
   - Próbuje usunąć markdown code blocks
   - Retry z surowszą instrukcją
   - Fallback: `irrelevant` z confidence=0.1

2. **Invalid label**:
   - Pydantic waliduje label
   - ValueError jeśli nie w VALID_LABELS

3. **API failures**:
   - Propagowane do wywołującego
   - Logged z pełnym traceback

## 💡 Best Practices

1. **Zawsze używaj kontekstu**:
   ```python
   # Dobrze
   result = classify_segment(client, seg, prev_text, next_text)
   
   # Słabo (brak kontekstu)
   result = classify_segment(client, seg, "", "")
   ```

2. **Batch processing**:
   ```python
   # Dobrze - single function dla wszystkich
   results = classify_segments(segments, client)
   
   # Słabo - loop manual
   results = [classify_segment(client, s) for s in segments]
   ```

3. **Check confidence**:
   ```python
   if result.confidence < 0.7:
       logger.warning(f"Low confidence for {result.segment_id}")
       # Maybe flag for manual review
   ```

4. **Use FakeGPTClient w testach**:
   ```python
   # Nigdy nie rób prawdziwych API calls w unit tests
   def test_my_function():
       fake_client = FakeGPTClient()
       result = my_function(fake_client, ...)
       assert result.label == "expected"
   ```

## 📝 Przykłady

Zobacz `examples/classify_segments_example.py` dla pełnych przykładów:
- Użycie FakeGPTClient
- Użycie prawdziwego GPT
- Wyświetlanie dostępnych etykiet
- Label distribution

## 🚀 Performance

- **FakeGPTClient**: <1ms per segment (deterministyczny)
- **Real GPT**: ~500-1000ms per segment (zależne od API)
- **Batch**: ~2-3s dla 10 segmentów z real GPT

**Optimization tips:**
- Rozważ `parallel_llm_calls=True` w config (w przyszłości)
- Cache wyników dla identycznych segmentów
- Use async/await dla concurrent calls (TBD)

---

**Status: ✅ Kompletny i przetestowany**  
**Część ekosystemu SIWZ Mapper** 🏥

