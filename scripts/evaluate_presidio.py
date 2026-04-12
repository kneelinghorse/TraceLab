#!/usr/bin/env python3
"""
CLI script to evaluate Presidio on the synthetic corpus.

Usage:
    python scripts/evaluate_presidio.py [--corpus-dir DIR] [--output FILE]
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate Presidio on synthetic corpus"
    )
    parser.add_argument(
        "--corpus-dir",
        type=str,
        default="data/corpus",
        help="Directory containing corpus files and annotations (default: data/corpus)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="cmos/reports/sprint-01/presidio_corpus_baseline.json",
        help="Output path for evaluation report (default: cmos/reports/sprint-01/presidio_corpus_baseline.json)",
    )
    parser.parse_args()

    message = (
        "Presidio evaluator tooling has been retired. "
        "Use the lightweight regex-based redaction service directly instead."
    )
    print(message)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
