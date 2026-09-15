"""Presentation envelopes; the Evidence object fields retain their original schema."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.evidence_ledger import LedgerEntryRead


class EvidenceLink(BaseModel):
    kind: Literal["mission", "report"]
    id: str
    title: str
    href: str
    relationship: str
    mission_result: bool = False


class EvidenceDetail(BaseModel):
    entry: LedgerEntryRead
    links: list[EvidenceLink]
