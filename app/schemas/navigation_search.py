"""Bounded, caller-scoped names for the command palette."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

NavigationEntityType = Literal["project", "document", "mission", "report", "collection", "evidence"]


class NavigationItem(BaseModel):
    id: UUID
    title: str
    href: str


class NavigationGroup(BaseModel):
    entity_type: NavigationEntityType
    total: int
    page: int
    page_size: int
    items: list[NavigationItem]


class NavigationSearchResponse(BaseModel):
    query: str
    groups: list[NavigationGroup]
