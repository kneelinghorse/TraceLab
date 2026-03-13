"""API schemas for Mission Protocol import/export workflows."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.mission import MissionRead


class MissionImportRequest(BaseModel):
    """Request body used to import Mission Protocol YAML."""

    project_id: UUID = Field(..., description="Project that owns the imported mission")
    yaml_text: str = Field(..., description="Mission Protocol YAML payload")
    promote_to_complete: bool = Field(
        default=False,
        description="Promote the imported payload to MissionProtocolComplete before storing",
    )


class MissionImportResponse(BaseModel):
    """Response returned after importing YAML into the Mission Protocol engine."""

    mission: MissionRead
    promoted: bool = False


class MissionExportResponse(BaseModel):
    """YAML export payload for a mission."""

    mission_id: UUID
    yaml_text: str
