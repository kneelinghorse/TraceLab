#!/usr/bin/env python3
"""
Package and stage the synthetic corpus archive for secure upload.

Creates a packaged corpus artifact (via package_corpus.py) and copies the
resulting files into the specified destination directory, ready for manual
promotion to a secure cloud bucket.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from package_corpus import package_corpus  # type: ignore  # noqa: E402


def copy_to_destination(files: List[Path], destination: Path) -> List[Path]:
    """Copy files into the destination directory, returning the copied paths."""
    destination.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []

    for file_path in files:
        if not file_path:
            continue
        target = destination / file_path.name
        shutil.copy2(file_path, target)
        copied.append(target)

    return copied


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the corpus and copy artifacts to a secure destination."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("data/corpus"),
        help="Directory containing generated corpus artifacts (default: data/corpus)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/corpus_packages"),
        help="Directory for intermediate archive/manifest files (default: artifacts/corpus_packages)",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="Destination directory representing secure storage or upload staging area.",
    )
    parser.add_argument(
        "--archive-format",
        choices=["gztar", "zip"],
        default="gztar",
        help="Archive format to create before copying (default: gztar)",
    )
    parser.add_argument(
        "--retain-local",
        action="store_true",
        help="Retain the packaged archive in the output directory after copying.",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip copying the baseline evaluation report.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)

    result = package_corpus(
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        archive_format=args.archive_format,  # type: ignore[arg-type]
        include_baseline=not args.no_baseline,
        baseline_path=None,
    )

    files_to_copy = [
        result["archive_path"],
        result["manifest_path"],
        result.get("baseline_path"),
    ]
    copied_files = copy_to_destination([p for p in files_to_copy if p], args.destination)

    if not args.retain_local:
        for file_path in [result["archive_path"], result["manifest_path"]]:
            if file_path and file_path.exists():
                file_path.unlink()
        if result.get("baseline_path") and result["baseline_path"].exists():
            result["baseline_path"].unlink()

    print("=" * 72)
    print("Corpus upload staging complete.")
    print(f"Destination: {args.destination.resolve()}")
    if copied_files:
        print("Copied files:")
        for copied_file in copied_files:
            print(f"  - {copied_file}")
    else:
        print("Copied files: none")
    print("=" * 72)
    print("Suggested next step:")
    print("  Use your preferred tooling to transfer the archive to secure storage.")
    if copied_files:
        example_path = copied_files[0]
        print("  Examples:")
        print(
            f"    aws s3 cp {example_path} "
            f"s3://<bucket>/presidio/{datetime.now(timezone.utc):%Y%m%d}/"
        )
        print(f"    az storage blob upload --file {example_path} --container-name <container>")
    print("=" * 72)


if __name__ == "__main__":
    main(sys.argv[1:])
