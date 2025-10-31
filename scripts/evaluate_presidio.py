#!/usr/bin/env python3
"""
CLI script to evaluate Presidio on the synthetic corpus.

Usage:
    python scripts/evaluate_presidio.py [--corpus-dir DIR] [--output FILE]
"""

import argparse
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.presidio_evaluator import PresidioEvaluator


def main():
    parser = argparse.ArgumentParser(description="Evaluate Presidio on synthetic corpus")
    parser.add_argument(
        "--corpus-dir",
        type=str,
        default="data/corpus",
        help="Directory containing corpus files and annotations (default: data/corpus)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="cmos/reports/sprint-01/presidio_corpus_baseline.json",
        help="Output path for evaluation report (default: cmos/reports/sprint-01/presidio_corpus_baseline.json)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Presidio PII Detection Evaluation")
    print("=" * 60)
    print(f"Corpus directory: {args.corpus_dir}")
    print(f"Output file: {args.output}")
    print()
    
    evaluator = PresidioEvaluator(corpus_dir=args.corpus_dir)
    
    try:
        results = evaluator.evaluate_corpus()
        evaluator.save_baseline_report(results, args.output)
        
        print("\n" + "=" * 60)
        print("Evaluation Summary")
        print("=" * 60)
        print(f"Total samples: {results['total_samples']}")
        print(f"\nOverall Metrics:")
        print(f"  Precision: {results['metrics']['overall']['precision']:.4f}")
        print(f"  Recall:    {results['metrics']['overall']['recall']:.4f}")
        print(f"  F1-Score: {results['metrics']['overall']['f1']:.4f}")
        
        if results.get('per_entity'):
            print(f"\nPer-Entity Metrics:")
            for entity, metrics in results['per_entity'].items():
                print(f"  {entity}:")
                print(f"    Precision: {metrics['precision']:.4f}")
                print(f"    Recall:    {metrics['recall']:.4f}")
                print(f"    F1-Score:  {metrics['f1']:.4f}")
                print(f"    Support:   {metrics['support']}")
        
        print("\n" + "=" * 60)
        
    except Exception as e:
        print(f"\nError during evaluation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

