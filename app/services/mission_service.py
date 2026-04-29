"""Mission CRUD service with pagination, filtering, and status transitions.

Provides business logic for mission operations aligned with the DeepSearch-compatible
Mission model from B16.1.
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.mission_events import emit_mission_status_change
from app.models.mission import MISSION_STATUSES, Mission
from app.schemas.mission import MissionCreate, MissionUpdate
from app.schemas.pagination import PaginationMeta


class MissionServiceError(RuntimeError):
    """Base exception for mission service operations."""


class MissionNotFoundError(MissionServiceError):
    """Raised when a mission cannot be found."""


class MissionValidationError(MissionServiceError):
    """Raised when mission data fails validation."""


class MissionService:
    """Encapsulates CRUD operations, filtering, and pagination for missions."""

    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def list_missions(
        self,
        db: Session,
        *,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        status: str | None = None,
        project_id: UUID | None = None,
    ) -> tuple[list[Mission], PaginationMeta]:
        """Return paginated missions with optional filtering.

        Args:
            db: Database session
            page: Page number (1-indexed)
            page_size: Results per page
            status: Filter by mission status
            project_id: Filter by project

        Returns:
            Tuple of (missions list, pagination metadata)
        """
        clamped_page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)
        query = db.query(Mission).options(joinedload(Mission.project))

        # Apply filters
        if status:
            if status not in MISSION_STATUSES:
                raise MissionValidationError(
                    f"Invalid status '{status}'. Must be one of: {', '.join(sorted(MISSION_STATUSES))}"
                )
            query = query.filter(Mission.status == status)

        if project_id:
            query = query.filter(Mission.project_id == project_id)

        # Order by creation time (most recent first)
        query = query.order_by(Mission.created_at.desc())

        # Get total count for pagination
        total = query.count()

        # Apply pagination
        items = (
            query.offset((page - 1) * clamped_page_size).limit(clamped_page_size).all()
        )

        total_pages = math.ceil(total / clamped_page_size) if total else 0
        meta = PaginationMeta(
            page=page,
            page_size=clamped_page_size,
            total=total,
            pages=total_pages,
        )
        return items, meta

    def get_mission(self, db: Session, mission_id: UUID) -> Mission:
        """Get a single mission by its UUID.

        Args:
            db: Database session
            mission_id: The mission's UUID (not mission_id string)

        Returns:
            The Mission instance

        Raises:
            MissionNotFoundError: If mission doesn't exist
        """
        mission = (
            db.query(Mission)
            .options(joinedload(Mission.project))
            .filter(Mission.id == mission_id)
            .first()
        )
        if not mission:
            raise MissionNotFoundError(f"Mission {mission_id} not found")
        return mission

    def get_mission_by_mission_id(self, db: Session, mission_id_str: str) -> Mission:
        """Get a mission by its human-readable mission_id (e.g., 'B16.1').

        Args:
            db: Database session
            mission_id_str: The human-readable mission identifier

        Returns:
            The Mission instance

        Raises:
            MissionNotFoundError: If mission doesn't exist
        """
        mission = db.query(Mission).filter(Mission.mission_id == mission_id_str).first()
        if not mission:
            raise MissionNotFoundError(
                f"Mission with mission_id '{mission_id_str}' not found"
            )
        return mission

    def create_mission(self, db: Session, data: MissionCreate) -> Mission:
        """Create a new mission.

        Args:
            db: Database session
            data: Mission creation payload

        Returns:
            The created Mission instance
        """
        # Map schema fields to model fields
        mission = Mission(
            project_id=data.project_id,
            mission_id=data.mission_id,
            title=data.title,
            objective=data.objective,
            success_criteria=data.success_criteria,
            context=data.context or {},
            deliverables=data.deliverables or [],
            research_phases=data.research_phases or {},
            tags=data.tags or [],
            mission_metadata=data.metadata
            or {},  # Schema uses 'metadata', model uses 'mission_metadata'
            status=data.status or "draft",
            created_by=data.created_by,
            # Authoring fields (T40.1/T40.2) — nullable; pass through as-is.
            background=data.background,
            focus=data.focus,
            references=data.references,
            required_entities=data.required_entities,
            excluded_entities=data.excluded_entities,
            expected_output_schema=data.expected_output_schema,
            coverage_thresholds=data.coverage_thresholds,
            validation_thresholds=data.validation_thresholds,
            deliverable_format=data.deliverable_format,
            max_loops=data.max_loops,
            min_loops=data.min_loops,
            constraints=data.constraints,
        )

        # Set queued_at if status is queued
        if mission.status == "queued":
            mission.queued_at = datetime.utcnow()
        elif mission.status == "in_progress":
            mission.queued_at = datetime.utcnow()
            mission.started_at = datetime.utcnow()

        db.add(mission)
        db.commit()
        db.refresh(mission)
        return mission

    def update_mission(
        self, db: Session, mission_id: UUID, data: MissionUpdate
    ) -> Mission:
        """Update an existing mission.

        Args:
            db: Database session
            mission_id: The mission's UUID
            data: Fields to update

        Returns:
            The updated Mission instance

        Raises:
            MissionNotFoundError: If mission doesn't exist
        """
        mission = self.get_mission(db, mission_id)

        # Get update data, excluding unset fields
        update_data = data.model_dump(exclude_unset=True)

        # Handle special field mappings
        if "metadata" in update_data:
            update_data["mission_metadata"] = update_data.pop("metadata")

        # Handle status transitions with timestamp updates
        if "status" in update_data:
            new_status = update_data["status"]
            if new_status not in MISSION_STATUSES:
                raise MissionValidationError(
                    f"Invalid status '{new_status}'. Must be one of: {', '.join(sorted(MISSION_STATUSES))}"
                )

            # Update timestamps based on status transitions
            now = datetime.utcnow()
            if new_status == "queued" and mission.queued_at is None:
                mission.queued_at = now
            elif new_status == "in_progress":
                if mission.queued_at is None:
                    mission.queued_at = now
                if mission.started_at is None:
                    mission.started_at = now
            elif new_status in ("completed", "blocked", "cancelled"):
                if mission.started_at is None:
                    mission.started_at = now
                if new_status == "completed" and mission.completed_at is None:
                    mission.completed_at = now

        previous_status = mission.status

        # Apply updates
        for key, value in update_data.items():
            if hasattr(mission, key):
                # Convert UUID lists to strings for JSON columns
                if key == "result_document_ids" and value is not None:
                    value = [str(v) for v in value]
                setattr(mission, key, value)

        db.commit()
        db.refresh(mission)

        # Emit event if status changed
        if "status" in update_data and mission.status != previous_status:
            emit_mission_status_change(
                mission_id=mission.mission_id or str(mission.id),
                title=mission.title or "",
                new_status=mission.status,
                previous_status=previous_status,
            )

        return mission

    def delete_mission(self, db: Session, mission_id: UUID) -> None:
        """Delete a mission.

        Args:
            db: Database session
            mission_id: The mission's UUID

        Raises:
            MissionNotFoundError: If mission doesn't exist
        """
        mission = self.get_mission(db, mission_id)
        db.delete(mission)
        db.commit()

    def transition_status(
        self,
        db: Session,
        mission_id: UUID,
        new_status: str,
        error_message: str | None = None,
    ) -> Mission:
        """Transition a mission to a new status with proper timestamp handling.

        Args:
            db: Database session
            mission_id: The mission's UUID
            new_status: Target status
            error_message: Optional error message (for blocked status)

        Returns:
            The updated Mission instance
        """
        update_data = MissionUpdate(status=new_status)
        if error_message and new_status == "blocked":
            update_data.error_message = error_message
        return self.update_mission(db, mission_id, update_data)
