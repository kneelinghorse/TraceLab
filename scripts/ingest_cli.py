#!/usr/bin/env python3
"""Lightweight CLI to drive the ingestion API end-to-end."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
from starlette.testclient import TestClient

from app.core.config import settings
from app.main import app


def _detect_mime_type(path: Path) -> str:
    mapping: Dict[str, str] = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
    }
    return mapping.get(path.suffix.lower(), "application/octet-stream")


def run_ingestion(
    *,
    project_id: str,
    file_path: Path,
    base_url: Optional[str] = None,
    offline: bool = False,
) -> Dict[str, object]:
    """Upload and process a document through the ingestion API."""

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    api_prefix = settings.api_v1_prefix.rstrip("/")
    upload_url = f"{api_prefix}/documents/upload"
    client_context = (
        TestClient(app)
        if offline
        else httpx.Client(timeout=30.0, base_url=(base_url or "").rstrip("/"))
    )

    if not offline and not base_url:
        raise ValueError("base_url must be provided when not running offline")

    with client_context as client:
        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, _detect_mime_type(file_path))}
            upload_response = client.post(upload_url, params={"project_id": project_id}, files=files)

        upload_response.raise_for_status()
        upload_payload = upload_response.json()
        document_id = upload_payload["id"]

        process_url = f"{api_prefix}/documents/{document_id}/process"
        process_response = client.post(process_url)
        process_response.raise_for_status()

        detail_url = f"{api_prefix}/documents/{document_id}"
        detail_response = client.get(detail_url)
        detail_response.raise_for_status()

    return {
        "document_id": document_id,
        "project_id": project_id,
        "upload": upload_payload,
        "process": process_response.json(),
        "document": detail_response.json(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive ingestion flow via CLI")
    parser.add_argument("file", help="Path to document to ingest")
    parser.add_argument("project_id", help="Project identifier (UUID)")
    parser.add_argument("--base-url", dest="base_url", help="API base URL (required when not using --offline)")
    parser.add_argument("--offline", action="store_true", help="Execute against in-process FastAPI app")
    parser.add_argument("--output", help="Optional path to write JSON results")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = run_ingestion(
            project_id=args.project_id,
            file_path=Path(args.file),
            base_url=args.base_url,
            offline=args.offline,
        )
    except Exception as exc:  # pragma: no cover - surfaced via CLI exit code
        print(f"[ingest-cli] error: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(result, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
