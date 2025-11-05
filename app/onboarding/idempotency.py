"""Idempotency helpers for onboarding API endpoints."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyRecord


def _canonical_body(payload: Optional[Dict[str, Any]]) -> str:
    """Return deterministic JSON string for hashing."""
    if not payload:
        return "{}"
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except TypeError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payload is not JSON serializable for idempotent storage: {exc}",
        ) from exc


def _hash_payload(payload: Optional[Dict[str, Any]]) -> str:
    """Compute SHA-256 hash for a request payload."""
    return hashlib.sha256(_canonical_body(payload).encode("utf-8")).hexdigest()


@dataclass
class CachedResponse:
    """Container for cached responses."""

    status_code: int
    data: Dict[str, Any]


class IdempotencyService:
    """Store and retrieve cached responses keyed by the Idempotency-Key header."""

    def __init__(self, db: Session, *, method: str, path: str, key: Optional[str]) -> None:
        self.db = db
        self.method = method.upper()
        self.path = path
        self.key = key

    def check_replay(self, request_payload: Optional[Dict[str, Any]]) -> Optional[CachedResponse]:
        """Return cached response if the request has been processed."""
        if not self.key:
            return None

        record = (
            self.db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.key == self.key)
            .first()
        )
        if not record:
            return None

        expected_hash = record.request_hash
        incoming_hash = _hash_payload(request_payload)
        if expected_hash != incoming_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reused with different payload",
            )

        return CachedResponse(status_code=record.status_code, data=record.response_data or {})

    def save_response(
        self,
        *,
        request_payload: Optional[Dict[str, Any]],
        response_payload: Dict[str, Any],
        status_code: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Persist response payload for future replays."""
        if not self.key:
            return

        payload_hash = _hash_payload(request_payload)

        record = (
            self.db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.key == self.key)
            .first()
        )
        if record:
            record.method = self.method
            record.path = self.path
            record.request_hash = payload_hash
            record.status_code = status_code
            record.response_data = response_payload
            record.error_message = error_message
        else:
            record = IdempotencyRecord(
                key=self.key,
                method=self.method,
                path=self.path,
                request_hash=payload_hash,
                status_code=status_code,
                response_data=response_payload,
                error_message=error_message,
            )
            self.db.add(record)
        self.db.flush()
