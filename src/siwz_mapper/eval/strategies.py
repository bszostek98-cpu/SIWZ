# src/siwz_mapper/eval/strategies.py
from __future__ import annotations

from collections import OrderedDict
from typing import Protocol, List, Optional, Tuple
import json

from pydantic import BaseModel

from .manual_items import VariantItem, ServiceCandidate
from .codebook import ServiceCode


# ----------------------------------------------------------------------
# Wspólne modele i interfejs
# ----------------------------------------------------------------------


class ServiceItemMappingResult(BaseModel):
    """
    Result of mapping for a single VariantItem.
    """
    candidates: list[ServiceCandidate]

    @property
    def predicted_codes(self) -> list[str]:
        return [c.code for c in self.candidates]


class ServiceItemMappingStrategy(Protocol):
    """
    Common interface for all mapping strategies.
    """
    name: str

    def map_item(self, item: VariantItem) -> ServiceItemMappingResult:
        ...


class DummyHeuristicStrategy:
    """
    Minimal baseline strategy – returns no candidates.
    Just to test the pipeline.
    """
    name = "dummy_heuristic"

    def map_item(self, item: VariantItem) -> ServiceItemMappingResult:
        return ServiceItemMappingResult(candidates=[])


class LLMCodeResponse(BaseModel):
    """
    Response model expected from LLM for mapping request.
    """
    codes: List[str]
    reasoning: Optional[str] = None

# ----------------------------------------------------------------------
# Modele odpowiedzi dla wariantu jako całość (V0 / V0.1)
# ----------------------------------------------------------------------


class VariantChunkMapping(BaseModel):
    """
    Jeden kawałek tekstu wariantu + lista kodów.
    """
    text_chunk: str
    codes: List[str]


class VariantChunkMappingResponse(BaseModel):
    """
    Odpowiedź V0.1 – lista kawałków + przypisane kody.
    """
    mappings: List[VariantChunkMapping]
    reasoning: Optional[str] = None


# ----------------------------------------------------------------------
# V0 – cały wariant jako tekst -> jedna lista kodów
# ----------------------------------------------------------------------


class VariantWholeTextMappingStrategyV0:
    """
    V0 – najprostsze podejście:
    - wejście: cały tekst jednego wariantu (string)
    - LLM widzi:
        * pełny tekst wariantu,
        * pełną listę kodów (pogrupowaną kategoria/podkategoria),
    - wyjście: lista kodów dla całego wariantu (bez dzielenia na kawałki).
    """

    name = "variant_whole_text_v0"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        debug_log_prompts: bool = False,
    ) -> None:
        self.client = client
        self.service_codes = service_codes
        self.debug_log_prompts = debug_log_prompts

    def _build_codes_block(
        self,
        codes_for_call: List[ServiceCode],
    ) -> Tuple[str, List[ServiceCode]]:
        """
        Jak w V2/V3 – grupujemy kody po Kategoria / Podkategoria, bez limitów.
        """
        grouped: "OrderedDict[str, OrderedDict[str, List[ServiceCode]]]" = OrderedDict()

        for sc in codes_for_call:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"

            if cat not in grouped:
                grouped[cat] = OrderedDict()
            if sub not in grouped[cat]:
                grouped[cat][sub] = []
            grouped[cat][sub].append(sc)

        lines: List[str] = []
        used_codes: List[ServiceCode] = []

        for cat, subdict in grouped.items():
            lines.append(f"Kategoria: {cat}")
            for sub, codes_in_sub in subdict.items():
                lines.append(f"Podkategoria: {sub}")
                for sc in codes_in_sub:
                    name = sc.name or ""
                    code_line = f"{sc.code} - {name}"
                    lines.append(code_line)
                    used_codes.append(sc)

        block = "\n".join(lines)
        return block, used_codes

    def _build_prompt(self, variant_text: str, codes_block: str) -> tuple[str, str]:
        system_prompt = (
            "You are an assistant that maps Polish medical insurance variant descriptions "
            "from tender documents (SIWZ/OPZ) to internal medical service codes.\n"
            "You receive:\n"
            "- the full text of one insurance variant (Polish),\n"
            "- a list of all possible service codes grouped by category and subcategory.\n\n"
            "Your task is to identify ALL codes that clearly appear in this variant "
            "(either explicitly or implicitly as described services).\n"
            "If nothing fits, return an empty list.\n"
        )

        user_prompt = f"""Oto pełny tekst jednego wariantu z dokumentu (SIWZ / OPZ):

=== TEKST WARIANTU ===
{variant_text}
======================

Masz do dyspozycji poniższą listę kodów usług, pogrupowaną kategoriami i podkategoriami:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Przeczytaj cały tekst wariantu.
2. Zidentyfikuj wszystkie kody z listy, które opisują usługi objęte tym wariantem.
3. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "codes": ["KOD1", "KOD2", ...] }}

Jeżeli nic nie pasuje – zwróć pustą listę kodów.
"""

        return system_prompt, user_prompt

    def map_variant(self, variant_text: str) -> ServiceItemMappingResult:
        """
        Mapuje CAŁY wariant (tekst) do listy kodów.
        """
        codes_block, used_codes = self._build_codes_block(self.service_codes)
        system_prompt, user_prompt = self._build_prompt(variant_text, codes_block)

        if self.debug_log_prompts:
            print("\n[DEBUG PROMPT V0]")
            print("=== SYSTEM PROMPT (V0) ===")
            print(system_prompt)
            print("=== USER PROMPT (V0) ===")
            print(user_prompt)

        # używamy tego samego modelu odpowiedzi co wcześniej
        if hasattr(self.client, "ask_structured"):
            response: LLMCodeResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=LLMCodeResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                response = LLMCodeResponse.model_validate(data)
            except Exception:
                response = LLMCodeResponse(codes=[])

        if self.debug_log_prompts:
            print("=== PARSED RESPONSE (V0) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        # konwersja na ServiceCandidate, żeby mieć spójny wynik
        candidates: list[ServiceCandidate] = []

        for rank, code in enumerate(response.codes, start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)
            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)


# ----------------------------------------------------------------------
# V0.1 – cały wariant -> JSON: kawałek tekstu -> lista kodów
# ----------------------------------------------------------------------


