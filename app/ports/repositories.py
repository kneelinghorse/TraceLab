# ABOUTME: Protocol interfaces for database repository operations.
# ABOUTME: Uses typing.Protocol for structural subtyping — existing classes conform automatically.

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session


class DocumentRepository(Protocol):
    """Read/write operations for Document entities."""

    def get_document(
        self,
        db: Session,
        document_id: UUID,
        include_deleted: bool = False,
    ) -> Any | None: ...

    def list_documents(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        project_id: UUID | None = None,
        processed: bool | None = None,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[Any], Any]: ...

    def soft_delete_document(
        self,
        db: Session,
        document_id: UUID,
        deleted_by: str | None = None,
    ) -> bool | None: ...

    def restore_document(
        self,
        db: Session,
        document_id: UUID,
    ) -> bool | None: ...


class ProjectRepository(Protocol):
    """Read/write operations for Project entities."""

    def get_project(
        self,
        db: Session,
        project_id: UUID,
        include_deleted: bool = False,
    ) -> Any | None: ...

    def list_projects(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[list[Any], Any]: ...

    def create_project(self, db: Session, data: Any) -> Any: ...

    def update_project(self, db: Session, project_id: UUID, data: Any) -> Any | None: ...

    def soft_delete_project(
        self,
        db: Session,
        project_id: UUID,
        deleted_by: str | None = None,
    ) -> bool | None: ...


class ChunkRepository(Protocol):
    """Read/write operations for DocumentChunk entities."""

    def get_chunks_for_document(
        self,
        db: Session,
        document_id: UUID,
    ) -> list[Any]: ...

    def create_chunks_batch(
        self,
        db: Session,
        chunks: list[dict[str, Any]],
    ) -> list[Any]: ...

    def delete_chunks_for_document(
        self,
        db: Session,
        document_id: UUID,
    ) -> int: ...


class MissionRepository(Protocol):
    """Read/write operations for Mission entities."""

    def get_mission(self, db: Session, mission_id: UUID) -> Any | None: ...

    def list_missions(
        self,
        db: Session,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        project_id: UUID | None = None,
    ) -> tuple[list[Any], Any]: ...

    def create_mission(self, db: Session, data: Any) -> Any: ...

    def update_mission(self, db: Session, mission_id: UUID, data: Any) -> Any: ...

    def transition_status(
        self,
        db: Session,
        mission_id: UUID,
        new_status: str,
        error_message: str | None = None,
    ) -> Any: ...


class UserRepository(Protocol):
    """Read/write operations for User entities."""

    def get_by_email(self, db: Session, email: str) -> Any | None: ...

    def get_by_id(self, db: Session, user_id: UUID) -> Any | None: ...

    def create(self, db: Session, *, email: str, display_name: str, password_hash: str) -> Any: ...


class CollectionRepository(Protocol):
    """Read/write operations for Collection entities."""

    def get(self, collection_id: UUID | str) -> Any | None: ...

    def list_collections(self) -> list[Any]: ...

    def create(self, *, name: str, description: str | None = None) -> Any: ...

    def update(self, collection_id: UUID | str, *, updates: dict[str, Any]) -> Any | None: ...

    def delete(self, collection_id: UUID | str) -> bool: ...


class ReportRepository(Protocol):
    """Read/write operations for Report entities."""

    def get_report(self, report_id: UUID) -> Any | None: ...

    def list_reports(
        self,
        *,
        project_id: UUID | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Any], int]: ...

    def delete_report(self, report_id: UUID) -> bool: ...


class SearchHistoryRepository(Protocol):
    """Read/write operations for SearchHistory entities."""

    def record_search(self, *, query: str, search_mode: str, **kwargs: Any) -> Any: ...

    def list_history(self, limit: int = 20) -> list[Any]: ...

    def get_entry(self, entry_id: UUID | str) -> Any | None: ...

    def clear_history(self) -> int: ...
