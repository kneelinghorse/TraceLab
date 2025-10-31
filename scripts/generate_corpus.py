#!/usr/bin/env python3
"""
CLI script to generate the synthetic UX research corpus.

Usage:
    python scripts/generate_corpus.py [--output-dir DIR] [--seed SEED]
"""

import argparse
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.corpus_generator import CorpusGenerator


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic UX research corpus")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/corpus",
        help="Output directory for generated corpus (default: data/corpus)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    parser.add_argument(
        "--transcript-txt",
        type=int,
        default=200,
        help="Number of TXT interview transcripts (default: 200)"
    )
    parser.add_argument(
        "--transcript-docx",
        type=int,
        default=200,
        help="Number of DOCX interview transcripts (default: 200)"
    )
    parser.add_argument(
        "--survey-responses",
        type=int,
        default=300,
        help="Number of survey responses to include in the CSV artifact (default: 300)"
    )
    parser.add_argument(
        "--persona-pdf",
        type=int,
        default=75,
        help="Number of PDF user personas (default: 75)"
    )
    parser.add_argument(
        "--persona-docx",
        type=int,
        default=75,
        help="Number of DOCX user personas (default: 75)"
    )
    parser.add_argument(
        "--test-notes",
        type=int,
        default=150,
        help="Number of usability test notes (default: 150)"
    )
    parser.add_argument(
        "--research-briefs",
        type=int,
        default=100,
        help="Number of Markdown research briefs (default: 100)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Synthetic UX Research Corpus Generator")
    print("=" * 60)
    print(f"Output directory: {args.output_dir}")
    print(f"Seed: {args.seed}")
    print()
    
    generator = CorpusGenerator(output_dir=args.output_dir, seed=args.seed)
    
    metadata = generator.generate_corpus(
        transcript_txt_count=args.transcript_txt,
        transcript_docx_count=args.transcript_docx,
        survey_responses=args.survey_responses,
        persona_pdf_count=args.persona_pdf,
        persona_docx_count=args.persona_docx,
        test_notes_count=args.test_notes,
        research_brief_count=args.research_briefs,
    )
    
    print("\n" + "=" * 60)
    print("Corpus generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
