"""Corpus Q&A: a question about a project's documents in, a cited answer out (QA-1).

This is the only Q&A path (decision #543): the Librarian's answer mode calls it,
and MCP-6's ``tracelab_search`` ask will too. It applies the caller's project
scope exactly as POST /search does, runs the RAG pipeline with the relevance
floor as a refusal rule, and splits the answer into passages whose citations
all resolve to chunks the model read, in documents that still exist. A question
the project cannot support is refused, never guessed. It records nothing: each
surface meters its own calls from the usage it returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.authorization import accessible_project_ids
from app.core.security import AuthenticatedUser
from app.models.document import Document
from app.services.rag_service import (
    NO_EVIDENCE_ANSWER,
    RagService,
    build_empty_scope_result,
    get_rag_service,
)

# RagQuery's default, which is what the Search page asks for.
ANSWER_TOP_K = 5

_PASSAGE_BREAK = re.compile(r"\n[ \t]*\n")
# The pipeline's label, "[Document: d, Chunk: 1]", with the spaces before it, so
# "fact [Document: d, Chunk: 1]." reads "fact.". It also reads a label naming several
# chunks, "Chunks: 9–10" or "Chunk: 10, 12", which the pipeline's CITATION_PATTERN
# does not: QA-1's production acceptance found one left in an answer as raw text.
_LABEL = re.compile(
    r"[ \t]*\[Document:\s*(?P<document>[^\],]+),\s*Chunks?:\s*(?P<chunks>[^\]]+)\]",
    re.IGNORECASE,
)
_RANGE = re.compile(r"(\d+)\s*[-‐-―]\s*(\d+)")
_LIST_SEPARATOR = re.compile(r",|;|&|\band\b", re.IGNORECASE)
# Retrieval returns five chunks, so a longer range names chunks it cannot cite.
_MAX_RANGE = 20


def _chunk_labels(spec: str) -> list[str]:
    """The chunks one label names: "9", a range "9–10" or a list "9, 10"."""
    labels: list[str] = []
    for part in _LIST_SEPARATOR.split(spec):
        part = part.strip()
        span = _RANGE.fullmatch(part)
        if span and 0 <= int(span[2]) - int(span[1]) <= _MAX_RANGE:
            labels.extend(str(index) for index in range(int(span[1]), int(span[2]) + 1))
        elif part:
            labels.append(part)
    return labels


@dataclass(frozen=True)
class AnswerPassage:
    """One paragraph of an answer; ``citations`` are chunk ids, empty when uncited."""

    text: str
    citations: list[str]


@dataclass(frozen=True)
class AnswerCitation:
    chunk_id: str
    document_id: str
    document_name: str
    chunk_index: int | None
    snippet: str | None
    href: str


@dataclass
class CorpusAnswer:
    passages: list[AnswerPassage]
    citations: list[AnswerCitation]
    no_evidence: bool
    # Chunk ids the model read: a rendered citation must be one of them.
    source_chunk_ids: list[str] = field(default_factory=list)
    model: str | None = None
    # (model, usage) for each paid model call; empty when the answer came from a cache.
    usage: list[tuple[str, dict[str, int]]] = field(default_factory=list)

    @property
    def answer(self) -> str:
        return "\n\n".join(passage.text for passage in self.passages)


def chunk_href(document_id: str, chunk_id: str, chunk_index: int | None) -> str:
    """The page that opens a cited chunk: its document, on the chunk, expanded."""
    params: dict[str, Any] = {"chunk": chunk_id}
    if chunk_index is not None:
        params["index"] = chunk_index
    return f"/documents/{document_id}?{urlencode(params)}"


def answer_question(
    db: Session,
    user: AuthenticatedUser,
    project_id: UUID,
    question: str,
    *,
    max_tokens: int | None = None,
) -> CorpusAnswer:
    """Answer ``question`` from one project's documents, or refuse.

    ``max_tokens`` is the answer budget; None uses settings.rag_default_max_tokens.
    """
    question = question.strip()
    if not question:
        raise ValueError("A question is required.")
    allowed = accessible_project_ids(user, db)
    if allowed == [] or (allowed is not None and project_id not in set(allowed)):
        # The search route's empty-scope rule: no pipeline call, nothing asserted.
        return _refusal(build_empty_scope_result(search_mode="semantic")["answer"])

    query: dict[str, Any] = {
        "query": question,
        "top_k": ANSWER_TOP_K,
        "project_id": str(project_id),
        "max_tokens": max_tokens,
        "refuse_unsupported": True,
    }
    if allowed is not None:
        query["allowed_project_ids"] = allowed
    result = get_rag_service().run_query(**query)
    model = (result.get("routing") or {}).get("selected_model")
    if result.get("no_evidence"):
        return _refusal(result.get("answer") or NO_EVIDENCE_ANSWER, model=model)

    sources = list(result.get("sources") or [])
    live_names = _live_document_names(db, sources)
    passages = _passages(result.get("answer") or "", sources, live_names)
    usage = _paid_usage(result)
    if not any(passage.citations for passage in passages):
        # The model read relevant chunks and cited none of them: its answer rests on
        # nothing the user can open, so it is not shown.
        return _refusal(NO_EVIDENCE_ANSWER, model=model, usage=usage)

    by_id = {str(source.get("chunk_id")): source for source in sources}
    citations: list[AnswerCitation] = []
    for chunk_id in dict.fromkeys(cited for passage in passages for cited in passage.citations):
        source = by_id[chunk_id]
        document_id = str(_document_uuid(source))
        content = source.get("content") or ""
        citations.append(
            AnswerCitation(
                chunk_id=chunk_id,
                document_id=document_id,
                document_name=live_names[document_id],
                chunk_index=source.get("chunk_index"),
                snippet=content[:280] or None,
                href=chunk_href(document_id, chunk_id, source.get("chunk_index")),
            )
        )
    return CorpusAnswer(
        passages=passages,
        citations=citations,
        no_evidence=False,
        source_chunk_ids=[str(source.get("chunk_id")) for source in sources if source.get("chunk_id")],
        model=model,
        usage=usage,
    )


def _refusal(
    text: str,
    *,
    model: str | None = None,
    usage: list[tuple[str, dict[str, int]]] | None = None,
) -> CorpusAnswer:
    return CorpusAnswer(
        passages=[AnswerPassage(text=text, citations=[])],
        citations=[],
        no_evidence=True,
        model=model,
        usage=usage or [],
    )


def _passages(
    answer: str,
    sources: list[dict[str, Any]],
    live_names: dict[str, str],
) -> list[AnswerPassage]:
    """Split the answer on blank lines and resolve each paragraph's labels.

    A label resolves with the pipeline's own matcher, against the chunks the model
    read, and only when the chunk's document still exists; any other label is
    dropped. Every label is removed from the text, since the citations list carries
    them. A paragraph that was only labels lends them to the paragraph before it.
    """
    passages: list[AnswerPassage] = []
    for paragraph in _PASSAGE_BREAK.split(answer.strip()):
        cited: list[str] = []
        for match in _LABEL.finditer(paragraph):
            document = match.group("document").strip()
            for label in _chunk_labels(match.group("chunks")):
                chunk = RagService.match_chunk(document, label, sources)
                if chunk is None or not chunk.get("chunk_id") or str(_document_uuid(chunk)) not in live_names:
                    continue
                chunk_id = str(chunk["chunk_id"])
                if chunk_id not in cited:
                    cited.append(chunk_id)
        text = "\n".join(line.rstrip() for line in _LABEL.sub("", paragraph).splitlines()).strip()
        if text:
            passages.append(AnswerPassage(text=text, citations=cited))
        elif cited and passages:
            previous = passages[-1]
            merged = list(dict.fromkeys([*previous.citations, *cited]))
            passages[-1] = AnswerPassage(text=previous.text, citations=merged)
    return passages


def _document_uuid(chunk: dict[str, Any]) -> UUID | None:
    try:
        return UUID(str(chunk.get("document_id")))
    except ValueError:
        return None


def _live_document_names(db: Session, sources: list[dict[str, Any]]) -> dict[str, str]:
    """Name by document id, for the sources' documents that are not deleted."""
    ids = {document_id for source in sources if (document_id := _document_uuid(source)) is not None}
    if not ids:
        return {}
    rows = db.query(Document.id, Document.name).filter(Document.id.in_(ids), Document.deleted_at.is_(None)).all()
    return {str(row.id): row.name for row in rows}


def _paid_usage(result: dict[str, Any]) -> list[tuple[str, dict[str, int]]]:
    if (result.get("cache") or {}).get("hit"):
        return []
    return [
        (str(attempt.get("model")), attempt["usage"])
        for attempt in (result.get("routing") or {}).get("attempts") or []
        if attempt.get("usage")
    ]