class VariantWholeTextMappingStrategyV01:
    """
    V0.1 – podobnie jak V0, ale:
    - LLM dzieli tekst wariantu na kawałki (np. punkty listy, zdania, logiczne akapity),
    - dla każdego kawałka zwraca listę kodów,
    - struktura JSON w odpowiedzi:

      {
        "mappings": [
          { "text_chunk": "...", "codes": ["KOD1", "KOD2"] },
          { "text_chunk": "...", "codes": [] }
        ]
      }

    Czyli: „z czego co”.
    """

    name = "variant_whole_text_v0_1_chunk_mappings"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        debug_log_prompts: bool = False,
    ) -> None:
        self.client = client
        self.service_codes = service_codes
        self.debug_log_prompts = debug_log_prompts

    def _build_codes_block(
        self,
        codes_for_call: List[ServiceCode],
    ) -> Tuple[str, List[ServiceCode]]:
        """
        To samo grupowanie po kategoriach / podkategoriach.
        """
        grouped: "OrderedDict[str, OrderedDict[str, List[ServiceCode]]]" = OrderedDict()

        for sc in codes_for_call:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"

            if cat not in grouped:
                grouped[cat] = OrderedDict()
            if sub not in grouped[cat]:
                grouped[cat][sub] = []
            grouped[cat][sub].append(sc)

        lines: List[str] = []
        used_codes: List[ServiceCode] = []

        for cat, subdict in grouped.items():
            lines.append(f"Kategoria: {cat}")
            for sub, codes_in_sub in subdict.items():
                lines.append(f"Podkategoria: {sub}")
                for sc in codes_in_sub:
                    name = sc.name or ""
                    code_line = f"{sc.code} - {name}"
                    lines.append(code_line)
                    used_codes.append(sc)

        block = "\n".join(lines)
        return block, used_codes

    def _build_prompt(self, variant_text: str, codes_block: str) -> tuple[str, str]:
        system_prompt = (
            "You are an assistant that maps Polish medical insurance variant descriptions "
            "from tender documents (SIWZ/OPZ) to internal medical service codes.\n"
            "You receive:\n"
            "- the full text of one insurance variant (Polish),\n"
            "- a list of all possible service codes grouped by category and subcategory.\n\n"
            "Your task is to:\n"
            "1) split the variant text into meaningful chunks (e.g. bullet points, sentences or groups of sentences),\n"
            "2) for each chunk, assign zero or more codes from the provided list.\n"
            "If nothing fits for a given chunk, use an empty codes list.\n"
        )

        user_prompt = f"""Oto pełny tekst jednego wariantu z dokumentu (SIWZ / OPZ):

=== TEKST WARIANTU ===
{variant_text}
======================

Masz do dyspozycji poniższą listę kodów usług, pogrupowaną kategoriami i podkategoriami:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Podziel tekst wariantu na kawałki (chunks) – każdy chunk powinien być logiczną jednostką opisu usługi
   (np. jeden punkt listy, jedno wymaganie, grupa blisko powiązanych zdań).
2. Dla każdego kawałka wybierz wszystkie kody z listy, które najlepiej pasują do opisanej w nim usługi.
3. Zwróć wynik w formacie JSON zgodnym z modelem:

{{
  "mappings": [
    {{
      "text_chunk": "dokładny tekst kawałka z wariantu",
      "codes": ["KOD1", "KOD2"]
    }},
    {{
      "text_chunk": "inny fragment tekstu",
      "codes": []
    }}
  ]
}}

Jeżeli w całym wariancie nie ma żadnych usług pasujących do kodów – zwróć pustą listę mappings.
"""

        return system_prompt, user_prompt

    def map_variant(self, variant_text: str) -> VariantChunkMappingResponse:
        """
        Mapuje CAŁY wariant (tekst) do listy (chunk -> kody).
        """
        codes_block, used_codes = self._build_codes_block(self.service_codes)
        system_prompt, user_prompt = self._build_prompt(variant_text, codes_block)

        if self.debug_log_prompts:
            print("\n[DEBUG PROMPT V0.1]")
            print("=== SYSTEM PROMPT (V0.1) ===")
            print(system_prompt)
            print("=== USER PROMPT (V0.1) ===")
            print(user_prompt)

        if hasattr(self.client, "ask_structured"):
            response: VariantChunkMappingResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=VariantChunkMappingResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                response = VariantChunkMappingResponse.model_validate(data)
            except Exception:
                response = VariantChunkMappingResponse(mappings=[])

        if self.debug_log_prompts:
            print("=== PARSED RESPONSE (V0.1) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        return response

# ----------------------------------------------------------------------
# V0.3 – jak V0.1, ale kody idą w N batchach (podajesz ile batchy)
# ----------------------------------------------------------------------


class VariantWholeTextMappingStrategyV03:
    """
    V0.3 – pełny tekst wariantu + kody w batchach, wynik jak w V0.1:

    - wejście:
        * pełny tekst wariantu (string),
        * pełna lista kodów (ServiceCode),
        * num_code_batches – na ile batchy podzielić listę kodów.

    - działanie:
        * dzieli listę kodów na num_code_batches ~równych części,
        * dla każdego batcha:
            - wysyła ten sam tekst wariantu,
            - tylko podzbiór kodów,
            - dostaje VariantChunkMappingResponse (chunks -> kody z tego batcha),
        * scala wyniki:
            - dla każdego text_chunk robi union kodów ze wszystkich batchy.

    - wyjście:
        VariantChunkMappingResponse (tak samo jak w V0.1):
        {
          "mappings": [
            { "text_chunk": "...", "codes": ["KOD1", "KOD2"] },
            ...
          ]
        }
    """

    name = "variant_whole_text_v0_3_chunk_mappings_batched_by_batches"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        num_code_batches: int = 3,
        debug_log_prompts: bool = False,
    ) -> None:
        """
        :param client: gptClient
        :param service_codes: pełna lista kodów z Excela
        :param num_code_batches: na ile batchy podzielić kody (min. 1)
        :param debug_log_prompts: jeśli True, pokazuje prompt + odpowiedź dla pierwszego batcha
        """
        self.client = client
        self.service_codes = service_codes
        self.num_code_batches = max(1, num_code_batches)
        self.debug_log_prompts = debug_log_prompts

    # --- helper: budowa listy kodów (jak w V0.1) ------------------------

    def _build_codes_block(
        self,
        codes_for_call: List[ServiceCode],
    ) -> Tuple[str, List[ServiceCode]]:
        """
        Grupuje kody po Kategoria / Podkategoria – jak w V0.1.
        """
        grouped: "OrderedDict[str, OrderedDict[str, List[ServiceCode]]]" = OrderedDict()

        for sc in codes_for_call:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"

            if cat not in grouped:
                grouped[cat] = OrderedDict()
            if sub not in grouped[cat]:
                grouped[cat][sub] = []
            grouped[cat][sub].append(sc)

        lines: List[str] = []
        used_codes: List[ServiceCode] = []

        for cat, subdict in grouped.items():
            lines.append(f"Kategoria: {cat}")
            for sub, codes_in_sub in subdict.items():
                lines.append(f"Podkategoria: {sub}")
                for sc in codes_in_sub:
                    name = sc.name or ""
                    code_line = f"{sc.code} - {name}"
                    lines.append(code_line)
                    used_codes.append(sc)

        block = "\n".join(lines)
        return block, used_codes

    def _build_prompt(self, variant_text: str, codes_block: str) -> tuple[str, str]:
        """
        Prompt identyczny jak w V0.1, tylko używany wielokrotnie dla różnych batchy kodów.
        """
        system_prompt = (
            "You are an assistant that maps Polish medical insurance variant descriptions "
            "from tender documents (SIWZ/OPZ) to internal medical service codes.\n"
            "You receive:\n"
            "- the full text of one insurance variant (Polish),\n"
            "- a list of possible service codes grouped by category and subcategory.\n\n"
            "Your task is to:\n"
            "1) split the variant text into meaningful chunks (e.g. bullet points, sentences or groups of sentences),\n"
            "2) for each chunk, assign zero or more codes from the provided list.\n"
            "If nothing fits for a given chunk, use an empty codes list.\n"
        )

        user_prompt = f"""Oto pełny tekst jednego wariantu z dokumentu (SIWZ / OPZ):

=== TEKST WARIANTU ===
{variant_text}
======================

Masz do dyspozycji poniższą listę kodów usług, pogrupowaną kategoriami i podkategoriami:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Podziel tekst wariantu na kawałki (chunks) – każdy chunk powinien być logiczną jednostką opisu usługi
   (np. jeden punkt listy, jedno wymaganie, grupa blisko powiązanych zdań).
2. Dla każdego kawałka wybierz wszystkie kody z listy, które najlepiej pasują do opisanej w nim usługi.
3. Zwróć wynik w formacie JSON zgodnym z modelem:

{{
  "mappings": [
    {{
      "text_chunk": "dokładny tekst kawałka z wariantu",
      "codes": ["KOD1", "KOD2"]
    }},
    {{
      "text_chunk": "inny fragment tekstu",
      "codes": []
    }}
  ]
}}

Jeżeli w całym wariancie nie ma żadnych usług pasujących do kodów – zwróć pustą listę mappings.
"""

        return system_prompt, user_prompt

    def _call_llm_for_batch(
        self,
        variant_text: str,
        codes_batch: List[ServiceCode],
        is_first_batch: bool,
    ) -> VariantChunkMappingResponse:
        """
        Wywołuje LLM dla jednego batcha kodów i zwraca odpowiedź w formie VariantChunkMappingResponse.
        """
        codes_block, used_codes = self._build_codes_block(codes_batch)
        system_prompt, user_prompt = self._build_prompt(variant_text, codes_block)

        if self.debug_log_prompts and is_first_batch:
            print("\n[DEBUG PROMPT V0.3 – first batch]")
            print("=== SYSTEM PROMPT (V0.3) ===")
            print(system_prompt)
            print("=== USER PROMPT (V0.3) ===")
            print(user_prompt)

        if hasattr(self.client, "ask_structured"):
            response: VariantChunkMappingResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=VariantChunkMappingResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                response = VariantChunkMappingResponse.model_validate(data)
            except Exception:
                response = VariantChunkMappingResponse(mappings=[])

        if self.debug_log_prompts and is_first_batch:
            print("=== PARSED RESPONSE (V0.3) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        return response

    def map_variant(self, variant_text: str) -> VariantChunkMappingResponse:
        """
        Mapuje CAŁY wariant (tekst) do listy (chunk -> kody),
        dzieląc słownik kodów na num_code_batches części,
        a potem scalamy wyniki po text_chunk.
        """
        total_codes = len(self.service_codes)
        if total_codes == 0:
            return VariantChunkMappingResponse(mappings=[])

        # obliczamy rozmiar batcha: ~równo dzielimy na num_code_batches
        batch_size = max(1, (total_codes + self.num_code_batches - 1) // self.num_code_batches)

        # słownik: text_chunk -> set(kodów)
        from collections import OrderedDict as _OD
        chunk_to_codes: "OrderedDict[str, set[str]]" = _OD()

        batch_index = 0
        for start in range(0, total_codes, batch_size):
            end = min(total_codes, start + batch_size)
            codes_batch = self.service_codes[start:end]
            is_first_batch = (batch_index == 0)
            batch_index += 1

            try:
                resp = self._call_llm_for_batch(
                    variant_text=variant_text,
                    codes_batch=codes_batch,
                    is_first_batch=is_first_batch,
                )
            except Exception as e:
                print(f"[V0.3] Error in batch {batch_index} ({start}:{end}): {e}")
                continue

            for mapping in resp.mappings:
                text = mapping.text_chunk or ""
                codes = mapping.codes or []
                if text not in chunk_to_codes:
                    chunk_to_codes[text] = set()
                chunk_to_codes[text].update(codes)

        # budujemy finalny VariantChunkMappingResponse
        final_mappings: List[VariantChunkMapping] = []
        for text, codes_set in chunk_to_codes.items():
            final_mappings.append(
                VariantChunkMapping(
                    text_chunk=text,
                    codes=sorted(codes_set),
                )
            )

        return VariantChunkMappingResponse(mappings=final_mappings)


# ----------------------------------------------------------------------
# v1 – „płaska” lista kodów, jedna linia = ServiceCode.as_prompt_line()
# ----------------------------------------------------------------------


class SingleLLMMappingStrategyV1:
    """
    v1 – proste podejście:
    - dla każdej pozycji wysyłamy opis usługi + pełną listę kodów (jeden kod = jedna linia)
    - używamy ServiceCode.as_prompt_line()
    - brak grupowania po kategoriach/podkategoriach
    """

    name = "single_llm_all_codes_v1"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        debug_log_prompts: bool = False,
        debug_max_items: int = 1,
    ) -> None:
        """
        :param client: gptClient-like object with ask_structured(system_prompt, user_prompt, response_model)
                       or chat(system_prompt, user_prompt) -> str
        :param service_codes: full list of all available service codes (from Excel)
        :param debug_log_prompts: if True, prints full system/user prompts and responses for first N items
        :param debug_max_items: how many items to log with full prompts
        """
        self.client = client
        self.service_codes = service_codes
        self.debug_log_prompts = debug_log_prompts
        self.debug_max_items = debug_max_items
        self._debug_prompt_items = 0

    def _build_prompt(self, item: VariantItem) -> tuple[str, str]:
        """
        Build (system_prompt, user_prompt) for LLM.
        Uses ALL service_codes without any limits.
        """
        codes_block = "\n".join(c.as_prompt_line() for c in self.service_codes)

        system_prompt = (
            "You are an assistant that maps Polish medical service descriptions "
            "from insurance tender documents (SIWZ/OPZ) to internal service codes.\n"
            "You receive:\n"
            "- a short fragment of text describing a medical service in Polish,\n"
            "- a list of possible service codes with category, subcategory and description.\n\n"
            "Your task is to return ONLY the codes that clearly match the described service.\n"
            "If nothing fits, return an empty list.\n"
        )

        user_prompt = f"""Oto opis usługi medycznej wycięty z dokumentu (SIWZ / OPZ):

=== OPIS USŁUGI ===
{item.service_text}
===================

Dodatkowe informacje o kontekście:
- Nagłówek bloku: {item.block_heading_raw or "-"}
- Kategoria bloku: {item.block_category}
- Czy profilaktyka: {item.is_prophylaxis}
- Czy medycyna pracy: {item.is_occupational_medicine}
- Czy telemedycyna: {item.is_telemedicine}
- Czy tylko cennik: {item.is_pricing_only}

Masz do dyspozycji poniższą listę kodów usług:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Wybierz wszystkie kody, które najlepiej pasują do podanej usługi.
2. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "codes": ["KOD1", "KOD2", ...] }}

Jeżeli nic nie pasuje – zwróć pustą listę kodów.
"""

        return system_prompt, user_prompt

    def map_item(self, item: VariantItem) -> ServiceItemMappingResult:
        system_prompt, user_prompt = self._build_prompt(item)

        # Debug: pokaż wejście dla pierwszych N pozycji
        log_this = self.debug_log_prompts and (self._debug_prompt_items < self.debug_max_items)
        if log_this:
            self._debug_prompt_items += 1
            print(f"\n[DEBUG PROMPT V1 #{self._debug_prompt_items}] "
                  f"service_local_id={item.service_local_id}, variant_id={item.variant_id}")
            print("=== SYSTEM PROMPT (V1) ===")
            print(system_prompt)
            print("=== USER PROMPT (V1) ===")
            print(user_prompt)

        # Prefer ask_structured if available
        if hasattr(self.client, "ask_structured"):
            response: LLMCodeResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=LLMCodeResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                response = LLMCodeResponse.model_validate(data)
            except Exception:
                response = LLMCodeResponse(codes=[])

        if log_this:
            print("=== PARSED RESPONSE (V1) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        candidates: list[ServiceCandidate] = []

        for rank, code in enumerate(response.codes, start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)

            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)


# ----------------------------------------------------------------------
# v2 – grupowanie: Kategoria / Podkategoria (bez limitów, pełne opisy)
# ----------------------------------------------------------------------


class SingleLLMMappingStrategyV2:
    """
    v2 – podejście z grupowaniem:
    - kody pogrupowane po Kategoria / Podkategoria
    - format:

      Kategoria: <category_1>
      Podkategoria: <subcategory_1>
      CODE1 - pełna nazwa usługi
      CODE2 - pełna nazwa usługi
      ...

    - brak ucinania opisów i brak limitu znaków / liczby kodów
    """

    name = "single_llm_all_codes_v2"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        debug: bool = False,
        debug_log_prompts: bool = False,
        debug_max_items: int = 1,
    ) -> None:
        """
        :param client: gptClient-like object with ask_structured(system_prompt, user_prompt, response_model)
                       or chat(system_prompt, user_prompt) -> str
        :param service_codes: full list of all available service codes (from Excel)
        :param debug: if True, prints prompt stats (chars, codes count) once
        :param debug_log_prompts: if True, prints full system/user prompts and responses for first N items
        :param debug_max_items: how many items to log with full prompts
        """
        self.client = client
        self.service_codes = service_codes
        self.debug = debug
        self.debug_log_prompts = debug_log_prompts
        self.debug_max_items = debug_max_items
        self._debug_printed_once = False
        self._debug_prompt_items = 0

    # --- helpers ---------------------------------------------------------

    def _build_codes_block(
        self,
        codes_for_call: List[ServiceCode],
    ) -> Tuple[str, List[ServiceCode]]:
        """
        Build block of codes grouped by category / subcategory.

        Format:

        Kategoria: <category_1>
        Podkategoria: <subcategory_1>
        CODE1 - pełna nazwa usługi
        CODE2 - pełna nazwa usługi
        ...

        Kategoria: <category_2>
        ...

        Bez limitów znaków – używa wszystkich kodów z listy.
        """
        grouped: "OrderedDict[str, OrderedDict[str, List[ServiceCode]]]" = OrderedDict()

        for sc in codes_for_call:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"

            if cat not in grouped:
                grouped[cat] = OrderedDict()
            if sub not in grouped[cat]:
                grouped[cat][sub] = []
            grouped[cat][sub].append(sc)

        lines: List[str] = []
        used_codes: List[ServiceCode] = []

        for cat, subdict in grouped.items():
            lines.append(f"Kategoria: {cat}")
            for sub, codes_in_sub in subdict.items():
                lines.append(f"Podkategoria: {sub}")
                for sc in codes_in_sub:
                    name = sc.name or ""
                    code_line = f"{sc.code} - {name}"
                    lines.append(code_line)
                    used_codes.append(sc)

        block = "\n".join(lines)
        return block, used_codes

    def _build_prompt(self, item: VariantItem, codes_block: str) -> tuple[str, str]:
        """
        Build (system_prompt, user_prompt) for LLM.
        """
        system_prompt = (
            "You are an assistant that maps Polish medical service descriptions "
            "from insurance tender documents (SIWZ/OPZ) to internal service codes.\n"
            "You receive:\n"
            "- a short fragment of text describing a medical service in Polish,\n"
            "- a list of possible service codes grouped by category and subcategory.\n\n"
            "Your task is to return ONLY the codes that clearly match the described service.\n"
            "If nothing fits, return an empty list.\n"
        )

        user_prompt = f"""Oto opis usługi medycznej wycięty z dokumentu (SIWZ / OPZ):

=== OPIS USŁUGI ===
{item.service_text}
===================

Dodatkowe informacje o kontekście:
- Nagłówek bloku: {item.block_heading_raw or "-"}
- Kategoria bloku: {item.block_category}
- Czy profilaktyka: {item.is_prophylaxis}
- Czy medycyna pracy: {item.is_occupational_medicine}
- Czy telemedycyna: {item.is_telemedicine}
- Czy tylko cennik: {item.is_pricing_only}

Masz do dyspozycji poniższą listę kodów usług, pogrupowaną kategoriami i podkategoriami:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Wybierz wszystkie kody, które najlepiej pasują do podanej usługi.
2. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "codes": ["KOD1", "KOD2", ...] }}

Jeżeli nic nie pasuje – zwróć pustą listę kodów.
"""

        return system_prompt, user_prompt

    # --- main API --------------------------------------------------------

    def map_item(self, item: VariantItem) -> ServiceItemMappingResult:
        # Używamy wszystkich kodów (pełny słownik)
        codes_block, used_codes = self._build_codes_block(self.service_codes)

        system_prompt, user_prompt = self._build_prompt(item, codes_block)

        # Debug – statystyki promptu (raz)
        if self.debug and not self._debug_printed_once:
            print("[DEBUG] SingleLLMMappingStrategyV2 prompt stats:")
            print("  service_text chars:", len(item.service_text or ""))
            print("  codes in prompt   :", len(used_codes))
            print("  codes_block chars :", len(codes_block))
            self._debug_printed_once = True

        # Debug – pełne wejście/wyjście dla pierwszych N pozycji
        log_this = self.debug_log_prompts and (self._debug_prompt_items < self.debug_max_items)
        if log_this:
            self._debug_prompt_items += 1
            print(f"\n[DEBUG PROMPT V2 #{self._debug_prompt_items}] "
                  f"service_local_id={item.service_local_id}, variant_id={item.variant_id}")
            print("=== SYSTEM PROMPT (V2) ===")
            print(system_prompt)
            print("=== USER PROMPT (V2) ===")
            print(user_prompt)

        # 4) wołamy klienta
        if hasattr(self.client, "ask_structured"):
            response: LLMCodeResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=LLMCodeResponse,
            )
        else:
            raw = self.client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            try:
                data = json.loads(raw)
                response = LLMCodeResponse.model_validate(data)
            except Exception:
                response = LLMCodeResponse(codes=[])

        if log_this:
            print("=== PARSED RESPONSE (V2) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        # 5) konwersja na ServiceCandidate
        candidates: list[ServiceCandidate] = []

        for rank, code in enumerate(response.codes, start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)

            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)

