"""Schemas for RAG query requests and responses."""
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievalQuery, RetrievedChunk


class RagQuery(RetrievalQuery):
    """Client payload for full RAG query execution."""
    max_tokens: int = Field(
        default=350,
        ge=64,
        le=1024,
        description="Maximum number of tokens to generate in the answer.",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for answer generation.",
    )


class RagCitation(BaseModel):
    """Structured citation extracted from the generated answer."""
    document_id: Optional[str]
    chunk_id: Optional[str]
    chunk_index: Optional[int]
    source_type: Optional[str] = None
    score: Optional[float] = None
    snippet: Optional[str] = None


class CompressionMetrics(BaseModel):
    """Observability metrics for context compression."""
    original_chunks: int
    filtered_chunks: int
    original_tokens: int
    filtered_tokens: int
    reduction_ratio: float
    threshold: float
    compression_ms: float


class CacheInfo(BaseModel):
    """Metadata describing semantic cache evaluation."""
    hit: bool
    score: Optional[float] = None
    age_seconds: Optional[float] = None
    ttl_seconds: Optional[float] = None


class RagResponse(BaseModel):
    """Response containing the generated answer alongside supporting metadata."""
    answer: str
    citations: List[RagCitation]
    sources: List[RetrievedChunk]
    latency_ms: float
    compression: CompressionMetrics
    cache: CacheInfo
