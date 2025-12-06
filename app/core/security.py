"""Security helpers for password hashing, JWT handling, and API key authentication."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)

# API Key constants
API_KEY_PREFIX = "tl_"
API_KEY_LENGTH = 32  # Random alphanumeric chars after prefix


@dataclass(frozen=True)
class AuthCredentials:
    """Stored credentials resolved from configuration."""

    username: str
    password_hash: str


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents an authenticated principal for downstream dependencies."""

    username: str


@lru_cache(maxsize=1)
def get_configured_credentials() -> AuthCredentials:
    """Load configured credentials, hashing the fallback password when necessary."""
    password_hash = settings.auth_password_hash
    if not password_hash:
        if not settings.auth_password:
            raise RuntimeError(
                "AUTH_PASSWORD or AUTH_PASSWORD_HASH must be configured for authentication to function."
            )
        password_hash = _pwd_context.hash(settings.auth_password)
    return AuthCredentials(username=settings.auth_username, password_hash=password_hash)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compare a plain text password with a hashed value."""
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    *, subject: str, expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT for the given subject."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to issue JWTs.")

    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode_access_token(token: str) -> str:
    """Validate and decode a JWT, returning the subject."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to validate JWTs.")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:  # pragma: no cover - jose already unit tested
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token subject missing")
    return subject


def issue_token_response(user: AuthCredentials, *, expires_in_seconds: Optional[int] = None) -> dict:
    """Helper to construct a JWT response payload."""
    access_token = create_access_token(subject=user.username)
    expires = expires_in_seconds or settings.access_token_expire_minutes * 60
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires,
        "user": {"username": user.username},
    }


# --- API Key Functions ---


def generate_api_key() -> str:
    """Generate a new API key with tl_ prefix and 32 random alphanumeric chars."""
    random_part = secrets.token_urlsafe(24)[:API_KEY_LENGTH]  # 32 chars
    return f"{API_KEY_PREFIX}{random_part}"


def hash_api_key(key: str) -> str:
    """Hash an API key using bcrypt (same as passwords)."""
    return _pwd_context.hash(key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return _pwd_context.verify(plain_key, hashed_key)


def get_key_prefix(key: str) -> str:
    """Extract displayable prefix from an API key (e.g., tl_a1b2c3d4)."""
    if key.startswith(API_KEY_PREFIX):
        # Return prefix + first 8 chars of random part
        return key[: len(API_KEY_PREFIX) + 8]
    return key[:12]


def _validate_api_key(api_key: str) -> Optional[AuthenticatedUser]:
    """Validate an API key and return the authenticated user if valid.

    This function checks the database for a matching key, verifies it hasn't expired,
    and updates the last_used_at timestamp.
    """
    # Import here to avoid circular dependency
    from app.models.api_key import APIKey

    if not api_key.startswith(API_KEY_PREFIX):
        return None

    key_prefix = get_key_prefix(api_key)

    # Use a fresh session for API key validation
    db = SessionLocal()
    try:
        # Find keys with matching prefix
        candidates = db.query(APIKey).filter(APIKey.key_prefix == key_prefix).all()

        for candidate in candidates:
            # Verify the full key against the hash
            if verify_api_key(api_key, candidate.key_hash):
                # Check expiration
                if candidate.expires_at and candidate.expires_at < datetime.utcnow():
                    return None

                # Update last_used_at (debounced: only if >1 minute since last update)
                if (
                    candidate.last_used_at is None
                    or (datetime.utcnow() - candidate.last_used_at).total_seconds() > 60
                ):
                    candidate.last_used_at = datetime.utcnow()
                    db.commit()

                return AuthenticatedUser(username=candidate.user_id)

        return None
    finally:
        db.close()


async def require_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedUser:
    """FastAPI dependency that ensures requests include a valid bearer token or API key.

    Authentication priority:
    1. X-API-Key header (if present)
    2. Authorization bearer token (JWT)
    """
    # Check API key first
    if x_api_key:
        user = _validate_api_key(x_api_key)
        if user:
            return user
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired API key")

    # Fall back to JWT
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token or X-API-Key header",
        )

    subject = _decode_access_token(credentials.credentials)
    stored = get_configured_credentials()
    if subject != stored.username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token subject is not recognized")
    return AuthenticatedUser(username=subject)