class SingleLLMMappingStrategyV3:
    """
    v3 – podejście z grupowaniem kodów + dodatkowy kontekst:

    - kody pogrupowane po Kategoria / Podkategoria (jak w V2),
    - kontekst w dwóch warstwach:
      1) bloki główne (po nagłówkach) – do N bloków nad i pod,
      2) sąsiednie segmenty – do M segmentów nad i pod.

    Domyślnie:
    - blocks_above = 5, blocks_below = 5
    - segments_above = 5, segments_below = 5

    Liczby można łatwo zmienić parametrami konstruktora.
    """

    name = "single_llm_all_codes_v3_with_rich_context"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        blocks_above: int = 5,
        blocks_below: int = 5,
        segments_above: int = 5,
        segments_below: int = 5,
        max_examples_per_block: int = 3,
        debug: bool = False,
        debug_log_prompts: bool = False,
        debug_max_items: int = 1,
    ) -> None:
        self.client = client
        self.service_codes = service_codes

        # ile bloków/segmentów nad i pod
        self.blocks_above = blocks_above
        self.blocks_below = blocks_below
        self.segments_above = segments_above
        self.segments_below = segments_below
        self.max_examples_per_block = max_examples_per_block

        self.debug = debug
        self.debug_log_prompts = debug_log_prompts
        self.debug_max_items = debug_max_items
        self._debug_printed_once = False
        self._debug_prompt_items = 0

        # kontekst dla pozycji: key -> tekst
        self._context_by_key: dict[str, str] = {}

    # --- helper: klucz pozycji ------------------------------------------

    def _make_item_key(self, variant_id: str, item: VariantItem) -> str:
        """
        Fallback, gdybyśmy nie mieli source_segment_id – używamy variant_id + service_local_id.
        """
        return f"{variant_id}:{item.service_local_id}"

    # --- przygotowanie kontekstu dla całego dokumentu -------------------

    def prepare(self, manual_doc) -> None:
        """
        Buduje mapę:
            key (source_segment_id lub variant:local_id) -> tekst kontekstu.

        Kontekst zawiera:
        - informacje o blokach głównych nad/pod bieżącym blokiem,
        - informacje o sąsiednich segmentach nad/pod.
        """
        self._context_by_key = {}

        for variant_id, items in manual_doc.variant_items_by_id.items():
            n = len(items)

            # 1) Zbuduj listę bloków głównych w kolejności występowania
            #    (nagłówek bloku może się powtarzać dla wielu pozycji)
            heading_order: list[str] = []
            heading_to_indices: dict[str, list[int]] = {}

            last_heading: Optional[str] = None
            for idx, it in enumerate(items):
                heading = getattr(it, "block_heading_raw", None) or "Brak nagłówka"
                if heading != last_heading:
                    heading_order.append(heading)
                    last_heading = heading
                heading_to_indices.setdefault(heading, []).append(idx)

            # 2) Dla każdej pozycji budujemy kontekst
            for idx, item in enumerate(items):
                lines: list[str] = []

                current_heading = getattr(item, "block_heading_raw", None) or "Brak nagłówka"

                # ---------- A. Kontekst bloków głównych ----------
                lines.append(f"Wariant: {variant_id}")
                lines.append("Kontekst bloków głównych (nagłówki nad/pod):")

                # pozycja bieżącego bloku w heading_order
                try:
                    block_pos = heading_order.index(current_heading)
                except ValueError:
                    block_pos = 0

                start_block = max(0, block_pos - self.blocks_above)
                end_block = min(len(heading_order) - 1, block_pos + self.blocks_below)

                for pos in range(start_block, end_block + 1):
                    heading = heading_order[pos]
                    if pos < block_pos:
                        rel = "blok powyżej"
                    elif pos > block_pos:
                        rel = "blok poniżej"
                    else:
                        rel = "bieżący blok"

                    lines.append(f"- {rel}: {heading}")

                    # przykładowe pozycje z tego bloku
                    example_indices = heading_to_indices.get(heading, [])[: self.max_examples_per_block]
                    for j in example_indices:
                        ex_item = items[j]
                        lines.append(
                            f"  * [{ex_item.service_local_id}] {ex_item.service_text}"
                        )

                # ---------- B. Kontekst sąsiednich segmentów ----------
                lines.append("")
                lines.append(
                    f"Sąsiednie segmenty (do {self.segments_above} nad i "
                    f"{self.segments_below} pod bieżącą pozycją):"
                )

                # segmenty nad
                start_seg = max(0, idx - self.segments_above)
                above_items = items[start_seg:idx]
                if above_items:
                    lines.append("Poprzednie pozycje w tym wariancie:")
                    for it_above in above_items:
                        lines.append(
                            f"- [{it_above.service_local_id}] {it_above.service_text}"
                        )

                # segmenty pod
                end_seg = min(n, idx + 1 + self.segments_below)
                below_items = items[idx + 1:end_seg]
                if below_items:
                    lines.append("Następne pozycje w tym wariancie:")
                    for it_below in below_items:
                        lines.append(
                            f"- [{it_below.service_local_id}] {it_below.service_text}"
                        )

                context_text = "\n".join(lines)

                # klucz: preferujemy source_segment_id, fallback na variant:local_id
                source_id = getattr(item, "source_segment_id", None)
                if source_id:
                    key = source_id
                else:
                    key = self._make_item_key(variant_id, item)

                self._context_by_key[key] = context_text

    def _lookup_context_for_item(self, item: VariantItem) -> str:
        """
        Zwraca tekst kontekstu dla danej pozycji, jeśli udało się go zbudować.
        """
        source_id = getattr(item, "source_segment_id", None)
        if source_id and source_id in self._context_by_key:
            return self._context_by_key[source_id]

        variant_id = getattr(item, "variant_id", None) or "UNKNOWN"
        key = self._make_item_key(variant_id, item)
        return self._context_by_key.get(key, "")

    # --- helper: budowa listy kodów jak w V2 ----------------------------

    def _build_codes_block(
        self,
        codes_for_call: List[ServiceCode],
    ) -> Tuple[str, List[ServiceCode]]:
        """
        Jak w V2 – grupujemy Kategoria / Podkategoria, bez limitów.
        """
        grouped: "OrderedDict[str, OrderedDict[str, List[ServiceCode]]]" = OrderedDict()

        for sc in codes_for_call:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"

            if cat not in grouped:
                grouped[cat] = OrderedDict()
            if sub not in grouped[cat]:
                grouped[cat][sub] = []
            grouped[cat][sub].append(sc)

        lines: List[str] = []
        used_codes: List[ServiceCode] = []

        for cat, subdict in grouped.items():
            lines.append(f"Kategoria: {cat}")
            for sub, codes_in_sub in subdict.items():
                lines.append(f"Podkategoria: {sub}")
                for sc in codes_in_sub:
                    name = sc.name or ""
                    code_line = f"{sc.code} - {name}"
                    lines.append(code_line)
                    used_codes.append(sc)

        block = "\n".join(lines)
        return block, used_codes

    # --- budowa promptu -------------------------------------------------

    def _build_prompt(self, item: VariantItem, codes_block: str, context_text: str) -> tuple[str, str]:
        """
        Build (system_prompt, user_prompt) for LLM – jak V2, ale z sekcją „Dodatkowy kontekst”.
        """
        system_prompt = (
            "You are an assistant that maps Polish medical service descriptions "
            "from insurance tender documents (SIWZ/OPZ) to internal service codes.\n"
            "You receive:\n"
            "- a short fragment of text describing a medical service in Polish,\n"
            "- a list of possible service codes grouped by category and subcategory,\n"
            "- additional local context around this fragment: neighbouring blocks and segments.\n\n"
            "Your task is to return ONLY the codes that clearly match the described service.\n"
            "If nothing fits, return an empty list.\n"
        )

        extra_context_block = ""
        if context_text:
            extra_context_block = f"""

=== DODATKOWY KONTEKST Z DOKUMENTU ===
{context_text}
=====================================
"""

        user_prompt = f"""Oto opis usługi medycznej wycięty z dokumentu (SIWZ / OPZ):

=== OPIS USŁUGI ===
{item.service_text}
===================

Dodatkowe informacje o segmencie:
- Nagłówek bloku: {item.block_heading_raw or "-"}
- Kategoria bloku: {item.block_category}
- Czy profilaktyka: {item.is_prophylaxis}
- Czy medycyna pracy: {item.is_occupational_medicine}
- Czy telemedycyna: {item.is_telemedicine}
- Czy tylko cennik: {item.is_pricing_only}
{extra_context_block}

Masz do dyspozycji poniższą listę kodów usług, pogrupowaną kategoriami i podkategoriami:

=== LISTA KODÓW ===
{codes_block}
===================

Zadanie:
1. Wykorzystaj dodatkowy kontekst i listę kodów, aby wybrać wszystkie kody,
   które najlepiej pasują do podanej usługi.
2. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "codes": ["KOD1", "KOD2", ...] }}

Jeżeli nic nie pasuje – zwróć pustą listę kodów.
"""

        return system_prompt, user_prompt

    # --- główne API -----------------------------------------------------

    def map_item(self, item: VariantItem) -> ServiceItemMappingResult:
        # pełny słownik kodów
        codes_block, used_codes = self._build_codes_block(self.service_codes)

        context_text = self._lookup_context_for_item(item)
        system_prompt, user_prompt = self._build_prompt(item, codes_block, context_text)

        # Debug – statystyki promptu (raz)
        if self.debug and not self._debug_printed_once:
            print("[DEBUG] SingleLLMMappingStrategyV3 prompt stats:")
            print("  service_text chars:", len(item.service_text or ""))
            print("  codes in prompt   :", len(used_codes))
            print("  codes_block chars :", len(codes_block))
            print("  context chars     :", len(context_text or ""))
            self._debug_printed_once = True

        # Debug – pełne prompty dla pierwszych N
        log_this = self.debug_log_prompts and (self._debug_prompt_items < self.debug_max_items)
        if log_this:
            self._debug_prompt_items += 1
            print(f"\n[DEBUG PROMPT V3 #{self._debug_prompt_items}] "
                  f"service_local_id={item.service_local_id}, variant_id={getattr(item, 'variant_id', 'UNKNOWN')}")
            print("=== SYSTEM PROMPT (V3) ===")
            print(system_prompt)
            print("=== USER PROMPT (V3) ===")
            print(user_prompt)

        # wywołanie LLM
        if hasattr(self.client, "ask_structured"):
            response: LLMCodeResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=LLMCodeResponse,
            )
        else:
            raw = self.client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            try:
                data = json.loads(raw)
                response = LLMCodeResponse.model_validate(data)
            except Exception:
                response = LLMCodeResponse(codes=[])

        if log_this:
            print("=== PARSED RESPONSE (V3) ===")
            try:
                print(response.model_dump_json(indent=2, ensure_ascii=False))
            except Exception:
                print(response)

        candidates: list[ServiceCandidate] = []

        for rank, code in enumerate(response.codes, start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)

            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)


