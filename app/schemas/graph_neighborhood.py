"""Bounded, canonical object relationships for the graph and its list equivalent."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.navigation_search import NavigationEntityType


class GraphNode(BaseModel):
    key: str
    type: NavigationEntityType
    id: UUID
    title: str
    href: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_key: str = Field(alias="from")
    to_key: str = Field(alias="to")
    relation: str
    basis: str


class GraphGroup(BaseModel):
    from_key: str
    relation: str
    target_type: NavigationEntityType
    total: int = Field(ge=0)
    shown: int = Field(ge=0)


class GraphNeighborhoodResponse(BaseModel):
    root: GraphNode
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    groups: list[GraphGroup]
    truncated: bool
