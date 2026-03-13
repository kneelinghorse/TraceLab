#!/usr/bin/env python3
"""
Package the synthetic UX research corpus into a distributable archive.

Generates a compressed archive, manifest, and optional baseline report copy to
facilitate secure promotion to a cloud bucket or external storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional


ARCHIVE_FORMAT = Literal["gztar", "zip"]
DEFAULT_BASELINE_PATH = Path("cmos/reports/sprint-01/presidio_corpus_baseline.json")


def _compute_sha256(file_path: Path) -> str:
    """Return the SHA-256 checksum of a file."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_corpus(
    corpus_dir: Path,
    output_dir: Path,
    archive_format: ARCHIVE_FORMAT = "gztar",
    include_baseline: bool = True,
    baseline_path: Optional[Path] = None,
) -> Dict[str, Optional[Path]]:
    """
    Package a corpus directory into an archive and produce a manifest.

    Args:
        corpus_dir: Directory containing generated corpus artifacts.
        output_dir: Destination directory for the archive and manifest.
        archive_format: Archive format supported by shutil.make_archive.
        include_baseline: Whether to copy the baseline JSON into the package directory.
        baseline_path: Optional explicit path to the baseline report.

    Returns:
        Dictionary with paths to the archive, manifest, and baseline copy.
    """

    corpus_dir = corpus_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = corpus_dir / "corpus_metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"corpus_metadata.json not found at {metadata_path}. Generate the corpus first."
        )

    with open(metadata_path, "r", encoding="utf-8") as handle:
        corpus_metadata = json.load(handle)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    archive_basename = output_dir / f"synthetic_corpus_{timestamp}"

    archive_path_str = shutil.make_archive(
        base_name=str(archive_basename),
        format=archive_format,
        root_dir=str(corpus_dir),
    )
    archive_path = Path(archive_path_str)
    checksum = _compute_sha256(archive_path)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest: Dict[str, object] = {
        "generated_at": generated_at,
        "archive": {
            "path": str(archive_path),
            "format": archive_format,
            "size_bytes": archive_path.stat().st_size,
            "sha256": checksum,
        },
        "corpus_metadata": corpus_metadata,
    }

    baseline_copy: Optional[Path] = None
    if include_baseline:
        resolved_baseline = (baseline_path or DEFAULT_BASELINE_PATH).resolve()
        if resolved_baseline.exists():
            baseline_copy = output_dir / resolved_baseline.name
            shutil.copy2(resolved_baseline, baseline_copy)
            manifest["baseline_report"] = {
                "path": str(baseline_copy),
                "source": str(resolved_baseline),
            }
        else:
            print(
                f"Warning: Baseline report not found at {resolved_baseline}. Skipping copy."
            )

    manifest_path = archive_path.with_name(f"{archive_path.stem}_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    return {
        "archive_path": archive_path,
        "manifest_path": manifest_path,
        "baseline_path": baseline_copy,
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package the synthetic corpus into an archive with manifest."
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
        help="Directory where the archive and manifest will be written (default: artifacts/corpus_packages)",
    )
    parser.add_argument(
        "--archive-format",
        choices=["gztar", "zip"],
        default="gztar",
        help="Archive format to generate (default: gztar)",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Skip copying the baseline evaluation report into the package directory.",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=None,
        help="Optional explicit path to the baseline JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    result = package_corpus(
        corpus_dir=args.corpus_dir,
        output_dir=args.output_dir,
        archive_format=args.archive_format,  # type: ignore[arg-type]
        include_baseline=not args.no_baseline,
        baseline_path=args.baseline_path,
    )

    print("=" * 72)
    print("Corpus packaging complete.")
    print(f"Archive: {result['archive_path']}")
    print(f"Manifest: {result['manifest_path']}")
    if result.get("baseline_path"):
        print(f"Baseline copy: {result['baseline_path']}")
    else:
        print("Baseline copy: skipped")
    print("=" * 72)
    print("Next steps:")
    print("  - Inspect the manifest for configuration details.")
    print(
        "  - Transfer the archive to your secure bucket or vault using your preferred tool."
    )
    print("  - Record the SHA-256 checksum for integrity verification.")
    print("=" * 72)


if __name__ == "__main__":
    main(sys.argv[1:])
