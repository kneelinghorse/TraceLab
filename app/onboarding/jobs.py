"""Job registry helpers for onboarding ingestion workflow."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.ingestion_job import IngestionJob

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Lifecycle states for ingestion jobs."""

    PENDING = "PENDING"
    INGESTING = "INGESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def create_job(db: Session, *, document: Document) -> IngestionJob:
    """Persist a new ingestion job for the given document."""
    job = IngestionJob(
        project_id=document.project_id,
        document_id=document.id,
        status=JobStatus.PENDING.value,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def process_job(job_id: UUID) -> None:
    """Background task entrypoint that executes the ingestion workflow."""
    session = SessionLocal()
    try:
        job = (
            session.query(IngestionJob).filter(IngestionJob.id == job_id).one_or_none()
        )
        if not job:
            logger.warning("Ingestion job %s not found; aborting", job_id)
            return

        logger.info("Starting ingestion job %s", job_id)
        job.status = JobStatus.INGESTING.value
        job.started_at = datetime.utcnow()
        session.commit()

        document = (
            session.query(Document).filter(Document.id == job.document_id).first()
        )
        if not document:
            raise ValueError(f"Document {job.document_id} not found")

        from app.api.v1.documents import (
            get_ingestion_service,
        )  # late import to avoid cycle

        ingestion_service = get_ingestion_service()
        result: dict[str, object] = ingestion_service.process_document(
            db=session,
            document_id=document.id,
            file_path=document.file_path,
        )

        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        job.status_detail = f"status={result.get('status')}"
        session.commit()
        logger.info("Ingestion job %s completed", job_id)

    except Exception as exc:  # pragma: no cover - defensive logging branch
        session.rollback()
        try:
            job = (
                session.query(IngestionJob)
                .filter(IngestionJob.id == job_id)
                .one_or_none()
            )
            if job:
                job.status = JobStatus.FAILED.value
                job.status_detail = str(exc)
                job.completed_at = datetime.utcnow()
                session.commit()
        finally:
            logger.exception("Ingestion job %s failed", job_id)
    finally:
        session.close()
