"""Decision–Insight linking API for cross-referencing CMOS decisions with TraceLab evidence.

GET  /api/v1/decisions/linked
  → List decisions that have TraceLab evidence references

GET  /api/v1/decisions/linked/{decision_id}
  → Get a single decision with its evidence details

POST /api/v1/decisions/linked/{decision_id}/evidence
  → Add evidence references to an existing decision
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import AuthenticatedUser, require_authenticated_user

logger = logging.getLogger(__name__)

router = APIRouter()

_CMOS_DB_PATH: Optional[Path] = None


def _find_cmos_db() -> Path:
    """Locate the CMOS SQLite database relative to the project root."""
    global _CMOS_DB_PATH
    if _CMOS_DB_PATH and _CMOS_DB_PATH.exists():
        return _CMOS_DB_PATH

    candidates = [
        Path(__file__).resolve().parents[3] / "cmos" / "db" / "cmos.sqlite",
        Path.cwd() / "cmos" / "db" / "cmos.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            _CMOS_DB_PATH = candidate
            return candidate

    raise FileNotFoundError("CMOS database not found")


def _query_cmos(sql: str, params: dict | None = None) -> List[Dict[str, Any]]:
    """Execute a read-only query against the CMOS SQLite database."""
    db_path = _find_cmos_db()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _update_cmos(sql: str, params: dict | None = None) -> int:
    """Execute a write query against the CMOS SQLite database."""
    db_path = _find_cmos_db()
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(sql, params or {})
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# --- Schemas ---


class EvidenceRef(BaseModel):
    """A reference to a TraceLab entity used as evidence for a decision."""

    type: str = Field(..., description="Evidence type: insight, document, chunk, mission, search_result")
    id: str = Field(..., description="TraceLab entity ID (UUID or URN)")


class LinkedDecision(BaseModel):
    """A CMOS strategic decision with its TraceLab evidence links."""

    id: int
    decision_text: str
    created_at: str
    sprint_id: Optional[str] = None
    mission_id: Optional[str] = None
    project_domain: Optional[str] = None
    evidence: List[EvidenceRef] = Field(default_factory=list)


class AddEvidenceRequest(BaseModel):
    """Payload for adding evidence to a decision."""

    evidence: List[EvidenceRef] = Field(..., min_length=1, description="Evidence references to add")
    mission_id: Optional[str] = Field(None, description="CMOS mission ID to associate")


# --- Endpoints ---


@router.get("/decisions/linked", response_model=List[LinkedDecision])
def list_linked_decisions(
    mission_id: Optional[str] = Query(None, description="Filter by CMOS mission ID"),
    sprint_id: Optional[str] = Query(None, description="Filter by sprint ID"),
    has_evidence: bool = Query(False, description="Only return decisions with evidence links"),
    limit: int = Query(50, ge=1, le=200),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """List CMOS strategic decisions with their TraceLab evidence links."""
    try:
        conditions = ["1=1"]
        params: Dict[str, Any] = {}

        if mission_id:
            conditions.append("mission_id = :mission_id")
            params["mission_id"] = mission_id
        if sprint_id:
            conditions.append("sprint_id = :sprint_id")
            params["sprint_id"] = sprint_id
        if has_evidence:
            conditions.append("evidence IS NOT NULL AND evidence != '[]'")

        where = " AND ".join(conditions)
        params["limit"] = limit

        rows = _query_cmos(
            f"""
            SELECT id, decision_text, created_at, sprint_id, mission_id,
                   project_domain, evidence
            FROM strategic_decisions
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            params,
        )

        return [_row_to_linked_decision(row) for row in rows]

    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="CMOS database not available")
    except Exception as exc:
        logger.warning("Failed to query CMOS decisions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to query decisions")


@router.get("/decisions/linked/{decision_id}", response_model=LinkedDecision)
def get_linked_decision(
    decision_id: int,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Get a single CMOS decision with its evidence links."""
    try:
        rows = _query_cmos(
            """
            SELECT id, decision_text, created_at, sprint_id, mission_id,
                   project_domain, evidence
            FROM strategic_decisions
            WHERE id = :id
            """,
            {"id": decision_id},
        )

        if not rows:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

        return _row_to_linked_decision(rows[0])

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="CMOS database not available")
    except Exception as exc:
        logger.warning("Failed to get decision %s: %s", decision_id, exc)
        raise HTTPException(status_code=500, detail="Failed to get decision")


@router.post("/decisions/linked/{decision_id}/evidence", response_model=LinkedDecision)
def add_evidence_to_decision(
    decision_id: int,
    payload: AddEvidenceRequest,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Add TraceLab evidence references to an existing CMOS decision.

    Merges new evidence with any existing references (no duplicates).
    """
    try:
        rows = _query_cmos(
            "SELECT id, decision_text, created_at, sprint_id, mission_id, project_domain, evidence "
            "FROM strategic_decisions WHERE id = :id",
            {"id": decision_id},
        )

        if not rows:
            raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")

        row = rows[0]

        existing_evidence = _parse_evidence(row.get("evidence"))
        existing_keys = {(e["type"], e["id"]) for e in existing_evidence}

        for ref in payload.evidence:
            key = (ref.type, ref.id)
            if key not in existing_keys:
                existing_evidence.append({"type": ref.type, "id": ref.id})
                existing_keys.add(key)

        updates = {"evidence": json.dumps(existing_evidence, ensure_ascii=False), "id": decision_id}
        update_sql = "UPDATE strategic_decisions SET evidence = :evidence"

        if payload.mission_id and not row.get("mission_id"):
            updates["mission_id"] = payload.mission_id
            update_sql += ", mission_id = :mission_id"

        update_sql += " WHERE id = :id"
        _update_cmos(update_sql, updates)

        updated_rows = _query_cmos(
            "SELECT id, decision_text, created_at, sprint_id, mission_id, project_domain, evidence "
            "FROM strategic_decisions WHERE id = :id",
            {"id": decision_id},
        )
        return _row_to_linked_decision(updated_rows[0])

    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="CMOS database not available")
    except Exception as exc:
        logger.warning("Failed to add evidence to decision %s: %s", decision_id, exc)
        raise HTTPException(status_code=500, detail="Failed to add evidence")


# --- Helpers ---


def _parse_evidence(raw: Any) -> List[Dict[str, str]]:
    """Parse evidence JSON from database column."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_linked_decision(row: Dict[str, Any]) -> LinkedDecision:
    """Convert a database row to a LinkedDecision model."""
    evidence_data = _parse_evidence(row.get("evidence"))
    evidence_refs = [
        EvidenceRef(type=e["type"], id=e["id"])
        for e in evidence_data
        if isinstance(e, dict) and "type" in e and "id" in e
    ]

    return LinkedDecision(
        id=row["id"],
        decision_text=row["decision_text"],
        created_at=row["created_at"],
        sprint_id=row.get("sprint_id"),
        mission_id=row.get("mission_id"),
        project_domain=row.get("project_domain"),
        evidence=evidence_refs,
    )
