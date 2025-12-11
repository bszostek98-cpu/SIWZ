"""
LLM-based classification of service blocks into high-level categories.

Używane po ekstrakcji VariantServiceItem – klasyfikujemy całe BLOKI
(np. "4. Nielimitowany dostęp do konsultacji ...", "14. Badania biochemiczne z krwi")
do kategorii typu: consultation, lab, imaging, prophylaxis itp.
"""

from __future__ import annotations

import json
import logging
from typing import List, Dict, Tuple, Optional

from pydantic import BaseModel, Field

from .gpt_client import GPTClientProtocol
from ..models import VariantServiceItem, BlockCategory

logger = logging.getLogger(__name__)


# ======================================================================
# Definicje pomocnicze
# ======================================================================


class ServiceCategoryDef(BaseModel):
    """
    Definicja kategorii usług, konfigurowalna z zewnątrz.

    Przykłady:
    - id="consultation", label="Konsultacje lekarskie"
    - id="lab",          label="Diagnostyka laboratoryjna"
    """

    id: str = Field(..., description="Krótki identyfikator kategorii (np. 'consultation', 'lab')")
    label: str = Field(..., description="Przyjazna nazwa kategorii")
    description: str = Field(..., description="Opis znaczenia kategorii (po polsku)")
    examples: List[str] = Field(
        default_factory=list,
        description="Przykładowe nazwy usług, które do niej należą",
    )


class BlockContext(BaseModel):
    """
    Zbiorczy kontekst jednego bloku usług dla LLM.

    Grupuje VariantServiceItem (z tego samego wariantu i block_no) do jednej
    paczki, którą potem klasyfikujemy jednym wywołaniem GPT.
    """

    variant_id: str
    block_no: str
    header: Optional[str] = None
    example_lines: List[str] = Field(default_factory=list)
    is_prophylaxis_hint: bool = False  # np. jeśli w usługach jest dużo "szczepień", "przeglądów" itd.


class BlockCategoryDecision(BaseModel):
    """
    Wynik klasyfikacji jednego bloku przez LLM.
    """

    variant_id: str
    block_no: str
    category_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


# ======================================================================
# Główny classifier
# ======================================================================


