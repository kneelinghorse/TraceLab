"""Focused unit contracts for keyed evidence-note upserts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.evidence_ledger import LedgerNote
from app.schemas.evidence_ledger import NoteUpsertRequest
from app.services.evidence_ledger import EvidenceLedgerService

pytestmark = pytest.mark.unit


def _integrity_error(constraint_name: str) -> IntegrityError:
    original = Exception("duplicate key value violates unique constraint")
    original.diag = SimpleNamespace(constraint_name=constraint_name)
    return IntegrityError("INSERT INTO ledger_notes", {}, original)


def _request() -> NoteUpsertRequest:
    return NoteUpsertRequest(
        project_id=uuid4(),
        session_key="shared-session",
        content="The retrying writer owns the complete replacement.",
        tags=["retry", "complete"],
    )


def test_note_identity_conflict_retries_full_server_owned_replacement() -> None:
    """The losing insert retries as an update without losing provenance or tenancy."""
    db = MagicMock(spec=Session)
    request = _request()
    owner_id = uuid4()
    workspace_id = uuid4()
    persisted = LedgerNote(
        project_id=request.project_id,
        session_key=request.session_key,
        note_key="working-note",
        origin="deepsearch-worker",
        content="First writer",
        tags=["first"],
        owner_id=uuid4(),
        workspace_id=uuid4(),
    )
    first = db.query.return_value.filter.return_value.first
    first.side_effect = [None, persisted]
    conflict = _integrity_error("uq_ledger_notes_project_session_key")
    db.commit.side_effect = [conflict, None]

    result = EvidenceLedgerService().upsert_note(
        db,
        "working-note",
        request,
        owner_id=owner_id,
        workspace_id=workspace_id,
    )

    assert result is persisted
    assert result.origin == "mcp-agent"
    assert result.content == request.content
    assert result.tags == request.tags
    assert result.owner_id == owner_id
    assert result.workspace_id == workspace_id
    assert first.call_count == 2
    assert db.commit.call_count == 2
    db.rollback.assert_called_once_with()
    db.refresh.assert_called_once_with(persisted)


def test_unrelated_integrity_error_is_rolled_back_and_reraised() -> None:
    """The retry must never convert foreign-key or other constraint failures."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = None
    unrelated = _integrity_error("ledger_notes_project_id_fkey")
    db.commit.side_effect = unrelated

    with pytest.raises(IntegrityError) as caught:
        EvidenceLedgerService().upsert_note(
            db,
            "working-note",
            _request(),
            owner_id=uuid4(),
            workspace_id=uuid4(),
        )

    assert caught.value is unrelated
    db.commit.assert_called_once_with()
    db.rollback.assert_called_once_with()
    assert db.query.return_value.filter.return_value.first.call_count == 1
