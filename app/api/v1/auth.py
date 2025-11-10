"""Authentication API endpoints for JWT login and refresh."""
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import (
    AuthenticatedUser,
    get_configured_credentials,
    issue_token_response,
    require_authenticated_user,
    verify_password,
)
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate a user and return a signed JWT."""
    credentials = get_configured_credentials()
    if payload.username != credentials.username or not verify_password(
        payload.password, credentials.password_hash
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    response_payload = issue_token_response(credentials)
    return TokenResponse(**response_payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(_: AuthenticatedUser = Depends(require_authenticated_user)) -> TokenResponse:
    """Refresh the caller's JWT while preserving the current session."""
    credentials = get_configured_credentials()
    response_payload = issue_token_response(credentials)
    return TokenResponse(**response_payload)
