"""End-to-end authentication helpers for TraceLab."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict

import requests


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def login(base_url: str, username: str, password: str) -> str:
    """Authenticate against the FastAPI service and return an access token."""
    response = requests.post(
        _url(base_url, "/api/v1/auth/login"),
        json={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Login response missing access_token field")
    return token


def refresh_token(base_url: str, token: str) -> str:
    """Refresh an existing token and return the rotated JWT."""
    response = requests.post(
        _url(base_url, "/api/v1/auth/refresh"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    refreshed = payload.get("access_token")
    if not refreshed:
        raise RuntimeError("Refresh response missing access_token field")
    return refreshed


def fetch_missions(base_url: str, token: str) -> Dict[str, Any]:
    """Fetch the missions listing to prove downstream access works."""
    response = requests.get(
        _url(base_url, "/api/v1/missions/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TraceLab auth smoke test helper.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="FastAPI base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--username",
        default="tracelab-admin",
        help="Auth username (default: %(default)s)",
    )
    parser.add_argument(
        "--password", default="changeme", help="Auth password (default: %(default)s)"
    )
    args = parser.parse_args(argv)

    print(f"[auth] Logging in to {args.base_url} as {args.username}")
    token = login(args.base_url, args.username, args.password)
    print("[auth] Received access token.")

    print("[auth] Refreshing token...")
    refreshed = refresh_token(args.base_url, token)
    print("[auth] Refresh successful.")

    print("[auth] Fetching missions with refreshed token...")
    missions = fetch_missions(args.base_url, refreshed)
    mission_count = len(missions) if isinstance(missions, list) else 1
    print(f"[auth] Retrieved {mission_count} mission entries.")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    sys.exit(main())
