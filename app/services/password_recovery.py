"""Single-use recovery, serialized with credential issuance at the user row."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import logging
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import recovery_recipient_limiter
from app.core.security import hash_password
from app.models.api_key import APIKey
from app.models.device_authorization import DeviceAuthorizationGrant
from app.models.password_recovery import PasswordRecovery, PasswordRecoveryAudit
from app.models.user import User
from app.ports.email import EmailSender
from app.services.device_credentials import forget_device_credentials
from app.services.notifications import Email, deliverable_address

logger = logging.getLogger(__name__)
TOKEN_TTL = timedelta(minutes=30)
SEND_COOLDOWN = timedelta(seconds=60)
REQUEST_MESSAGE = "If this account can receive recovery email, instructions will be sent. Check your inbox and spam folder."
INVALID_LINK = "This reset link is invalid or expired. Request a new link."
HUMAN_ROLES = frozenset({"owner", "admin", "member", "viewer"})


def ensure_recovery_configured() -> None:
    destination = urlsplit(settings.frontend_url)
    if not (settings.resend_api_key and settings.resend_from_address
            and destination.scheme == "https" and destination.hostname
            and not destination.username and not destination.password
            and not destination.query and not destination.fragment):
        raise HTTPException(503, detail="Password recovery is temporarily unavailable. Please try again later.")


def recipient_budget(email: str) -> bool:
    """Same invisible cooldown for every address; never retain raw recipient keys."""
    key = hmac.new(settings.secret_key.encode(), email.encode(), hashlib.sha256).hexdigest()
    try:
        recovery_recipient_limiter.check_key(key)
        return True
    except HTTPException:
        return False


class PasswordRecoveryService:
    def __init__(self, session_factory: Callable[[], Session], sender: EmailSender):
        self.session_factory = session_factory
        self.sender = sender

    def _prepare(
        self, email: str | None, *, target_user_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> tuple[str, Email, UUID | None] | None:
        with self.session_factory() as db:
            query = db.query(User)
            query = query.filter(User.id == target_user_id) if target_user_id else query.filter(User.email == email)
            user = query.with_for_update().first()
            now = datetime.utcnow()
            audit = None
            if actor_user_id is not None and target_user_id is not None:
                audit = PasswordRecoveryAudit(actor_user_id=actor_user_id, target_user_id=target_user_id,
                                              requested_at=now, outcome="pending")
                db.add(audit)

            def refuse(outcome: str, message: str, status_code: int = 400) -> None:
                if audit is not None:
                    audit.outcome = outcome
                    audit.completed_at = now
                    db.commit()
                    raise HTTPException(status_code, detail=message,
                                        headers={"Retry-After": "60"} if status_code == 429 else None)

            if user is None:
                return refuse("not_found", "User not found", 404)
            if not user.is_active:
                return refuse("ineligible", "This account is disabled. No reset email was sent.")
            if user.role not in HUMAN_ROLES:
                return refuse("ineligible", "Service accounts cannot use password recovery.")
            if not deliverable_address(user.email):
                return refuse("ineligible", "This account does not have a deliverable email address.")
            # Public requests spend this same budget before account lookup to
            # avoid enumeration; admin requests resolve the stored address here.
            if audit is not None and not recipient_budget(user.email.strip().lower()):
                return refuse("rate_limited", "Too many reset requests for this account. Try again later.", 429)
            recovery = db.get(PasswordRecovery, user.id)
            if recovery and recovery.requested_at > now - SEND_COOLDOWN:
                return refuse("rate_limited", "A reset email was recently requested. Wait a minute before retrying.", 429)
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            if recovery is None:
                recovery = PasswordRecovery(user_id=user.id)
                db.add(recovery)
            recovery.token_hash = digest
            recovery.credential_version = user.credential_version
            recovery.requested_at = now
            recovery.expires_at = now + TOKEN_TTL
            recovery.delivery_status = "pending"
            link = f"{settings.frontend_url.rstrip('/')}/reset-password#token={token}"
            text = ("A password reset was requested for your TraceLab account.\n\n"
                    f"Choose a new password: {link}\n\n"
                    "This link expires in 30 minutes. Only the newest link works. "
                    "Your sessions and integration keys are revoked only when you submit a new password. "
                    "If you did not request this, ignore this email.")
            message = Email(to=user.email, subject="Reset your TraceLab password", text=text,
                            html=f'<p>A password reset was requested for your TraceLab account.</p><p><a href="{html.escape(link)}">Choose a new password</a></p><p>This link expires in 30 minutes. Only the newest link works. Your sessions and integration keys are revoked only when you submit a new password. If you did not request this, ignore this email.</p>')
            db.commit()
            return digest, message, audit.id if audit is not None else None

    def _finish(self, digest: str, accepted: bool, audit_id: UUID | None = None) -> None:
        with self.session_factory() as db:
            # An old send finishing late must never change the replacement token.
            values = {"delivery_status": "accepted" if accepted else "failed"}
            if not accepted:
                values["token_hash"] = None
            db.query(PasswordRecovery).filter(PasswordRecovery.token_hash == digest).update(values)
            if audit_id is not None:
                db.query(PasswordRecoveryAudit).filter(PasswordRecoveryAudit.id == audit_id).update({
                    "outcome": "accepted" if accepted else "failed", "completed_at": datetime.utcnow(),
                })
            db.commit()

    async def request(
        self, email: str | None, *, target_user_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> bool:
        """Public callers enqueue this; admins await the same provider outcome."""
        digest = None
        audit_id = None
        try:
            prepared = await asyncio.to_thread(self._prepare, email, target_user_id=target_user_id,
                                              actor_user_id=actor_user_id)
            if prepared is None:
                return False
            digest, message, audit_id = prepared
            accepted = bool(await self.sender.send(message))
            await asyncio.to_thread(self._finish, digest, accepted, audit_id)
            logger.info("password_recovery delivery=%s", "provider_accepted" if accepted else "failed")
            return accepted
        except Exception as exc:  # noqa: BLE001 - never echo email/provider exceptions or token-bearing locals
            if digest is None and isinstance(exc, HTTPException):
                raise  # Explicit admin target/cooldown refusal before sending.
            logger.error("password_recovery delivery=failed")
            if digest:
                try:
                    await asyncio.to_thread(self._finish, digest, False, audit_id)
                except Exception:  # noqa: BLE001 - database failures must not expose task arguments
                    logger.error("password_recovery cleanup=failed")
            return False

    def confirm(self, db: Session, token: str, password: str) -> None:
        digest = hashlib.sha256(token.encode()).hexdigest()
        user_id = db.query(PasswordRecovery.user_id).filter(PasswordRecovery.token_hash == digest).scalar()
        if user_id is None:
            raise HTTPException(400, detail=INVALID_LINK)
        user = db.query(User).populate_existing().filter(User.id == user_id).with_for_update().first()
        if not user or not user.is_active or user.role not in HUMAN_ROLES or not deliverable_address(user.email):
            raise HTTPException(400, detail=INVALID_LINK)
        # The conditional consume is also the SQLite compare-and-swap boundary.
        consumed = db.query(PasswordRecovery).filter(
            PasswordRecovery.user_id == user.id,
            PasswordRecovery.token_hash == digest,
            PasswordRecovery.delivery_status == "accepted",
            PasswordRecovery.credential_version == user.credential_version,
            PasswordRecovery.expires_at > datetime.utcnow(),
        ).delete(synchronize_session=False)
        if consumed != 1:
            raise HTTPException(400, detail=INVALID_LINK)
        user.password_hash = hash_password(password)
        user.credential_version += 1
        grant_ids = [row.id for row in db.query(DeviceAuthorizationGrant.id).filter(DeviceAuthorizationGrant.user_id == user.id)]
        db.query(DeviceAuthorizationGrant).filter(DeviceAuthorizationGrant.user_id == user.id).delete(synchronize_session=False)
        db.query(APIKey).filter(APIKey.user_id == user.id).delete(synchronize_session=False)
        db.commit()
        forget_device_credentials(grant_ids)
        logger.info("password_recovery completed user_id=%s", user_id)
