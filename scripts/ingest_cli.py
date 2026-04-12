#!/usr/bin/env python3
"""Lightweight CLI to drive the ingestion API end-to-end."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import httpx
from starlette.testclient import TestClient

from app.core.config import settings
from app.main import app


AUTH_TOKEN_ENV = ("INGEST_CLI_TOKEN",)
AUTH_USERNAME_ENV = ("INGEST_CLI_USERNAME", "AUTH_USERNAME")
AUTH_PASSWORD_ENV = ("INGEST_CLI_PASSWORD", "AUTH_PASSWORD")


@dataclass(slots=True)
class AuthConfig:
    """Resolved authentication inputs for the CLI."""

    token: Optional[str]
    username: Optional[str]
    password: Optional[str]


def _first_non_empty(*candidates: Optional[str]) -> Optional[str]:
    """Return the first non-empty string from the provided candidates."""

    for value in candidates:
        if value:
            return value
    return None


def _resolve_auth_config(
    *,
    token: Optional[str],
    username: Optional[str],
    password: Optional[str],
) -> AuthConfig:
    """Merge CLI args, env vars, and default settings into an auth config."""

    env = os.environ
    resolved_token = _first_non_empty(token, *(env.get(key) for key in AUTH_TOKEN_ENV))
    resolved_username = _first_non_empty(
        username,
        *(env.get(key) for key in AUTH_USERNAME_ENV),
        settings.auth_username,
    )
    resolved_password = _first_non_empty(
        password,
        *(env.get(key) for key in AUTH_PASSWORD_ENV),
        settings.auth_password,
    )
    return AuthConfig(
        token=resolved_token, username=resolved_username, password=resolved_password
    )


def _acquire_token(
    client: httpx.Client | TestClient, api_prefix: str, auth: AuthConfig
) -> str:
    """Ensure a bearer token is available, logging in when necessary."""

    if auth.token:
        return auth.token

    if not auth.username or not auth.password:
        raise RuntimeError(
            "Authentication credentials are required. Provide --username/--password or set AUTH_USERNAME/AUTH_PASSWORD."
        )

    login_url = f"{api_prefix}/auth/login"
    response = client.post(
        login_url,
        json={"username": auth.username, "password": auth.password},
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but response did not include access_token")
    return token


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
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload and process a document through the ingestion API with authentication."""

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    api_prefix = settings.api_v1_prefix.rstrip("/")
    upload_url = f"{api_prefix}/documents/upload"
    client_context: httpx.Client | TestClient
    if offline:
        client_context = TestClient(app)
    else:
        if not base_url:
            raise ValueError("base_url must be provided when not running offline")
        client_context = httpx.Client(
            timeout=30.0, base_url=(base_url or "").rstrip("/")
        )

    auth = _resolve_auth_config(token=token, username=username, password=password)

    with client_context as client:
        bearer_token = _acquire_token(client, api_prefix, auth)
        headers = {"Authorization": f"Bearer {bearer_token}"}
        with file_path.open("rb") as handle:
            files = {"file": (file_path.name, handle, _detect_mime_type(file_path))}
            upload_response = client.post(
                upload_url,
                params={"project_id": project_id},
                files=files,
                headers=headers,
            )

        upload_response.raise_for_status()
        upload_payload = upload_response.json()
        document_id = upload_payload["id"]

        process_url = f"{api_prefix}/documents/{document_id}/process"
        process_response = client.post(process_url, headers=headers)
        process_response.raise_for_status()
        process_payload = process_response.json()

        detail_url = f"{api_prefix}/documents/{document_id}"
        detail_response = client.get(detail_url, headers=headers)
        detail_response.raise_for_status()
        detail_payload = detail_response.json()

    if not detail_payload.get("processed"):
        raise RuntimeError(
            "Document ingestion did not complete: processed flag is False"
        )
    if not detail_payload.get("chunked"):
        raise RuntimeError("Document ingestion did not complete: chunked flag is False")

    return {
        "document_id": document_id,
        "project_id": project_id,
        "upload": upload_payload,
        "process": process_payload,
        "document": detail_payload,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Drive ingestion flow via CLI")
    parser.add_argument("file", help="Path to document to ingest")
    parser.add_argument("project_id", help="Project identifier (UUID)")
    parser.add_argument(
        "--base-url",
        dest="base_url",
        help="API base URL (required when not using --offline)",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Execute against in-process FastAPI app"
    )
    parser.add_argument("--output", help="Optional path to write JSON results")
    parser.add_argument(
        "--username", help="Authentication username (defaults to env AUTH_USERNAME)"
    )
    parser.add_argument(
        "--password", help="Authentication password (defaults to env AUTH_PASSWORD)"
    )
    parser.add_argument(
        "--token", help="Existing bearer token to use instead of logging in"
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = run_ingestion(
            project_id=args.project_id,
            file_path=Path(args.file),
            base_url=args.base_url,
            offline=args.offline,
            username=args.username,
            password=args.password,
            token=args.token,
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
