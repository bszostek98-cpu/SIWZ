"""
Example usage of segment classification with GPT.

Demonstrates:
- Creating fake client for testing
- Classifying segments without real API calls
- Using real GPT client (requires OPENAI_API_KEY)
"""

import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import (
    GPTClient,
    FakeGPTClient,
    classify_segment,
    classify_segments,
    VALID_LABELS
)


def example_with_fake_client():
    """Example using FakeGPTClient (no API calls)."""
    print("=" * 60)
    print("SEGMENT CLASSIFICATION WITH FAKE CLIENT")
    print("=" * 60)
    
    # Create fake client
    client = FakeGPTClient()
    
    # Create sample segments
    segments = [
        PdfSegment(
            segment_id="seg_1",
            text="OGŁOSZENIE O ZAMÓWIENIU PUBLICZNYM\nZamówienie na ochronę zdrowia",
            page=1
        ),
        PdfSegment(
            segment_id="seg_2",
            text="Załącznik nr 2 A – WARIANT 1\nPakiet podstawowy",
            page=5
        ),
        PdfSegment(
            segment_id="seg_3",
            text="• Konsultacja lekarska\n• Badania laboratoryjne\n• USG",
            page=6
        ),
        PdfSegment(
            segment_id="seg_4",
            text="Program profilaktyczny - przegląd stanu zdrowia:\n• Morfologia\n• Badanie moczu",
            page=10
        ),
    ]
    
    print(f"\n📦 Classifying {len(segments)} segments\n")
    
    # Classify all segments
    results = classify_segments(segments, client, show_progress=False)
    
    # Display results
    for i, (segment, result) in enumerate(zip(segments, results), 1):
        print(f"{i}. Segment: {segment.segment_id} (page {segment.page})")
        print(f"   Text preview: {segment.text[:60]}...")
        print(f"   Label: {result.label}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Is prophylaxis: {result.is_prophylaxis}")
        if result.variant_hint:
            print(f"   Variant hint: {result.variant_hint}")
        print(f"   Rationale: {result.rationale}")
        print()
    
    # Show label distribution
    label_counts = {}
    for r in results:
        label_counts[r.label] = label_counts.get(r.label, 0) + 1
    
    print("📊 Label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"   {label}: {count}")


def example_with_real_gpt():
    """Example using real GPT client (requires OPENAI_API_KEY)."""
    print("\n" + "=" * 60)
    print("SEGMENT CLASSIFICATION WITH REAL GPT")
    print("=" * 60)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️  OPENAI_API_KEY not set. Skipping real GPT example.")
        print("\nTo use real GPT, set the environment variable:")
        print("  Windows PowerShell: $env:OPENAI_API_KEY = 'your-api-key'")
        print("  Linux/Mac: export OPENAI_API_KEY='your-api-key'")
        return
    
    try:
        # Create real GPT client
        client = GPTClient(
            model="gpt-4o-mini",
            temperature=0.0
        )
        
        print(f"\n✅ GPT client initialized (model={client.model})")
        
        # Create a test segment
        segment = PdfSegment(
            segment_id="test_seg",
            text="WARIANT 2 - Pakiet rozszerzony\nObejmuje wszystkie badania z wariantu 1 oraz dodatkowo:",
            page=7
        )
        
        print(f"\n📄 Classifying segment: {segment.segment_id}")
        print(f"   Text: {segment.text[:80]}...")
        
        # Classify
        result = classify_segment(client, segment)
        
        print(f"\n✅ Classification result:")
        print(f"   Label: {result.label}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Variant hint: {result.variant_hint}")
        print(f"   Rationale: {result.rationale}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


def show_available_labels():
    """Show all available classification labels."""
    print("\n" + "=" * 60)
    print("AVAILABLE CLASSIFICATION LABELS")
    print("=" * 60)
    
    label_descriptions = {
        "irrelevant": "Introductory, legal, or meta information",
        "general": "General scope description (not specific variant)",
        "variant_header": "Headers introducing medical variants (e.g., 'WARIANT 1')",
        "variant_body": "Service lists belonging to a specific variant",
        "prophylaxis": "Prophylactic program sections",
        "pricing_table": "Pricing tables (not medical variant definitions)"
    }
    
    print("\n")
    for label in sorted(VALID_LABELS):
        description = label_descriptions.get(label, "No description")
        print(f"  • {label:20} - {description}")


def main():
    """Run all examples."""
    print("\n🚀 SIWZ Mapper - Segment Classification Examples\n")
    
    try:
        show_available_labels()
        example_with_fake_client()
        example_with_real_gpt()
        
        print("\n" + "=" * 60)
        print("✅ Examples completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

