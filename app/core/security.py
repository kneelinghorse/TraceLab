"""Security helpers for password hashing, JWT handling, and API key authentication."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
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
    """Represents an authenticated principal for downstream dependencies.

    Carries user_id (UUID), email, and display_name from the users table.
    The 'username' property is kept for backward compatibility.
    """

    user_id: UUID
    email: str
    display_name: str

    @property
    def username(self) -> str:
        """Backward-compatible alias for display_name."""
        return self.display_name


def hash_password(plain_password: str) -> str:
    """Hash a password using bcrypt."""
    return _pwd_context.hash(plain_password)


@lru_cache(maxsize=1)
def get_configured_credentials() -> AuthCredentials:
    """Load configured credentials, hashing the fallback password when necessary.

    Kept as fallback for migration period — if no users in DB, env-var auth still works.
    """
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
    """Create a signed JWT for the given subject (user UUID as string)."""
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


def issue_token_response(user, *, expires_in_seconds: Optional[int] = None) -> dict:
    """Helper to construct a JWT response payload.

    Accepts either an AuthCredentials (legacy) or a User model instance.
    """
    from app.models.user import User

    if isinstance(user, User):
        access_token = create_access_token(subject=str(user.id))
        expires = expires_in_seconds or settings.access_token_expire_minutes * 60
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires,
            "user": {
                "user_id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "username": user.display_name,
            },
        }
    else:
        # Legacy AuthCredentials path (fallback)
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
    """Validate an API key and return the authenticated user if valid."""
    from app.models.api_key import APIKey
    from app.models.user import User

    if not api_key.startswith(API_KEY_PREFIX):
        return None

    key_prefix = get_key_prefix(api_key)

    db = SessionLocal()
    try:
        candidates = db.query(APIKey).filter(APIKey.key_prefix == key_prefix).all()

        for candidate in candidates:
            if verify_api_key(api_key, candidate.key_hash):
                if candidate.expires_at and candidate.expires_at < datetime.utcnow():
                    return None

                # Update last_used_at (debounced)
                if (
                    candidate.last_used_at is None
                    or (datetime.utcnow() - candidate.last_used_at).total_seconds() > 60
                ):
                    candidate.last_used_at = datetime.utcnow()
                    db.commit()

                # Look up user from UUID
                db_user = db.query(User).filter(User.id == candidate.user_id).first()
                if db_user:
                    return AuthenticatedUser(
                        user_id=db_user.id,
                        email=db_user.email,
                        display_name=db_user.display_name,
                    )
                return None

        return None
    finally:
        db.close()


def _resolve_user_from_jwt(subject: str) -> AuthenticatedUser:
    """Resolve a JWT subject to an AuthenticatedUser.

    Tries UUID lookup first (new flow), falls back to display_name lookup (migration).
    """
    from app.models.user import User

    db = SessionLocal()
    try:
        # Try UUID lookup first (new JWT format: sub=user.id)
        try:
            user_uuid = UUID(subject)
            db_user = db.query(User).filter(User.id == user_uuid).first()
            if db_user:
                return AuthenticatedUser(
                    user_id=db_user.id,
                    email=db_user.email,
                    display_name=db_user.display_name,
                )
        except (ValueError, AttributeError):
            pass

        # Fallback: subject is a username/display_name (legacy tokens)
        db_user = db.query(User).filter(User.display_name == subject).first()
        if db_user:
            return AuthenticatedUser(
                user_id=db_user.id,
                email=db_user.email,
                display_name=db_user.display_name,
            )

        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token subject is not recognized")
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
    return _resolve_user_from_jwt(subject)
