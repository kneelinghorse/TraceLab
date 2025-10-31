"""
FastAPI routes for Presidio redaction service.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.presidio_redaction import PresidioRedactionService

router = APIRouter()

_redaction_service: Optional[PresidioRedactionService] = None
_service_init_error: Optional[str] = None


def get_redaction_service() -> PresidioRedactionService:
    """Instantiate the Presidio redaction service lazily."""
    global _redaction_service, _service_init_error
    if _redaction_service is None:
        try:
            _redaction_service = PresidioRedactionService()
            _service_init_error = None
        except Exception as exc:  # pragma: no cover - defensive
            _service_init_error = str(exc)
            raise
    return _redaction_service


class RedactionRequest(BaseModel):
    """Request model for document redaction."""
    text: str
    document_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    use_pseudonymization: bool = True


class RedactionResponse(BaseModel):
    """Response model for document redaction."""
    redacted_text: str
    entities: list[Dict[str, Any]]
    audit_trail: Dict[str, Any]


@router.post("/redact", response_model=RedactionResponse)
async def redact_document(request: RedactionRequest) -> RedactionResponse:
    """
    Redact PII from document text.
    
    Returns redacted text, detected entities, and audit trail.
    """
    try:
        service = get_redaction_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redaction service unavailable: {exc}") from exc

    try:
        result = service.redact_document(
            text=request.text,
            document_id=request.document_id,
            metadata=request.metadata,
            use_pseudonymization=request.use_pseudonymization
        )
        return RedactionResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redaction failed: {str(e)}")


@router.get("/health")
async def health() -> Dict[str, str]:
    """Health check for redaction service."""
    status = "healthy" if _service_init_error is None else "degraded"
    response = {"status": status, "service": "presidio-redaction"}
    if _service_init_error:
        response["detail"] = _service_init_error
    return response
