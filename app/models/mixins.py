"""SQLAlchemy model mixins for reusable functionality."""

from datetime import datetime

from sqlalchemy import Column, DateTime, String


class SoftDeleteMixin:
    """Mixin that adds soft delete capability to models.

    Instead of permanently deleting records, this mixin sets a deleted_at
    timestamp and optional deleted_by field. Records can be restored by
    clearing these fields.

    Usage:
        class MyModel(Base, SoftDeleteMixin):
            __tablename__ = "my_table"
            # ... other columns

    Query filtering:
        # Exclude deleted records (default behavior)
        query.filter(MyModel.deleted_at.is_(None))

        # Include deleted records
        query  # no filter

        # Only deleted records
        query.filter(MyModel.deleted_at.isnot(None))
    """

    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by = Column(String(100), nullable=True)

    def soft_delete(self, deleted_by: str = None) -> None:
        """Mark this record as deleted.

        Args:
            deleted_by: Optional identifier of who/what performed the deletion
        """
        self.deleted_at = datetime.utcnow()
        self.deleted_by = deleted_by

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.deleted_by = None

    @property
    def is_deleted(self) -> bool:
        """Check if this record has been soft-deleted."""
        return self.deleted_at is not None
