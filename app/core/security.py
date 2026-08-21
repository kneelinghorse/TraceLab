"""Security helpers for password hashing, JWT handling, and API key authentication."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.database import SessionLocal

# passlib 1.7.x probes bcrypt.__about__.__version__, which bcrypt>=4 removed, and
# logs a noisy (harmless) "(trapped) error reading bcrypt version" WARNING when the
# backend loads. Quiet just that logger so it doesn't drown real auth logs (T47.5).
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

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


# Role hierarchy (Sprint 43 RBAC foundation; architecture locked 2026-05-28).
# Linear and cumulative — a higher role has every privilege of the ones below it
# (owner ⊇ admin ⊇ member ⊇ viewer). The require_role/require_admin dependencies
# below check "at least this role" against this ranking. These helpers are defined
# but NOT applied to any route in Sprint 43; enforcement is wired up in Sprint C.
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLE_VIEWER = "viewer"

# Service principal (T47.4): a non-human machine identity (e.g. the DeepSearch
# runner) used for service-to-service writes such as POST /missions/{id}/logs.
# DELIBERATELY OUTSIDE the cumulative human hierarchy above — and deliberately
# absent from _ROLE_RANK below — so it ranks -1 (fail-closed) on every human role
# gate (require_admin / require_role) and is non-privileged in authorize(). A
# service principal therefore passes only the dedicated service gates plus the
# read-only ``GET /auth/me`` role-verification endpoint; it can do nothing a
# human role can, and no human role satisfies the service gate. See
# app/core/authorization.py.
ROLE_SERVICE = "service"

# Ascending privilege rank. Unknown roles (incl. ROLE_SERVICE, intentionally) default
# to rank -1 (below viewer) so any future role check fails closed rather than silently
# granting access.
_ROLE_RANK: dict[str, int] = {
    ROLE_VIEWER: 0,
    ROLE_MEMBER: 1,
    ROLE_ADMIN: 2,
    ROLE_OWNER: 3,
}


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents an authenticated principal for downstream dependencies.

    Carries user_id (UUID), email, display_name, and role from the users table.
    The 'username' property is kept for backward compatibility.
    """

    user_id: UUID
    email: str
    display_name: str
    role: str

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


def create_access_token(*, subject: str, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT for the given subject (user UUID as string)."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to issue JWTs.")

    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _decode_access_token(token: str) -> str:
    """Validate and decode a JWT, returning the subject."""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be configured to validate JWTs.")
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:  # pragma: no cover - jose already unit tested
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Token subject missing"
        )
    return subject


def issue_token_response(user, *, expires_in_seconds: int | None = None) -> dict:
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


def _to_authenticated_user(db_user) -> AuthenticatedUser:
    """Build the request principal from a users row, enforcing the is_active gate.

    Sprint C (T46.3): a soft-disabled user (is_active=False) is rejected at EVERY
    principal-resolution point — JWT and API key — so a disable/demote takes effect
    on the user's very next request without waiting for token expiry (standing rule,
    decision #226: role/identity is resolved live from the DB per request, never
    cached in the token).
    """
    if not db_user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return AuthenticatedUser(
        user_id=db_user.id,
        email=db_user.email,
        display_name=db_user.display_name,
        role=db_user.role,
    )


def _validate_api_key(api_key: str) -> AuthenticatedUser | None:
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
                    return _to_authenticated_user(db_user)
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
                return _to_authenticated_user(db_user)
        except (ValueError, AttributeError):
            pass

        # Fallback: subject is a username/display_name (legacy tokens)
        db_user = db.query(User).filter(User.display_name == subject).first()
        if db_user:
            return _to_authenticated_user(db_user)

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Token subject is not recognized"
        )
    finally:
        db.close()


async def require_authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedUser:
    """Resolve any active authenticated principal, including a service account.

    Authentication priority:
    1. X-API-Key header (if present)
    2. Authorization bearer token (JWT)

    This lower-level dependency is intentionally restricted to explicit machine
    carve-outs and ``GET /auth/me`` (which DeepSearch uses to verify its startup
    role). Human-facing routes must use :func:`require_authenticated_user` so a
    service credential cannot become a general API credential when RBAC is off.
    """
    # Check API key first
    if x_api_key:
        user = _validate_api_key(x_api_key)
        if user:
            return user
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired API key"
        )

    # Fall back to JWT
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization bearer token or X-API-Key header",
        )

    subject = _decode_access_token(credentials.credentials)
    return _resolve_user_from_jwt(subject)


def _require_human_principal(user: AuthenticatedUser) -> AuthenticatedUser:
    """Reject machine identities at the shared human-route authentication gate."""
    if user.role == ROLE_SERVICE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Service principals may only access explicit service endpoints.",
        )
    return user


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AuthenticatedUser:
    """Require an active authenticated human principal.

    ``ROLE_SERVICE`` is denied here unconditionally, independently of the RBAC
    rollout flag. Explicit service routes use ``require_authenticated_principal``
    and then apply their dedicated service authorization policy.
    """
    user = await require_authenticated_principal(
        credentials=credentials,
        x_api_key=x_api_key,
    )
    return _require_human_principal(user)


async def require_authenticated_user_sse(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    token: str | None = Query(default=None),
) -> AuthenticatedUser:
    """Auth dependency for SSE endpoints that also accepts a JWT via query parameter.

    EventSource API cannot send custom headers, so the frontend passes
    the JWT as ``?token=<jwt>``. This dependency checks that first,
    then falls back to the standard header-based auth.
    """
    # Check query param token first (SSE / EventSource)
    if token:
        subject = _decode_access_token(token)
        return _require_human_principal(_resolve_user_from_jwt(subject))

    # Fall through to standard auth
    return await require_authenticated_user(
        credentials=credentials, x_api_key=x_api_key
    )


def require_admin(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    """FastAPI dependency requiring the caller to be admin or owner.

    Convenience gate equivalent to ``require_role(ROLE_ADMIN)``: returns the
    principal on success, raises 403 otherwise. Applied (T43.5) to the admin
    user-management API and invite-code generation; route-level resource
    enforcement remains a Sprint C concern.
    """
    if _ROLE_RANK.get(user.role, -1) < _ROLE_RANK[ROLE_ADMIN]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def require_role(
    minimum_role: str,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Build a FastAPI dependency requiring at least ``minimum_role``.

    Roles form a linear, cumulative hierarchy (viewer < member < admin < owner),
    so a higher role satisfies a requirement for any lower one. A principal whose
    role is unknown ranks below viewer and is always denied (fail closed).

    NOT applied to any route in Sprint 43 (RBAC foundation, zero enforcement) —
    intended for Sprint C, when enforcement is flipped on.

    Raises KeyError at wiring time if ``minimum_role`` is not a known role, so a
    typo surfaces immediately rather than silently never matching.
    """
    required_rank = _ROLE_RANK[minimum_role]

    def _require_role(
        user: AuthenticatedUser = Depends(require_authenticated_user),
    ) -> AuthenticatedUser:
        if _ROLE_RANK.get(user.role, -1) < required_rank:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum_role}' role or higher",
            )
        return user

    return _require_role
