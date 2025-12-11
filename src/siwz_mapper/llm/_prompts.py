"""Prompt templates for LLM calls."""


class PromptTemplates:
    """Collection of prompt templates for different tasks."""
    
    VARIANT_DETECTION = """
Przeanalizuj poniższy fragment dokumentu SIWZ i zidentyfikuj wszystkie warianty.

Warianty są zazwyczaj oznaczone jako:
- "Wariant 1", "Wariant 2", itp.
- "Wariant podstawowy", "Wariant rozszerzony"
- Sekcje z różnymi zakresami usług

Dla każdego wariantu określ:
- Identyfikator i nazwę wariantu
- Czy jest to część programu profilaktycznego
- Współczynnik pewności (0-1)

Zwróć TYLKO informacje obecne w tekście źródłowym.
"""
    
    SERVICE_EXTRACTION = """
Wyodrębnij wszystkie wzmianki o usługach medycznych z poniższego fragmentu.

Dla każdej wzmianki o usłudze zwróć:
- Dokładny cytat z tekstu (TYLKO z dostarczonego fragmentu)
- Opis usługi własnymi słowami
- Współczynnik pewności (0-1)

Usługi medyczne mogą obejmować:
- Badania diagnostyczne (np. USG, RTG, tomografia)
- Konsultacje specjalistyczne
- Zabiegi i procedury
- Rehabilitację
- Szczepienia (program profilaktyczny)

NIE WYMYŚLAJ usług, które nie są wymienione w tekście.
"""
    
    SERVICE_MAPPING = """
Dopasuj poniższą wzmiankę o usłudze do najbardziej pasujących pozycji ze słownika usług.

Wzmianka o usłudze: {mention}

Dostępne usługi (TOP {k}):
{services_list}

Dla każdej dopasowanej usługi zwróć:
- Kod usługi
- Wynik dopasowania (0-1)
- Uzasadnienie dopasowania

Sortuj wyniki według wyniku dopasowania (najlepsze najpierw).
"""
    
    PROPHYLAXIS_CLASSIFICATION = """
Określ, czy poniższy fragment dotyczy programu profilaktycznego (szczepienia, badania przesiewowe, itp.).

Program profilaktyczny zazwyczaj zawiera:
- Szczepienia
- Badania przesiewowe
- Profilaktyka zdrowotna
- Sekcje oznaczone jako "program profilaktyczny"

Zwróć:
- is_prophylaxis: true/false
- confidence: 0-1
- reasoning: krótkie uzasadnienie
"""
    
    @staticmethod
    def format_services_for_prompt(services: list, max_services: int = 20) -> str:
        """
        Format services list for inclusion in prompt.
        
        Args:
            services: List of Service objects
            max_services: Maximum number to include
            
        Returns:
            Formatted string
        """
        lines = []
        for i, svc in enumerate(services[:max_services], 1):
            lines.append(f"{i}. [{svc.code}] {svc.name}")
            if svc.category_info:
                lines.append(f"   Kategoria: {svc.category_info}")
        
        return "\n".join(lines)

