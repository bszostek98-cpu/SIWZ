"""
Script to run the SIWZ mapping pipeline on a PDF file.

Usage:
    python scripts/run_pipeline.py --pdf path/to/siwz.pdf --services path/to/services.json
"""

import argparse
import sys
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import Config, Service
from siwz_mapper.pipeline import Pipeline
from siwz_mapper.utils import setup_logging


def load_services(services_path: Path) -> list[Service]:
    """Load services from JSON file."""
    with open(services_path, 'r', encoding='utf-8') as f:
        services_data = json.load(f)
    
    return [Service(**svc) for svc in services_data]


def main():
    parser = argparse.ArgumentParser(
        description="Run SIWZ mapping pipeline"
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        required=True,
        help="Path to input SIWZ PDF file"
    )
    parser.add_argument(
        "--services",
        type=Path,
        required=True,
        help="Path to services dictionary JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to output JSON (default: output/<pdf_name>.json)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config YAML (optional)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(level=args.log_level)
    
    # Validate inputs
    if not args.pdf.exists():
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)
    
    if not args.services.exists():
        print(f"Error: Services file not found: {args.services}")
        sys.exit(1)
    
    # Load services
    print(f"Loading services from: {args.services}")
    services = load_services(args.services)
    print(f"Loaded {len(services)} services")
    
    # Create config
    config = Config()
    if args.config and args.config.exists():
        # TODO: Load from YAML when implemented
        print(f"Loading config from: {args.config}")
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / f"{args.pdf.stem}_mapping.json"
    
    # Initialize pipeline
    print("Initializing pipeline...")
    pipeline = Pipeline(config=config, services=services)
    
    # Process document
    print(f"\nProcessing: {args.pdf}")
    print("-" * 60)
    
    result = pipeline.process(
        pdf_path=args.pdf,
        output_path=output_path
    )
    
    # Print summary
    print("-" * 60)
    print("\nRESULTS:")
    print(f"  Document: {result.document_name}")
    print(f"  Mapping type: {result.mapping_type}")
    print(f"  Variants found: {len(result.variants)}")
    
    for variant_mapping in result.variants:
        print(f"\n  Variant: {variant_mapping.variant_name}")
        print(f"    Core services: {len(variant_mapping.core_services)}")
        print(f"    Prophylaxis services: {len(variant_mapping.prophylaxis_services)}")
        print(f"    Candidates: {len(variant_mapping.core_candidates)}")
    
    print(f"\nOutput saved to: {output_path}")


if __name__ == "__main__":
    main()

