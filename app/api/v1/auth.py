"""Authentication API endpoints for JWT login, refresh, and API key management."""
import logging
from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import auth_rate_limiter
from app.core.security import (
    AuthenticatedUser,
    generate_api_key,
    get_key_prefix,
    hash_api_key,
    hash_password,
    issue_token_response,
    require_authenticated_user,
    verify_password,
)
from app.models.api_key import APIKey
from app.models.invite_code import InviteCode, generate_invite_code
from app.models.user import User
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyDeleted,
    APIKeyInfo,
    APIKeyList,
    APIKeyResponse,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Maximum API keys per user
MAX_API_KEYS_PER_USER = 10


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a user against the users table and return a signed JWT."""
    auth_rate_limiter.check(request)

    db_user = db.query(User).filter(User.email == payload.email).first()

    if not db_user or not verify_password(payload.password, db_user.password_hash):
        _log_auth_failure(request, payload.email, "invalid_credentials")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    # Update last_login_at
    db_user.last_login_at = datetime.utcnow()
    db.commit()

    response_payload = issue_token_response(db_user)
    return TokenResponse(**response_payload)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register a new user with a valid invite code and return a signed JWT."""
    auth_rate_limiter.check(request)

    # Check email uniqueness
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        _log_auth_failure(request, payload.email, "email_already_registered")
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")

    # Validate invite code
    invite = db.query(InviteCode).filter(
        InviteCode.code == payload.invite_code.upper(),
        InviteCode.used_by.is_(None),
    ).first()
    if not invite:
        _log_auth_failure(request, payload.email, "invalid_invite_code")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or already used invite code")
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        _log_auth_failure(request, payload.email, "expired_invite_code")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invite code has expired")

    # Create user
    new_user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role="admin",
        invite_code_used=payload.invite_code.upper(),
    )
    db.add(new_user)
    db.flush()

    # Mark invite code as used
    invite.used_by = new_user.id
    invite.used_at = datetime.utcnow()

    db.commit()
    db.refresh(new_user)

    response_payload = issue_token_response(new_user)
    return TokenResponse(**response_payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Refresh the caller's JWT."""
    db_user = db.query(User).filter(User.id == user.user_id).first()
    if not db_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found")
    response_payload = issue_token_response(db_user)
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
    existing_count = db.query(APIKey).filter(APIKey.user_id == user.user_id).count()
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
        user_id=user.user_id,
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
    keys = db.query(APIKey).filter(APIKey.user_id == user.user_id).order_by(APIKey.created_at.desc()).all()

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
    api_key = db.query(APIKey).filter(APIKey.id == key_id, APIKey.user_id == user.user_id).first()

    if not api_key:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="API key not found or does not belong to you",
        )

    key_name = api_key.name
    db.delete(api_key)
    db.commit()

    return APIKeyDeleted(success=True, message=f"API key '{key_name}' deleted successfully")


# --- Invite Code Management Endpoints ---


@router.post("/invite-codes", status_code=status.HTTP_201_CREATED)
def create_invite_code(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Generate a new single-use invite code."""
    code = generate_invite_code()
    invite = InviteCode(
        code=code,
        created_by=user.user_id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return {
        "id": str(invite.id),
        "code": invite.code,
        "created_at": invite.created_at.isoformat(),
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
    }


@router.get("/invite-codes")
def list_invite_codes(
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """List invite codes created by the current user."""
    codes = db.query(InviteCode).filter(
        InviteCode.created_by == user.user_id
    ).order_by(InviteCode.created_at.desc()).all()

    return {
        "codes": [
            {
                "id": str(c.id),
                "code": c.code,
                "status": "used" if c.used_by else ("expired" if c.expires_at and c.expires_at < datetime.utcnow() else "unused"),
                "created_at": c.created_at.isoformat(),
                "used_at": c.used_at.isoformat() if c.used_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            }
            for c in codes
        ],
        "total": len(codes),
    }


@router.delete("/invite-codes/{code_id}")
def delete_invite_code(
    code_id: UUID,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> dict:
    """Revoke an unused invite code."""
    invite = db.query(InviteCode).filter(
        InviteCode.id == code_id,
        InviteCode.created_by == user.user_id,
    ).first()

    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")

    if invite.used_by:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot delete a used invite code")

    db.delete(invite)
    db.commit()

    return {"success": True, "message": "Invite code deleted"}


# --- Audit Logging ---


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _log_auth_failure(request: Request, email: str, reason: str) -> None:
    """Log a failed authentication attempt with structured context.

    Logs IP and failure reason for security audit. Does NOT log passwords or
    other sensitive data.
    """
    ip = _get_client_ip(request)
    logger.warning(
        "auth_failure: ip=%s email=%s reason=%s",
        ip,
        email,
        reason,
    )
