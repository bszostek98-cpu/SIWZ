"""
Example: Loading medical services dictionary from CSV/XLSX

Usage:
    python examples/load_dictionary_example.py tests/fixtures/services_v1.0.csv
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper import load_dictionary, DictionaryLoader


def main():
    if len(sys.argv) < 2:
        print("Usage: python load_dictionary_example.py <csv_or_xlsx_file>")
        sys.exit(1)
    
    file_path = Path(sys.argv[1])
    
    print(f"Loading dictionary from: {file_path}")
    print("=" * 60)
    
    # Method 1: Convenience function
    services, version = load_dictionary(file_path)
    
    print(f"\n✓ Loaded {len(services)} services (version {version})")
    print()
    
    # Show first 5 services
    print("First 5 services:")
    print("-" * 60)
    for service in services[:5]:
        print(f"  [{service.code}] {service.name}")
        print(f"    Category: {service.category}")
        if service.subcategory:
            print(f"    Subcategory: {service.subcategory}")
        if service.synonyms:
            print(f"    Synonyms: {', '.join(service.synonyms[:3])}")
        print()
    
    # Show statistics
    print("Statistics:")
    print("-" * 60)
    loader = DictionaryLoader()
    services2, version2 = loader.load(file_path)
    stats = loader.get_stats()
    
    print(f"  Total rows: {stats.get('total_rows', 'N/A')}")
    print(f"  Valid services: {stats['valid_services']}")
    print(f"  Version: {stats['version']}")
    print(f"  Source: {Path(stats['source_file']).name}")
    print()
    
    # Show categories
    categories = {}
    for service in services:
        cat = service.category
        categories[cat] = categories.get(cat, 0) + 1
    
    print("Services by category:")
    print("-" * 60)
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        print(f"  {cat}: {count} services")
    
    print()
    print("=" * 60)
    print(f"✓ Successfully loaded {len(services)} services!")


if __name__ == "__main__":
    main()

