"""Synthesis cache service for content-addressable caching of LLM synthesis results."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.synthesis_cache import SynthesisCache

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class SynthesisCacheService:
    """Content-addressable cache for synthesis results.

    Uses SHA-256 hash of (sorted chunk_ids + normalized prompt + format) as cache key.
    Cache hits return instantly, saving LLM API costs.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self.session_factory = session_factory

    @staticmethod
    def compute_hash(
        *,
        chunk_ids: List[UUID],
        prompt: Optional[str],
        output_format: str,
    ) -> str:
        """Compute deterministic hash for cache lookup.

        Args:
            chunk_ids: List of chunk UUIDs (will be sorted for consistency)
            prompt: Custom prompt (will be stripped and lowercased)
            output_format: Output format (will be lowercased)

        Returns:
            SHA-256 hex digest of the normalized input
        """
        # Sort chunk_ids for deterministic ordering
        sorted_ids = sorted(str(cid) for cid in chunk_ids)

        # Normalize prompt: strip whitespace and lowercase
        normalized_prompt = (prompt or "").strip().lower()

        # Normalize format
        normalized_format = (output_format or "markdown").strip().lower()

        # Build canonical JSON representation
        canonical = json.dumps({
            "chunk_ids": sorted_ids,
            "prompt": normalized_prompt,
            "format": normalized_format,
        }, sort_keys=True, separators=(",", ":"))

        # Compute SHA-256
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(
        self,
        *,
        chunk_ids: List[UUID],
        prompt: Optional[str],
        output_format: str,
    ) -> Optional[Dict[str, Any]]:
        """Look up cached synthesis result.

        If found, increments hit_count and updates last_hit_at.

        Args:
            chunk_ids: List of chunk UUIDs
            prompt: Custom prompt
            output_format: Output format

        Returns:
            Cached result dict with content, citations, tokens_used, etc. or None
        """
        input_hash = self.compute_hash(
            chunk_ids=chunk_ids,
            prompt=prompt,
            output_format=output_format,
        )

        session = self.session_factory()
        try:
            cached = (
                session.query(SynthesisCache)
                .filter(SynthesisCache.input_hash == input_hash)
                .with_for_update()  # Prevent race conditions
                .one_or_none()
            )

            if cached is None:
                return None

            # Update hit stats
            cached.hit_count = (cached.hit_count or 0) + 1
            cached.last_hit_at = datetime.now(timezone.utc)
            session.commit()

            logger.info(
                "Synthesis cache hit: hash=%s hit_count=%d",
                input_hash[:12],
                cached.hit_count,
            )

            return {
                "content": cached.content,
                "citations": cached.citations or [],
                "tokens_used": cached.tokens_used,
                "cache_hit": True,
                "cache_id": str(cached.id),
                "hit_count": cached.hit_count,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set(
        self,
        *,
        chunk_ids: List[UUID],
        prompt: Optional[str],
        output_format: str,
        content: str,
        citations: List[Dict[str, Any]],
        tokens_used: int,
        model_used: Optional[str] = None,
    ) -> str:
        """Store synthesis result in cache.

        Uses upsert pattern to handle concurrent requests safely.

        Args:
            chunk_ids: List of chunk UUIDs
            prompt: Custom prompt
            output_format: Output format
            content: Synthesis result content
            citations: List of citation dicts
            tokens_used: Token count from LLM
            model_used: Model name used for synthesis

        Returns:
            Cache entry ID
        """
        input_hash = self.compute_hash(
            chunk_ids=chunk_ids,
            prompt=prompt,
            output_format=output_format,
        )

        session = self.session_factory()
        try:
            # Check if already exists (race condition handling)
            existing = (
                session.query(SynthesisCache)
                .filter(SynthesisCache.input_hash == input_hash)
                .one_or_none()
            )

            if existing:
                # Already cached (likely by concurrent request)
                logger.debug("Cache entry already exists: hash=%s", input_hash[:12])
                return str(existing.id)

            # Create new cache entry
            cache_entry = SynthesisCache(
                input_hash=input_hash,
                content=content,
                citations=citations,
                model_used=model_used,
                tokens_used=tokens_used,
                hit_count=0,
            )
            session.add(cache_entry)
            session.commit()

            logger.info(
                "Synthesis cached: hash=%s tokens=%d",
                input_hash[:12],
                tokens_used,
            )

            return str(cache_entry.id)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_hit(
        self,
        *,
        cache_id: str,
    ) -> None:
        """Record a cache hit for an existing entry.

        Use this when you've already retrieved the cached data but want to
        track additional hits (e.g., from MCP tools that cache locally).

        Args:
            cache_id: Cache entry UUID
        """
        session = self.session_factory()
        try:
            cached = (
                session.query(SynthesisCache)
                .filter(SynthesisCache.id == cache_id)
                .with_for_update()
                .one_or_none()
            )

            if cached:
                cached.hit_count = (cached.hit_count or 0) + 1
                cached.last_hit_at = datetime.now(timezone.utc)
                session.commit()
                logger.debug("Recorded cache hit: id=%s count=%d", cache_id[:12], cached.hit_count)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring.

        Returns:
            Dict with total_entries, total_hits, total_tokens_saved, etc.
        """
        session = self.session_factory()
        try:
            # Aggregate stats
            result = session.query(
                func.count(SynthesisCache.id).label("total_entries"),
                func.sum(SynthesisCache.hit_count).label("total_hits"),
                func.sum(SynthesisCache.tokens_used).label("total_tokens_cached"),
                func.sum(SynthesisCache.hit_count * SynthesisCache.tokens_used).label("total_tokens_saved"),
                func.max(SynthesisCache.last_hit_at).label("last_hit_at"),
                func.min(SynthesisCache.created_at).label("oldest_entry"),
            ).one()

            # Get top hit entries
            top_entries = (
                session.query(SynthesisCache)
                .filter(SynthesisCache.hit_count > 0)
                .order_by(SynthesisCache.hit_count.desc())
                .limit(5)
                .all()
            )

            top_hits = [
                {
                    "cache_id": str(entry.id),
                    "hit_count": entry.hit_count,
                    "tokens_used": entry.tokens_used,
                    "tokens_saved": entry.hit_count * entry.tokens_used,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "last_hit_at": entry.last_hit_at.isoformat() if entry.last_hit_at else None,
                }
                for entry in top_entries
            ]

            return {
                "total_entries": result.total_entries or 0,
                "total_hits": int(result.total_hits or 0),
                "total_tokens_cached": int(result.total_tokens_cached or 0),
                "total_tokens_saved": int(result.total_tokens_saved or 0),
                "last_hit_at": result.last_hit_at.isoformat() if result.last_hit_at else None,
                "oldest_entry": result.oldest_entry.isoformat() if result.oldest_entry else None,
                "top_entries": top_hits,
            }
        finally:
            session.close()

    def invalidate(
        self,
        *,
        chunk_ids: Optional[List[UUID]] = None,
        cache_id: Optional[str] = None,
    ) -> int:
        """Invalidate cache entries.

        Args:
            chunk_ids: If provided, invalidate entries containing these chunks
                      (Note: requires scanning all entries since we hash chunk_ids)
            cache_id: If provided, invalidate specific entry

        Returns:
            Number of entries invalidated
        """
        if cache_id is None and chunk_ids is None:
            raise ValueError("Either cache_id or chunk_ids must be provided")

        session = self.session_factory()
        try:
            if cache_id:
                # Direct deletion by ID
                count = (
                    session.query(SynthesisCache)
                    .filter(SynthesisCache.id == cache_id)
                    .delete()
                )
                session.commit()
                return count

            # For chunk_ids, we'd need to scan all entries and check
            # This is expensive - in practice, use TTL-based expiration instead
            logger.warning(
                "Invalidation by chunk_ids not implemented - use cache_id or TTL"
            )
            return 0
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Singleton instance
_synthesis_cache_service: Optional[SynthesisCacheService] = None


def get_synthesis_cache_service() -> SynthesisCacheService:
    """Return the singleton synthesis cache service instance."""
    global _synthesis_cache_service
    if _synthesis_cache_service is None:
        _synthesis_cache_service = SynthesisCacheService()
    return _synthesis_cache_service


__all__ = ["SynthesisCacheService", "get_synthesis_cache_service"]
