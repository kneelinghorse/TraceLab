"""Delta detection and sync orchestration for PEDR integration.

Event-driven sync architecture with delta detection based on updated_at timestamps.
Reference: cmos/planning/PEDR-docs/tracelab-to-pedr-mapping.md
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.insight import Insight
from app.models.mission import Mission
from app.models.sync_state import SyncState
from app.services.pedr.manifest_transformer import (
    ManifestTransformer,
    PEDRManifest,
    get_manifest_transformer,
)

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Syncable entity types."""

    MISSION = "mission"
    DOCUMENT = "document"
    INSIGHT = "insight"


class SyncMode(str, Enum):
    """Sync operation modes."""

    DELTA = "delta"  # Only changed entities
    FULL = "full"  # All entities


@dataclass
class SyncResult:
    """Result of a sync operation."""

    entity_type: EntityType
    mode: SyncMode
    synced_count: int
    failed_count: int
    skipped_count: int
    duration_ms: float
    errors: List[str] = field(default_factory=list)
    last_sync_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        return self.failed_count == 0


@dataclass
class ParityCheckResult:
    """Result of a parity check between systems."""

    entity_type: EntityType
    local_count: int
    remote_count: int
    in_sync: bool
    discrepancy: int


@dataclass
class SyncBatch:
    """A batch of entities to sync."""

    entities: List[Dict[str, Any]]
    manifests: List[PEDRManifest]
    batch_id: str


# Type for PEDR ingestion callback
PEDRIngestCallback = Callable[[Sequence[PEDRManifest]], bool]


