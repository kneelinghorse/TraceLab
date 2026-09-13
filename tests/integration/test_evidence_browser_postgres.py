"""The browser's exact tag/date filters must work with JSONB and ranked FTS."""

from datetime import date, datetime
from uuid import uuid4

import pytest

from app.models.evidence_ledger import LedgerEntry
from app.models.project import Project
from app.models.user import User
from app.schemas.evidence_ledger import CaptureRequest
from app.services.evidence_ledger import EvidenceLedgerService

pytestmark = pytest.mark.integration
_HASH = "placeholder-not-a-real-hash"


def test_postgres_browser_filters_before_count_and_page(db_session):
    user = User(id=uuid4(), email=f"{uuid4()}@example.test", display_name="Evidence reviewer", password_hash=_HASH, role="member")
    project = Project(id=uuid4(), name="Exact evidence filters")
    db_session.add_all([user, project])
    db_session.flush()
    service = EvidenceLedgerService()
    for size in (100, 23):
        service.capture(
            db_session,
            CaptureRequest(
                project_id=project.id,
                session_key="browser-pg",
                entries=[
                    {
                        "claim": "Needle evidence",
                        "source_url": "https://example.test/filter",
                        "tags": ["100% exact"],
                        "disposition": "supporting",
                    }
                    for _ in range(size)
                ],
            ),
            owner_id=user.id,
            workspace_id=None,
        )
    db_session.query(LedgerEntry).filter(LedgerEntry.project_id == project.id).update(
        {"created_at": datetime(2026, 9, 12, 23, 59, 59)}
    )
    db_session.commit()
    service.capture(
        db_session,
        CaptureRequest(
            project_id=project.id,
            session_key="browser-pg",
            entries=[
                {
                    "claim": "Needle excluded",
                    "source_url": "https://example.test/filter",
                    "tags": ["100X exact"],
                    "disposition": "supporting",
                }
            ],
        ),
        owner_id=user.id,
        workspace_id=None,
    )
    args = dict(
        project_id=project.id,
        session_key=None,
        mission_id=None,
        disposition=None,
        page=7,
        page_size=20,
        tag="100% exact",
        created_from=date(2026, 9, 12),
        created_until=date(2026, 9, 12),
    )
    rows, _, total, _ = service.list_ledger(db_session, **args, entry_access_filter=None, note_access_filter=None)
    assert total == 123 and len(rows) == 3
    rows, total = service.search(db_session, **args, keyword="needle", access_filter=None)
    assert total == 123 and len(rows) == 3
