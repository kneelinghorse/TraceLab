#!/usr/bin/env python3
"""Generate ingestion parity reports comparing source Markdown to persisted chunks."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.processing_status import DocumentProcessingStatus


@dataclass
class ParityMetrics:
    document_id: str
    source_path: Optional[str]
    source_char_count: int
    chunk_count: int
    chunk_char_count: int
    coverage_ratio: float
    processed: bool
    chunked: bool
    validation_status: Optional[str]


def _open_session(provided: Optional[Session]) -> Session:
    if provided is not None:
        return provided
    return SessionLocal()


def _close_session(session: Session, provided: Optional[Session]) -> None:
    if provided is None:
        session.close()


def _derive_metrics(document: Document, chunks: List[DocumentChunk], source_text: str) -> ParityMetrics:
    chunk_char_count = sum(len(chunk.content or "") for chunk in chunks)
    source_chars = len(source_text)
    ratio = (chunk_char_count / source_chars) if source_chars else 0.0
    return ParityMetrics(
        document_id=str(document.id),
        source_path=document.file_path,
        source_char_count=source_chars,
        chunk_count=len(chunks),
        chunk_char_count=chunk_char_count,
        coverage_ratio=round(ratio, 4),
        processed=bool(document.processed),
        chunked=bool(document.chunked),
        validation_status=document.validation_status,
    )


def generate_parity_report(
    document_id: str,
    *,
    output_dir: Path = Path("artifacts/ingestion-parity"),
    markdown_path: Optional[Path] = None,
    session: Optional[Session] = None,
) -> Path:
    """Compute parity metrics and persist them to JSON."""

    db = _open_session(session)
    try:
        document = db.query(Document).filter(Document.id == document_id).one()
        source_path = markdown_path or (Path(document.file_path) if document.file_path else None)
        if source_path and not source_path.exists():
            source_text = ""
        elif source_path:
            source_text = source_path.read_text()
        else:
            source_text = document.content or ""

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        events = (
            db.query(DocumentProcessingStatus)
            .filter(DocumentProcessingStatus.document_id == document.id)
            .order_by(DocumentProcessingStatus.created_at)
            .all()
        )

        metrics = _derive_metrics(document, chunks, source_text)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{document_id}.json"
        payload = {
            "metrics": asdict(metrics),
            "processing_events": [
                {
                    "stage": event.stage,
                    "status": event.status,
                    "detail": event.message,
                    "created_at": event.created_at.isoformat() + "Z" if event.created_at else None,
                }
                for event in events
            ],
        }
        output_path.write_text(json.dumps(payload, indent=2))
        return output_path
    finally:
        _close_session(db, session)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate ingestion parity report")
    parser.add_argument("document_id", help="Target document identifier")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ingestion-parity"))
    parser.add_argument("--markdown-path", type=Path, help="Optional path to source markdown file")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output_path = generate_parity_report(
            args.document_id,
            output_dir=args.output_dir,
            markdown_path=args.markdown_path,
        )
    except Exception as exc:  # pragma: no cover - CLI entry point
        print(f"[parity] error: {exc}")
        return 1

    print(json.dumps({"report": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
