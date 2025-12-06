"""Authentication API endpoints for JWT login, refresh, and API key management."""
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    AuthenticatedUser,
    generate_api_key,
    get_configured_credentials,
    get_key_prefix,
    hash_api_key,
    issue_token_response,
    require_authenticated_user,
    verify_password,
)
from app.models.api_key import APIKey
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyDeleted,
    APIKeyInfo,
    APIKeyList,
    APIKeyResponse,
)
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(tags=["auth"])

# Maximum API keys per user
MAX_API_KEYS_PER_USER = 10


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


# --- API Key Management Endpoints ---


@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: APIKeyCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> APIKeyResponse:
    """Create a new API key. The full key is only returned once at creation time."""
    # Check rate limit (max 10 keys per user)
    existing_count = db.query(APIKey).filter(APIKey.user_id == user.username).count()
    if existing_count >= MAX_API_KEYS_PER_USER:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Maximum of {MAX_API_KEYS_PER_USER} API keys allowed per user",
        )

    # Generate the key
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)
    key_prefix = get_key_prefix(plain_key)

    # Calculate expiration
    expires_at = None
    if payload.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=payload.expires_in_days)

    # Create the key record
    api_key = APIKey(
        user_id=user.username,
        name=payload.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=plain_key,  # Only returned at creation
        key_prefix=key_prefix,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get("/api-keys", response_model=APIKeyList)
def list_api_keys(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> APIKeyList:
    """List all API keys for the authenticated user (without key values)."""
    keys = db.query(APIKey).filter(APIKey.user_id == user.username).order_by(APIKey.created_at.desc()).all()

    return APIKeyList(
        keys=[
            APIKeyInfo(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
                expires_at=k.expires_at,
            )
            for k in keys
        ],
        total=len(keys),
    )


@router.delete("/api-keys/{key_id}", response_model=APIKeyDeleted)
def delete_api_key(
    key_id: UUID,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> APIKeyDeleted:
    """Delete an API key by ID."""
    api_key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.user_id == user.username).first()

    if not api_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="API key not found or does not belong to you",
        )

    key_name = api_key.name
    db.delete(api_key)
    db.commit()

    return APIKeyDeleted(success=True, message=f"API key '{key_name}' deleted successfully")
