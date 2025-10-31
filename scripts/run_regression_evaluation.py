#!/usr/bin/env python3
"""
Regression evaluation script for Presidio redaction service.

Compares tuned configuration (en_core_web_lg + custom recognizers) against baseline.
"""

import argparse
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.presidio_redaction import PresidioRedactionService


def main():
    parser = argparse.ArgumentParser(
        description="Run regression evaluation for Presidio redaction service"
    )
    parser.add_argument(
        "--corpus-dir",
        type=str,
        default="data/corpus",
        help="Directory containing corpus files and annotations (default: data/corpus)"
    )
    parser.add_argument(
        "--baseline-report",
        type=str,
        default="cmos/reports/sprint-01/presidio_corpus_baseline.json",
        help="Path to baseline evaluation report (default: cmos/reports/sprint-01/presidio_corpus_baseline.json)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="cmos/reports/sprint-01/presidio_tuned_results.json",
        help="Output path for comparison results (default: cmos/reports/sprint-01/presidio_tuned_results.json)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Presidio Redaction Service - Regression Evaluation")
    print("=" * 60)
    print(f"Corpus directory: {args.corpus_dir}")
    print(f"Baseline report: {args.baseline_report}")
    print(f"Output file: {args.output}")
    print()
    
    # Initialize redaction service with tuned configuration
    print("Initializing Presidio redaction service...")
    service = PresidioRedactionService(spacy_model="en_core_web_lg")
    print(f"Using spaCy model: {service.spacy_model}")
    print(f"Custom recognizers: PARTICIPANT_ID, PROJECT_ID")
    print()
    
    # Run regression evaluation
    try:
        results = service.run_regression_evaluation(
            corpus_dir=args.corpus_dir,
            baseline_report_path=args.baseline_report,
            output_path=args.output
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("Evaluation Summary")
        print("=" * 60)
        
        tuned_metrics = results["tuned_metrics"]["overall"]
        print(f"Tuned Configuration Metrics:")
        print(f"  Precision: {tuned_metrics['precision']:.4f}")
        print(f"  Recall: {tuned_metrics['recall']:.4f}")
        print(f"  F1 Score: {tuned_metrics['f1']:.4f}")
        print(f"  Total Samples: {results['total_samples']}")
        
        if "deltas" in results:
            print(f"\nComparison to Baseline:")
            deltas = results["deltas"]
            print(f"  Precision Delta: {deltas['precision']:+.4f}")
            print(f"  Recall Delta: {deltas['recall']:+.4f}")
            print(f"  F1 Delta: {deltas['f1']:+.4f}")
            
            if "improvement" in results:
                impr = results["improvement"]
                print(f"\nImprovements:")
                print(f"  Precision Improved: {impr['precision_improved']}")
                print(f"  Recall Improved: {impr['recall_improved']}")
                print(f"  F1 Improved: {impr['f1_improved']}")
        
        print(f"\nDetailed results saved to: {args.output}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError during evaluation: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

