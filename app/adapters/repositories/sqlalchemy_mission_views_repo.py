"""Owner-scoped preference CRUD with live, permission-filtered totals."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authorization import accessible_filter
from app.core.security import AuthenticatedUser
from app.models.mission import Mission
from app.models.project import Project
from app.models.user import User
from app.models.user_saved_view import UserSavedView
from app.schemas.mission_views import MissionViewCreate, MissionViewFilters, MissionViewResponse, MissionViewUpdate
from app.services.mission_service import MissionService


class SQLAlchemyMissionViewRepository:
    def _query(self, db: Session, user: AuthenticatedUser):
        return db.query(UserSavedView).filter(UserSavedView.user_id == user.user_id)

    def _response(self, db: Session, user: AuthenticatedUser, row: UserSavedView) -> MissionViewResponse:
        filters = MissionViewFilters.model_validate(row.filters)
        readable = True
        if filters.project_id:
            project = db.query(Project).filter(Project.id == filters.project_id, Project.deleted_at.is_(None))
            scope = accessible_filter(user, Project, db)
            if scope is not None:
                project = project.filter(scope)
            readable = project.first() is not None
        total = 0
        if readable:
            _, pagination = MissionService().list_missions(
                db, page_size=1, access_filter=accessible_filter(user, Mission, db), user_id=user.user_id,
                **filters.model_dump(),
            )
            total = pagination.total
        return MissionViewResponse(
            id=row.id, name=row.name, entity_type=row.entity_type, filters=row.filters,
            created_at=row.created_at, updated_at=row.updated_at, total=total,
        )

    def list(self, db: Session, user: AuthenticatedUser) -> list[MissionViewResponse]:
        rows = self._query(db, user).order_by(UserSavedView.updated_at.desc(), UserSavedView.id).all()
        return [self._response(db, user, row) for row in rows]

    def _commit(self, db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("A saved view with that name already exists.") from exc

    def create(self, db: Session, user: AuthenticatedUser, data: MissionViewCreate) -> MissionViewResponse:
        # Serialize per-user creates on PostgreSQL so concurrent requests cannot exceed 50.
        db.query(User).filter(User.id == user.user_id).with_for_update().one()
        if self._query(db, user).count() >= 50:
            raise ValueError("Saved view limit of 50 reached.")
        row = UserSavedView(user_id=user.user_id, name=data.name,
                            filters=data.filters.model_dump(mode="json", exclude_unset=True))
        db.add(row)
        self._commit(db)
        return self._response(db, user, row)

    def update(self, db: Session, user: AuthenticatedUser, view_id: UUID, data: MissionViewUpdate) -> MissionViewResponse:
        row = self._query(db, user).filter(UserSavedView.id == view_id).first()
        if row is None:
            raise LookupError("Saved view not found.")
        row.name = data.name
        if data.filters is not None:
            row.filters = data.filters.model_dump(mode="json", exclude_unset=True)
        self._commit(db)
        return self._response(db, user, row)

    def delete(self, db: Session, user: AuthenticatedUser, view_id: UUID) -> None:
        row = self._query(db, user).filter(UserSavedView.id == view_id).first()
        if row is None:
            raise LookupError("Saved view not found.")
        db.delete(row)
        db.commit()