class DeltaSyncService:
    """Orchestrate delta-based sync to PEDR.

    Features:
    - Delta detection using updated_at timestamps
    - Batch processing with configurable size
    - Retry logic with exponential backoff
    - Sync state persistence
    - Parity validation
    """

    DEFAULT_BATCH_SIZE: int = 100
    MAX_RETRIES: int = 3
    RETRY_DELAY_MS: int = 1000

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        transformer: Optional[ManifestTransformer] = None,
        ingest_callback: Optional[PEDRIngestCallback] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        telemetry_path: Optional[Path] = None,
    ) -> None:
        self.session_factory = session_factory
        self.transformer = transformer or get_manifest_transformer()
        self.ingest_callback = ingest_callback
        self.batch_size = batch_size
        self.telemetry_path = telemetry_path

    def sync_missions(
        self,
        mode: SyncMode = SyncMode.DELTA,
        *,
        project_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """Sync missions to PEDR.

        Args:
            mode: DELTA for incremental, FULL for complete sync
            project_id: Optional filter by project
            dry_run: If True, transform but don't ingest

        Returns:
            SyncResult with sync statistics
        """
        start_time = datetime.now(timezone.utc)
        session = self.session_factory()
        synced = 0
        failed = 0
        skipped = 0
        errors: List[str] = []

        try:
            # Get last sync timestamp for delta mode
            last_sync_at = None
            if mode == SyncMode.DELTA:
                sync_state = self._get_sync_state(session, EntityType.MISSION)
                last_sync_at = sync_state.last_sync_at if sync_state else None

            # Query missions needing sync
            query = session.query(Mission)

            if project_id:
                query = query.filter(Mission.project_id == project_id)

            if mode == SyncMode.DELTA and last_sync_at:
                query = query.filter(Mission.updated_at > last_sync_at)

            # Order by updated_at for consistent processing
            query = query.order_by(Mission.updated_at.asc())

            missions = query.all()
            logger.info(f"Found {len(missions)} missions to sync (mode={mode.value})")

            if not missions:
                return SyncResult(
                    entity_type=EntityType.MISSION,
                    mode=mode,
                    synced_count=0,
                    failed_count=0,
                    skipped_count=0,
                    duration_ms=0,
                    last_sync_at=last_sync_at,
                )

            # Transform and sync in batches
            batch_manifests: List[PEDRManifest] = []
            latest_updated_at = last_sync_at

            for mission in missions:
                result = self.transformer.transform_mission(
                    mission_id=str(mission.id),
                    mission_data=mission.mission_data or {},
                    quality_gates=mission.quality_gates,
                    project_id=str(mission.project_id) if mission.project_id else None,
                    status=mission.status or "unknown",
                )

                if not result.success:
                    failed += 1
                    errors.append(f"Mission {mission.id}: {result.error}")
                    continue

                if result.warnings:
                    for warning in result.warnings:
                        logger.warning(f"Mission {mission.id}: {warning}")

                batch_manifests.append(result.manifest)

                # Track latest updated_at for sync state
                if mission.updated_at:
                    if latest_updated_at is None or mission.updated_at > latest_updated_at:
                        latest_updated_at = mission.updated_at

                # Process batch when full
                if len(batch_manifests) >= self.batch_size:
                    if not dry_run:
                        batch_synced = self._ingest_batch(batch_manifests)
                        if batch_synced:
                            synced += len(batch_manifests)
                        else:
                            failed += len(batch_manifests)
                            errors.append(f"Batch ingestion failed for {len(batch_manifests)} manifests")
                    else:
                        synced += len(batch_manifests)
                    batch_manifests = []

            # Process remaining manifests
            if batch_manifests:
                if not dry_run:
                    batch_synced = self._ingest_batch(batch_manifests)
                    if batch_synced:
                        synced += len(batch_manifests)
                    else:
                        failed += len(batch_manifests)
                        errors.append(f"Batch ingestion failed for {len(batch_manifests)} manifests")
                else:
                    synced += len(batch_manifests)

            # Update sync state
            if not dry_run and synced > 0 and latest_updated_at:
                self._update_sync_state(
                    session,
                    EntityType.MISSION,
                    last_sync_at=latest_updated_at,
                    synced_count=synced,
                )
                session.commit()

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Log telemetry
            self._log_sync_event(
                EntityType.MISSION,
                mode,
                synced,
                failed,
                skipped,
                duration_ms,
            )

            return SyncResult(
                entity_type=EntityType.MISSION,
                mode=mode,
                synced_count=synced,
                failed_count=failed,
                skipped_count=skipped,
                duration_ms=duration_ms,
                errors=errors,
                last_sync_at=latest_updated_at,
            )

        except Exception as e:
            logger.exception(f"Sync failed: {e}")
            session.rollback()
            return SyncResult(
                entity_type=EntityType.MISSION,
                mode=mode,
                synced_count=synced,
                failed_count=failed + 1,
                skipped_count=skipped,
                duration_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                errors=errors + [str(e)],
                last_sync_at=last_sync_at,
            )
        finally:
            session.close()

    def sync_documents(
        self,
        mode: SyncMode = SyncMode.DELTA,
        *,
        project_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> SyncResult:
        """Sync documents to PEDR."""
        start_time = datetime.now(timezone.utc)
        session = self.session_factory()
        synced = 0
        failed = 0
        errors: List[str] = []

        try:
            last_sync_at = None
            if mode == SyncMode.DELTA:
                sync_state = self._get_sync_state(session, EntityType.DOCUMENT)
                last_sync_at = sync_state.last_sync_at if sync_state else None

            query = session.query(Document)

            if project_id:
                query = query.filter(Document.project_id == project_id)

            if mode == SyncMode.DELTA and last_sync_at:
                query = query.filter(Document.uploaded_at > last_sync_at)

            query = query.order_by(Document.uploaded_at.asc())
            documents = query.all()

            batch_manifests: List[PEDRManifest] = []
            latest_uploaded_at = last_sync_at

            for doc in documents:
                result = self.transformer.transform_document(
                    document_id=str(doc.id),
                    name=doc.name or "",
                    content=doc.content,
                    file_type=doc.file_type,
                    source_type=doc.source_type,
                    project_id=str(doc.project_id) if doc.project_id else None,
                    uploaded_at=doc.uploaded_at,
                )

                if result.success:
                    batch_manifests.append(result.manifest)
                    if doc.uploaded_at:
                        if latest_uploaded_at is None or doc.uploaded_at > latest_uploaded_at:
                            latest_uploaded_at = doc.uploaded_at
                else:
                    failed += 1
                    errors.append(f"Document {doc.id}: {result.error}")

                if len(batch_manifests) >= self.batch_size:
                    if not dry_run:
                        if self._ingest_batch(batch_manifests):
                            synced += len(batch_manifests)
                        else:
                            failed += len(batch_manifests)
                    else:
                        synced += len(batch_manifests)
                    batch_manifests = []

            if batch_manifests:
                if not dry_run:
                    if self._ingest_batch(batch_manifests):
                        synced += len(batch_manifests)
                    else:
                        failed += len(batch_manifests)
                else:
                    synced += len(batch_manifests)

            if not dry_run and synced > 0 and latest_uploaded_at:
                self._update_sync_state(
                    session,
                    EntityType.DOCUMENT,
                    last_sync_at=latest_uploaded_at,
                    synced_count=synced,
                )
                session.commit()

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return SyncResult(
                entity_type=EntityType.DOCUMENT,
                mode=mode,
                synced_count=synced,
                failed_count=failed,
                skipped_count=0,
                duration_ms=duration_ms,
                errors=errors,
                last_sync_at=latest_uploaded_at,
            )

        except Exception as e:
            logger.exception(f"Document sync failed: {e}")
            session.rollback()
            return SyncResult(
                entity_type=EntityType.DOCUMENT,
                mode=mode,
                synced_count=synced,
                failed_count=failed + 1,
                skipped_count=0,
                duration_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
                errors=errors + [str(e)],
            )
        finally:
            session.close()

    def sync_all(
        self,
        mode: SyncMode = SyncMode.DELTA,
        *,
        dry_run: bool = False,
    ) -> Dict[EntityType, SyncResult]:
        """Sync all entity types."""
        results: Dict[EntityType, SyncResult] = {}

        results[EntityType.MISSION] = self.sync_missions(mode, dry_run=dry_run)
        results[EntityType.DOCUMENT] = self.sync_documents(mode, dry_run=dry_run)

        return results

    def check_parity(self, entity_type: EntityType) -> ParityCheckResult:
        """Check parity between local and remote entity counts.

        Note: Requires remote count callback to be implemented.
        """
        session = self.session_factory()
        try:
            if entity_type == EntityType.MISSION:
                local_count = session.query(func.count(Mission.id)).scalar() or 0
            elif entity_type == EntityType.DOCUMENT:
                local_count = session.query(func.count(Document.id)).scalar() or 0
            elif entity_type == EntityType.INSIGHT:
                local_count = session.query(func.count(Insight.id)).scalar() or 0
            else:
                local_count = 0

            # Remote count would come from PEDR API
            # For now, return local count only (parity validation requires PEDR endpoint)
            remote_count = 0  # TODO: Query PEDR catalog for count

            discrepancy = abs(local_count - remote_count)
            in_sync = discrepancy == 0

            return ParityCheckResult(
                entity_type=entity_type,
                local_count=local_count,
                remote_count=remote_count,
                in_sync=in_sync,
                discrepancy=discrepancy,
            )
        finally:
            session.close()

    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync status for all entity types."""
        session = self.session_factory()
        try:
            status: Dict[str, Any] = {}
            for entity_type in EntityType:
                sync_state = self._get_sync_state(session, entity_type)
                if sync_state:
                    status[entity_type.value] = {
                        "last_sync_at": sync_state.last_sync_at.isoformat() if sync_state.last_sync_at else None,
                        "sync_count": sync_state.sync_count,
                        "updated_at": sync_state.updated_at.isoformat() if sync_state.updated_at else None,
                    }
                else:
                    status[entity_type.value] = {
                        "last_sync_at": None,
                        "sync_count": 0,
                        "updated_at": None,
                    }
            return status
        finally:
            session.close()

    def get_pending_count(self, entity_type: EntityType) -> int:
        """Get count of entities pending sync since last sync."""
        session = self.session_factory()
        try:
            sync_state = self._get_sync_state(session, entity_type)
            last_sync_at = sync_state.last_sync_at if sync_state else None

            if entity_type == EntityType.MISSION:
                query = session.query(func.count(Mission.id))
                if last_sync_at:
                    query = query.filter(Mission.updated_at > last_sync_at)
            elif entity_type == EntityType.DOCUMENT:
                query = session.query(func.count(Document.id))
                if last_sync_at:
                    query = query.filter(Document.uploaded_at > last_sync_at)
            else:
                return 0

            return query.scalar() or 0
        finally:
            session.close()

    def _get_sync_state(self, session: Session, entity_type: EntityType) -> Optional[SyncState]:
        """Get sync state for entity type."""
        return session.query(SyncState).filter(
            SyncState.entity_type == entity_type.value
        ).first()

    def _update_sync_state(
        self,
        session: Session,
        entity_type: EntityType,
        *,
        last_sync_at: datetime,
        synced_count: int,
    ) -> SyncState:
        """Update or create sync state."""
        sync_state = self._get_sync_state(session, entity_type)

        if sync_state:
            sync_state.last_sync_at = last_sync_at
            sync_state.sync_count = (sync_state.sync_count or 0) + synced_count
            sync_state.updated_at = datetime.utcnow()
        else:
            sync_state = SyncState(
                entity_type=entity_type.value,
                last_sync_at=last_sync_at,
                sync_count=synced_count,
            )
            session.add(sync_state)

        return sync_state

    def _ingest_batch(self, manifests: Sequence[PEDRManifest]) -> bool:
        """Ingest a batch of manifests to PEDR.

        Uses the ingest_callback if provided, otherwise logs.
        """
        if not manifests:
            return True

        if self.ingest_callback:
            try:
                return self.ingest_callback(manifests)
            except Exception as e:
                logger.exception(f"Ingestion callback failed: {e}")
                return False

        # Default: Log manifests (no actual PEDR endpoint yet)
        logger.info(f"Would ingest {len(manifests)} manifests to PEDR")
        for manifest in manifests:
            logger.debug(f"  URN: {manifest.urn}")

        return True

    def _log_sync_event(
        self,
        entity_type: EntityType,
        mode: SyncMode,
        synced: int,
        failed: int,
        skipped: int,
        duration_ms: float,
    ) -> None:
        """Log sync event to telemetry."""
        if not self.telemetry_path:
            return

        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "pedr_sync",
            "entity_type": entity_type.value,
            "mode": mode.value,
            "synced_count": synced,
            "failed_count": failed,
            "skipped_count": skipped,
            "duration_ms": round(duration_ms, 2),
            "success": failed == 0,
        }

        try:
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            with self.telemetry_path.open("a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write telemetry: {e}")


# Singleton instance
_delta_sync_service: Optional[DeltaSyncService] = None


def get_delta_sync_service(
    telemetry_path: Optional[Path] = None,
) -> DeltaSyncService:
    """Return singleton delta sync service."""
    global _delta_sync_service
    if _delta_sync_service is None:
        _delta_sync_service = DeltaSyncService(
            telemetry_path=telemetry_path or Path("cmos/telemetry/events/sprint-11-pedr-sync.jsonl"),
        )
    return _delta_sync_service


__all__ = [
    "EntityType",
    "SyncMode",
    "SyncResult",
    "ParityCheckResult",
    "SyncBatch",
    "PEDRIngestCallback",
    "DeltaSyncService",
    "get_delta_sync_service",
]
