"""
Example usage of variant aggregator.

Demonstrates:
- Classifying segments
- Aggregating into variants
- Extracting variant information
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import PdfSegment
from siwz_mapper.llm import FakeGPTClient, classify_segments
from siwz_mapper.pipeline import aggregate_variants, VariantAggregator


def example_basic_aggregation():
    """Basic example with synthetic SIWZ segments."""
    print("=" * 60)
    print("VARIANT AGGREGATION - BASIC EXAMPLE")
    print("=" * 60)
    
    # Create synthetic segments (simulating a SIWZ document)
    segments = [
        PdfSegment(
            segment_id="seg_1",
            text="OGŁOSZENIE O ZAMÓWIENIU PUBLICZNYM",
            page=1
        ),
        PdfSegment(
            segment_id="seg_2",
            text="Załącznik nr 2 A – WARIANT 1\nPakiet podstawowy",
            page=5
        ),
        PdfSegment(
            segment_id="seg_3",
            text="• Konsultacja lekarska\n• Badania podstawowe\n• USG",
            page=5
        ),
        PdfSegment(
            segment_id="seg_4",
            text="WARIANT 2 – Pakiet rozszerzony",
            page=7
        ),
        PdfSegment(
            segment_id="seg_5",
            text="• Wszystkie usługi z wariantu 1\n• Badania specjalistyczne",
            page=7
        ),
        PdfSegment(
            segment_id="seg_6",
            text="Program profilaktyczny:\n• Morfologia\n• Badanie moczu",
            page=10
        ),
    ]
    
    print(f"\n📄 Input: {len(segments)} segments")
    
    # 1. Classify segments
    print("\n1️⃣  Classifying segments...")
    client = FakeGPTClient()
    classifications = classify_segments(segments, client, show_progress=False)
    
    print("\n   Classification results:")
    for seg, cls in zip(segments, classifications):
        print(f"   {seg.segment_id}: {cls.label}")
    
    # 2. Aggregate into variants
    print("\n2️⃣  Aggregating variants...")
    updated_segments, variants = aggregate_variants(segments, classifications)
    
    print(f"\n   Found {len(variants)} variants")
    
    # 3. Display variant information
    print("\n3️⃣  Variant details:")
    for variant in variants:
        print(f"\n   {variant.variant_id}:")
        if variant.header_segment:
            print(f"      Header: {variant.header_segment.text[:50]}...")
        print(f"      Body segments: {len(variant.body_segments)}")
        print(f"      Prophylaxis segments: {len(variant.prophylaxis_segments)}")
        print(f"      Total: {variant.segment_count()} segments")
    
    # 4. Show segments with assigned variant_id
    print("\n4️⃣  Segments with variant_id:")
    for seg in updated_segments:
        if seg.variant_id:
            print(f"   {seg.segment_id}: variant={seg.variant_id}")


def example_single_variant():
    """Example with no variant headers (single default variant)."""
    print("\n" + "=" * 60)
    print("SINGLE VARIANT EXAMPLE (No Headers)")
    print("=" * 60)
    
    segments = [
        PdfSegment(
            segment_id="seg_1",
            text="Zakres usług medycznych",
            page=1
        ),
        PdfSegment(
            segment_id="seg_2",
            text="• Konsultacje lekarskie\n• Badania laboratoryjne",
            page=1
        ),
        PdfSegment(
            segment_id="seg_3",
            text="• Badania obrazowe",
            page=2
        ),
    ]
    
    # Classify
    client = FakeGPTClient()
    classifications = classify_segments(segments, client, show_progress=False)
    
    # Aggregate
    updated_segments, variants = aggregate_variants(segments, classifications)
    
    print(f"\n📦 Variants found: {len(variants)}")
    print(f"   Default variant: {variants[0].variant_id}")
    print(f"   Body segments: {len(variants[0].body_segments)}")


def example_with_aggregator_class():
    """Example using VariantAggregator class directly."""
    print("\n" + "=" * 60)
    print("USING VariantAggregator CLASS")
    print("=" * 60)
    
    segments = [
        PdfSegment(
            segment_id="seg_1",
            text="WARIANT 1",
            page=1
        ),
        PdfSegment(
            segment_id="seg_2",
            text="Body text",
            page=1
        ),
    ]
    
    # Classify
    client = FakeGPTClient()
    classifications = classify_segments(segments, client, show_progress=False)
    
    # Use VariantAggregator class with custom default
    aggregator = VariantAggregator(default_variant_id="CUSTOM_V1")
    updated_segments, variants = aggregator.aggregate(segments, classifications)
    
    print(f"\n   Variant ID: {variants[0].variant_id}")
    
    # Extract variant IDs
    variant_ids = aggregator.get_variant_ids(variants)
    print(f"   All variant IDs: {variant_ids}")


def example_prophylaxis_handling():
    """Example showing prophylaxis segment handling."""
    print("\n" + "=" * 60)
    print("PROPHYLAXIS HANDLING EXAMPLE")
    print("=" * 60)
    
    segments = [
        PdfSegment(
            segment_id="seg_1",
            text="WARIANT 1",
            page=1
        ),
        PdfSegment(
            segment_id="seg_2",
            text="• Konsultacje",
            page=1
        ),
        PdfSegment(
            segment_id="seg_3",
            text="Program profilaktyczny",
            page=2
        ),
        PdfSegment(
            segment_id="seg_4",
            text="WARIANT 2",
            page=3
        ),
        PdfSegment(
            segment_id="seg_5",
            text="• Badania",
            page=3
        ),
    ]
    
    # Classify
    client = FakeGPTClient()
    classifications = classify_segments(segments, client, show_progress=False)
    
    # Aggregate
    updated_segments, variants = aggregate_variants(segments, classifications)
    
    print(f"\n   Variants: {len(variants)}")
    for variant in variants:
        print(f"\n   {variant.variant_id}:")
        print(f"      Body: {len(variant.body_segments)}")
        print(f"      Prophylaxis: {len(variant.prophylaxis_segments)}")


def main():
    """Run all examples."""
    print("\n🚀 SIWZ Mapper - Variant Aggregator Examples\n")
    
    try:
        example_basic_aggregation()
        example_single_variant()
        example_with_aggregator_class()
        example_prophylaxis_handling()
        
        print("\n" + "=" * 60)
        print("✅ All examples completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