class ServiceBlockCategoryClassifier:
    """
    Klasyfikator bloków usług do kategorii konfigurowanych przez użytkownika.

    Flow:
      1) build_block_contexts(...) – z VariantServiceItem budujemy BlockContext
      2) classify_blocks(contexts) – LLM wybiera category_id dla każdego bloku
      3) to_block_category_map(...) – mapujemy category_id -> BlockCategory (Literal),
         np. {"consultation" -> "consultation", "lab" -> "lab", inne -> "other"}
    """

    def __init__(
        self,
        client: GPTClientProtocol,
        categories: List[ServiceCategoryDef],
        max_retries: int = 1,
    ) -> None:
        self.client = client
        self.categories = categories
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # 1) Budowa kontekstów bloków na podstawie VariantServiceItem
    # ------------------------------------------------------------------

    def build_block_contexts(
        self,
        items_by_variant: Dict[str, List[VariantServiceItem]],
        max_examples_per_block: int = 8,
    ) -> List[BlockContext]:
        """
        Grupuje VariantServiceItem per (variant_id, block_no) w BlockContext.

        Args:
            items_by_variant: dict[variant_id, list[VariantServiceItem]]
            max_examples_per_block: ile przykładowych linii usług dajemy LLM-owi

        Returns:
            Lista BlockContext (po jednym na blok).
        """
        blocks: Dict[Tuple[str, str], List[VariantServiceItem]] = {}

        for vid, items in items_by_variant.items():
            for it in items:
                block_no = it.block_no or "?"
                key = (vid, block_no)
                blocks.setdefault(key, []).append(it)

        contexts: List[BlockContext] = []

        for (vid, block_no), block_items in blocks.items():
            # nagłówek – pierwszy niepusty block_heading_raw
            header = None
            for it in block_items:
                if it.block_heading_raw and it.block_heading_raw.strip():
                    header = it.block_heading_raw.strip()
                    break

            # przykładowe linie dla LLM
            example_lines: List[str] = []
            for it in block_items:
                line = it.service_text.strip()
                if not line:
                    continue
                example_lines.append(line)
                if len(example_lines) >= max_examples_per_block:
                    break

            # hint profilaktyki
            is_proph_hint = any(it.is_prophylaxis for it in block_items)

            contexts.append(
                BlockContext(
                    variant_id=vid,
                    block_no=block_no,
                    header=header,
                    example_lines=example_lines,
                    is_prophylaxis_hint=is_proph_hint,
                )
            )

        return contexts

    # ------------------------------------------------------------------
    # 2) Wywołanie LLM i wybór category_id per blok
    # ------------------------------------------------------------------

    def classify_blocks(self, block_contexts: List[BlockContext]) -> List[BlockCategoryDecision]:
        """
        Woła GPT dla każdego bloku i zwraca decyzje (category_id + confidence + rationale).
        """
        decisions: List[BlockCategoryDecision] = []

        # Zbuduj część system promptu zawierającą listę kategorii
        cats_desc = []
        for c in self.categories:
            ex_str = "; ".join(c.examples) if c.examples else ""
            cats_desc.append(
                f"- id: {c.id}\n  nazwa: {c.label}\n  opis: {c.description}\n  "
                f"przykłady: {ex_str}"
            )
        cats_block = "\n".join(cats_desc)

        system_prompt = (
            "Jesteś ekspertem w analizie dokumentów medycznych (OPZ, SIWZ) w Polsce.\n"
            "Twoim zadaniem jest przypisać KAŻDY blok świadczeń do dokładnie JEDNEJ kategorii.\n\n"
            "Dostępne kategorie (category_id):\n"
            f"{cats_block}\n\n"
            "Zawsze wybierz NAJLEPIEJ pasującą kategorię na podstawie nagłówka bloku i listy świadczeń.\n"
            "Jeśli blok dotyczy przeglądu stanu zdrowia lub szczepień, zwykle będzie to kategoria profilaktyczna.\n\n"
            "FORMAT ODPOWIEDZI:\n"
            "Zwróć TYLKO poprawny JSON:\n"
            "{\n"
            '  "category_id": "consultation | lab | imaging | prophylaxis | ...",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "rationale": "krótkie uzasadnienie po polsku"\n'
            "}\n"
            "Bez komentarzy, bez markdown, bez dodatkowego tekstu."
        )

        for ctx in block_contexts:
            # budujemy user_prompt dla konkretnego bloku
            user_parts: List[str] = [
                "Analizujesz jeden blok świadczeń z dokumentu OPZ.\n",
                f"Wariant: {ctx.variant_id}\n",
                f"Numer bloku (local_id): {ctx.block_no}\n",
            ]
            if ctx.header:
                user_parts.append(f"NAGŁÓWEK BLOKU:\n{ctx.header}\n")
            if ctx.is_prophylaxis_hint:
                user_parts.append(
                    "\nUWAGA: W tym bloku pojawia się dużo treści profilaktycznych "
                    "(szczepienia, przegląd stanu zdrowia, itp.).\n"
                )

            if ctx.example_lines:
                user_parts.append("\nPRZYKŁADOWE ŚWIADCZENIA Z TEGO BLOKU:\n")
                for line in ctx.example_lines:
                    user_parts.append(f"- {line}\n")
            else:
                user_parts.append("\n[Brak przykładowych świadczeń – jeśli nie jesteś pewien, wybierz 'other']\n")

            user_parts.append(
                "\nWybierz JEDEN 'category_id' z listy zdefiniowanej w instrukcji systemowej "
                "i zwróć JSON w dokładnie takim formacie, jak opisano.\n"
            )

            user_prompt = "".join(user_parts)

            # Wywołanie GPT + parsowanie JSON
            try:
                raw_data = self._call_gpt_json(system_prompt, user_prompt)
                cat_id = str(raw_data.get("category_id") or "other")
                confidence = float(raw_data.get("confidence") or 0.5)
                rationale = str(raw_data.get("rationale") or "")

                decisions.append(
                    BlockCategoryDecision(
                        variant_id=ctx.variant_id,
                        block_no=ctx.block_no,
                        category_id=cat_id,
                        confidence=confidence,
                        rationale=rationale,
                    )
                )
            except Exception as e:
                logger.error(
                    "Błąd podczas klasyfikacji bloku (variant=%s, block_no=%s): %s",
                    ctx.variant_id,
                    ctx.block_no,
                    e,
                )
                # Fallback: 'other' z niską pewnością
                decisions.append(
                    BlockCategoryDecision(
                        variant_id=ctx.variant_id,
                        block_no=ctx.block_no,
                        category_id="other",
                        confidence=0.1,
                        rationale=f"[FALLBACK] Błąd parsowania odpowiedzi LLM: {e}",
                    )
                )

        return decisions

    def _call_gpt_json(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Helper: woła self.client.chat(...) i próbuje sparsować odpowiedź jako JSON.
        Radzi sobie z ewentualnymi ```json ... ``` w odpowiedzi.
        """
        last_err: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.chat(system_prompt, user_prompt)
                text = response.strip()

                # Usuń ewentualne fence'y markdown
                if text.startswith("```"):
                    lines = text.splitlines()
                    # usuń pierwszą i ostatnią linię jeśli są ```...
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()

                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("Odpowiedź JSON nie jest słownikiem.")
                return data

            except Exception as e:
                last_err = e
                logger.warning(f"Nie udało się sparsować JSON z odpowiedzi GPT (próba {attempt+1}): {e}")

        # Po wyczerpaniu retry – podnieś ostatni błąd
        assert last_err is not None
        raise last_err

    # ------------------------------------------------------------------
    # 3) Mapowanie na BlockCategory (Literal)
    # ------------------------------------------------------------------

    def to_block_category_map(
        self,
        decisions: List[BlockCategoryDecision],
        category_id_to_block_category: Dict[str, BlockCategory],
    ) -> Dict[Tuple[str, str], BlockCategory]:
        """
        Buduje mapę {(variant_id, block_no) -> BlockCategory} na potrzeby ServiceExtractor.

        Args:
            decisions: wyniki z classify_blocks()
            category_id_to_block_category:
                mapowanie "logicznego id kategorii z LLM-a" na BlockCategory (Literal z models.py),
                np. {"consultation": "consultation", "lab": "lab", ...}.

        Wszystkie nieznane category_id wylądują w "other".
        """
        result: Dict[Tuple[str, str], BlockCategory] = {}

        for dec in decisions:
            key = (dec.variant_id, dec.block_no)
            block_cat: BlockCategory = category_id_to_block_category.get(dec.category_id, "other")
            result[key] = block_cat

        return result