def split_text_into_chunks(text: str, max_chunk_chars: int = 800) -> List[str]:
    """
    Bardzo prosty chunker:
    - dzieli tekst po pustych liniach (\n\n) na paragrafy,
    - potem składa z nich kawałki nie dłuższe niż max_chunk_chars.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p)
        # jeśli pojedynczy paragraf > max_chunk_chars, wrzucamy go jako osobny chunk
        if p_len > max_chunk_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.append(p)
            continue

        if current_len + p_len + (2 if current else 0) <= max_chunk_chars:
            current.append(p)
            current_len += p_len + (2 if current else 0)
        else:
            # zamykamy aktualny chunk i zaczynamy nowy
            if current:
                chunks.append("\n\n".join(current))
            current = [p]
            current_len = p_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks

class CategoryRouterResponse(BaseModel):
    """
    Odpowiedź routera kategorii:
    - categories: lista nazw kategorii, które powinny obsłużyć ten fragment
    """
    categories: List[str]
    reasoning: Optional[str] = None

class CategoryRouterLLM:
    """
    Router LLM:
    - dostaje fragment tekstu (chunk),
    - widzi listę kategorii + kilka przykładowych usług z każdej,
    - wybiera kategorie, które powinny dostać ten fragment.
    - max_categories_per_chunk:
        * None  -> brak twardego limitu, tylko miękka sugestia w promptach,
        * liczba -> twardy limit (awaryjnie, jeśli kiedyś będziesz chciał).
    """

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        max_categories_per_chunk: Optional[int] = None,
        examples_per_category: int = 3,
        debug_log_prompts: bool = False,
    ) -> None:
        """
        :param client: gptClient
        :param service_codes: pełna lista kodów
        :param max_categories_per_chunk:
            - None  -> brak twardego limitu, model może zwrócić dowolną liczbę kategorii,
            - liczba (np. 5) -> twardy limit, przycinamy nadmiarowe kategorie.
        :param examples_per_category: ile usług (nazw) pokazać jako przykład na kategorię
        :param debug_log_prompts: czy logować prompt (tylko dla pierwszego chunku)
        """
        self.client = client
        self.max_categories_per_chunk = max_categories_per_chunk
        self.examples_per_category = examples_per_category
        self.debug_log_prompts = debug_log_prompts
        self._debug_used = False

        # grupujemy kody po kategorii i bierzemy przykłady nazw usług
        cat_to_examples: dict[str, List[str]] = {}
        for sc in service_codes:
            cat = sc.category or "Brak kategorii"
            name = sc.name or ""
            if not name:
                continue
            cat_to_examples.setdefault(cat, [])
            if len(cat_to_examples[cat]) < self.examples_per_category:
                cat_to_examples[cat].append(name)

        self.category_examples = cat_to_examples
        self.categories = list(cat_to_examples.keys())

    def _build_prompt(self, chunk_text: str) -> tuple[str, str]:
        """
        Buduje prompt z listą kategorii i przykładowych usług.
        """
        lines: List[str] = []
        for cat, examples in self.category_examples.items():
            lines.append(f"Kategoria: {cat}")
            if examples:
                lines.append("Przykładowe usługi:")
                for ex in examples:
                    lines.append(f"  - {ex}")
            lines.append("")  # pusta linia między kategoriami

        categories_block = "\n".join(lines)

        # część systemowa – zależy od tego, czy mamy twardy limit
        if self.max_categories_per_chunk is None:
            system_prompt = (
                "You are an assistant that routes Polish medical insurance text fragments (chunks) "
                "from tender documents (SIWZ/OPZ) to specialized category agents.\n"
                "You receive:\n"
                "- one text fragment in Polish,\n"
                "- a list of all possible service categories with a few example services for each.\n\n"
                "Your task is to choose all categories that are relevant for this fragment.\n"
                "In practice, most fragments match 0–3 categories, but if more categories are clearly relevant, "
                "you may include all of them.\n"
            )
        else:
            system_prompt = (
                "You are an assistant that routes Polish medical insurance text fragments (chunks) "
                "from tender documents (SIWZ/OPZ) to specialized category agents.\n"
                "You receive:\n"
                "- one text fragment in Polish,\n"
                "- a list of all possible service categories with a few example services for each.\n\n"
                f"Your task is to choose ONLY those categories that are relevant for this fragment, "
                f"and return at most {self.max_categories_per_chunk} categories.\n"
            )

        user_prompt = f"""Oto fragment tekstu z dokumentu (SIWZ / OPZ):

