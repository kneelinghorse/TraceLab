"""Live relational neighborhoods: scoped SQL totals, bounded rows, batched expansion."""

from collections import defaultdict
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, case, cast, exists, func, literal, or_, select, union, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, aliased, load_only, noload

from app.core.authorization import accessible_filter, authorize
from app.core.security import AuthenticatedUser
from app.models.chunk import DocumentChunk
from app.models.collection import Collection, CollectionItem
from app.models.collection_document import CollectionDocument
from app.models.document import Document
from app.models.evidence_ledger import LedgerEntry
from app.models.mission import Mission
from app.models.project import Project
from app.models.report import Report, ReportSource
from app.models.types import GUID
from app.ports.graph_neighborhood import GraphRootError
from app.schemas.graph_neighborhood import GraphEdge, GraphGroup, GraphNeighborhoodResponse, GraphNode
from app.schemas.navigation_search import NavigationEntityType
from app.services.document_policy import document_read_policy
from app.services.evidence_browser import document_evidence_condition, report_evidence_condition

_MODELS = {
    "project": Project, "document": Document, "collection": Collection,
    "mission": Mission, "report": Report, "evidence": LedgerEntry,
}
_FIELDS = {
    "project": "id name owner_id workspace_id updated_at deleted_at status",
    "document": "id name owner_id project_id updated_at deleted_at source_mission_id source_report_id document_metadata processed",
    "collection": "id name owner_id workspace_id updated_at",
    "mission": "id title owner_id project_id updated_at status result_report_id",
    "report": "id title owner_id project_id updated_at status parent_id content",
    "evidence": "id claim owner_id project_id updated_at disposition mission_id",
}
_ROUTES = {kind: f"/{kind}s" for kind in _MODELS}
_ROUTES["evidence"] = "/evidence"


