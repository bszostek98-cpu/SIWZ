"""
Example script showing how to validate SIWZ mapper outputs.

Usage:
    python examples/validate_output.py examples/example_output.json
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper import ValidationHelper, DocumentResult
from pydantic import ValidationError


def validate_file(file_path: Path) -> bool:
    """
    Validate a DocumentResult JSON file.
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        True if valid, False otherwise
    """
    print(f"Validating: {file_path}")
    print("=" * 60)
    
    # Load JSON
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"✗ Błąd wczytywania JSON: {e}")
        return False
    
    # Validate structure
    try:
        result = ValidationHelper.validate_document_result(data)
        print(f"✓ Struktura JSON jest poprawna")
        print(f"  Document ID: {result.doc_id}")
        print(f"  Variants: {len(result.variants)}")
        print()
    except ValidationError as e:
        print(f"✗ Błąd walidacji struktury:")
        print(e)
        return False
    
    # Validate consistency for each variant
    all_ok = True
    for variant in result.variants:
        print(f"Checking variant: {variant.variant_id}")
        print(f"  Core codes: {len(variant.core_codes)}")
        print(f"  Prophylaxis codes: {len(variant.prophylaxis_codes)}")
        print(f"  Mappings: {len(variant.mappings)}")
        
        warnings = ValidationHelper.validate_mapping_type_consistency(variant)
        if warnings:
            print(f"  ⚠ Ostrzeżenia:")
            for w in warnings:
                print(f"    - {w}")
            all_ok = False
        else:
            print(f"  ✓ Brak ostrzeżeń")
        print()
    
    # Summary
    if all_ok:
        print("=" * 60)
        print("✓ WALIDACJA ZAKOŃCZONA SUKCESEM")
        print(f"  Dokument: {result.doc_id}")
        print(f"  Warianty: {len(result.variants)}")
        
        total_core = sum(len(v.core_codes) for v in result.variants)
        total_proph = sum(len(v.prophylaxis_codes) for v in result.variants)
        total_mappings = sum(len(v.mappings) for v in result.variants)
        
        print(f"  Łączna liczba kodów core: {total_core}")
        print(f"  Łączna liczba kodów profilaktyka: {total_proph}")
        print(f"  Łączna liczba mapowań: {total_mappings}")
        return True
    else:
        print("=" * 60)
        print("⚠ WALIDACJA ZAKOŃCZONA Z OSTRZEŻENIAMI")
        return False


def print_json_schema():
    """Print JSON schema for DocumentResult."""
    print("JSON Schema dla DocumentResult:")
    print("=" * 60)
    
    schema = ValidationHelper.get_json_schema(DocumentResult)
    print(json.dumps(schema, indent=2, ensure_ascii=False))


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_output.py <json_file>")
        print("   or: python validate_output.py --schema")
        sys.exit(1)
    
    if sys.argv[1] == "--schema":
        print_json_schema()
    else:
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"✗ Plik nie istnieje: {file_path}")
            sys.exit(1)
        
        success = validate_file(file_path)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