=== FRAGMENT TEKSTU ===
{chunk_text}
=======================

Masz do dyspozycji następujące kategorie usług medycznych z przykładowymi usługami:

=== KATEGORIE I PRZYKŁADY ===
{categories_block}
============================

Zadanie:
1. Zastanów się, które kategorie pasują do treści fragmentu (mogą być 0, 1 lub kilka).
2. Wybierz wszystkie kategorie, które są rzeczywiście istotne dla tego fragmentu.
3. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "categories": ["Nazwa kategorii 1", "Nazwa kategorii 2", ...] }}

Jeżeli fragment nie dotyczy żadnej kategorii – zwróć pustą listę categories.
"""

        return system_prompt, user_prompt

    def select_categories_for_chunk(self, chunk_text: str) -> List[str]:
        """
        Zwraca listę nazw kategorii, które powinny obsłużyć dany chunk.
        """
        system_prompt, user_prompt = self._build_prompt(chunk_text)

        if self.debug_log_prompts and not self._debug_used:
            self._debug_used = True
            print("\n[DEBUG CategoryRouterLLM – first chunk]")
            print("=== SYSTEM PROMPT ===")
            print(system_prompt)
            print("=== USER PROMPT ===")
            print(user_prompt)

        if hasattr(self.client, "ask_structured"):
            resp: CategoryRouterResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=CategoryRouterResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                resp = CategoryRouterResponse.model_validate(data)
            except Exception:
                resp = CategoryRouterResponse(categories=[])

        if self.debug_log_prompts and self._debug_used:
            print("=== PARSED ROUTER RESPONSE ===")
            try:
                print(resp.model_dump_json(indent=2))
            except Exception:
                print(resp)

        # tylko kategorie, które rzeczywiście istnieją
        selected = [c for c in resp.categories if c in self.category_examples]

        # jeśli NIE mamy limitu -> zwracamy wszystko, co model podał (przefiltrowane)
        if self.max_categories_per_chunk is None:
            return selected

        # jeśli mamy twardy limit -> przycinamy
        if len(selected) > self.max_categories_per_chunk:
            selected = selected[: self.max_categories_per_chunk]

        return selected


class CategoryChunkAgent:
    """
    Agent wyspecjalizowany w jednej kategorii kodów.

    - ma listę ServiceCode tylko dla danej kategorii,
    - dostaje JEDEN kawałek tekstu (chunk),
    - zwraca listę kodów pasujących do tego chunku.
    """

    def __init__(
        self,
        client,
        category: str,
        service_codes: List[ServiceCode],
        name: Optional[str] = None,
        debug_log_prompts: bool = False,
        debug_max_chunks: int = 1,
    ) -> None:
        self.client = client
        self.category = category
        self.service_codes = service_codes
        self.name = name or f"CategoryAgent[{category}]"
        self.debug_log_prompts = debug_log_prompts
        self.debug_max_chunks = debug_max_chunks
        self._debug_chunks_shown = 0

    def _build_codes_block(self, codes_for_call: List[ServiceCode]) -> str:
        """
        Buduje listę kodów w ramach tej kategorii,
        pogrupowaną po Podkategoriach.
        """
        grouped: "OrderedDict[str, List[ServiceCode]]" = OrderedDict()

        for sc in codes_for_call:
            sub = sc.subcategory or "Brak podkategorii"
            if sub not in grouped:
                grouped[sub] = []
            grouped[sub].append(sc)

        lines: List[str] = []
        for sub, codes_in_sub in grouped.items():
            lines.append(f"Podkategoria: {sub}")
            for sc in codes_in_sub:
                name = sc.name or ""
                lines.append(f"{sc.code} - {name}")
        return "\n".join(lines)

    def _build_prompt(
        self,
        chunk_text: str,
        codes_for_call: List[ServiceCode],
    ) -> tuple[str, str]:
        codes_block = self._build_codes_block(codes_for_call)

        system_prompt = (
            "You are an assistant that maps Polish medical service descriptions "
            f"to internal service codes in ONE specific category: {self.category}.\n"
            "You receive:\n"
            "- a short fragment of text (chunk) from an insurance variant (Polish),\n"
            "- a list of possible service codes in this category, grouped by subcategory.\n\n"
            "Your task is to return ONLY the codes from this list that clearly match "
            "the described services in this fragment. If nothing fits, return an empty list.\n"
        )

        user_prompt = f"""Oto fragment tekstu (chunk) z dokumentu SIWZ / OPZ:

