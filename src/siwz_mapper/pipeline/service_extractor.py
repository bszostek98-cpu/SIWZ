"""
Extraction of service items from VariantGroup.

Logika:
- pracujemy na poziomie wariantu (VariantGroup),
- składamy wszystkie segmenty w jedną sekwencję linii,
- rozpoznajemy:
    * top-level:   "X. ..."        -> nagłówek bloku (block_no = "X")
    * sub-level:   "X.Y. ..."      -> pojedyncza usługa (service_local_id = "X.Y")
- linie nienumerowane dokładamy jako continuation do ostatniej usługi/nagłówka.

Dodatkowo:
- (jeśli dostępne) uwzględniamy body_segments, prophylaxis_segments ORAZ other_segments
  z VariantGroup,
- łączymy "popękane" linie z PDF:
    "15."   + "Diagnostyka ..."  -> "15. Diagnostyka ..."
    "15.1." + "cholesterol..."   -> "15.1. cholesterol..."
"""

from __future__ import annotations

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
import re

from ..models import PdfSegment, VariantServiceItem
from .variant_aggregator import VariantGroup


@dataclass
class _BlockCandidate:
    """
    Rezerwowe – na przyszłość, gdybyśmy chcieli wysyłać całe bloki do LLM.
    """
    variant_id: str
    block_no: str
    heading_raw: Optional[str]
    items: List[Dict[str, Any]]
    primary_segment_id: str


