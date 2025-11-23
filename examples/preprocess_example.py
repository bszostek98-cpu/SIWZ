"""
Example usage of text preprocessing (normalization and segmentation).

Demonstrates:
- Loading PDF
- Normalizing text
- Segmenting into manageable chunks
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.io import load_pdf
from siwz_mapper.preprocess import TextNormalizer, Segmenter, normalize_text, segment_pdf_blocks


def example_normalization():
    """Example of text normalization."""
    print("=" * 60)
    print("TEXT NORMALIZATION EXAMPLE")
    print("=" * 60)
    
    # Raw text with issues
    raw_text = """
    Tekst  z    wieloma     spacjami
    
    
    
    i wielokrotnymi newline'ami.
    
    Słowo  podzie-
    lone na końcu linii.
    
    "Smart quotes" i 'inne' cudzysłowy.
    """
    
    print("\n📄 RAW TEXT:")
    print(repr(raw_text))
    
    # Normalize
    normalized = normalize_text(raw_text)
    
    print("\n✨ NORMALIZED TEXT:")
    print(repr(normalized))
    print("\nCleaned version:")
    print(normalized)


def example_segmentation():
    """Example of text segmentation."""
    print("\n" + "=" * 60)
    print("TEXT SEGMENTATION EXAMPLE")
    print("=" * 60)
    
    from siwz_mapper.models import PdfSegment
    
    # Sample text blocks (simulating PDF loader output)
    blocks = [
        PdfSegment(
            segment_id="block_1",
            text="""Rozdział 1: Zakres usług

Wykonawca zobowiązuje się do świadczenia następujących usług medycznych:

• Konsultacje lekarskie
• Badania diagnostyczne
• Terapia rehabilitacyjna""",
            page=1,
            start_char=0,
            end_char=200
        ),
        PdfSegment(
            segment_id="block_2",
            text="To jest bardzo długi paragraf " * 50,  # >1200 chars
            page=2,
            start_char=200,
            end_char=1700
        ),
    ]
    
    print(f"\n📦 Input: {len(blocks)} blocks")
    for block in blocks:
        print(f"  - {block.segment_id}: {len(block.text)} chars")
    
    # Segment
    segmenter = Segmenter(
        soft_min_chars=800,
        soft_max_chars=1200,
        normalize_text=True
    )
    
    segments = segmenter.segment(blocks)
    
    print(f"\n📊 Output: {len(segments)} segments")
    for i, seg in enumerate(segments, 1):
        print(f"  {i}. {seg.segment_id}: {len(seg.text)} chars, page {seg.page}")
        print(f"     Preview: {seg.text[:60]}...")


def example_with_real_pdf():
    """Example with real PDF (if available)."""
    print("\n" + "=" * 60)
    print("FULL PIPELINE EXAMPLE")
    print("=" * 60)
    
    # Check if test PDF exists
    test_pdf = Path(__file__).parent.parent / "tests" / "fixtures" / "tiny.pdf"
    
    if not test_pdf.exists():
        print("\n⚠️  No test PDF found, skipping...")
        return
    
    print(f"\n📄 Loading PDF: {test_pdf.name}")
    
    # Load PDF
    blocks = load_pdf(test_pdf)
    print(f"  Loaded {len(blocks)} blocks")
    
    # Segment
    segments = segment_pdf_blocks(
        blocks,
        soft_min_chars=500,
        soft_max_chars=800,
        normalize=True
    )
    
    print(f"  Segmented into {len(segments)} segments")
    
    # Show first few
    print("\n📋 First segments:")
    for i, seg in enumerate(segments[:3], 1):
        print(f"\n  Segment {i} (page {seg.page}):")
        print(f"  ID: {seg.segment_id}")
        print(f"  Length: {len(seg.text)} chars")
        if seg.start_char is not None:
            print(f"  Char range: {seg.start_char}-{seg.end_char}")
        print(f"  Text: {seg.text[:100]}...")


def main():
    """Run all examples."""
    print("\n🚀 SIWZ Mapper - Preprocessing Examples\n")
    
    try:
        example_normalization()
        example_segmentation()
        example_with_real_pdf()
        
        print("\n" + "=" * 60)
        print("✅ All examples completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