=== FRAGMENT TEKSTU ===
{chunk_text}
=======================

Jesteś agentem wyspecjalizowanym w kategorii: {self.category}.

Masz do dyspozycji listę kodów w tej kategorii, pogrupowaną po podkategoriach:

=== KODY W TEJ KATEGORII ===
{codes_block}
============================

Zadanie:
1. Przeczytaj fragment tekstu.
2. Wybierz wszystkie kody, które najlepiej pasują do opisanych w nim usług.
3. Zwróć wynik w formacie JSON zgodnym z modelem:
   {{ "codes": ["KOD1", "KOD2", ...] }}

Jeżeli nic nie pasuje – zwróć pustą listę kodów.
"""

        return system_prompt, user_prompt

    def map_chunk(
        self,
        chunk_text: str,
        allowed_subcategories: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Mapuje JEDEN fragment tekstu do listy kodów w tej kategorii.

        :param allowed_subcategories:
            - None          -> używa wszystkich podkategorii tej kategorii,
            - lista nazw    -> filtruje kody tylko do tych podkategorii;
                               jeśli filtr da pustkę, wraca do wszystkich kodów (fallback).
        """
        codes_for_call = self.service_codes

        if allowed_subcategories:
            allowed_norm = {
                (s or "").strip().lower() for s in allowed_subcategories if (s or "").strip()
            }
            filtered = [
                sc
                for sc in self.service_codes
                if (sc.subcategory or "Brak podkategorii").strip().lower() in allowed_norm
            ]
            # jeśli filtr usunął wszystko, wolimy nie stracić coverage – fallback do pełnej kategorii
            if filtered:
                codes_for_call = filtered

        system_prompt, user_prompt = self._build_prompt(chunk_text, codes_for_call)

        log_this = self.debug_log_prompts and (self._debug_chunks_shown < self.debug_max_chunks)
        if log_this:
            self._debug_chunks_shown += 1
            print(f"\n[DEBUG {self.name} – chunk #{self._debug_chunks_shown}]")
            print("=== SYSTEM PROMPT ===")
            print(system_prompt)
            print("=== USER PROMPT ===")
            print(user_prompt)

        if hasattr(self.client, "ask_structured"):
            response: LLMCodeResponse = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=LLMCodeResponse,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                response = LLMCodeResponse.model_validate(data)
            except Exception:
                response = LLMCodeResponse(codes=[])

        if log_this:
            print("=== PARSED RESPONSE ===")
            try:
                print(response.model_dump_json(indent=2))
            except Exception:
                print(response)

        return response.codes or []

class PlannedChunkCategory(BaseModel):
    """
    Jedno przypisanie kategorii w planie:
    - category: nazwa kategorii zgodna z słownikiem (ServiceCode.category),
    - subcategories: lista nazw podkategorii (ServiceCode.subcategory),
                     może być pusta -> użyj całej kategorii.
    """
    category: str
    subcategories: List[str] = []


