"""
Evaluation harness for SIWZ mapper.

Compares system mappings against ground truth annotations.

Usage:
    python scripts/evaluate.py --predictions output/results.json --ground-truth data/ground_truth.json
"""

import argparse
import sys
from pathlib import Path
import json
from typing import Dict, List, Set
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from siwz_mapper.models import MappingResult


@dataclass
class EvaluationMetrics:
    """Evaluation metrics."""
    
    precision: float
    recall: float
    f1: float
    
    # Per-variant metrics
    variant_metrics: Dict[str, Dict[str, float]]
    
    # Coverage metrics
    num_variants: int
    num_mapped: int
    num_unmapped: int
    
    def __str__(self) -> str:
        lines = [
            "EVALUATION METRICS",
            "=" * 60,
            f"Overall Precision: {self.precision:.3f}",
            f"Overall Recall:    {self.recall:.3f}",
            f"Overall F1:        {self.f1:.3f}",
            "",
            f"Variants: {self.num_variants}",
            f"Mapped:   {self.num_mapped}",
            f"Unmapped: {self.num_unmapped}",
        ]
        
        if self.variant_metrics:
            lines.append("\nPer-Variant Metrics:")
            lines.append("-" * 60)
            for variant_id, metrics in self.variant_metrics.items():
                lines.append(f"\n{variant_id}:")
                lines.append(f"  Precision: {metrics['precision']:.3f}")
                lines.append(f"  Recall:    {metrics['recall']:.3f}")
                lines.append(f"  F1:        {metrics['f1']:.3f}")
        
        return "\n".join(lines)


class Evaluator:
    """Evaluates mapping results against ground truth."""
    
    def __init__(self, ground_truth: Dict):
        """
        Initialize evaluator.
        
        Args:
            ground_truth: Ground truth annotations
        """
        self.ground_truth = ground_truth
    
    def evaluate(self, predictions: MappingResult) -> EvaluationMetrics:
        """
        Evaluate predictions against ground truth.
        
        Args:
            predictions: System predictions
            
        Returns:
            EvaluationMetrics
        """
        # Extract ground truth mappings
        gt_mappings = self._extract_ground_truth_mappings()
        
        # Extract predicted mappings
        pred_mappings = self._extract_predicted_mappings(predictions)
        
        # Calculate overall metrics
        overall_metrics = self._calculate_metrics(
            predicted=pred_mappings,
            ground_truth=gt_mappings
        )
        
        # Calculate per-variant metrics
        variant_metrics = {}
        for variant_id in gt_mappings.keys():
            gt_variant = gt_mappings.get(variant_id, set())
            pred_variant = pred_mappings.get(variant_id, set())
            
            variant_metrics[variant_id] = self._calculate_metrics(
                predicted={variant_id: pred_variant},
                ground_truth={variant_id: gt_variant}
            )
        
        return EvaluationMetrics(
            precision=overall_metrics['precision'],
            recall=overall_metrics['recall'],
            f1=overall_metrics['f1'],
            variant_metrics=variant_metrics,
            num_variants=len(predictions.variants),
            num_mapped=sum(
                len(v.core_services) + len(v.prophylaxis_services)
                for v in predictions.variants
            ),
            num_unmapped=len(predictions.unmapped_spans)
        )
    
    def _extract_ground_truth_mappings(self) -> Dict[str, Set[str]]:
        """Extract ground truth mappings per variant."""
        mappings = {}
        
        for variant in self.ground_truth.get('variants', []):
            variant_id = variant['variant_id']
            services = set(variant.get('core_services', []))
            services.update(variant.get('prophylaxis_services', []))
            mappings[variant_id] = services
        
        return mappings
    
    def _extract_predicted_mappings(self, predictions: MappingResult) -> Dict[str, Set[str]]:
        """Extract predicted mappings per variant."""
        mappings = {}
        
        for variant in predictions.variants:
            services = set(variant.core_services)
            services.update(variant.prophylaxis_services)
            mappings[variant.variant_id] = services
        
        return mappings
    
    def _calculate_metrics(
        self,
        predicted: Dict[str, Set[str]],
        ground_truth: Dict[str, Set[str]]
    ) -> Dict[str, float]:
        """Calculate precision, recall, F1."""
        # Flatten all services
        pred_all = set()
        gt_all = set()
        
        for services in predicted.values():
            pred_all.update(services)
        
        for services in ground_truth.values():
            gt_all.update(services)
        
        # Calculate metrics
        if len(pred_all) == 0:
            precision = 0.0
        else:
            precision = len(pred_all & gt_all) / len(pred_all)
        
        if len(gt_all) == 0:
            recall = 0.0
        else:
            recall = len(pred_all & gt_all) / len(gt_all)
        
        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1
        }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate SIWZ mapping results"
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Path to predictions JSON"
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Path to ground truth JSON"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to save evaluation results"
    )
    
    args = parser.parse_args()
    
    # Load files
    print(f"Loading predictions from: {args.predictions}")
    with open(args.predictions, 'r', encoding='utf-8') as f:
        predictions_data = json.load(f)
    
    predictions = MappingResult(**predictions_data)
    
    print(f"Loading ground truth from: {args.ground_truth}")
    with open(args.ground_truth, 'r', encoding='utf-8') as f:
        ground_truth = json.load(f)
    
    # Evaluate
    print("\nEvaluating...")
    evaluator = Evaluator(ground_truth=ground_truth)
    metrics = evaluator.evaluate(predictions)
    
    # Print results
    print("\n" + str(metrics))
    
    # Save if requested
    if args.output:
        metrics_dict = {
            'precision': metrics.precision,
            'recall': metrics.recall,
            'f1': metrics.f1,
            'num_variants': metrics.num_variants,
            'num_mapped': metrics.num_mapped,
            'num_unmapped': metrics.num_unmapped,
            'variant_metrics': metrics.variant_metrics
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(metrics_dict, f, indent=2, ensure_ascii=False)
        
        print(f"\nMetrics saved to: {args.output}")


if __name__ == "__main__":
    main()

