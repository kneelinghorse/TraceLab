"""Acceptance contract for the DeepSearch-owned Evidence Ledger writer.

The endpoint is intentionally a trigger, not a second evidence-upload API.  A
service principal identifies an already-persisted mission/job; TraceLab owns
the projection, tenancy, provenance, and idempotency decisions.  These tests
lock the failure modes that would make that trust boundary unsafe: caller-
supplied evidence, partial batches, payload drift on replay, human access, and
source-sighting inflation.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_SERVICE,
    ROLE_VIEWER,
    create_access_token,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
)
from app.main import app
from app.models.api_key import APIKey
from app.models.evidence_ledger import (
    DeepSearchEvidenceOutbox,
    DeepSearchLedgerBatch,
    LedgerEntry,
    LedgerSource,
)
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.workspace import Workspace
from app.services.evidence_ledger import (
    DeepSearchEvidenceValidationError,
    _project_deepsearch_items,
)

API = f"{settings.api_v1_prefix}/missions"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deepsearch_evidence_projection_v1.json"
_HASH = "placeholder-not-a-real-hash"
_HUMAN_ROLES = (ROLE_VIEWER, ROLE_MEMBER, ROLE_ADMIN, ROLE_OWNER)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rbac_on(monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)


@pytest.fixture
def projection_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _user(db, *, role: str, label: str) -> User:
    user = User(
        email=f"{label}-{uuid4().hex[:8]}@example.test",
        display_name=label,
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
            name="DeepSearch evidence projection acceptance",
            key_hash=hash_api_key(plain),
            key_prefix=get_key_prefix(plain),
        )
    )
    db.commit()
    return {"X-API-Key": plain}


def _seed_mission(
    db,
    fixture: dict,
    *,
    status: str | None = None,
    deepsearch_job_id: str | None = None,
    project: Project | None = None,
) -> tuple[Mission, Project, User]:
    owner = _user(db, role=ROLE_OWNER, label="projection-owner")
    if project is None:
        workspace = Workspace(name=f"Projection space {uuid4().hex[:8]}")
        db.add(workspace)
        db.flush()
        project = Project(
            name=f"Projection project {uuid4().hex[:8]}",
            owner_id=owner.id,
            workspace_id=workspace.id,
        )
        db.add(project)
        db.flush()

    stored = fixture["mission"]
    mission = Mission(
        project_id=project.id,
        mission_id=f"{stored['mission_id']}-{uuid4().hex[:8]}",
        title="DeepSearch evidence projection fixture",
        objective="Project persisted research into the Evidence Ledger.",
        success_criteria=["Every projected row retains source provenance."],
        status=status or stored["status"],
        deepsearch_job_id=(deepsearch_job_id if deepsearch_job_id is not None else stored["deepsearch_job_id"]),
        result_markdown=stored["result_markdown"],
        result_protocol=deepcopy(stored["result_protocol"]),
        execution_metadata=deepcopy(stored["execution_metadata"]),
        owner_id=owner.id,
        workspace_id=project.workspace_id,
        completed_at=datetime.utcnow(),
    )
    db.add(mission)
    db.commit()
    db.refresh(project)
    db.refresh(mission)
    return mission, project, owner


def _trigger(
    client: TestClient,
    mission: Mission,
    headers: dict[str, str],
    request: dict,
):
    return client.post(
        f"{API}/{mission.id}/evidence",
        json=request,
        headers=headers,
    )


def _rows_for_mission(db, mission: Mission) -> list[LedgerEntry]:
    db.expire_all()
    return (
        db.query(LedgerEntry)
        .filter(LedgerEntry.mission_id == mission.id)
        .order_by(LedgerEntry.created_at, LedgerEntry.id)
        .all()
    )


def _assert_no_projection(db, mission: Mission) -> None:
    db.expire_all()
    assert db.query(DeepSearchLedgerBatch).filter(DeepSearchLedgerBatch.mission_id == mission.id).count() == 0
    assert db.query(LedgerEntry).filter(LedgerEntry.mission_id == mission.id).count() == 0


def _outbox_row(mission: Mission, **overrides) -> DeepSearchEvidenceOutbox:
    values = {
        "mission_id": mission.id,
        "deepsearch_job_id": mission.deepsearch_job_id,
        "deepsearch_result_key": f"result:{mission.id}",
        "mission_attempt_count": 1,
        "terminal_status": mission.status,
        "next_attempt_at": datetime.now(UTC),
    }
    values.update(overrides)
    return DeepSearchEvidenceOutbox(**values)


def test_frozen_deepsearch_shape_projects_exact_claim_level_entries(
    projection_fixture,
):
    """Lock the handoff fixture independently of HTTP and persistence plumbing."""
    mission = projection_fixture["mission"]
    projected = _project_deepsearch_items(
        result_protocol=mission["result_protocol"],
        result_markdown=mission["result_markdown"],
        execution_metadata=mission["execution_metadata"],
    )
    exact_fields = (
        "claim",
        "summary",
        "source_url",
        "snippet",
        "query",
        "disposition",
        "tags",
    )
    expected = [
        {field: entry[field] for field in exact_fields}
        for entry in projection_fixture["expected_projection"]["entries"]
    ]

    assert [item.model_dump(mode="json") for item in projected] == expected


def test_live_citation_does_not_erase_an_earlier_failed_retrieval_claim():
    """One URL can support a claim while its failed retrieval remains evidence.

    Projection is claim-level, not one-row-per-URL: a later live citation proves
    the cited claim, but it does not retroactively erase an observed failed tool
    attempt against the same source.
    """
    url = "https://example.test/same-source"
    cited_claim = "The persisted source supports this exact claim."

    projected = _project_deepsearch_items(
        result_protocol={
            "sources_collected": [
                {
                    "url": url,
                    "title": "Same source",
                    "snippet": "A source can be retried successfully.",
                    "alive": True,
                }
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": url,
                    "title": "Same source",
                    "start_index": 0,
                    "end_index": len(cited_claim),
                    "live": True,
                }
            ],
        },
        result_markdown=cited_claim,
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [
                        {
                            "tool": "source_fetch",
                            "url": url,
                            "status": "error",
                            "status_code": 503,
                            "error_category": "upstream_unavailable",
                        }
                    ],
                    "ledger_records_truncated": 0,
                }
            }
        },
    )

    same_url = [item for item in projected if str(item.source_url) == url]
    assert len(same_url) == 2

    supporting = next(item for item in same_url if item.disposition == "supporting")
    rejected = next(item for item in same_url if item.disposition == "rejected")
    assert supporting.claim == cited_claim
    assert "failed retrieval attempt" in rejected.claim
    assert rejected.summary is not None
    assert "tool=source_fetch" in rejected.summary
    assert "status=error" in rejected.summary
    assert "status_code=503" in rejected.summary
    assert "error_category=upstream_unavailable" in rejected.summary


def test_distinct_tool_failures_for_one_accepted_url_remain_distinct_claims():
    """Tool-specific failures are observations, not one lossy URL summary."""
    url = "https://example.test/retried-source"
    claim = "A later live citation supports this claim."
    projected = _project_deepsearch_items(
        result_protocol={
            "sources_collected": [
                {
                    "url": url,
                    "title": "Retried source",
                    "snippet": "The source eventually became available.",
                    "alive": True,
                }
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": url,
                    "start_index": 0,
                    "end_index": len(claim),
                    "live": True,
                }
            ],
        },
        result_markdown=claim,
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [
                        {
                            "tool": "source_fetch",
                            "url": url,
                            "status": "error",
                            "status_code": 503,
                            "error_category": "upstream_unavailable",
                        },
                        {
                            "tool": "source_fetch",
                            "url": url,
                            "status": "error",
                            "status_code": 503,
                            "error_category": "upstream_unavailable",
                        },
                        {
                            "tool": "url_liveness",
                            "url": url,
                            "status": "error",
                            "status_code": 404,
                            "error_category": "http_404",
                            "alive": False,
                        },
                    ],
                    "ledger_records_truncated": 0,
                }
            }
        },
    )

    assert len(projected) == 3
    assert sum(item.disposition == "supporting" for item in projected) == 1
    rejected = [item for item in projected if item.disposition == "rejected"]
    assert len(rejected) == 2
    by_tool = {next(tag for tag in item.tags if tag in {"source_fetch", "url_liveness"}): item for item in rejected}
    assert set(by_tool) == {"source_fetch", "url_liveness"}
    assert "tool=source_fetch" in (by_tool["source_fetch"].summary or "")
    assert "status_code=503" in (by_tool["source_fetch"].summary or "")
    assert "tool=url_liveness" in (by_tool["url_liveness"].summary or "")
    assert "status_code=404" in (by_tool["url_liveness"].summary or "")


def test_canonical_equivalent_urls_converge_across_every_projection_input():
    """Source identity is one canonical HTTP URL across all DS envelopes."""
    claim = "A canonical source supports this claim."
    projected = _project_deepsearch_items(
        result_protocol={
            "sources_collected": [
                {
                    "url": "HTTPS://Example.COM:443/canonical",
                    "title": "Canonical source",
                    "snippet": "Canonical evidence snippet.",
                    "alive": True,
                }
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": "https://example.com/canonical",
                    "start_index": 0,
                    "end_index": len(claim),
                    "live": True,
                }
            ],
        },
        result_markdown=claim,
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [
                        {
                            "tool": "source_fetch",
                            "url": "https://EXAMPLE.com:443/canonical",
                            "status": "error",
                            "status_code": 503,
                            "error_category": "upstream_unavailable",
                        }
                    ],
                    "ledger_records_truncated": 0,
                },
                "critique_telemetry": {
                    "annotations": [
                        {
                            "anchor": "A critique claim tied to the same source.",
                            "verdict": "unsupported",
                            "note": "The critique rationale is source-backed.",
                            "citation_urls": ["HTTPS://example.COM:443/canonical"],
                            "applied": True,
                            "reason": "unsupported_claim",
                        }
                    ]
                },
            }
        },
    )

    assert len(projected) == 3
    assert {str(item.source_url) for item in projected} == {"https://example.com/canonical"}
    assert {item.disposition for item in projected} == {"supporting", "rejected"}
    assert sum(item.disposition == "rejected" for item in projected) == 2


def test_url_query_parameters_are_preserved_without_being_treated_as_userinfo():
    url = "HTTPS://Example.COM:443/query?username=researcher&mode=full"
    projected = _project_deepsearch_items(
        result_protocol={
            "sources_collected": [
                {
                    "url": url,
                    "title": "Query-bearing source",
                }
            ],
            "citations": [],
        },
        result_markdown="No cited claim.",
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                }
            }
        },
    )

    assert len(projected) == 1
    assert str(projected[0].source_url) == ("https://example.com/query?username=researcher&mode=full")


def test_generic_sampling_cannot_hide_a_late_ledger_failure():
    """Lossy diagnostic sampling cannot truncate the evidence ledger surface."""
    url = "https://example.test/late-ledger-failure"
    projected = _project_deepsearch_items(
        result_protocol={"sources_collected": [], "citations": []},
        result_markdown="No synthesized citation was accepted.",
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "records": [
                        {
                            "tool": "web_search",
                            "status": "ok",
                            "diagnostic_ordinal": index,
                        }
                        for index in range(250)
                    ],
                    "records_truncated": 17,
                    "ledger_records": [
                        {
                            "tool": "source_fetch",
                            "url": url,
                            "status": "error",
                            "status_code": 503,
                            "error_category": "late_failure",
                        }
                    ],
                    "ledger_records_truncated": 0,
                }
            }
        },
    )

    assert len(projected) == 1
    [failure] = projected
    assert str(failure.source_url) == url
    assert failure.disposition == "rejected"
    assert "tool=source_fetch" in (failure.summary or "")
    assert "error_category=late_failure" in (failure.summary or "")


def test_canonical_duplicate_sources_merge_only_compatible_metadata():
    claim = "Compatible partial source records enrich one citation."
    projected = _project_deepsearch_items(
        result_protocol={
            "sources_collected": [
                {
                    "url": "HTTPS://Example.COM:443/merge",
                    "title": "Merged source",
                    "alive": True,
                },
                {
                    "url": "https://example.com/merge",
                    "snippet": "Metadata from a compatible duplicate.",
                },
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": "https://EXAMPLE.com:443/merge",
                    "start_index": 0,
                    "end_index": len(claim),
                    "live": True,
                }
            ],
        },
        result_markdown=claim,
        execution_metadata={
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                }
            }
        },
    )

    assert len(projected) == 1
    [item] = projected
    assert str(item.source_url) == "https://example.com/merge"
    assert item.summary == "Merged source"
    assert item.snippet == "Metadata from a compatible duplicate."


@pytest.mark.parametrize(
    "conflict",
    (
        ("title", "First title", "Second title"),
        ("snippet", "First snippet", "Second snippet"),
        ("alive", True, False),
    ),
    ids=("title", "snippet", "alive"),
)
def test_canonical_duplicate_sources_reject_conflicting_metadata(conflict):
    field, first, second = conflict
    first_source = {"url": "HTTPS://Example.COM:443/conflict", field: first}
    second_source = {"url": "https://example.com/conflict", field: second}

    with pytest.raises(DeepSearchEvidenceValidationError, match="conflict"):
        _project_deepsearch_items(
            result_protocol={
                "sources_collected": [first_source, second_source],
                "citations": [],
            },
            result_markdown="No cited claim.",
            execution_metadata={
                "synthesis_telemetry": {
                    "tool_outcomes": {
                        "ledger_records": [],
                        "ledger_records_truncated": 0,
                    }
                }
            },
        )


class TestProjectionContract:
    def test_persisted_protocol_projects_authoritative_dispositions_and_tenancy(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """Citations and retrieval outcomes, not caller claims, own the ledger."""
        mission, project, owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="projection-service")

        response = _trigger(
            client,
            mission,
            _api_key(db_session, service),
            projection_fixture["request"],
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body == {
            "status": "captured",
            "mission_id": str(mission.id),
            "deepsearch_job_id": projection_fixture["request"]["deepsearch_job_id"],
            "session_key": projection_fixture["expected_projection"]["session_key"],
            "entry_ids": body["entry_ids"],
            "entry_count": len(body["entry_ids"]),
        }
        assert len(set(body["entry_ids"])) == body["entry_count"]
        assert body["entry_count"] == projection_fixture["expected_projection"]["entry_count"]

        rows = _rows_for_mission(db_session, mission)
        assert {str(row.id) for row in rows} == set(body["entry_ids"])
        assert {row.project_id for row in rows} == {project.id}
        assert {row.mission_id for row in rows} == {mission.id}
        assert {row.session_key for row in rows} == {body["session_key"]}
        assert {row.origin for row in rows} == {"deepsearch-worker"}
        assert {row.workspace_id for row in rows} == {project.workspace_id}
        assert {row.owner_id for row in rows} == {owner.id}

        by_url_and_disposition = {(row.source_url, row.disposition): row for row in rows}
        for expected in projection_fixture["expected_projection"]["entries"]:
            row = by_url_and_disposition[(expected["source_url"], expected["disposition"])]
            assert expected["claim_contains"] in row.claim
            if expected["rationale_contains"] is not None:
                assert expected["rationale_contains"] in (row.summary or "")

        dispositions = {row.disposition for row in rows}
        assert "supporting" in dispositions
        assert "background" in dispositions
        assert "rejected" in dispositions
        assert (
            "contradicting" not in dispositions
        ), "DeepSearch has no persisted contradiction verdict at this boundary; the server must not fabricate one"

    def test_owner_can_list_and_search_projected_rejected_rationale(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """Projection is useful only if project readers can retrieve its rationale."""
        mission, project, owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="retrieval-projection-service")
        captured = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )
        assert captured.status_code == 201, captured.text
        session_key = captured.json()["session_key"]
        owner_headers = _bearer(owner)
        filters = {
            "project_id": str(project.id),
            "mission_id": str(mission.id),
            "session_key": session_key,
            "disposition": "rejected",
        }

        listed = client.get(
            f"{settings.api_v1_prefix}/evidence",
            headers=owner_headers,
            params=filters,
        )

        assert listed.status_code == 200, listed.text
        assert listed.json()["entry_total"] == 2
        assert {entry["mission_id"] for entry in listed.json()["entries"]} == {str(mission.id)}
        assert {entry["session_key"] for entry in listed.json()["entries"]} == {session_key}
        assert any("unsupported_claim" in (entry["summary"] or "") for entry in listed.json()["entries"])
        assert any("http_404" in (entry["summary"] or "") for entry in listed.json()["entries"])

        searched = client.get(
            f"{settings.api_v1_prefix}/evidence/search",
            headers=owner_headers,
            params={**filters, "q": "http_404"},
        )

        assert searched.status_code == 200, searched.text
        assert searched.json()["total"] == 1
        [rejected] = searched.json()["entries"]
        assert rejected["mission_id"] == str(mission.id)
        assert rejected["session_key"] == session_key
        assert "http_404" in (rejected["summary"] or "")

    def test_exact_replay_returns_stable_ids_without_incrementing_sightings(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="replay-service")
        headers = _api_key(db_session, service)

        first = _trigger(client, mission, headers, projection_fixture["request"])
        assert first.status_code == 201, first.text
        db_session.expire_all()
        before_sightings = {str(source.id): source.sighting_count for source in db_session.query(LedgerSource).all()}
        before_count = db_session.query(LedgerEntry).count()

        replay = _trigger(client, mission, headers, projection_fixture["request"])

        assert replay.status_code == 200, replay.text
        assert replay.json() == {
            **first.json(),
            "status": "already_processed",
        }
        assert replay.json()["entry_ids"] == sorted(replay.json()["entry_ids"])
        db_session.expire_all()
        assert db_session.query(LedgerEntry).count() == before_count
        assert {
            str(source.id): source.sighting_count for source in db_session.query(LedgerSource).all()
        } == before_sightings
        assert (
            db_session.query(DeepSearchLedgerBatch).filter(DeepSearchLedgerBatch.mission_id == mission.id).count() == 1
        )

    def test_long_canonical_url_associates_all_provenance_and_replays(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """TraceLab preserves DS URLs beyond legacy 200-character truncation."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        path = "source-" + ("a" * 240)
        canonical_url = f"https://long.example.test/{path}?view=complete"
        claim = "The long source URL supports this exact claim."
        mission.result_markdown = claim
        mission.result_protocol = {
            "sources_collected": [
                {
                    "url": f"HTTPS://LONG.EXAMPLE.TEST:443/{path}?view=complete",
                    "title": "Long URL source",
                    "snippet": "Long URLs retain one canonical source identity.",
                    "alive": True,
                }
            ],
            "citations": [
                {
                    "type": "url_citation",
                    "url": canonical_url,
                    "start_index": 0,
                    "end_index": len(claim),
                    "live": True,
                }
            ],
        }
        mission.execution_metadata = {
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [
                        {
                            "tool": "source_fetch",
                            "url": f"https://LONG.example.test:443/{path}?view=complete",
                            "status": "error",
                            "status_code": 503,
                            "error_category": "upstream_unavailable",
                        }
                    ],
                    "ledger_records_truncated": 0,
                }
            }
        }
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="long-url-service")
        headers = _api_key(db_session, service)

        first = _trigger(client, mission, headers, projection_fixture["request"])

        assert first.status_code == 201, first.text
        assert first.json()["entry_count"] == 2
        assert len(canonical_url) > 200
        rows = _rows_for_mission(db_session, mission)
        assert {row.source_url for row in rows} == {canonical_url}
        assert len({row.source_id for row in rows}) == 1
        source = db_session.query(LedgerSource).filter_by(source_url=canonical_url).one()
        sightings_before = source.sighting_count

        replay = _trigger(client, mission, headers, projection_fixture["request"])

        assert replay.status_code == 200, replay.text
        assert replay.json() == {**first.json(), "status": "already_processed"}
        db_session.expire_all()
        assert (
            db_session.query(LedgerSource).filter_by(source_url=canonical_url).one().sighting_count == sightings_before
        )

    def test_projection_list_order_is_irrelevant_to_replay_identity(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """Canonical replay identity follows facts, not persisted array order."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="order-replay-service")
        headers = _api_key(db_session, service)

        protocol = deepcopy(mission.result_protocol)
        markdown = mission.result_markdown
        second_claim = "A secondary explainer provides implementation background."
        second_start = markdown.index(second_claim)
        protocol["citations"].append(
            {
                "type": "url_citation",
                "start_index": second_start,
                "end_index": second_start + len(second_claim),
                "url": "https://developer.example.test/http-redirects",
                "title": "HTTP redirect implementation notes",
                "live": True,
            }
        )
        metadata = deepcopy(mission.execution_metadata)
        telemetry = metadata["synthesis_telemetry"]
        telemetry["tool_outcomes"]["ledger_records"].append(
            {
                "tool": "url_liveness",
                "url": "https://dead.example.test/removed-redirect-guide",
                "status": "error",
                "alive": False,
                "error_category": "timeout",
                "status_code": 503,
            }
        )
        telemetry["critique_telemetry"]["annotations"].append(
            {
                "anchor": "The removed guide cannot substantiate this claim.",
                "verdict": "unsupported",
                "note": "The source was unavailable during final synthesis.",
                "citation_urls": ["https://dead.example.test/removed-redirect-guide"],
                "applied": True,
                "reason": "unavailable_source",
            }
        )
        mission.result_protocol = protocol
        mission.execution_metadata = metadata
        db_session.commit()

        first = _trigger(client, mission, headers, projection_fixture["request"])
        assert first.status_code == 201, first.text
        db_session.expire_all()
        before_sightings = {str(source.id): source.sighting_count for source in db_session.query(LedgerSource).all()}

        reordered_protocol = deepcopy(mission.result_protocol)
        reordered_protocol["sources_collected"].reverse()
        reordered_protocol["citations"].reverse()
        reordered_metadata = deepcopy(mission.execution_metadata)
        reordered_telemetry = reordered_metadata["synthesis_telemetry"]
        reordered_telemetry["tool_outcomes"]["ledger_records"].reverse()
        reordered_telemetry["critique_telemetry"]["annotations"].reverse()
        equivalent_urls = {
            "https://www.rfc-editor.org/rfc/rfc9110#section-15.4.8": (
                "HTTPS://WWW.RFC-EDITOR.ORG:443/rfc/rfc9110#section-15.4.8"
            ),
            "https://developer.example.test/http-redirects": ("HTTPS://DEVELOPER.EXAMPLE.TEST:443/http-redirects"),
            "https://dead.example.test/removed-redirect-guide": (
                "HTTPS://DEAD.EXAMPLE.TEST:443/removed-redirect-guide"
            ),
        }
        for source in reordered_protocol["sources_collected"]:
            source["url"] = equivalent_urls[source["url"]]
        for citation in reordered_protocol["citations"]:
            citation["url"] = equivalent_urls[citation["url"]]
        for record in reordered_telemetry["tool_outcomes"]["ledger_records"]:
            if "url" in record:
                record["url"] = equivalent_urls[record["url"]]
        for annotation in reordered_telemetry["critique_telemetry"]["annotations"]:
            annotation["citation_urls"] = [equivalent_urls[url] for url in annotation["citation_urls"]]
        mission.result_protocol = reordered_protocol
        mission.execution_metadata = reordered_metadata
        db_session.commit()

        replay = _trigger(client, mission, headers, projection_fixture["request"])

        assert replay.status_code == 200, replay.text
        assert replay.json() == {**first.json(), "status": "already_processed"}
        db_session.expire_all()
        assert {
            str(source.id): source.sighting_count for source in db_session.query(LedgerSource).all()
        } == before_sightings

    def test_projected_payload_drift_on_same_mission_job_conflicts_without_mutation(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="drift-service")
        headers = _api_key(db_session, service)
        first = _trigger(client, mission, headers, projection_fixture["request"])
        assert first.status_code == 201, first.text
        db_session.expire_all()
        ids_before = {row.id for row in db_session.query(LedgerEntry).filter_by(mission_id=mission.id)}
        sightings_before = {row.id: row.sighting_count for row in db_session.query(LedgerSource).all()}

        persisted = db_session.get(Mission, mission.id)
        changed_protocol = deepcopy(persisted.result_protocol)
        changed_protocol["sources_collected"][0]["snippet"] = "The persisted result changed after its first projection."
        persisted.result_protocol = changed_protocol
        db_session.commit()

        replay = _trigger(client, mission, headers, projection_fixture["request"])

        assert replay.status_code == 409, replay.text
        db_session.expire_all()
        assert {row.id for row in db_session.query(LedgerEntry).filter_by(mission_id=mission.id)} == ids_before
        assert {row.id: row.sighting_count for row in db_session.query(LedgerSource).all()} == sightings_before

    def test_unprojected_mission_fields_do_not_create_false_replay_drift(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """The replay hash covers the evidence substrate, not mutable UI prose."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="irrelevant-drift-service")
        headers = _api_key(db_session, service)
        first = _trigger(client, mission, headers, projection_fixture["request"])
        assert first.status_code == 201, first.text

        persisted = db_session.get(Mission, mission.id)
        persisted.title = "A reviewer clarified this title after completion"
        persisted.execution_metadata = {
            **persisted.execution_metadata,
            "reviewer_note": "This field does not participate in projection.",
        }
        db_session.commit()

        replay = _trigger(client, mission, headers, projection_fixture["request"])
        assert replay.status_code == 200, replay.text
        assert replay.json()["status"] == "already_processed"
        assert replay.json()["entry_ids"] == first.json()["entry_ids"]

    def test_raw_bodies_and_tool_errors_are_excluded_from_projection_identity(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """Large/raw worker internals neither drift nor leak into ledger claims."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="excluded-raw-service")
        headers = _api_key(db_session, service)
        first = _trigger(client, mission, headers, projection_fixture["request"])
        assert first.status_code == 201, first.text

        persisted = db_session.get(Mission, mission.id)
        protocol = deepcopy(persisted.result_protocol)
        for index, source in enumerate(protocol["sources_collected"]):
            source["body"] = f"RAW-BODY-MUST-NOT-LEAK-{index}"
            source["body_source"] = f"raw-body-origin-{index}"
        metadata = deepcopy(persisted.execution_metadata)
        for index, record in enumerate(metadata["synthesis_telemetry"]["tool_outcomes"]["records"]):
            record["error"] = f"RAW-EXCEPTION-MUST-NOT-LEAK-{index}"
        persisted.result_protocol = protocol
        persisted.execution_metadata = metadata
        db_session.commit()

        replay = _trigger(client, mission, headers, projection_fixture["request"])

        assert replay.status_code == 200, replay.text
        assert replay.json() == {**first.json(), "status": "already_processed"}
        rows = _rows_for_mission(db_session, mission)
        serialized_projection = json.dumps(
            [
                {
                    "claim": row.claim,
                    "summary": row.summary,
                    "source_url": row.source_url,
                    "snippet": row.snippet,
                    "query": row.query,
                    "tags": row.tags,
                }
                for row in rows
            ]
        )
        assert "RAW-BODY-MUST-NOT-LEAK" not in serialized_projection
        assert "raw-body-origin" not in serialized_projection
        assert "RAW-EXCEPTION-MUST-NOT-LEAK" not in serialized_projection


class TestProjectionValidationAndAtomicity:
    @pytest.mark.parametrize(
        "extra_field",
        (
            {"project_id": str(uuid4())},
            {"origin": "deepsearch-worker"},
            {"entries": [{"claim": "caller supplied"}]},
            {"result_protocol": {"sources_collected": []}},
        ),
        ids=("project", "origin", "entries", "protocol"),
    )
    def test_request_rejects_caller_owned_projection_fields(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        extra_field,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="owned-field-service")
        request = {**projection_fixture["request"], **extra_field}

        response = _trigger(client, mission, _bearer(service), request)

        assert response.status_code == 422, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize(
        "request_body",
        (
            {"schema_version": 2, "deepsearch_job_id": "ds-job-ledger-v1"},
            {"deepsearch_job_id": "ds-job-ledger-v1"},
            {"schema_version": 1, "deepsearch_job_id": " ds-job-ledger-v1 "},
            {"schema_version": 1, "deepsearch_job_id": "   "},
            {"schema_version": 1},
        ),
        ids=(
            "future-schema",
            "missing-schema",
            "padded-job",
            "blank-job",
            "missing-job",
        ),
    )
    def test_request_schema_fails_before_any_projection(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        request_body,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="schema-service")

        response = _trigger(client, mission, _bearer(service), request_body)

        assert response.status_code == 422, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize(
        "status",
        ("draft", "queued", "in_progress", "blocked", "cancelled"),
    )
    def test_non_result_statuses_cannot_be_projected(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        status,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture, status=status)
        service = _user(db_session, role=ROLE_SERVICE, label="terminal-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 409, response.text
        _assert_no_projection(db_session, mission)

    def test_validation_failed_is_a_terminal_persisted_result(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """A failed validation still has authoritative research to preserve."""
        mission, _project, _owner = _seed_mission(
            db_session,
            projection_fixture,
            status="validation_failed",
        )
        service = _user(db_session, role=ROLE_SERVICE, label="validation-result-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "captured"
        assert response.json()["entry_count"] == projection_fixture["expected_projection"]["entry_count"]

    def test_request_job_must_match_the_persisted_attempt(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label="job-service")
        request = {
            **projection_fixture["request"],
            "deepsearch_job_id": "a-different-job",
        }

        response = _trigger(client, mission, _bearer(service), request)

        assert response.status_code == 409, response.text
        _assert_no_projection(db_session, mission)

    def test_missing_mission_is_not_disclosed_as_a_projection_error(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        service = _user(db_session, role=ROLE_SERVICE, label="missing-service")
        response = client.post(
            f"{API}/{uuid4()}/evidence",
            json=projection_fixture["request"],
            headers=_bearer(service),
        )
        assert response.status_code == 404, response.text

    def test_soft_deleted_project_fails_without_cross_tenant_rows(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, project, _owner = _seed_mission(db_session, projection_fixture)
        project.soft_delete()
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="deleted-project-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 404, response.text
        _assert_no_projection(db_session, mission)

    def test_missing_project_fails_without_orphan_ledger_rows(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        mission.project_id = None
        mission.workspace_id = None
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="orphan-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 409, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize(
        ("field", "value"),
        (
            ("result_protocol", None),
            ("result_protocol", {}),
            ("result_markdown", None),
            ("result_markdown", ""),
        ),
        ids=("no-protocol", "empty-protocol", "no-markdown", "empty-markdown"),
    )
    def test_empty_persisted_result_fails_loudly(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        field,
        value,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        setattr(mission, field, value)
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="empty-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)

    def test_well_shaped_but_empty_projection_fails_loudly(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """A zero-row success would falsely imply that research was captured."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        mission.result_protocol = {
            "sources_collected": [],
            "citations": [],
        }
        mission.execution_metadata = {
            "synthesis_telemetry": {
                "critique_telemetry": {"annotations": []},
                "tool_outcomes": {
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                },
            }
        }
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="zero-row-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)

    def test_truncated_tool_outcomes_fail_instead_of_losing_rejected_evidence(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        """A capped worker record list is incomplete evidence, never success."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        metadata = deepcopy(mission.execution_metadata)
        metadata["synthesis_telemetry"]["tool_outcomes"]["ledger_records_truncated"] = 1
        mission.execution_metadata = metadata
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="truncated-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize(
        "execution_metadata",
        (
            {},
            {"synthesis_telemetry": {}},
            {
                "synthesis_telemetry": {
                    "tool_outcomes": {
                        "records": [{"tool": "web_search", "status": "ok"}],
                        "records_truncated": 1,
                        "ledger_records_truncated": 0,
                    },
                }
            },
            {
                "synthesis_telemetry": {
                    "tool_outcomes": {
                        "records": [],
                        "records_truncated": 0,
                        "ledger_records": [],
                    },
                }
            },
        ),
        ids=(
            "missing-synthesis-telemetry",
            "missing-tool-outcomes",
            "missing-ledger-records",
            "missing-ledger-records-truncated",
        ),
    )
    def test_missing_tool_outcome_envelopes_fail_atomically(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        execution_metadata,
    ):
        """Omitted telemetry is unknown evidence, not an empty observation set."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        mission.execution_metadata = execution_metadata
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="missing-envelope-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0

    def test_explicit_empty_tool_outcome_records_are_complete_and_valid(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        mission.execution_metadata = {
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "records": [
                        {
                            "tool": "web_search",
                            "status": "ok",
                            "diagnostic_only": True,
                        }
                    ],
                    "records_truncated": 9,
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                },
                "critique_telemetry": {"annotations": []},
            }
        }
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="explicit-empty-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 201, response.text
        assert response.json()["entry_count"] == 3

    @pytest.mark.parametrize(
        "anchor",
        (
            " A secondary explainer provides implementation background.",
            "A secondary explainer provides implementation background. ",
        ),
        ids=("leading-whitespace", "trailing-whitespace"),
    )
    def test_applied_critique_anchor_must_preserve_exact_claim_whitespace(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        anchor,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        metadata = deepcopy(mission.execution_metadata)
        metadata["synthesis_telemetry"]["critique_telemetry"]["annotations"][0]["anchor"] = anchor
        mission.execution_metadata = metadata
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="critique-anchor-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0

    @pytest.mark.parametrize(
        ("protocol_mutation", "metadata_mutation"),
        (
            ({"sources_collected": "not-a-list"}, None),
            ({"citations": ["not-an-object"]}, None),
            (None, {"synthesis_telemetry": {"tool_outcomes": "not-an-object"}}),
        ),
        ids=("source-envelope", "citation-item", "tool-envelope"),
    )
    def test_malformed_active_envelopes_fail_atomically(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        protocol_mutation,
        metadata_mutation,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        if protocol_mutation is not None:
            protocol = deepcopy(mission.result_protocol)
            protocol.update(protocol_mutation)
            mission.result_protocol = protocol
        if metadata_mutation is not None:
            mission.execution_metadata = metadata_mutation
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="malformed-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize(
        "record",
        (
            {
                "tool": 7,
                "url": "https://example.test/tool",
                "status": "error",
            },
            {
                "tool": "web_search",
                "url": "https://example.test/tool",
                "status": "error",
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "error": "raw exceptions are forbidden in ledger v1",
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": 7,
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "pending",
            },
            {
                "tool": "source_fetch",
                "url": "not-an-http-url",
                "status": "error",
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "status_code": True,
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "status_code": -1,
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "status_code": 600,
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "status_code": "503",
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "error_category": {"unsafe": "structured"},
            },
            {
                "tool": "source_fetch",
                "url": "https://example.test/tool",
                "status": "error",
                "error_category": "x" * 201,
            },
            {
                "tool": "url_liveness",
                "url": "https://example.test/tool",
                "status": "error",
                "alive": "false",
            },
            {
                "tool": "url_liveness",
                "url": "https://example.test/tool",
                "status": "error",
            },
            {
                "tool": "url_liveness",
                "url": "https://example.test/tool",
                "status": "error",
                "alive": None,
            },
        ),
        ids=(
            "tool-type",
            "unknown-tool",
            "extra-key",
            "status-type",
            "status-enum",
            "url",
            "status-code-bool",
            "status-code-negative",
            "status-code-too-large",
            "status-code-string",
            "error-category-type",
            "error-category-too-long",
            "alive-type",
            "liveness-alive-missing",
            "liveness-alive-null",
        ),
    )
    def test_malformed_relevant_tool_fields_fail_atomically(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        record,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        mission.execution_metadata = {
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [record],
                    "ledger_records_truncated": 0,
                }
            }
        }
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="typed-outcome-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0

    def test_invalid_middle_source_rolls_back_the_valid_prefix_and_suffix(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        protocol = deepcopy(mission.result_protocol)
        protocol["sources_collected"] = [
            protocol["sources_collected"][0],
            {"url": "not-an-absolute-http-url", "title": "invalid middle"},
            protocol["sources_collected"][1],
        ]
        protocol["citations"] = []
        mission.result_protocol = protocol
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="atomic-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0

    @pytest.mark.parametrize(
        "userinfo_url",
        (
            "https://researcher@example.test/source",
            "https://researcher:credential@example.test/source",
        ),
        ids=("username", "password"),
    )
    def test_url_userinfo_is_rejected_atomically(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        userinfo_url,
    ):
        """Credential-like authority fields can never enter source provenance."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        protocol = deepcopy(mission.result_protocol)
        protocol["sources_collected"] = [
            protocol["sources_collected"][0],
            {
                "url": userinfo_url,
                "title": "Userinfo must be rejected",
            },
            protocol["sources_collected"][1],
        ]
        protocol["citations"] = []
        mission.result_protocol = protocol
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="userinfo-service")

        response = _trigger(
            client,
            mission,
            _bearer(service),
            projection_fixture["request"],
        )

        assert response.status_code == 400, response.text
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0

    def test_projection_cap_fails_instead_of_silently_truncating(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        protocol = deepcopy(mission.result_protocol)
        protocol["citations"] = []
        protocol["sources_collected"] = [
            {
                "url": f"https://cap.example.test/source-{index}",
                "title": f"Cap source {index}",
                "snippet": "A valid source that must not be partially committed.",
            }
            for index in range(1_001)
        ]
        mission.result_protocol = protocol
        mission.execution_metadata = {
            "synthesis_telemetry": {
                "tool_outcomes": {
                    "ledger_records": [],
                    "ledger_records_truncated": 0,
                }
            }
        }
        db_session.commit()
        service = _user(db_session, role=ROLE_SERVICE, label="cap-service")

        response = _trigger(client, mission, _bearer(service), projection_fixture["request"])

        assert response.status_code == 400, response.text
        assert "1000" in response.json()["detail"]
        _assert_no_projection(db_session, mission)
        assert db_session.query(LedgerSource).count() == 0


class TestProjectionAuthentication:
    def test_anonymous_projection_is_rejected_before_mission_lookup(self, client, rbac_on, projection_fixture):
        response = client.post(
            f"{API}/{uuid4()}/evidence",
            json=projection_fixture["request"],
        )
        assert response.status_code == 401, response.text

    def test_service_gate_precedes_mission_lookup_for_authenticated_callers(
        self,
        client,
        db_session,
        monkeypatch,
        projection_fixture,
    ):
        """Humans cannot distinguish a missing mission through the trusted writer."""
        monkeypatch.setattr(settings, "rbac_enabled", False)
        missing_id = uuid4()
        human = _user(db_session, role=ROLE_OWNER, label="non-oracle-human")
        service = _user(db_session, role=ROLE_SERVICE, label="non-oracle-service")

        human_response = client.post(
            f"{API}/{missing_id}/evidence",
            headers=_bearer(human),
            json=projection_fixture["request"],
        )
        service_response = client.post(
            f"{API}/{missing_id}/evidence",
            headers=_bearer(service),
            json=projection_fixture["request"],
        )

        assert human_response.status_code == 403, human_response.text
        assert service_response.status_code == 404, service_response.text

    @pytest.mark.parametrize("role", _HUMAN_ROLES)
    @pytest.mark.parametrize("credential", ("jwt", "api-key"))
    def test_every_human_role_and_credential_is_forbidden(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        role,
        credential,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        human = _user(db_session, role=role, label=f"human-{role}-{credential}")
        headers = _bearer(human) if credential == "jwt" else _api_key(db_session, human)

        response = _trigger(client, mission, headers, projection_fixture["request"])

        assert response.status_code == 403, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize("credential", ("jwt", "api-key"))
    def test_service_principal_can_trigger_projection(
        self,
        client,
        db_session,
        rbac_on,
        projection_fixture,
        credential,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label=f"service-{credential}")
        headers = _bearer(service) if credential == "jwt" else _api_key(db_session, service)

        response = _trigger(client, mission, headers, projection_fixture["request"])

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "captured"

    @pytest.mark.parametrize("role", _HUMAN_ROLES)
    @pytest.mark.parametrize("credential", ("jwt", "api-key"))
    def test_service_gate_stays_closed_to_humans_when_global_rbac_is_off(
        self,
        client,
        db_session,
        monkeypatch,
        projection_fixture,
        role,
        credential,
    ):
        """Trusted DeepSearch provenance is not controlled by the RBAC rollout flag."""
        monkeypatch.setattr(settings, "rbac_enabled", False)
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        human = _user(db_session, role=role, label=f"rbac-off-{role}-{credential}")
        headers = _bearer(human) if credential == "jwt" else _api_key(db_session, human)

        response = _trigger(client, mission, headers, projection_fixture["request"])

        assert response.status_code == 403, response.text
        _assert_no_projection(db_session, mission)

    @pytest.mark.parametrize("credential", ("jwt", "api-key"))
    def test_service_principal_succeeds_when_global_rbac_is_off(
        self,
        client,
        db_session,
        monkeypatch,
        projection_fixture,
        credential,
    ):
        monkeypatch.setattr(settings, "rbac_enabled", False)
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        service = _user(db_session, role=ROLE_SERVICE, label=f"rbac-off-service-{credential}")
        headers = _bearer(service) if credential == "jwt" else _api_key(db_session, service)

        response = _trigger(client, mission, headers, projection_fixture["request"])

        assert response.status_code == 201, response.text
        assert response.json()["status"] == "captured"


class TestDeepSearchEvidenceOutboxModel:
    def test_pending_row_can_be_leased_then_acknowledged(self, db_session, projection_fixture):
        """The DB permits the one coherent success lifecycle DS must resume."""
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        outbox = _outbox_row(mission)
        db_session.add(outbox)
        db_session.commit()
        db_session.refresh(outbox)

        assert outbox.state == "pending"
        assert outbox.schema_version == 1
        assert outbox.delivery_attempt_count == 0
        assert outbox.lease_token is None
        assert outbox.lease_expires_at is None
        assert outbox.acked_at is None
        assert outbox.created_at is not None
        assert outbox.updated_at is not None

        lease_token = uuid4()
        lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        outbox.state = "leased"
        outbox.delivery_attempt_count = 1
        outbox.lease_token = lease_token
        outbox.lease_expires_at = lease_expires_at
        outbox.next_attempt_at = lease_expires_at
        db_session.commit()
        db_session.refresh(outbox)
        assert outbox.state == "leased"
        assert outbox.lease_token == lease_token
        assert outbox.delivery_attempt_count == 1

        outbox.state = "acked"
        outbox.lease_token = None
        outbox.lease_expires_at = None
        outbox.acked_at = datetime.now(UTC)
        outbox.last_http_status = 201
        db_session.commit()
        db_session.refresh(outbox)

        assert outbox.state == "acked"
        assert outbox.acked_at is not None
        assert outbox.last_http_status == 201
        assert outbox.lease_token is None
        assert outbox.lease_expires_at is None

    @pytest.mark.parametrize(
        "overrides",
        (
            {"deepsearch_job_id": "   "},
            {"deepsearch_result_key": "   "},
            {"mission_attempt_count": 0},
            {"terminal_status": "blocked"},
            {"schema_version": 2},
            {"state": "retrying"},
            {"delivery_attempt_count": -1},
            {"last_http_status": 99},
            {"last_http_status": 600},
            {"state": "leased"},
            {
                "state": "pending",
                "lease_token": uuid4(),
                "lease_expires_at": datetime.now(UTC) + timedelta(minutes=5),
            },
            {
                "state": "leased",
                "lease_token": uuid4(),
                "lease_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "next_attempt_at": datetime.now(UTC) + timedelta(minutes=10),
            },
            {"state": "acked"},
        ),
        ids=(
            "blank-job",
            "blank-result-key",
            "nonpositive-mission-attempt",
            "nonterminal-mission-status",
            "future-schema",
            "unknown-delivery-state",
            "negative-delivery-attempts",
            "http-below-range",
            "http-above-range",
            "lease-without-fence",
            "pending-with-lease",
            "lease-deadline-mismatch",
            "ack-without-timestamp",
        ),
    )
    def test_outbox_constraints_reject_incoherent_or_unbounded_state(
        self,
        db_session,
        projection_fixture,
        overrides,
    ):
        mission, _project, _owner = _seed_mission(db_session, projection_fixture)
        db_session.add(_outbox_row(mission, **overrides))

        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_interactive_human_capture_contract_remains_mcp_agent_owned(
    client,
    db_session,
    rbac_on,
    projection_fixture,
):
    """Adding the worker channel must not broaden or rewrite LEDGER-1 writes."""
    mission, project, owner = _seed_mission(db_session, projection_fixture)
    response = client.post(
        f"{settings.api_v1_prefix}/evidence/capture",
        headers=_bearer(owner),
        json={
            "project_id": str(project.id),
            "mission_id": str(mission.id),
            "session_key": "human-capture-unchanged",
            "entries": [
                {
                    "claim": "A human-authenticated agent still owns this capture.",
                    "source_url": "https://example.test/human-capture",
                    "disposition": "supporting",
                }
            ],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["entries"][0]["origin"] == "mcp-agent"
    row = db_session.query(LedgerEntry).filter_by(session_key="human-capture-unchanged").one()
    assert row.origin == "mcp-agent"
