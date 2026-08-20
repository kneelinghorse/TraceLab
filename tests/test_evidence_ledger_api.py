"""Acceptance tests for the project-scoped Evidence Ledger HTTP surface.

The ledger exists to preserve sourced findings across agent sessions.  These tests
therefore emphasize the failure modes that would make that memory unsafe or useless:
partial batch writes, caller-controlled provenance, cross-tenant visibility, totals
computed before authorization, and promotion that loses source provenance.
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import (
    ROLE_MEMBER,
    ROLE_SERVICE,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry, LedgerNote
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.space_member import SpaceMember
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.evidence_ledger import CaptureRequest
from app.services.evidence_ledger import (
    EvidenceLedgerService,
    get_evidence_ledger_service,
)
from app.services.report_promotion import ReportPromotionService

API = f"{settings.api_v1_prefix}/evidence"
_HASH = "placeholder-not-a-real-hash"

ENTRY_FIELDS = {
    "id",
    "project_id",
    "mission_id",
    "session_key",
    "origin",
    "claim",
    "summary",
    "source_url",
    "snippet",
    "query",
    "disposition",
    "tags",
    "owner_id",
    "workspace_id",
    "created_at",
    "updated_at",
}
NOTE_FIELDS = {
    "id",
    "project_id",
    "mission_id",
    "session_key",
    "origin",
    "note_key",
    "content",
    "tags",
    "owner_id",
    "workspace_id",
    "created_at",
    "updated_at",
}


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


def _user(db, email: str, role: str = ROLE_MEMBER) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=_HASH,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _api_key(db, user: User) -> dict[str, str]:
    plain = generate_api_key()
    db.add(
        APIKey(
            user_id=user.id,
            name="evidence-ledger-test",
            key_hash=hash_api_key(plain),
            key_prefix=get_key_prefix(plain),
        )
    )
    db.commit()
    return {"X-API-Key": plain}


def _space_project(db, member: User, *, name: str = "Ledger project"):
    space = Workspace(name=f"{name} space")
    db.add(space)
    db.commit()
    db.refresh(space)
    db.add(SpaceMember(workspace_id=space.id, user_id=member.id))
    project = Project(name=name, workspace_id=space.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return space, project


def _mission(db, project: Project, *, label: str = "LEDGER") -> Mission:
    mission = Mission(
        project_id=project.id,
        mission_id=f"{label}-{uuid4().hex[:8]}",
        title="Evidence Ledger acceptance mission",
        objective="Preserve sourced findings across agent sessions.",
        success_criteria=["Every finding retains its provenance."],
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def _capture(
    client: TestClient,
    headers: dict[str, str],
    project: Project,
    *,
    session_key: str,
    entries: list[dict],
    mission: Mission | None = None,
):
    body = {
        "project_id": str(project.id),
        "mission_id": str(mission.id) if mission else None,
        "session_key": session_key,
        "entries": entries,
    }
    return client.post(f"{API}/capture", json=body, headers=headers)


class TestCaptureContract:
    def test_batch_capture_round_trips_every_field_and_forces_agent_origin(self, client, db_session, rbac_on):
        member = _user(db_session, "capture-member@example.com")
        space, project = _space_project(db_session, member)
        mission = _mission(db_session, project)
        headers = _api_key(db_session, member)
        entries = [
            {
                "claim": "Passkeys reduce phishing exposure.",
                "summary": "A primary standards source describes phishing resistance.",
                "source_url": "https://example.test/passkeys",
                "snippet": "Public-key credentials are scoped to the relying party.",
                "query": "passkey phishing resistance",
                "disposition": "supporting",
                "tags": ["authentication", "primary-source"],
            },
            {
                "claim": "Adoption is already universal.",
                "summary": "The available survey does not support the universal claim.",
                "source_url": "https://example.test/adoption-survey",
                "snippet": "Adoption varies materially by sector.",
                "query": "passkey adoption survey",
                "disposition": "rejected",
                "tags": ["authentication", "survey"],
            },
        ]

        response = _capture(
            client,
            headers,
            project,
            session_key="agent-session-001",
            mission=mission,
            entries=entries,
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["count"] == 2
        assert len(body["entries"]) == 2
        for returned, submitted in zip(body["entries"], entries, strict=True):
            assert returned.keys() >= ENTRY_FIELDS
            assert returned["origin"] == "mcp-agent"
            assert returned["project_id"] == str(project.id)
            assert returned["mission_id"] == str(mission.id)
            assert returned["session_key"] == "agent-session-001"
            assert returned["owner_id"] == str(member.id)
            assert returned["workspace_id"] == str(space.id)
            for field, value in submitted.items():
                assert returned[field] == value

        persisted = (
            db_session.query(LedgerEntry)
            .filter(LedgerEntry.project_id == project.id)
            .order_by(LedgerEntry.created_at.asc(), LedgerEntry.id.asc())
            .all()
        )
        assert len(persisted) == 2
        assert {row.origin for row in persisted} == {"mcp-agent"}
        assert {row.disposition for row in persisted} == {"supporting", "rejected"}

    def test_invalid_batch_is_rejected_without_partial_persistence(self, client, db_session, rbac_on):
        member = _user(db_session, "atomic-member@example.com")
        _space, project = _space_project(db_session, member, name="Atomic project")

        response = _capture(
            client,
            _bearer(member),
            project,
            session_key="atomic-session",
            entries=[
                {
                    "claim": "This first row is valid.",
                    "source_url": "https://example.test/valid",
                    "disposition": "supporting",
                },
                {
                    "claim": "This second row has no valid disposition.",
                    "source_url": "https://example.test/invalid",
                    "disposition": "unreviewed",
                },
            ],
        )

        assert response.status_code == 422, response.text
        assert db_session.query(LedgerEntry).count() == 0, "a rejected batch must not leave the valid prefix committed"

    def test_database_failure_on_later_row_rolls_back_the_full_batch(
        self,
        db_session,
    ):
        """Prove the service uses one transaction, beyond request validation."""
        member = _user(db_session, "atomic-service@example.com")
        space, project = _space_project(
            db_session,
            member,
            name="Atomic service project",
        )
        request = CaptureRequest.model_validate(
            {
                "project_id": str(project.id),
                "session_key": "database-atomicity",
                "entries": [
                    {
                        "claim": "The valid prefix must roll back.",
                        "source_url": "https://example.test/atomic-prefix",
                        "disposition": "supporting",
                    },
                    {
                        "claim": "This row is corrupted after boundary validation.",
                        "source_url": "https://example.test/atomic-failure",
                        "disposition": "rejected",
                    },
                ],
            }
        )
        # Simulate a database-side failure that request validation cannot predict.
        # Assignment validation is intentionally disabled on this test object.
        request.entries[1].disposition = "invalid-at-database"  # type: ignore[assignment]

        write_session = SessionLocal()
        try:
            with pytest.raises(IntegrityError):
                EvidenceLedgerService().capture(
                    write_session,
                    request,
                    owner_id=member.id,
                    workspace_id=space.id,
                )
        finally:
            write_session.close()

        verification_session = SessionLocal()
        try:
            assert verification_session.query(LedgerEntry).filter(LedgerEntry.project_id == project.id).count() == 0
        finally:
            verification_session.close()

    def test_capture_normalizes_absolute_http_source_urls(self, client, db_session, rbac_on):
        member = _user(db_session, "url-normalization@example.com")
        _space, project = _space_project(db_session, member, name="URL normalization")

        response = _capture(
            client,
            _bearer(member),
            project,
            session_key="normalized-url",
            entries=[
                {
                    "claim": "Canonical URLs keep duplicate evidence recognizable.",
                    "source_url": "HTTPS://Example.TEST:443/research",
                    "disposition": "background",
                }
            ],
        )

        assert response.status_code == 201, response.text
        assert response.json()["entries"][0]["source_url"] == "https://example.test/research"
        assert db_session.query(LedgerEntry).one().source_url == "https://example.test/research"

    def test_capture_enforces_normalized_source_url_length_boundary(
        self,
        client,
        db_session,
        rbac_on,
    ):
        member = _user(db_session, "url-length@example.com")
        _space, project = _space_project(db_session, member, name="URL length")
        headers = _bearer(member)
        prefix = "https://example.test/"
        maximum_url = prefix + ("a" * (4_096 - len(prefix)))
        oversized_url = maximum_url + "b"

        accepted = _capture(
            client,
            headers,
            project,
            session_key="maximum-url",
            entries=[
                {
                    "claim": "The normalized source URL is exactly at the boundary.",
                    "source_url": maximum_url,
                    "disposition": "background",
                }
            ],
        )
        rejected = _capture(
            client,
            headers,
            project,
            session_key="oversized-url",
            entries=[
                {
                    "claim": "The normalized source URL exceeds the boundary.",
                    "source_url": oversized_url,
                    "disposition": "background",
                }
            ],
        )

        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["entries"][0]["source_url"] == maximum_url
        assert len(accepted.json()["entries"][0]["source_url"]) == 4_096
        assert rejected.status_code == 422, rejected.text
        assert db_session.query(LedgerEntry).count() == 1

    @pytest.mark.parametrize(
        "source_url",
        ["relative/research", "not a url", "ftp://example.test/research"],
    )
    def test_capture_rejects_non_absolute_source_urls(self, client, db_session, rbac_on, source_url):
        member = _user(db_session, f"invalid-url-{uuid4()}@example.com")
        _space, project = _space_project(db_session, member, name="Invalid URL")

        response = _capture(
            client,
            _bearer(member),
            project,
            session_key="invalid-url",
            entries=[
                {
                    "claim": "Unsourced-looking paths cannot become durable evidence.",
                    "source_url": source_url,
                    "disposition": "background",
                }
            ],
        )

        assert response.status_code == 422, response.text
        assert db_session.query(LedgerEntry).count() == 0

    def test_capture_rejects_mission_from_another_project(self, client, db_session, rbac_on):
        member = _user(db_session, "mission-scope@example.com")
        space, project_a = _space_project(db_session, member, name="Project A")
        project_b = Project(name="Project B", workspace_id=space.id)
        db_session.add(project_b)
        db_session.commit()
        db_session.refresh(project_b)
        foreign_mission = _mission(db_session, project_b, label="OTHER")

        response = _capture(
            client,
            _bearer(member),
            project_a,
            mission=foreign_mission,
            session_key="mission-mismatch",
            entries=[
                {
                    "claim": "A mission cannot be attached across projects.",
                    "source_url": "https://example.test/mismatch",
                    "disposition": "background",
                }
            ],
        )

        assert response.status_code == 400, response.text
        assert db_session.query(LedgerEntry).count() == 0


class TestWorkingNotes:
    def test_put_upserts_one_key_per_project_session_and_preserves_provenance(self, client, db_session, rbac_on):
        member = _user(db_session, "note-member@example.com")
        space, project = _space_project(db_session, member, name="Notes project")
        headers = _bearer(member)
        note_key = "open/question ?"
        url = f"{API}/notes/{quote(note_key, safe='')}"
        first_payload = {
            "project_id": str(project.id),
            "session_key": "notes-session",
            "content": "Compare passkeys with magic links.",
            "tags": ["todo"],
        }

        first = client.put(url, json=first_payload, headers=headers)
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body.keys() >= NOTE_FIELDS
        assert first_body["origin"] == "mcp-agent"
        assert first_body["note_key"] == note_key
        assert first_body["owner_id"] == str(member.id)
        assert first_body["workspace_id"] == str(space.id)

        second = client.put(
            url,
            json={
                **first_payload,
                "content": "Compare passkeys, magic links, and recovery flows.",
                "tags": ["todo", "expanded"],
            },
            headers=headers,
        )
        assert second.status_code == 200, second.text
        second_body = second.json()
        assert second_body["id"] == first_body["id"]
        assert second_body["content"].endswith("recovery flows.")
        assert second_body["tags"] == ["todo", "expanded"]
        assert second_body["origin"] == "mcp-agent"

        notes = db_session.query(LedgerNote).all()
        assert len(notes) == 1
        assert notes[0].note_key == note_key
        assert notes[0].content == second_body["content"]

    @pytest.mark.parametrize("encoded_note_key", ("%2E", "%2E%2E"), ids=("dot", "dot-dot"))
    def test_dot_segment_note_keys_are_rejected(
        self,
        client,
        db_session,
        rbac_on,
        encoded_note_key,
    ):
        """Dot segments must not be normalized into a different ledger route."""
        member = _user(db_session, f"note-{uuid4().hex}@example.com")
        _space, project = _space_project(db_session, member, name="Reserved note key")

        response = client.put(
            f"{API}/notes/{encoded_note_key}",
            json={
                "project_id": str(project.id),
                "session_key": "reserved-note-key",
                "content": "This key must never be persisted.",
            },
            headers=_bearer(member),
        )

        assert response.status_code == 422, response.text
        assert db_session.query(LedgerNote).count() == 0


class TestScopedReadPaths:
    def test_list_and_search_filters_report_totals_before_pagination(self, client, db_session, rbac_on):
        member = _user(db_session, "reader@example.com")
        _space, project = _space_project(db_session, member, name="Read project")
        first_mission = _mission(db_session, project, label="READ-ONE")
        second_mission = _mission(db_session, project, label="READ-TWO")
        headers = _api_key(db_session, member)

        first = _capture(
            client,
            headers,
            project,
            session_key="session-one",
            mission=first_mission,
            entries=[
                {
                    "claim": "Passkey adoption is growing.",
                    "summary": "Needle appears in this supporting summary.",
                    "source_url": "https://example.test/growth",
                    "query": "adoption trend",
                    "disposition": "supporting",
                    "tags": ["auth", "primary"],
                },
                {
                    "claim": "A weak source made an absolute adoption claim.",
                    "source_url": "https://example.test/weak",
                    "query": "needle weak adoption claim",
                    "disposition": "rejected",
                    "tags": ["auth"],
                },
            ],
        )
        assert first.status_code == 201, first.text
        second = _capture(
            client,
            headers,
            project,
            session_key="session-two",
            mission=second_mission,
            entries=[
                {
                    "claim": "Recovery remains a material risk.",
                    "summary": "Needle is present, but in another session.",
                    "source_url": "https://example.test/recovery",
                    "disposition": "contradicting",
                    "tags": ["risk"],
                }
            ],
        )
        assert second.status_code == 201, second.text
        note = client.put(
            f"{API}/notes/next-query",
            json={
                "project_id": str(project.id),
                "mission_id": str(first_mission.id),
                "session_key": "session-one",
                "content": "Investigate recovery evidence next.",
                "tags": ["todo"],
            },
            headers=headers,
        )
        assert note.status_code == 200, note.text

        page = client.get(
            API,
            params={"project_id": str(project.id), "page": 1, "page_size": 1},
            headers=headers,
        )
        assert page.status_code == 200, page.text
        assert page.json()["entry_total"] == 3
        assert len(page.json()["entries"]) == 1

        filtered = client.get(
            API,
            params={
                "project_id": str(project.id),
                "mission_id": str(first_mission.id),
                "session_key": "session-one",
                "disposition": "supporting",
                "page": 1,
                "page_size": 1,
            },
            headers=headers,
        )
        assert filtered.status_code == 200, filtered.text
        filtered_body = filtered.json()
        assert filtered_body["entry_total"] == 1
        assert filtered_body["entries"][0]["disposition"] == "supporting"
        assert filtered_body["note_total"] == 1, "entry-only disposition filters must not discard session notes"

        searched = client.get(
            f"{API}/search",
            params={
                "project_id": str(project.id),
                "q": "NEEDLE",
                "mission_id": str(first_mission.id),
                "session_key": "session-one",
                "disposition": "rejected",
                "page": 1,
                "page_size": 1,
            },
            headers=headers,
        )
        assert searched.status_code == 200, searched.text
        search_body = searched.json()
        assert search_body["total"] == 1
        assert len(search_body["entries"]) == 1
        assert search_body["entries"][0]["disposition"] == "rejected"

    def test_search_treats_like_metacharacters_as_literal_text(
        self,
        client,
        db_session,
        rbac_on,
    ):
        """Agent queries containing LIKE syntax must not broaden result visibility."""
        member = _user(db_session, "literal-search@example.com")
        _space, project = _space_project(db_session, member, name="Literal search")
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="literal-search-session",
            entries=[
                {
                    "claim": "A control row contains no special marker.",
                    "source_url": "https://example.test/literal-control",
                    "disposition": "background",
                },
                {
                    "claim": "The measured rate is exactly 100%.",
                    "source_url": "https://example.test/literal-percent",
                    "disposition": "supporting",
                },
                {
                    "claim": "The source identifier is alpha_beta.",
                    "source_url": "https://example.test/literal-underscore",
                    "disposition": "supporting",
                },
                {
                    "claim": "The source path is alpha\\beta.",
                    "source_url": "https://example.test/literal-backslash",
                    "disposition": "supporting",
                },
            ],
        )
        assert captured.status_code == 201, captured.text
        expected_ids = {
            "%": captured.json()["entries"][1]["id"],
            "_": captured.json()["entries"][2]["id"],
            "\\": captured.json()["entries"][3]["id"],
        }

        for query, expected_id in expected_ids.items():
            response = client.get(
                f"{API}/search",
                params={"project_id": str(project.id), "q": query},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["total"] == 1
            assert [entry["id"] for entry in response.json()["entries"]] == [expected_id]

    def test_access_filters_are_applied_before_list_and_search_totals(self, client, db_session, rbac_on, monkeypatch):
        """A future query refactor must not count rows hidden by authorization."""
        from app.api.v1 import evidence as evidence_api

        member = _user(db_session, "filter-wiring@example.com")
        _space, project = _space_project(db_session, member, name="Filter project")
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="filter-session",
            entries=[
                {
                    "claim": "Visible shared needle.",
                    "source_url": "https://example.test/visible",
                    "disposition": "supporting",
                },
                {
                    "claim": "Hidden shared needle.",
                    "source_url": "https://example.test/hidden",
                    "disposition": "supporting",
                },
            ],
        )
        assert captured.status_code == 201, captured.text
        visible_id, hidden_id = [row["id"] for row in captured.json()["entries"]]
        for key in ("visible-note", "hidden-note"):
            response = client.put(
                f"{API}/notes/{key}",
                json={
                    "project_id": str(project.id),
                    "session_key": "filter-session",
                    "content": f"{key} content",
                },
                headers=headers,
            )
            assert response.status_code == 200, response.text
        hidden_note = db_session.query(LedgerNote).filter(LedgerNote.note_key == "hidden-note").one()

        def narrowed_access(_user, model, _db):
            if model is LedgerEntry:
                return LedgerEntry.id != hidden_id
            if model is LedgerNote:
                return LedgerNote.id != hidden_note.id
            raise AssertionError(f"unexpected model passed to accessible_filter: {model}")

        monkeypatch.setattr(evidence_api, "accessible_filter", narrowed_access)

        listed = client.get(
            API,
            params={
                "project_id": str(project.id),
                "session_key": "filter-session",
            },
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["entry_total"] == 1
        assert listed.json()["note_total"] == 1
        assert [row["id"] for row in listed.json()["entries"]] == [visible_id]

        searched = client.get(
            f"{API}/search",
            params={"project_id": str(project.id), "q": "shared needle"},
            headers=headers,
        )
        assert searched.status_code == 200, searched.text
        assert searched.json()["total"] == 1
        assert [row["id"] for row in searched.json()["entries"]] == [visible_id]

    def test_project_owner_without_space_membership_sees_member_written_rows(
        self,
        client,
        db_session,
        rbac_on,
    ):
        owner = _user(db_session, "ledger-owner@example.com")
        writer = _user(db_session, "ledger-writer@example.com")
        space = Workspace(name="Owner visibility space")
        db_session.add(space)
        db_session.commit()
        db_session.refresh(space)
        db_session.add(SpaceMember(workspace_id=space.id, user_id=writer.id))
        project = Project(
            name="Owner visibility project",
            owner_id=owner.id,
            workspace_id=space.id,
        )
        db_session.add(project)
        db_session.commit()
        db_session.refresh(project)
        assert (
            db_session.query(SpaceMember)
            .filter(
                SpaceMember.workspace_id == space.id,
                SpaceMember.user_id == owner.id,
            )
            .count()
            == 0
        )

        captured = _capture(
            client,
            _bearer(writer),
            project,
            session_key="owner-visible-session",
            entries=[
                {
                    "claim": "A project owner must see member-authored evidence.",
                    "source_url": "https://example.test/owner-visibility",
                    "disposition": "supporting",
                }
            ],
        )
        assert captured.status_code == 201, captured.text
        assert captured.json()["entries"][0]["owner_id"] == str(writer.id)

        owner_headers = _bearer(owner)
        listed = client.get(
            API,
            params={"project_id": str(project.id)},
            headers=owner_headers,
        )
        searched = client.get(
            f"{API}/search",
            params={"project_id": str(project.id), "q": "member-authored"},
            headers=owner_headers,
        )

        assert listed.status_code == 200, listed.text
        assert listed.json()["entry_total"] == 1
        assert listed.json()["entries"][0]["owner_id"] == str(writer.id)
        assert searched.status_code == 200, searched.text
        assert searched.json()["total"] == 1
        assert searched.json()["entries"][0]["owner_id"] == str(writer.id)


class TestDeletedProjectBoundary:
    def test_all_evidence_actions_hide_a_soft_deleted_project(
        self,
        client,
        db_session,
        rbac_on,
    ):
        """Deletion must close both ledger reads and writes until project restore."""
        member = _user(db_session, "deleted-ledger@example.com")
        _space, project = _space_project(db_session, member, name="Deleted ledger")
        headers = _bearer(member)
        seeded = _capture(
            client,
            headers,
            project,
            session_key="deleted-project-session",
            entries=[
                {
                    "claim": "This row predates project deletion.",
                    "source_url": "https://example.test/deleted-project",
                    "disposition": "background",
                }
            ],
        )
        assert seeded.status_code == 201, seeded.text

        project.soft_delete(deleted_by=member.email)
        db_session.commit()

        responses = {
            "capture": _capture(
                client,
                headers,
                project,
                session_key="after-deletion",
                entries=[
                    {
                        "claim": "Deleted projects reject new evidence.",
                        "source_url": "https://example.test/after-deletion",
                        "disposition": "rejected",
                    }
                ],
            ),
            "note": client.put(
                f"{API}/notes/after-deletion",
                json={
                    "project_id": str(project.id),
                    "session_key": "deleted-project-session",
                    "content": "Deleted projects reject note changes.",
                },
                headers=headers,
            ),
            "list": client.get(
                API,
                params={"project_id": str(project.id)},
                headers=headers,
            ),
            "search": client.get(
                f"{API}/search",
                params={"project_id": str(project.id), "q": "predates"},
                headers=headers,
            ),
            "promote": client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "deleted-project-session",
                    "target": "report",
                },
                headers=headers,
            ),
        }

        assert {action: response.status_code for action, response in responses.items()} == {
            "capture": 404,
            "note": 404,
            "list": 404,
            "search": 404,
            "promote": 404,
        }
        assert db_session.query(LedgerEntry).count() == 1
        assert db_session.query(LedgerNote).count() == 0
        assert db_session.query(Report).count() == 0


class TestRbacBoundary:
    def test_outsider_cannot_capture_list_search_or_promote(self, client, db_session, rbac_on):
        member = _user(db_session, "tenant-member@example.com")
        outsider = _user(db_session, "tenant-outsider@example.com")
        _space, project = _space_project(db_session, member, name="Private ledger")
        outsider_headers = _bearer(outsider)

        capture = _capture(
            client,
            outsider_headers,
            project,
            session_key="private-session",
            entries=[
                {
                    "claim": "An outsider must not write here.",
                    "source_url": "https://example.test/forbidden",
                    "disposition": "background",
                }
            ],
        )
        listed = client.get(
            API,
            params={"project_id": str(project.id)},
            headers=outsider_headers,
        )
        searched = client.get(
            f"{API}/search",
            params={"project_id": str(project.id), "q": "anything"},
            headers=outsider_headers,
        )
        promoted = client.post(
            f"{API}/promote",
            json={
                "project_id": str(project.id),
                "session_key": "private-session",
                "target": "report",
            },
            headers=outsider_headers,
        )

        for response in (capture, listed, searched, promoted):
            assert response.status_code == 403, response.text
        assert db_session.query(LedgerEntry).count() == 0
        assert db_session.query(Report).count() == 0

    def test_service_principal_is_not_an_agent_writer(self, client, db_session, rbac_on):
        member = _user(db_session, "human-member@example.com")
        service = _user(db_session, "deepsearch-service@example.com", ROLE_SERVICE)
        space, project = _space_project(db_session, member, name="Human ledger")
        db_session.add(SpaceMember(workspace_id=space.id, user_id=service.id))
        db_session.commit()
        service_headers = _api_key(db_session, service)

        capture = _capture(
            client,
            service_headers,
            project,
            session_key="service-session",
            entries=[
                {
                    "claim": "LEDGER-2 owns the service-writer contract.",
                    "source_url": "https://example.test/service-boundary",
                    "disposition": "background",
                }
            ],
        )
        listed = client.get(
            API,
            params={"project_id": str(project.id)},
            headers=service_headers,
        )

        assert capture.status_code == 403, capture.text
        assert listed.status_code == 403, listed.text

    @pytest.mark.parametrize(
        ("method", "path", "payload", "params"),
        [
            (
                "post",
                f"{API}/capture",
                {
                    "project_id": str(uuid4()),
                    "session_key": "anonymous",
                    "entries": [
                        {
                            "claim": "No anonymous writes.",
                            "source_url": "https://example.test/anonymous",
                            "disposition": "background",
                        }
                    ],
                },
                None,
            ),
            (
                "put",
                f"{API}/notes/key",
                {
                    "project_id": str(uuid4()),
                    "session_key": "anonymous",
                    "content": "No anonymous notes.",
                },
                None,
            ),
            ("get", API, None, {"project_id": str(uuid4())}),
            (
                "get",
                f"{API}/search",
                None,
                {"project_id": str(uuid4()), "q": "secret"},
            ),
            (
                "post",
                f"{API}/promote",
                {
                    "project_id": str(uuid4()),
                    "session_key": "anonymous",
                    "target": "report",
                },
                None,
            ),
        ],
        ids=("capture", "note", "list", "search", "promote"),
    )
    def test_every_evidence_route_requires_authentication(self, client, method, path, payload, params):
        kwargs = {"params": params}
        if payload is not None:
            kwargs["json"] = payload
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, response.text


class TestHttpVerbContract:
    def test_canonical_verbs_exist_and_competing_verbs_return_405(self, client, db_session, rbac_on):
        """Lock the server half of the MCP-client verb contract for all five actions."""
        member = _user(db_session, "verb-contract@example.com")
        _space, project = _space_project(db_session, member, name="Verb project")
        headers = _bearer(member)
        capture_body = {
            "project_id": str(project.id),
            "session_key": "verb-session",
            "entries": [
                {
                    "claim": "The canonical capture verb is POST.",
                    "source_url": "https://example.test/verb-contract",
                    "disposition": "background",
                }
            ],
        }
        note_body = {
            "project_id": str(project.id),
            "session_key": "verb-session",
            "content": "The canonical note verb is PUT.",
        }
        promote_body = {
            "project_id": str(project.id),
            "session_key": "verb-session",
            "target": "report",
        }

        canonical = [
            client.post(f"{API}/capture", json=capture_body, headers=headers),
            client.put(f"{API}/notes/verb-key", json=note_body, headers=headers),
            client.get(API, params={"project_id": str(project.id)}, headers=headers),
            client.get(
                f"{API}/search",
                params={"project_id": str(project.id), "q": "canonical"},
                headers=headers,
            ),
            client.post(f"{API}/promote", json=promote_body, headers=headers),
        ]
        assert [response.status_code for response in canonical] == [201, 200, 200, 200, 201]

        competing = [
            client.put(f"{API}/capture", json=capture_body, headers=headers),
            client.post(f"{API}/notes/verb-key", json=note_body, headers=headers),
            client.post(API, json={"project_id": str(project.id)}, headers=headers),
            client.post(
                f"{API}/search",
                json={"project_id": str(project.id), "q": "canonical"},
                headers=headers,
            ),
            client.put(f"{API}/promote", json=promote_body, headers=headers),
        ]
        assert [response.status_code for response in competing] == [405] * 5


class TestPromotion:
    def test_report_promotion_preserves_session_content_and_row_provenance(self, client, db_session, rbac_on):
        member = _user(db_session, "promoter@example.com")
        space, project = _space_project(db_session, member, name="Promotion project")
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="promotion-session",
            entries=[
                {
                    "claim": "Primary evidence supports passkey rollout.",
                    "summary": "The standard documents phishing resistance.",
                    "source_url": "https://example.test/primary",
                    "snippet": "Credentials are origin-bound.",
                    "query": "passkey standard",
                    "disposition": "supporting",
                    "tags": ["primary"],
                },
                {
                    "claim": "Recovery flows eliminate every account risk.",
                    "source_url": "https://example.test/recovery-risk",
                    "disposition": "contradicting",
                    "tags": ["risk"],
                },
                {
                    "claim": "Operational rollout guidance supplies useful context.",
                    "source_url": "https://example.test/rollout-context",
                    "disposition": "background",
                    "tags": ["context"],
                },
                {
                    "claim": "An anonymous assertion has no usable provenance.",
                    "source_url": "https://example.test/rejected-assertion",
                    "disposition": "rejected",
                    "tags": ["weak-source"],
                },
            ],
        )
        assert captured.status_code == 201, captured.text
        note = client.put(
            f"{API}/notes/recommendation",
            json={
                "project_id": str(project.id),
                "session_key": "promotion-session",
                "content": "Recommend a staged rollout with recovery testing.",
                "tags": ["decision-input"],
            },
            headers=headers,
        )
        assert note.status_code == 200, note.text

        response = client.post(
            f"{API}/promote",
            json={
                "project_id": str(project.id),
                "session_key": "promotion-session",
                "title": "Passkey evidence review",
                "target": "report",
            },
            headers=headers,
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body == {
            "project_id": str(project.id),
            "session_key": "promotion-session",
            "target": "report",
            "report_id": body["report_id"],
            "document_id": None,
            "title": "Passkey evidence review",
            "entry_count": 4,
            "note_count": 1,
            "status": "created",
        }

        report = db_session.query(Report).filter(Report.id == body["report_id"]).one()
        assert str(report.project_id) == str(project.id)
        assert str(report.owner_id) == str(member.id)
        assert str(report.workspace_id) == str(space.id)
        assert report.title == "Passkey evidence review"
        assert report.report_type == "evidence-ledger"
        assert report.status == "draft"
        assert report.created_by == member.email
        assert report.content_hash == hashlib.sha256(report.content.encode()).hexdigest()
        for expected in (
            "Primary evidence supports passkey rollout.",
            "https://example.test/primary",
            "supporting",
            "Recovery flows eliminate every account risk.",
            "https://example.test/recovery-risk",
            "contradicting",
            "Operational rollout guidance supplies useful context.",
            "https://example.test/rollout-context",
            "background",
            "An anonymous assertion has no usable provenance.",
            "https://example.test/rejected-assertion",
            "rejected",
            "Recommend a staged rollout with recovery testing.",
        ):
            assert expected in report.content

        expected_sources = {("ledger_entry", row["id"]) for row in captured.json()["entries"]}
        expected_sources.add(("ledger_note", note.json()["id"]))
        actual_sources = {
            (source.source_type, str(source.source_id))
            for source in db_session.query(ReportSource).filter(ReportSource.report_id == report.id).all()
        }
        assert actual_sources == expected_sources
        assert {entry["disposition"] for entry in captured.json()["entries"]} == {
            "supporting",
            "contradicting",
            "background",
            "rejected",
        }
        assert len([source for source in actual_sources if source[0] == "ledger_entry"]) == 4

    def test_document_promotion_reuses_ingestion_and_preserves_provenance(
        self,
        client,
        db_session,
        rbac_on,
    ):
        """Document target must index the exact persisted report with full lineage."""

        class FakeIngestionService:
            def __init__(self):
                self.calls = []

            def process_document(self, **kwargs):
                self.calls.append(kwargs)
                return {"status": "completed"}

        class FakeStatusRecorder:
            def __init__(self):
                self.calls = []

            def record(self, db, document_id, stage, status, **kwargs):
                self.calls.append(
                    {
                        "db": db,
                        "document_id": document_id,
                        "stage": stage,
                        "status": status,
                        **kwargs,
                    }
                )

        member = _user(db_session, "document-promoter@example.com")
        space, project = _space_project(
            db_session,
            member,
            name="Document promotion project",
        )
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="document-promotion-session",
            entries=[
                {
                    "claim": "A canonical source supports the document artifact.",
                    "source_url": "https://example.test/document-primary",
                    "disposition": "supporting",
                    "tags": ["primary"],
                },
                {
                    "claim": "A conflicting source remains visible in the artifact.",
                    "source_url": "https://example.test/document-conflict",
                    "disposition": "contradicting",
                    "tags": ["conflict"],
                },
            ],
        )
        assert captured.status_code == 201, captured.text
        note = client.put(
            f"{API}/notes/document-follow-up",
            json={
                "project_id": str(project.id),
                "session_key": "document-promotion-session",
                "content": "Retain both findings in the searchable document.",
                "tags": ["follow-up"],
            },
            headers=headers,
        )
        assert note.status_code == 200, note.text

        ingestion = FakeIngestionService()
        status_recorder = FakeStatusRecorder()
        ledger_service = EvidenceLedgerService(
            promotion_service=ReportPromotionService(
                ingestion_service=ingestion,
                status_recorder=status_recorder,
            )
        )
        app.dependency_overrides[get_evidence_ledger_service] = lambda: ledger_service
        try:
            response = client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "document-promotion-session",
                    "title": "Searchable evidence artifact",
                    "target": "document",
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_evidence_ledger_service, None)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["target"] == "document"
        assert body["status"] == "completed"
        assert body["report_id"] is not None
        assert body["document_id"] is not None
        assert body["entry_count"] == 2
        assert body["note_count"] == 1

        report = db_session.query(Report).filter(Report.id == body["report_id"]).one()
        document = db_session.query(Document).filter(Document.id == body["document_id"]).one()
        assert document.project_id == project.id
        assert document.source_report_id == report.id
        assert document.source_mission_id is None
        assert document.owner_id == member.id
        assert document.workspace_id == space.id
        assert document.file_type == "report"
        assert document.source_type == "analysis"
        assert document.source_origin == "synthesized"
        assert document.content == report.content
        assert document.document_metadata == {
            "report_id": str(report.id),
            "report_title": "Searchable evidence artifact",
            "promoted": True,
            "promoted_from": "evidence-ledger",
            "ledger_session_key": "document-promotion-session",
            "entry_count": 2,
            "note_count": 1,
        }

        expected_sources = {("ledger_entry", row["id"]) for row in captured.json()["entries"]}
        expected_sources.add(("ledger_note", note.json()["id"]))
        actual_sources = {
            (source.source_type, str(source.source_id))
            for source in db_session.query(ReportSource).filter(ReportSource.report_id == report.id).all()
        }
        assert actual_sources == expected_sources

        assert len(ingestion.calls) == 1
        assert ingestion.calls[0]["document_id"] == document.id
        assert ingestion.calls[0]["file_content"] == report.content.encode("utf-8")
        assert len(status_recorder.calls) == 1
        assert status_recorder.calls[0]["document_id"] == document.id
        assert status_recorder.calls[0]["stage"] == "uploaded"
        assert status_recorder.calls[0]["status"] == "succeeded"

    def test_failed_document_promotion_is_compensated_and_retryable(
        self,
        client,
        db_session,
        rbac_on,
    ):
        class ConfigurableIngestion:
            def __init__(self, *, fail: bool):
                self.fail = fail

            def process_document(self, **_kwargs):
                if self.fail:
                    return {"status": "failed", "error": "injected ingestion failure"}
                return {"status": "completed"}

        class NoopStatusRecorder:
            def record(self, *_args, **_kwargs):
                return None

        member = _user(db_session, "promotion-retry@example.com")
        _space, project = _space_project(
            db_session,
            member,
            name="Promotion retry project",
        )
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="promotion-retry-session",
            entries=[
                {
                    "claim": "A failed indexing attempt must remain retryable.",
                    "source_url": "https://example.test/promotion-retry",
                    "disposition": "supporting",
                }
            ],
        )
        assert captured.status_code == 201, captured.text

        def ledger_service(*, fail: bool) -> EvidenceLedgerService:
            return EvidenceLedgerService(
                promotion_service=ReportPromotionService(
                    ingestion_service=ConfigurableIngestion(fail=fail),
                    status_recorder=NoopStatusRecorder(),
                )
            )

        app.dependency_overrides[get_evidence_ledger_service] = lambda: ledger_service(fail=True)
        try:
            failed = client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "promotion-retry-session",
                    "target": "document",
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_evidence_ledger_service, None)

        assert failed.status_code == 400, failed.text
        assert "injected ingestion failure" in failed.text
        db_session.expire_all()
        assert db_session.query(Report).count() == 0
        assert db_session.query(ReportSource).count() == 0
        assert db_session.query(Document).count() == 0

        app.dependency_overrides[get_evidence_ledger_service] = lambda: ledger_service(fail=False)
        try:
            retried = client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "promotion-retry-session",
                    "target": "document",
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_evidence_ledger_service, None)

        assert retried.status_code == 201, retried.text
        assert retried.json()["status"] == "completed"
        assert db_session.query(Report).count() == 1
        assert db_session.query(ReportSource).count() == 1
        assert db_session.query(Document).count() == 1

    @pytest.mark.parametrize(
        "ingestion_result",
        ({}, {"status": "success"}, {"status": "processing"}),
        ids=("missing-status", "legacy-success", "still-processing"),
    )
    def test_noncompleted_ingestion_status_is_compensated(
        self,
        client,
        db_session,
        rbac_on,
        monkeypatch,
        ingestion_result,
    ):
        """Only the ingestion pipeline's terminal status may create a document."""

        class StaticIngestion:
            def process_document(self, **_kwargs):
                return dict(ingestion_result)

        class NoopStatusRecorder:
            def record(self, *_args, **_kwargs):
                return None

        from app.services import report_promotion as report_promotion_module

        monkeypatch.setattr(
            report_promotion_module,
            "invalidate_pedr_cache",
            lambda: 0,
        )
        member = _user(db_session, f"status-{uuid4().hex}@example.com")
        _space, project = _space_project(
            db_session,
            member,
            name="Strict promotion status",
        )
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="strict-status-session",
            entries=[
                {
                    "claim": "Incomplete ingestion cannot become a durable artifact.",
                    "source_url": "https://example.test/strict-status",
                    "disposition": "supporting",
                }
            ],
        )
        assert captured.status_code == 201, captured.text

        ledger_service = EvidenceLedgerService(
            promotion_service=ReportPromotionService(
                ingestion_service=StaticIngestion(),
                status_recorder=NoopStatusRecorder(),
            )
        )
        app.dependency_overrides[get_evidence_ledger_service] = lambda: ledger_service
        try:
            response = client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "strict-status-session",
                    "target": "document",
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_evidence_ledger_service, None)

        assert response.status_code == 400, response.text
        assert "unexpected ingestion status" in response.text
        db_session.expire_all()
        assert db_session.query(Report).count() == 0
        assert db_session.query(ReportSource).count() == 0
        assert db_session.query(Document).count() == 0
        assert db_session.query(LedgerEntry).count() == 1

    def test_post_vector_failure_purges_vectors_and_cache_before_database_rows(
        self,
        client,
        db_session,
        rbac_on,
        monkeypatch,
    ):
        """A failed promotion must not leave a ghost vector after returning 400."""
        events: list[str] = []

        def persisted_artifact_counts() -> tuple[int, int, int]:
            verification = SessionLocal()
            try:
                return (
                    verification.query(Report).count(),
                    verification.query(ReportSource).count(),
                    verification.query(Document).count(),
                )
            finally:
                verification.close()

        class TrackingQdrant:
            def __init__(self):
                self.document_ids: set[str] = set()

            def delete_chunks(self, document_id: str) -> None:
                assert document_id in self.document_ids
                assert persisted_artifact_counts() == (1, 1, 1)
                events.append("qdrant-delete")
                self.document_ids.remove(document_id)

        class PostVectorFailureIngestion:
            def __init__(self):
                self.qdrant_service = TrackingQdrant()
                self.document_id = None

            def process_document(self, **kwargs):
                self.document_id = kwargs["document_id"]
                self.qdrant_service.document_ids.add(str(self.document_id))
                events.append("vector-written")
                return {
                    "status": "failed",
                    "error": "failure after vector persistence",
                }

        class NoopStatusRecorder:
            def record(self, *_args, **_kwargs):
                return None

        def invalidate_cache() -> int:
            assert persisted_artifact_counts() == (1, 1, 1)
            events.append("cache-invalidate")
            return 1

        from app.services import report_promotion as report_promotion_module

        monkeypatch.setattr(
            report_promotion_module,
            "invalidate_pedr_cache",
            invalidate_cache,
        )
        member = _user(db_session, "post-vector-failure@example.com")
        _space, project = _space_project(
            db_session,
            member,
            name="Post-vector cleanup",
        )
        headers = _bearer(member)
        captured = _capture(
            client,
            headers,
            project,
            session_key="post-vector-failure",
            entries=[
                {
                    "claim": "Failed indexing must not leak ghost search results.",
                    "source_url": "https://example.test/post-vector-failure",
                    "disposition": "contradicting",
                }
            ],
        )
        assert captured.status_code == 201, captured.text

        ingestion = PostVectorFailureIngestion()
        ledger_service = EvidenceLedgerService(
            promotion_service=ReportPromotionService(
                ingestion_service=ingestion,
                status_recorder=NoopStatusRecorder(),
            )
        )
        app.dependency_overrides[get_evidence_ledger_service] = lambda: ledger_service
        try:
            response = client.post(
                f"{API}/promote",
                json={
                    "project_id": str(project.id),
                    "session_key": "post-vector-failure",
                    "target": "document",
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_evidence_ledger_service, None)

        assert response.status_code == 400, response.text
        assert "failure after vector persistence" in response.text
        assert events == ["vector-written", "qdrant-delete", "cache-invalidate"]
        assert ingestion.document_id is not None
        assert ingestion.qdrant_service.document_ids == set()
        db_session.expire_all()
        assert db_session.query(Report).count() == 0
        assert db_session.query(ReportSource).count() == 0
        assert db_session.query(Document).count() == 0