class PlannedChunk(BaseModel):
    """
    Jeden zaplanowany fragment tekstu w wariancie.
    """
    chunk_id: str
    text_chunk: str
    categories: List[PlannedChunkCategory] = []


class VariantPlan(BaseModel):
    """
    Plan wariantu:
    - lista fragmentów (chunks),
    - każdy chunk ma tekst i przypisane kategorie/podkategorie.
    """
    chunks: List[PlannedChunk]



class MASVariantMappingStrategyV1:
    """
    MASv1 – Multi-Agent System z routerem kategorii (globalna lista kodów).

    - Agent nadrzędny:
        * dzieli tekst wariantu na chunki (split_text_into_chunks),
        * dla każdego chunku używa routera LLM, aby wybrać kategorie,
        * wysyła chunk TYLKO do agentów tych kategorii.

    - Agenci-kategorii:
        * jak w MASv0 – każdy ma swoją listę kodów (1 kategoria),
        * mapują chunk -> kody w swojej kategorii.

    - Wynik:
        * jedna lista kodów (union) dla całego wariantu.
    """

    name = "mas_v1_union_codes_with_router"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        max_chunk_chars: int = 800,
        router_max_categories_per_chunk: Optional[int] = None,
        router_examples_per_category: int = 3,
        debug_log_prompts_router: bool = False,
        debug_log_prompts_agents: bool = False,
    ) -> None:
        self.client = client
        self.service_codes = service_codes
        self.max_chunk_chars = max_chunk_chars
        self.debug_log_prompts_agents = debug_log_prompts_agents

        # agenci-kategorii
        self.category_agents: dict[str, CategoryChunkAgent] = self._build_category_agents()

        # router kategorii
        self.router = CategoryRouterLLM(
            client=client,
            service_codes=service_codes,
            max_categories_per_chunk=router_max_categories_per_chunk,  # None = brak limitu
            examples_per_category=router_examples_per_category,
            debug_log_prompts=debug_log_prompts_router,
        )

    # reszta klasy (map_variant itd.) bez zmian


    def _build_category_agents(self) -> dict[str, CategoryChunkAgent]:
        category_to_codes: dict[str, List[ServiceCode]] = {}
        for sc in self.service_codes:
            cat = sc.category or "Brak kategorii"
            category_to_codes.setdefault(cat, []).append(sc)

        agents: dict[str, CategoryChunkAgent] = {}
        for cat, codes in category_to_codes.items():
            agents[cat] = CategoryChunkAgent(
                client=self.client,
                category=cat,
                service_codes=codes,
                debug_log_prompts=self.debug_log_prompts_agents,
                debug_max_chunks=1,
            )
        return agents

    def map_variant(self, variant_text: str) -> ServiceItemMappingResult:
        chunks = split_text_into_chunks(variant_text, max_chunk_chars=self.max_chunk_chars)
        if not chunks:
            return ServiceItemMappingResult(candidates=[])

        all_codes: set[str] = set()

        for i, chunk in enumerate(chunks, start=1):
            print(f"[MASv1] Chunk {i}/{len(chunks)} (len={len(chunk)} chars)")

            # 1) router wybiera kategorie
            selected_categories = self.router.select_categories_for_chunk(chunk)
            if not selected_categories:
                continue

            print(f"[MASv1]  Router wybrał kategorie: {selected_categories}")

            # 2) chunk idzie tylko do wybranych agentów
            for cat in selected_categories:
                agent = self.category_agents.get(cat)
                if agent is None:
                    continue
                try:
                    codes = agent.map_chunk(chunk)
                except Exception as e:
                    print(f"[MASv1]  Błąd w agencie kategorii {cat}: {e}")
                    codes = []
                all_codes.update(codes)

        # konwersja na ServiceCandidate (jak zwykle)
        candidates: list[ServiceCandidate] = []
        for rank, code in enumerate(sorted(all_codes), start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)
            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)

class MASVariantMappingStrategyV11:
    """
    MASv1.1 – Multi-Agent System z routerem kategorii (chunk -> kody, JSON).
    """

    name = "mas_v1_1_chunk_json_with_router"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        max_chunk_chars: int = 800,
        router_max_categories_per_chunk: Optional[int] = None,
        router_examples_per_category: int = 3,
        debug_log_prompts_router: bool = False,
        debug_log_prompts_agents: bool = False,
    ) -> None:
        self.client = client
        self.service_codes = service_codes
        self.max_chunk_chars = max_chunk_chars
        self.debug_log_prompts_agents = debug_log_prompts_agents

        # agenci-kategorii – tworzymy tak samo jak w V1
        self.category_agents: dict[str, CategoryChunkAgent] = MASVariantMappingStrategyV1(
            client=client,
            service_codes=service_codes,
            max_chunk_chars=max_chunk_chars,
            router_max_categories_per_chunk=router_max_categories_per_chunk,
            router_examples_per_category=router_examples_per_category,
            debug_log_prompts_router=debug_log_prompts_router,
            debug_log_prompts_agents=debug_log_prompts_agents,
        ).category_agents

        # osobny router (żeby nie zależeć od instancji MASv1)
        self.router = CategoryRouterLLM(
            client=client,
            service_codes=service_codes,
            max_categories_per_chunk=router_max_categories_per_chunk,  # None = brak limitu
            examples_per_category=router_examples_per_category,
            debug_log_prompts=debug_log_prompts_router,
        )

    def map_variant(self, variant_text: str) -> VariantChunkMappingResponse:
        chunks = split_text_into_chunks(variant_text, max_chunk_chars=self.max_chunk_chars)
        if not chunks:
            return VariantChunkMappingResponse(mappings=[])

        mappings: List[VariantChunkMapping] = []

        for i, chunk in enumerate(chunks, start=1):
            print(f"[MASv1.1] Chunk {i}/{len(chunks)} (len={len(chunk)} chars)")

            selected_categories = self.router.select_categories_for_chunk(chunk)
            if not selected_categories:
                mappings.append(
                    VariantChunkMapping(text_chunk=chunk, codes=[])
                )
                continue

            print(f"[MASv1.1]  Router wybrał kategorie: {selected_categories}")

            codes_for_chunk: set[str] = set()

            for cat in selected_categories:
                agent = self.category_agents.get(cat)
                if agent is None:
                    continue
                try:
                    codes = agent.map_chunk(chunk)
                except Exception as e:
                    print(f"[MASv1.1]  Błąd w agencie kategorii {cat}: {e}")
                    codes = []
                codes_for_chunk.update(codes)

            mappings.append(
                VariantChunkMapping(
                    text_chunk=chunk,
                    codes=sorted(codes_for_chunk),
                )
            )

        return VariantChunkMappingResponse(mappings=mappings)

