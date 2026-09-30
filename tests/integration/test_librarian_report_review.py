"""LIB-4 PostgreSQL: reviewed content and the retry receipt commit together."""

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.document import Document
from app.models.idempotency import IdempotencyRecord
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.user import User
from app.schemas.librarian_reports import ReportAcceptRequest, ReportDraftRequest
from app.services.librarian import LibrarianService
from app.services.librarian_model import ModelReply
from app.services.librarian_reports import accept_report, draft_report, report_sources

pytestmark = pytest.mark.integration


def test_concurrent_accepts_save_one_exact_report_with_sources_and_receipt(pg_engine, monkeypatch):
    monkeypatch.setattr(settings, "rbac_enabled", True)
    factory = sessionmaker(bind=pg_engine)
    with factory.begin() as db:
        user = User(email=f"{uuid4()}@example.test", display_name="Report review", password_hash=str(uuid4()), role="member")
        db.add(user)
        db.flush()
        project = Project(name="Concurrent report", owner_id=user.id)
        collection = Collection(name="Reviewed sources", owner_id=user.id)
        db.add_all([project, collection])
        db.flush()
        doc = Document(name="Source", project_id=project.id, owner_id=user.id)
        db.add(doc)
        db.flush()
        chunks = [DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Source {i} describes navigation.") for i in range(2)]
        db.add_all(chunks)
        db.flush()
        db.add_all([CollectionItem(collection_id=collection.id, chunk_id=chunk.id, review_position=i) for i, chunk in enumerate(reversed(chunks))])
        project_id, collection_id, user_id = project.id, collection.id, user.id
        expected = [str(c.id) for c in reversed(chunks)]
        principal = AuthenticatedUser(user_id=user.id, email=user.email, display_name=user.display_name, role=user.role)
    model = Mock(model_name="isolated-report-model")
    model.complete.return_value = ModelReply(content=json.dumps({"content": "# Findings\n\nNavigation needs attention [1] [2]."}))
    with factory() as db:
        project = db.get(Project, project_id)
        inputs = report_sources(db, principal, project, collection_id)
        assert [m["chunk_id"] for m in inputs["members"]] == expected
        preview = draft_report(db, principal, project, ReportDraftRequest(project_id=project_id, source_token=inputs["source_token"],
                               chunk_ids=expected, reviewed_sources=True, title="Reviewed report", prompt="Summarise navigation", format="report"),
                               LibrarianService(model_factory=lambda: model))
    request = ReportAcceptRequest(project_id=project_id, proposal_token=preview["proposal_token"])
    def accept():
        with factory() as db:
            return accept_report(db, principal, db.get(Project, project_id), request)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(accept) for _ in range(2)]
        results = [future.result(timeout=20) for future in futures]
    assert results[0] == results[1]
    with factory() as db:
        report = db.query(Report).filter(Report.owner_id == user_id).one()
        assert report.content == preview["content"] and report.status == "draft"
        assert [s["chunk_id"] for s in report.citation_manifest] == expected
        assert report.generation_provenance["accepted_by"] == str(user_id)
        assert db.query(ReportSource).filter(ReportSource.report_id == report.id).count() == 3
        assert db.query(IdempotencyRecord).filter(IdempotencyRecord.key.like(f"librarian-report:{user_id}:%")).count() == 1
    assert model.complete.call_count == 1