class _Read:
    """One request's policies and bounded hydration; never retained across calls."""

    def __init__(self, db: Session, user: AuthenticatedUser):
        if user.role == "service":
            raise GraphRootError(403, "Graph neighborhoods require a human user principal.")
        self.db, self.user = db, user
        self.scopes = {kind: accessible_filter(user, model, db) for kind, model in _MODELS.items() if kind != "document"}
        self.evidence_row_scope = self.scopes["evidence"]
        if self.evidence_row_scope is not None:
            self.evidence_row_scope = or_(self.evidence_row_scope, LedgerEntry.project_id.in_(
                select(Project.id).where(Project.owner_id == user.user_id)
            ))
        live_projects = select(Project.id).where(Project.deleted_at.is_(None))
        doc_scope = document_read_policy(user, db)
        self.scopes["document"] = and_(
            Document.deleted_at.is_(None), Document.project_id.in_(live_projects),
            doc_scope if doc_scope is not None else True,
        )
        self.scopes["project"] = and_(Project.deleted_at.is_(None), self.scopes["project"] if self.scopes["project"] is not None else True)
        readable_parents = select(Project.id).where(self.scopes["project"])
        self.scopes["evidence"] = and_(
            LedgerEntry.project_id.in_(readable_parents),
            self.evidence_row_scope if self.evidence_row_scope is not None else True,
        )
        self.objects: dict[tuple[str, UUID], Any] = {}
        self.chunk_counts: dict[UUID, int] = {}

    def query(self, kind: str):
        query = self.db.query(_MODELS[kind])
        scope = self.scopes[kind]
        return query.filter(scope) if scope is not None else query

    def raw(self, kind: str):
        model = _MODELS[kind]
        return self.db.query(model).options(load_only(*(getattr(model, name) for name in _FIELDS[kind].split())), noload("*"))

    def remember(self, kind: str, rows: list[Any]) -> None:
        for row in rows:
            self.objects[kind, row.id] = row
        if kind == "document" and rows:
            counts = self.db.query(DocumentChunk.document_id, func.count()).filter(
                DocumentChunk.document_id.in_([row.id for row in rows])
            ).group_by(DocumentChunk.document_id).all()
            self.chunk_counts.update(dict(counts))

    def load(self, kind: str, ids: set[UUID]) -> dict[UUID, Any]:
        missing = ids - {key[1] for key in self.objects if key[0] == kind}
        if missing:
            query = self.raw(kind).filter(_MODELS[kind].id.in_(missing))
            if self.scopes[kind] is not None:
                query = query.filter(self.scopes[kind])
            self.remember(kind, query.order_by(_MODELS[kind].id).all())
        return {row_id: self.objects[kind, row_id] for row_id in sorted(ids) if (kind, row_id) in self.objects}

    def root(self, kind: str, root_id: UUID):
        model = _MODELS[kind]
        query = self.raw(kind).filter(model.id == root_id)
        if kind in {"project", "document"}:
            query = query.filter(model.deleted_at.is_(None))
        if kind == "evidence" and self.evidence_row_scope is not None:
            query = query.filter(self.evidence_row_scope)
        row = query.first()
        if row is None:
            raise GraphRootError(404, "Root object not found.")
        if kind in {"document", "evidence"}:
            parent = self.raw("project").filter(Project.id == row.project_id, Project.deleted_at.is_(None)).first()
            if parent is None:
                # Decision439: strict graph exclusion wins over document detail's200.
                raise GraphRootError(404, "Root project not found.")
            if kind == "evidence" and not authorize(self.user, "read", parent, self.db):
                raise GraphRootError(403, "You do not have access to this resource.")
        if kind != "evidence" and not authorize(self.user, "read", row, self.db):
            raise GraphRootError(403, "You do not have access to this resource.")
        self.remember(kind, [row])
        return row

    def node(self, kind: str, row: Any) -> GraphNode:
        attributes = {}
        for name in ("status", "disposition", "processed", "project_id"):
            value = getattr(row, name, None)
            if value is not None:
                attributes[name] = str(value) if isinstance(value, UUID) else value
        updated = row.updated_at
        if updated is not None:
            attributes["updated_at"] = (updated.replace(tzinfo=UTC) if updated.tzinfo is None else updated.astimezone(UTC)).isoformat()
        if kind == "document":
            attributes["chunk_count"] = self.chunk_counts.get(row.id, 0)
        title = row.claim if kind == "evidence" else row.name if kind in {"project", "document", "collection"} else row.title
        return GraphNode(key=f"{kind}:{row.id}", type=kind, id=row.id, title=title, href=f"{_ROUTES[kind]}/{row.id}", attributes=attributes)

    def pairs(self, kind: str, from_id: Any):
        model = _MODELS[kind]
        title = model.claim if kind == "evidence" else model.name if kind in {"project", "document", "collection"} else model.title
        return self.query(kind).with_entities(from_id.label("from_id"), model.id.label("target_id"), title.label("title"))

    def result_document_match(self):
        """Compare persisted JSON IDs without casting malformed legacy IDs to UUID."""
        if self.db.get_bind().dialect.name == "postgresql":
            data = cast(Mission.result_document_ids, JSONB)
            array = case((func.jsonb_typeof(data) == "array", data), else_=cast(literal("[]"), JSONB))
            values = func.jsonb_array_elements_text(array).table_valued("value").render_derived()
        else:
            array = case((func.json_type(Mission.result_document_ids) == "array", Mission.result_document_ids), else_="[]")
            values = func.json_each(array).table_valued("value")
        return exists(select(1).select_from(values).where(
            func.replace(func.lower(values.c.value), "-", "") == func.replace(cast(Document.id, String), "-", "")
        ))

    def relations(self, kind: str, parents: list[Any]):
        ids = [row.id for row in parents]
        if kind == "project":
            for target, relation, basis in (
                ("document", "documents", "documents.project_id"), ("mission", "missions", "missions.project_id"),
                ("report", "reports", "reports.project_id"), ("evidence", "evidence", "ledger_entries.project_id"),
            ):
                model = _MODELS[target]
                yield relation, target, basis, self.pairs(target, model.project_id).filter(model.project_id.in_(ids)).statement
        elif kind == "mission":
            yield "result_report", "report", "missions.result_report_id", self.pairs("report", Mission.id).join(
                Mission, Mission.result_report_id == Report.id
            ).filter(Mission.id.in_(ids), Mission.project_id == Report.project_id).statement
            yield "result_documents", "document", "missions.result_document_ids", self.pairs("document", Mission.id).join(
                Mission, Mission.project_id == Document.project_id
            ).filter(Mission.id.in_(ids), self.result_document_match()).statement
            yield "source_documents", "document", "documents.source_mission_id", self.pairs("document", Document.source_mission_id).join(
                Mission, Mission.id == Document.source_mission_id
            ).filter(Mission.id.in_(ids), Mission.project_id == Document.project_id).statement
            yield "evidence", "evidence", "ledger_entries.mission_id", self.pairs("evidence", LedgerEntry.mission_id).join(
                Mission, Mission.id == LedgerEntry.mission_id
            ).filter(Mission.id.in_(ids), Mission.project_id == LedgerEntry.project_id).statement
        elif kind == "document":
            for target, column, relation in (("mission", Document.source_mission_id, "source_mission"), ("report", Document.source_report_id, "source_report")):
                model = _MODELS[target]
                yield relation, target, f"documents.{column.key}", self.pairs(target, Document.id).join(
                    Document, column == model.id
                ).filter(Document.id.in_(ids), Document.project_id == model.project_id).statement
            missions = self.load("mission", {row.source_mission_id for row in parents if row.source_mission_id})
            reports = self.load("report", {row.source_report_id for row in parents if row.source_report_id})
            readable_missions = self.query("mission").with_entities(Mission.id).statement
            predicates = [(row, document_evidence_condition(row, missions.get(row.source_mission_id), reports.get(row.source_report_id), readable_missions)) for row in parents]
            yield "evidence", "evidence", "document_evidence_filter", self.evidence_pairs(predicates)
        elif kind == "report":
            yield "source_documents", "document", "documents.source_report_id", self.pairs("document", Document.source_report_id).join(
                Report, Report.id == Document.source_report_id
            ).filter(Report.id.in_(ids), Report.project_id == Document.project_id).statement
            yield "collections", "collection", "report_sources.collection", self.pairs("collection", ReportSource.report_id).join(
                ReportSource, and_(ReportSource.source_id == Collection.id, ReportSource.source_type == "collection")
            ).filter(ReportSource.report_id.in_(ids)).statement
            source = aliased(Report)
            yield "parent_report", "report", "reports.parent_id", self.pairs("report", source.id).join(
                source, source.parent_id == Report.id
            ).filter(source.id.in_(ids), source.project_id == Report.project_id).statement
            readable_missions = self.query("mission").with_entities(Mission.id).statement
            yield "evidence", "evidence", "report_evidence_filter", self.evidence_pairs([(row, report_evidence_condition(row, readable_missions)) for row in parents])
        elif kind == "evidence":
            yield "mission", "mission", "ledger_entries.mission_id", self.pairs("mission", LedgerEntry.id).join(
                LedgerEntry, LedgerEntry.mission_id == Mission.id
            ).filter(LedgerEntry.id.in_(ids), LedgerEntry.project_id == Mission.project_id).statement
        elif kind == "collection":
            members = union(
                select(CollectionDocument.collection_id.label("from_id"), CollectionDocument.document_id.label("target_id")).where(CollectionDocument.collection_id.in_(ids)),
                select(CollectionItem.collection_id, DocumentChunk.document_id).join(DocumentChunk, CollectionItem.chunk_id == DocumentChunk.id).where(CollectionItem.collection_id.in_(ids)),
            ).subquery()
            yield "documents", "document", "collection_documents|collection_items", self.pairs("document", members.c.from_id).join(
                members, members.c.target_id == Document.id
            ).join(Collection, Collection.id == members.c.from_id).join(Project, Project.id == Document.project_id).filter(
                or_(Collection.workspace_id.is_(None), Collection.workspace_id == Project.workspace_id)
            ).statement

    def evidence_pairs(self, predicates: list[tuple[Any, Any]]):
        # Citation URL sets differ per parent. Batch their shared REST predicates
        # into one statement; no per-document source or authorization lookups.
        statements = [self.pairs("evidence", literal(row.id, type_=GUID())).filter(
            LedgerEntry.project_id == row.project_id, predicate
        ).statement for row, predicate in predicates]
        return union_all(*statements) if len(statements) > 1 else statements[0]


