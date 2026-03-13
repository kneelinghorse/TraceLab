from __future__ import annotations

import uuid

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
)

from app.core.database import engine
from app.models import (
    Collection,
    CollectionItem,
    Document,
    DocumentChunk,
    GraphEdge,
    Insight,
    InsightSource,
    Mission,
    Project,
    Report,
    ReportSource,
)
from app.models.types import GUID
from app.services.pedr.edge_materialization import EdgeMaterializationService
from app.services.pedr.semantic_protocol import (
    URN,
    Edge,
    EntityType,
    ProtocolManifest,
    URNGenerator,
)


@pytest.fixture(scope="module", autouse=True)
def edge_materialization_schema():
    inspector = inspect(engine)

    def ensure_table(table):
        if not inspector.has_table(table.name):
            table.create(engine, checkfirst=True)

    def ensure_missions_table():
        if inspector.has_table(Mission.__tablename__):
            return
        metadata = MetaData()
        Project.__table__.to_metadata(metadata)
        Report.__table__.to_metadata(metadata)
        mission_table = Mission.__table__.to_metadata(metadata)
        for constraint in list(mission_table.constraints):
            if isinstance(constraint, CheckConstraint) and "jsonb_array_length" in str(
                constraint.sqltext
            ):
                mission_table.constraints.remove(constraint)
        mission_table.create(engine, checkfirst=True)

    def ensure_document_chunks_table():
        if inspector.has_table(DocumentChunk.__tablename__):
            return
        metadata = MetaData()
        Document.__table__.to_metadata(metadata)
        Table(
            "document_chunks",
            metadata,
            Column("id", GUID(), primary_key=True, default=uuid.uuid4),
            Column(
                "document_id",
                GUID(),
                ForeignKey("documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            Column("chunk_index", Integer, nullable=False),
            Column("content", Text, nullable=False),
            Column("content_tsv", Text, nullable=True),
            Column("embedding_id", String),
            Column("token_count", Integer),
            Column("start_char", Integer),
            Column("end_char", Integer),
            Column("prev_chunk_id", GUID(), ForeignKey("document_chunks.id")),
            Column("next_chunk_id", GUID(), ForeignKey("document_chunks.id")),
            Column("created_at", DateTime, nullable=True),
            UniqueConstraint(
                "document_id", "chunk_index", name="uq_document_chunks_document_index"
            ),
        )
        metadata.create_all(engine, checkfirst=True)

    ensure_table(Project.__table__)
    ensure_table(Report.__table__)
    ensure_missions_table()
    ensure_table(Document.__table__)
    ensure_document_chunks_table()
    ensure_table(Collection.__table__)
    ensure_table(CollectionItem.__table__)
    ensure_table(Insight.__table__)
    ensure_table(InsightSource.__table__)
    ensure_table(ReportSource.__table__)
    ensure_table(GraphEdge.__table__)

    yield


def test_materialize_implicit_edges_round_trip(db_session, project):
    report = Report(
        project_id=project.id,
        title="Edge Report",
        content="Report content",
    )
    db_session.add(report)

    mission_id = f"M-EDGE-{uuid.uuid4()}"
    mission = Mission(
        project_id=project.id,
        mission_id=mission_id,
        title="Edge Mission",
        objective="Test edge materialization",
        success_criteria=["edges materialized"],
    )
    db_session.add(mission)
    db_session.flush()

    document = Document(
        project_id=project.id,
        name="Edge Document",
        content="Content",
        file_type="txt",
        source_type="analysis",
        source_report_id=report.id,
        source_mission_id=mission.id,
    )
    db_session.add(document)
    db_session.flush()

    chunk_a = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Chunk A",
    )
    chunk_b = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        content="Chunk B",
    )
    db_session.add_all([chunk_a, chunk_b])

    mission.result_document_ids = [str(document.id)]
    mission.result_report_id = report.id

    insight = Insight(
        project_id=project.id,
        title="Edge Insight",
        content="Insight content",
        insight_type="finding",
    )
    db_session.add(insight)

    collection = Collection(name="Edge Collection")
    db_session.add(collection)
    db_session.flush()

    db_session.add_all(
        [
            InsightSource(
                insight_id=insight.id,
                chunk_id=chunk_a.id,
                relevance_score=0.85,
            ),
            ReportSource(
                report_id=report.id,
                source_type="chunk",
                source_id=chunk_b.id,
            ),
            ReportSource(
                report_id=report.id,
                source_type="collection",
                source_id=collection.id,
            ),
            CollectionItem(
                collection_id=collection.id,
                chunk_id=chunk_a.id,
            ),
        ]
    )
    db_session.commit()

    service = EdgeMaterializationService()
    result = service.materialize_implicit_edges(db_session)

    edges = {
        (edge.from_urn, edge.to_urn, edge.edge_type)
        for edge in db_session.query(GraphEdge).all()
    }

    project_urn = str(URNGenerator.for_project(str(project.id)))
    document_urn = str(URNGenerator.for_document(str(document.id)))
    chunk_urn_a = str(URNGenerator.for_chunk(str(document.id), 0))
    chunk_urn_b = str(URNGenerator.for_chunk(str(document.id), 1))
    mission_urn = str(URNGenerator.for_mission(mission.mission_id))
    insight_urn = str(URNGenerator.for_insight(str(insight.id)))
    insight_chunk_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_a.id)))
    report_urn = str(URNGenerator.generate(EntityType.REPORT, str(report.id)))
    report_chunk_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_b.id)))
    collection_urn = str(
        URNGenerator.generate(EntityType.COLLECTION, str(collection.id))
    )
    collection_chunk_urn = str(URNGenerator.generate(EntityType.CHUNK, str(chunk_a.id)))

    expected = {
        (project_urn, document_urn, "contains"),
        (document_urn, chunk_urn_a, "contains"),
        (document_urn, chunk_urn_b, "contains"),
        (chunk_urn_a, document_urn, "part_of"),
        (chunk_urn_b, document_urn, "part_of"),
        (document_urn, project_urn, "belongs_to"),
        (mission_urn, project_urn, "belongs_to"),
        (mission_urn, document_urn, "references"),
        (mission_urn, report_urn, "references"),
        (insight_urn, insight_chunk_urn, "derived_from"),
        (insight_urn, project_urn, "belongs_to"),
        (report_urn, report_chunk_urn, "references"),
        (report_urn, collection_urn, "references"),
        (report_urn, project_urn, "belongs_to"),
        (document_urn, report_urn, "derived_from"),
        (document_urn, mission_urn, "derived_from"),
        (collection_urn, collection_chunk_urn, "contains"),
    }

    assert expected.issubset(edges)
    assert result.inserted_count >= len(expected)


