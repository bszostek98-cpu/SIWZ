"""
Example: Loading PDF with position information

This example shows how to extract text from a PDF while preserving
position information for later citation and highlighting.

Usage:
    python examples/load_pdf_example.py path/to/document.pdf
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper import load_pdf, PDFLoader


def main():
    if len(sys.argv) < 2:
        print("Usage: python load_pdf_example.py <pdf_file>")
        print("\nNote: This is a demo. You'll need a real PDF file.")
        print("The implementation is ready to use with actual PDFs.")
        return
    
    pdf_path = Path(sys.argv[1])
    
    if not pdf_path.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        return
    
    print(f"Loading PDF: {pdf_path}")
    print("=" * 60)
    
    # Method 1: Simple convenience function
    segments = load_pdf(pdf_path, extract_bboxes=True)
    
    print(f"\n✓ Extracted {len(segments)} text segments")
    print()
    
    # Show first few segments
    print("First 5 segments:")
    print("-" * 60)
    for i, segment in enumerate(segments[:5], 1):
        print(f"\n{i}. Segment ID: {segment.segment_id}")
        print(f"   Page: {segment.page}")
        print(f"   Text: {segment.text[:80]}..." if len(segment.text) > 80 else f"   Text: {segment.text}")
        
        if segment.bbox:
            print(f"   Position: ({segment.bbox.x0:.1f}, {segment.bbox.y0:.1f}) "
                  f"to ({segment.bbox.x1:.1f}, {segment.bbox.y1:.1f})")
        
        if segment.start_char is not None:
            print(f"   Char range: {segment.start_char}-{segment.end_char}")
    
    # Method 2: Using PDFLoader with custom options
    print("\n" + "=" * 60)
    print("Using PDFLoader with custom options:")
    print("-" * 60)
    
    loader = PDFLoader(
        extract_bboxes=True,
        min_block_length=10  # Skip very short blocks
    )
    
    segments_filtered = loader.load(pdf_path)
    
    print(f"✓ Extracted {len(segments_filtered)} segments (min length: 10)")
    
    # Show page distribution
    page_counts = {}
    for segment in segments_filtered:
        page_counts[segment.page] = page_counts.get(segment.page, 0) + 1
    
    print("\nSegments per page:")
    for page in sorted(page_counts.keys()):
        print(f"  Page {page}: {page_counts[page]} segments")
    
    # Demonstrate citation generation
    print("\n" + "=" * 60)
    print("Example citations:")
    print("-" * 60)
    
    for segment in segments_filtered[:3]:
        citation = create_citation(segment)
        print(f"\n{citation}")
    
    print("\n" + "=" * 60)
    print("✓ PDF loading complete!")
    print("\nThe extracted segments are now ready for:")
    print("  - Variant detection")
    print("  - Entity extraction")
    print("  - Citation and highlighting")


def create_citation(segment):
    """Create a citation from a segment."""
    text_preview = segment.text[:60] + "..." if len(segment.text) > 60 else segment.text
    citation = f'"{text_preview}"'
    citation += f"\n  Source: Page {segment.page}"
    
    if segment.start_char is not None:
        citation += f", chars {segment.start_char}-{segment.end_char}"
    
    if segment.bbox:
        citation += f"\n  Position: ({segment.bbox.x0:.1f}, {segment.bbox.y0:.1f})"
    
    return citation


if __name__ == "__main__":
    main()