class SQLAlchemyGraphNeighborhoodRepository:
    def neighborhood(
        self, db: Session, user: AuthenticatedUser, *, root_type: NavigationEntityType,
        root_id: UUID, depth: int, per_relation_limit: int, max_nodes: int,
    ) -> GraphNeighborhoodResponse:
        read = _Read(db, user)
        root_row = read.root(root_type, root_id)
        root = read.node(root_type, root_row)
        nodes = {root.key: root}
        edges, groups = [], []
        frontier = {root_type: [root_row]}
        for _ in range(depth):
            candidates = []
            pending: dict[str, set[UUID]] = defaultdict(set)
            admitted = set(nodes)
            for kind in _MODELS:
                parents = frontier.get(kind, [])
                if not parents:
                    continue
                for relation, target, basis, statement in read.relations(kind, parents):
                    pairs = statement.subquery()
                    distinct_pairs = select(pairs.c.from_id, pairs.c.target_id, pairs.c.title).distinct().subquery()
                    ranked = select(
                        distinct_pairs.c.from_id, distinct_pairs.c.target_id,
                        func.count().over(partition_by=distinct_pairs.c.from_id).label("total"),
                        func.row_number().over(partition_by=distinct_pairs.c.from_id, order_by=(func.lower(distinct_pairs.c.title), distinct_pairs.c.target_id)).label("position"),
                    ).subquery()
                    rows = db.execute(select(ranked).where(ranked.c.position <= per_relation_limit).order_by(ranked.c.from_id, ranked.c.position)).all()
                    totals = {row.from_id: row.total for row in rows}
                    by_parent = {}
                    for parent in parents:
                        group = GraphGroup(from_key=f"{kind}:{parent.id}", relation=relation, target_type=target, total=totals.get(parent.id, 0), shown=0)
                        groups.append(group)
                        by_parent[parent.id] = group
                    for row in rows:
                        key = f"{target}:{row.target_id}"
                        if key not in admitted and len(admitted) >= max_nodes:
                            continue
                        admitted.add(key)
                        if key not in nodes:
                            pending[target].add(row.target_id)
                        candidates.append((by_parent[row.from_id], target, row.target_id, basis))
            next_frontier = {}
            for kind, ids in pending.items():
                loaded = read.load(kind, ids)
                next_frontier[kind] = list(loaded.values())
                for row in loaded.values():
                    node = read.node(kind, row)
                    nodes[node.key] = node
            for group, target, row_id, basis in candidates:
                key = f"{target}:{row_id}"
                if key in nodes:
                    edges.append(GraphEdge(from_key=group.from_key, to_key=key, relation=group.relation, basis=basis))
                    group.shown += 1
            frontier = next_frontier
            if not frontier:
                break
        return GraphNeighborhoodResponse(root=root, nodes=list(nodes.values()), edges=edges, groups=groups, truncated=any(g.shown < g.total for g in groups))
