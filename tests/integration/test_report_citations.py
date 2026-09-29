"""REPORT-1 PostgreSQL migration, atomic persistence and source-lock behavior."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.project import Project
from app.models.report import Report
from app.services.report_citations import persistable_citations, text_hash
from app.services.report_service import ReportService

pytestmark = pytest.mark.integration


def test_migration_retains_legacy_report_and_roundtrips_manifest(alembic_cfg, migration_db_url):
    command.upgrade(alembic_cfg, "052_personal_spaces")
    engine = create_engine(migration_db_url)
    report_id = uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO reports (id, title, content) VALUES (:id, 'Legacy', 'Unchanged [3]')"), {"id": report_id})
    command.upgrade(alembic_cfg, "053_report_citations")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT content, citation_manifest, generation_provenance FROM reports WHERE id=:id"), {"id": report_id}).one()
        assert tuple(row) == ("Unchanged [3]", None, None)
        conn.execute(text("UPDATE reports SET citation_manifest = '[{\"marker\": 3}]'::jsonb WHERE id=:id"), {"id": report_id})
        assert conn.execute(text("SELECT citation_manifest FROM reports WHERE id=:id"), {"id": report_id}).scalar() == [{"marker": 3}]
    command.downgrade(alembic_cfg, "052_personal_spaces")
    assert "citation_manifest" not in {c["name"] for c in inspect(engine).get_columns("reports")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT content FROM reports WHERE id=:id"), {"id": report_id}).scalar() == "Unchanged [3]"
    command.upgrade(alembic_cfg, "head")
    engine.dispose()


def test_postgres_save_reload_and_support_lock(pg_engine, monkeypatch):
    factory = sessionmaker(bind=pg_engine)
    with factory.begin() as db:
        project = Project(name="REPORT-1 isolated PostgreSQL")
        db.add(project)
        db.flush()
        doc = Document(name="Source", project_id=project.id)
        db.add(doc)
        db.flush()
        chunks = [DocumentChunk(document_id=doc.id, chunk_index=i, content=f"Finding {i}") for i in range(3)]
        db.add_all(chunks)
        db.flush()
        ids, doc_id, project_id = [c.id for c in chunks], doc.id, project.id
        mapping = [{"marker": i + 1, "chunk_id": str(chunks[i].id), "document_id": str(doc_id), "content_hash": text_hash(chunks[i].content)} for i in (0, 2)]
    result = {"content": "First [1]. Third [3].", "citations": mapping, "effective_chunk_ids": list(map(str, ids)), "chunk_count": 3}
    class Synthesis:
        def synthesize(self, **kwargs):
            return result
    service = ReportService(session_factory=factory, synthesis_service=Synthesis())
    report, _ = service.create_report(title="Atomic cited report", chunk_ids=ids)
    assert service.get_report(report.id).citation_manifest == mapping
    from app.api.v1.synthesize import _create_report_from_synthesis
    monkeypatch.setattr("app.api.v1.synthesize.SessionLocal", factory)
    second_id = _create_report_from_synthesis(
        title="Second writer", content=result["content"], output_format="summary", prompt=None,
        tokens_used=0, chunk_count=3, collection_id=None, chunk_ids=ids, project_id=project_id,
        owner_id=None, synthesis_result=result,
    )
    assert service.get_report(second_id).citation_manifest == mapping

    # A concurrent source rewrite cannot race between validation and report commit.
    with factory() as db:
        persistable_citations(db, result)
        def competing_edit():
            with pg_engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '100ms'"))
                conn.execute(text("UPDATE document_chunks SET content='changed' WHERE id=:id"), {"id": ids[0]})
        with ThreadPoolExecutor(max_workers=1) as executor, pytest.raises(OperationalError, match="lock timeout"):
            executor.submit(competing_edit).result()
        db.rollback()
    with factory.begin() as db:
        db.query(Document).filter_by(id=doc_id).update({"deleted_at": text("now()")})
    with pytest.raises(ValueError, match="no longer readable"):
        service.create_report(title="Must roll back", chunk_ids=ids)
    with factory.begin() as db:
        assert db.query(Report).filter_by(title="Must roll back").count() == 0
        db.delete(db.get(Report, report.id))
        db.delete(db.get(Report, second_id))
        db.delete(db.get(Project, project_id))