def test_materialize_implicit_edges_idempotent(db_session, project):
    """Second materialization run should skip all existing edges."""
    document = Document(
        project_id=project.id,
        name="Idempotent Doc",
        content="Content",
        file_type="txt",
        source_type="analysis",
    )
    db_session.add(document)
    db_session.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        content="Chunk",
    )
    db_session.add(chunk)
    db_session.commit()

    service = EdgeMaterializationService()

    first = service.materialize_implicit_edges(db_session)
    assert first.inserted_count > 0

    second = service.materialize_implicit_edges(db_session)
    assert second.inserted_count == 0
    assert second.updated_count == 0
    assert second.skipped_count == second.total
    assert second.total == first.total


def test_materialize_from_manifest_upsert_updates_existing_edge(db_session):
    unique_suffix = str(uuid.uuid4())
    from_urn = f"urn:research:mission:M-UPSERT-{unique_suffix}"
    to_urn = f"urn:research:project:P-UPSERT-{unique_suffix}"

    existing = GraphEdge(
        from_urn=from_urn,
        to_urn=to_urn,
        edge_type="belongs_to",
        direction="out",
        weight=0.1,
        reason="old",
        via="data",
    )
    db_session.add(existing)
    db_session.commit()

    manifest = ProtocolManifest(
        urn=URN.create(EntityType.MISSION, f"M-UPSERT-{unique_suffix}")
    )
    manifest.add_edge(
        Edge(
            edge_type="belongs_to",
            from_urn=from_urn,
            to_urn=to_urn,
            direction="out",
            weight=0.9,
            reason="new",
            via="api",
        )
    )

    service = EdgeMaterializationService()
    result = service.materialize_from_manifest(manifest, db_session)

    db_session.refresh(existing)

    assert existing.weight == 0.9
    assert existing.reason == "new"
    assert existing.via == "api"
    assert result.updated_count == 1
