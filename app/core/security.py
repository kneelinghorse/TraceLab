"""Security helpers for password hashing and JWT handling."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)


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


async def require_authenticated_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency that ensures requests include a valid bearer token."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization bearer token")

    subject = _decode_access_token(credentials.credentials)
    stored = get_configured_credentials()
    if subject != stored.username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token subject is not recognized")
    return AuthenticatedUser(username=subject)


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