class ServiceExtractor:
    """
    Główny ekstraktor usług z wariantów.

    Wejście:  List[VariantGroup]
    Wyjście:  Dict[variant_id, List[VariantServiceItem]]
    """

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def extract_from_variants(
        self,
        variant_groups: List[VariantGroup],
    ) -> Dict[str, List[VariantServiceItem]]:
        """
        Dla listy VariantGroup zwróć słownik:
            { variant_id: [VariantServiceItem, ...], ... }
        """
        result: Dict[str, List[VariantServiceItem]] = {}

        for vg in variant_groups:
            items = self._extract_for_variant(vg)
            result[vg.variant_id] = items

        return result

    # ------------------------------------------------------------------ #
    # logika per wariant
    # ------------------------------------------------------------------ #

    def _extract_for_variant(self, vg: VariantGroup) -> List[VariantServiceItem]:
        """
        Ekstrakcja usług dla pojedynczego wariantu.

        Kroki:
        1) zbuduj strumień linii (body + prophylaxis + other),
        2) z całego strumienia wyciągnij mapę nagłówków bloków: { "4": "...", "10": "...", ... },
        3) przejdź po liniach z automatem stanowym (blok, usługa, kontynuacje).

        Dzięki krokowi (2):
        - nagłówki bloków nie „przeciekają” między blokami,
        - jeśli istnieje "4. Nielimitowany dostęp...", to wszystkie 4.X dostają poprawny heading.
        """
        # 1) strumień linii (już po sklejaniu "15." + "Diagnostyka..." itd.)
        line_stream = self._build_line_stream(vg)

        # 2) mapa nagłówków typu "X. Coś tam"
        top_headings = self._collect_top_headings(line_stream)

        items: List[VariantServiceItem] = []

        current_block_no: Optional[str] = None
        current_block_heading: Optional[str] = None
        current_block_category: str = "unknown"

        current_item: Optional[VariantServiceItem] = None

        def flush_current_item():
            nonlocal current_item
            current_item = None

        for line in line_stream:
            raw = line["text"]
            text = raw.strip()
            if not text:
                flush_current_item()
                continue

            is_proph = line["is_prophylaxis"]
            seg: PdfSegment = line["segment"]

            # ---------- sub-punkt X.Y. -----------------------------------
            m_sub = re.match(r"^(\d+)\.(\d+)\.\s*(.*)$", text)
            if m_sub:
                prefix = m_sub.group(1)
                sub_no = m_sub.group(2)
                rest = m_sub.group(3).strip()

                # zmiana prefiksu (np. 10.* -> 11.*) = nowy blok
                if current_block_no != prefix:
                    flush_current_item()
                    current_block_no = prefix
                    current_block_heading = top_headings.get(prefix)
                    current_block_category = "prophylaxis" if is_proph else "unknown"

                flush_current_item()

                local_id = f"{prefix}.{sub_no}"

                item = VariantServiceItem(
                    variant_id=vg.variant_id,
                    block_no=current_block_no,
                    block_heading_raw=current_block_heading,
                    block_category=current_block_category,
                    service_local_id=local_id,
                    service_text=rest,
                    is_prophylaxis=is_proph,
                    is_occupational_medicine=False,
                    is_telemedicine=False,
                    is_pricing_only=False,
                    source_segment_id=seg.segment_id,
                    page=seg.page,
                    extra={
                        "source_line": raw,
                        "line_idx_in_segment": line["line_idx_in_segment"],
                        "is_sub_item": True,
                    },
                )
                items.append(item)
                current_item = item
                continue

            # ---------- top-level X. ... (nagłówek bloku) ----------------
            m_top = re.match(r"^(\d+)\.\s+(.+)$", text)
            if m_top:
                num = m_top.group(1)
                rest = m_top.group(2).strip()

                flush_current_item()

                current_block_no = num
                # opieramy się na top_headings, ale rest to i tak ta sama treść
                current_block_heading = top_headings.get(num, rest)
                current_block_category = "prophylaxis" if is_proph else "unknown"

                item = VariantServiceItem(
                    variant_id=vg.variant_id,
                    block_no=current_block_no,
                    block_heading_raw=current_block_heading,
                    block_category=current_block_category,
                    service_local_id=num,
                    service_text=current_block_heading,
                    is_prophylaxis=is_proph,
                    is_occupational_medicine=False,
                    is_telemedicine=False,
                    is_pricing_only=False,
                    source_segment_id=seg.segment_id,
                    page=seg.page,
                    extra={
                        "source_line": raw,
                        "line_idx_in_segment": line["line_idx_in_segment"],
                        "is_block_header": True,
                    },
                )
                items.append(item)
                current_item = item
                continue

            # ---------- linia nienumerowana = kontynuacja ----------------
            if current_item is not None:
                cont = current_item.extra.setdefault("continuation_lines", [])
                cont.append(raw)
            else:
                # luźna linia bez kontekstu – ignorujemy na poziomie usług
                pass

        return items

    # ------------------------------------------------------------------ #
    # budowa i normalizacja strumienia linii
    # ------------------------------------------------------------------ #

    def _build_line_stream(self, vg: VariantGroup) -> List[dict]:
        """
        Zwraca listę słowników:
        {
            "segment": PdfSegment,
            "is_prophylaxis": bool,
            "text": pojedyncza linia (str),
            "line_idx_in_segment": int,
        }

        Uwaga: uwzględniamy body_segments, prophylaxis_segments ORAZ other_segments,
        jeśli te ostatnie istnieją (kompatybilność wsteczna).
        """

        seg_with_flags: List[Tuple[PdfSegment, bool]] = []

        for seg in vg.body_segments:
            seg_with_flags.append((seg, False))
        for seg in vg.prophylaxis_segments:
            seg_with_flags.append((seg, True))

        other_segments = getattr(vg, "other_segments", None)
        if other_segments:
            for seg in other_segments:
                seg_with_flags.append((seg, False))

        def seg_key(t: Tuple[PdfSegment, bool]):
            s = t[0]
            return (s.page, s.start_char or 0, s.segment_id)

        seg_with_flags.sort(key=seg_key)

        raw_line_stream: List[dict] = []
        for seg, is_proph in seg_with_flags:
            lines = seg.text.splitlines()
            for idx, ln in enumerate(lines):
                raw_line_stream.append(
                    {
                        "segment": seg,
                        "is_prophylaxis": is_proph,
                        "text": ln,
                        "line_idx_in_segment": idx,
                    }
                )

        # sklejanie "15." + "Diagnostyka..." / "15.1." + "cholesterol..."
        return self._merge_broken_numbered_lines(raw_line_stream)

    # ------------------------------------------------------------------ #
    # krok 2: budowa mapy nagłówków bloków z całego strumienia
    # ------------------------------------------------------------------ #

    def _collect_top_headings(self, line_stream: List[dict]) -> Dict[str, str]:
        """
        Przegląda cały line_stream i wyciąga wszystkie linie "X. Coś tam",
        budując słownik:
            { "4": "Nielimitowany dostęp ...",
              "10": "Konsultacyjne zabiegi ... okulistyki ...",
              "11": "Konsultacyjne zabiegi ... urologii ...",
              ... }

        Dzięki temu, gdy widzimy "11.1. ...", możemy zawsze sięgnąć po
        poprawny nagłówek z top_headings["11"], niezależnie od kolejności linii.
        """
        top_headings: Dict[str, str] = {}

        top_with_text_re = re.compile(r"^(\d+)\.\s+(.+)$")

        for line in line_stream:
            text = line["text"].strip()
            m_top = top_with_text_re.match(text)
            if not m_top:
                continue
            num = m_top.group(1)
            rest = m_top.group(2).strip()
            # jeśli num pojawi się kilka razy, ostatnia wersja nadpisze poprzednią – OK
            top_headings[num] = rest

        return top_headings

    # ------------------------------------------------------------------ #
    # sklejanie "15." + "Diagnostyka..." itp.
    # ------------------------------------------------------------------ #

    def _merge_broken_numbered_lines(self, line_stream: List[dict]) -> List[dict]:
        """
        Scala pary:
            "15."   + "Diagnostyka miażdżycy ..." -> "15. Diagnostyka miażdżycy ..."
            "15.1." + "cholesterol – ..."         -> "15.1. cholesterol – ..."
        tam, gdzie to ma sens (kolejna linia nie wygląda sama jak numer punktu).
        """
        merged: List[dict] = []
        i = 0
        n = len(line_stream)

        pure_num_re = re.compile(r"^(\d+)\.\s*$")
        sub_num_re = re.compile(r"^(\d+)\.(\d+)\.\s*(.*)$")
        top_with_text_re = re.compile(r"^(\d+)\.\s+(.+)$")

        while i < n:
            cur = line_stream[i]
            text = cur["text"]
            stripped = text.strip()

            # "15."
            m_pure = pure_num_re.match(stripped)
            if m_pure and i + 1 < n:
                next_text = line_stream[i + 1]["text"]
                next_stripped = next_text.strip()

                if (
                    next_stripped
                    and not pure_num_re.match(next_stripped)
                    and not sub_num_re.match(next_stripped)
                    and not top_with_text_re.match(next_stripped)
                ):
                    new_cur = dict(cur)
                    new_cur["text"] = f"{m_pure.group(1)}. {next_stripped}"
                    merged.append(new_cur)
                    i += 2
                    continue

            # "15.1." bez opisu
            m_sub = sub_num_re.match(stripped)
            if m_sub and not m_sub.group(3).strip() and i + 1 < n:
                next_text = line_stream[i + 1]["text"]
                next_stripped = next_text.strip()

                if (
                    next_stripped
                    and not pure_num_re.match(next_stripped)
                    and not sub_num_re.match(next_stripped)
                    and not top_with_text_re.match(next_stripped)
                ):
                    new_cur = dict(cur)
                    new_cur["text"] = (
                        f"{m_sub.group(1)}.{m_sub.group(2)}. {next_stripped}"
                    )
                    merged.append(new_cur)
                    i += 2
                    continue

            merged.append(cur)
            i += 1

        return merged