class VariantPlannerRouterLLM:
    """
    Planner + router V2:

    - Dostaje cały tekst wariantu.
    - Dostaje taksonomię:
        Kategoria -> Podkategoria -> przykładowe usługi.
    - Ma za zadanie:
        1) podzielić tekst na sensowne fragmenty (chunks),
        2) dla każdego fragmentu przypisać kategorie i podkategorie
           (bez ograniczania liczby kategorii na siłę).

    Zwraca obiekt VariantPlan (lista PlannedChunk).
    """

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        max_examples_per_category: int = 5,
        max_examples_per_subcategory: int = 3,
        debug_log_prompts: bool = False,
    ) -> None:
        self.client = client
        self.debug_log_prompts = debug_log_prompts
        self._debug_used = False

        # budujemy taksonomię: category -> subcategory -> przykładowe usługi
        taxonomy: dict[str, dict[str, List[str]]] = {}

        for sc in service_codes:
            cat = sc.category or "Brak kategorii"
            sub = sc.subcategory or "Brak podkategorii"
            name = sc.name or ""
            if not name:
                continue

            taxonomy.setdefault(cat, {})
            taxonomy[cat].setdefault(sub, [])

            if len(taxonomy[cat][sub]) < max_examples_per_subcategory:
                taxonomy[cat][sub].append(name)

        # opcjonalnie moglibyśmy przycinać liczbę podkategorii na kategorię,
        # ale na razie tego nie robimy – max_examples_per_category możesz dodać później.
        self.taxonomy = taxonomy

    def _build_taxonomy_block(self) -> str:
        lines: List[str] = []
        for cat, subdict in self.taxonomy.items():
            lines.append(f"Kategoria: {cat}")
            for sub, examples in subdict.items():
                lines.append(f"  Podkategoria: {sub}")
                if examples:
                    lines.append("    Przykładowe usługi:")
                    for ex in examples:
                        lines.append(f"      - {ex}")
            lines.append("")  # pusta linia między kategoriami
        return "\n".join(lines)

    def _build_prompt(self, variant_text: str) -> tuple[str, str]:
        taxonomy_block = self._build_taxonomy_block()

        system_prompt = (
            "You are an assistant that plans and routes Polish medical insurance variant descriptions "
            "from tender documents (SIWZ/OPZ) to specialized category agents.\n"
            "You receive:\n"
            "- the full text of one insurance variant (Polish),\n"
            "- a taxonomy of medical services: categories, subcategories and example services.\n\n"
            "Your task is to:\n"
            "1) Split the variant text into meaningful chunks (fragments). Each chunk should be a coherent unit:\n"
            "   - one bullet point,\n"
            "   - one numbered item,\n"
            "   - or a small group of closely related sentences.\n"
            "   Avoid extremely long chunks; if needed, break long sections into smaller ones (~1–5 sentences).\n"
            "2) For each chunk, assign zero or more categories from the taxonomy, and for each category, "
            "   assign zero or more subcategories that are clearly relevant.\n"
            "3) Do NOT invent new category or subcategory names – only use names that appear in the taxonomy.\n"
            "4) Return the result as JSON matching the VariantPlan model.\n"
        )

        user_prompt = f"""Oto pełny tekst jednego wariantu z dokumentu (SIWZ / OPZ):

=== TEKST WARIANTU ===
{variant_text}
======================

Masz do dyspozycji taksonomię usług medycznych:

=== TAKSONOMIA (KATEGORIA -> PODKATEGORIA -> PRZYKŁADOWE USŁUGI) ===
{taxonomy_block}
===================================================================

Zadanie:
1. Podziel tekst na fragmenty (chunks), tak aby każdy fragment był logiczną jednostką opisu usług
   (np. jeden punkt listy, jedno wymaganie, grupa blisko powiązanych zdań).
2. Dla każdego fragmentu wybierz wszystkie pasujące kategorie. Dla każdej kategorii wybierz pasujące podkategorie.
3. Zwróć wynik w formacie JSON zgodnym z modelem VariantPlan:

{{
  "chunks": [
    {{
      "chunk_id": "c1",
      "text_chunk": "dokładny fragment tekstu wariantu...",
      "categories": [
        {{
          "category": "Nazwa kategorii dokładnie jak w taksonomii",
          "subcategories": ["Podkategoria 1", "Podkategoria 2"]
        }}
      ]
    }},
    {{
      "chunk_id": "c2",
      "text_chunk": "...",
      "categories": []
    }}
  ]
}}

Zasady:
- Jeśli fragment nie dotyczy żadnych usług medycznych z taksonomii – użyj pustej listy categories.
- Nie dodawaj żadnych pól poza chunk_id, text_chunk, categories, category, subcategories.
- Używaj dokładnie tych nazw kategorii i podkategorii, które występują w taksonomii powyżej.
"""

        return system_prompt, user_prompt

    def plan_variant(self, variant_text: str) -> VariantPlan:
        """
        Zwraca VariantPlan z listą chunków i przypisań kategorii/podkategorii.
        """
        system_prompt, user_prompt = self._build_prompt(variant_text)

        if self.debug_log_prompts and not self._debug_used:
            self._debug_used = True
            print("\n[DEBUG VariantPlannerRouterLLM – first call]")
            print("=== SYSTEM PROMPT ===")
            print(system_prompt)
            print("=== USER PROMPT ===")
            print(user_prompt)

        if hasattr(self.client, "ask_structured"):
            plan: VariantPlan = self.client.ask_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=VariantPlan,
            )
        else:
            raw = self.client.chat(system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                data = json.loads(raw)
                plan = VariantPlan.model_validate(data)
            except Exception:
                plan = VariantPlan(chunks=[])

        if self.debug_log_prompts:
            print("=== PARSED VARIANT PLAN ===")
            try:
                print(plan.model_dump_json(indent=2))
            except Exception:
                print(plan)

        return plan


class MASVariantMappingStrategyV2:
    """
    MASv2 – Multi-Agent System z plannerem wariantu.

    Workflow:
    1) VariantPlannerRouterLLM:
        - bierze cały tekst wariantu + taksonomię,
        - dzieli tekst na chunki,
        - dla każdego chunku przypisuje kategorie i podkategorie.

    2) Dla każdego chunku:
        - dla każdej przypisanej kategorii:
            * szukamy agenta-kategorii,
            * wywołujemy go z tekstem chunku i opcjonalną listą podkategorii,
            * agent zwraca kody z odpowiedniej (pod)części słownika.

    3) Wynik:
        - globalne union kodów dla całego wariantu (ServiceItemMappingResult).
    """

    name = "mas_v2_union_codes_with_planner"

    def __init__(
        self,
        client,
        service_codes: List[ServiceCode],
        planner_max_examples_per_category: int = 5,
        planner_max_examples_per_subcategory: int = 3,
        debug_log_prompts_planner: bool = False,
        debug_log_prompts_agents: bool = False,
        debug_max_agents_to_log: Optional[int] = None,
    ) -> None:
        self.client = client
        self.service_codes = service_codes
        self.debug_log_prompts_agents = debug_log_prompts_agents
        self.debug_max_agents_to_log = debug_max_agents_to_log
        self._debug_agents_logged = 0  # licznik, ilu agentów ma włączony debug

        # agenci-kategorii
        self.category_agents: dict[str, CategoryChunkAgent] = self._build_category_agents()

        # planner/router
        self.planner = VariantPlannerRouterLLM(
            client=client,
            service_codes=service_codes,
            max_examples_per_category=planner_max_examples_per_category,
            max_examples_per_subcategory=planner_max_examples_per_subcategory,
            debug_log_prompts=debug_log_prompts_planner,
        )

    def _build_category_agents(self) -> dict[str, CategoryChunkAgent]:
        from collections import OrderedDict  # jeśli nie masz, dodaj na górze pliku

        category_to_codes: dict[str, List[ServiceCode]] = {}
        for sc in self.service_codes:
            cat = sc.category or "Brak kategorii"
            category_to_codes.setdefault(cat, []).append(sc)

        agents: dict[str, CategoryChunkAgent] = {}

        for cat, codes in category_to_codes.items():
            # Czy dla tego agenta włączamy debug promptów?
            log_for_this = False
            if self.debug_log_prompts_agents:
                if (self.debug_max_agents_to_log is None) or (
                    self._debug_agents_logged < self.debug_max_agents_to_log
                ):
                    log_for_this = True
                    self._debug_agents_logged += 1

            agents[cat] = CategoryChunkAgent(
                client=self.client,
                category=cat,
                service_codes=codes,
                debug_log_prompts=log_for_this,
                debug_max_chunks=1,  # każdy agent pokaże prompt tylko dla pierwszego chunku
            )

        return agents

    def map_variant(self, variant_text: str) -> ServiceItemMappingResult:
        plan = self.planner.plan_variant(variant_text)

        if not plan.chunks:
            return ServiceItemMappingResult(candidates=[])

        all_codes: set[str] = set()

        for i, chunk in enumerate(plan.chunks, start=1):
            print(f"[MASv2] Chunk {i}/{len(plan.chunks)} (id={chunk.chunk_id}, len={len(chunk.text_chunk)} chars)")

            if not chunk.categories:
                continue

            for cat_assign in chunk.categories:
                cat_name = cat_assign.category
                subcats = cat_assign.subcategories or None

                agent = self.category_agents.get(cat_name)
                if agent is None:
                    print(f"[MASv2]  Brak agenta dla kategorii: {cat_name} – pomijam.")
                    continue

                try:
                    codes = agent.map_chunk(chunk.text_chunk, allowed_subcategories=subcats)
                except Exception as e:
                    print(f"[MASv2]  Błąd w agencie kategorii {cat_name} dla chunk {chunk.chunk_id}: {e}")
                    codes = []

                all_codes.update(codes)

        candidates: list[ServiceCandidate] = []
        for rank, code in enumerate(sorted(all_codes), start=1):
            matched = next((c for c in self.service_codes if c.code == code), None)
            candidates.append(
                ServiceCandidate(
                    code=code,
                    label=matched.name if matched else None,
                    score=None,
                    source=self.name,
                    rank=rank,
                )
            )

        return ServiceItemMappingResult(candidates=candidates)
