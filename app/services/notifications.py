"""Mission completion and failure emails through Resend (NOTIFY-1, decision #455).

Sending is disabled until RESEND_API_KEY and RESEND_FROM_ADDRESS are set. Each
terminal status is mailed at most once per mission, recorded in the mission's
execution_metadata["notification"] subrecord, which the worker cannot forge.
"""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.mission import Mission
from app.models.user import User

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
NOTIFY_STATUSES = frozenset({"completed", "validation_failed", "blocked"})
STATUS_LABELS = {"completed": "completed", "validation_failed": "failed validation", "blocked": "was blocked"}


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


def notifications_configured() -> bool:
    return bool(settings.notification_emails_enabled and settings.resend_api_key and settings.resend_from_address)


def build_terminal_email(mission: Mission, recipient: str) -> Email:
    label = STATUS_LABELS.get(mission.status, mission.status)
    link = f"{settings.frontend_url.rstrip('/')}/missions/{mission.id}"
    subject = f"Mission {label}: {mission.title}"
    detail = f"\n\n{mission.error_message}" if mission.status != "completed" and mission.error_message else ""
    text = f"Your mission \"{mission.title}\" ({mission.mission_id}) {label}.{detail}\n\nOpen it: {link}\n"
    body = (
        f"<p>Your mission <strong>{html.escape(mission.title)}</strong> ({html.escape(mission.mission_id)}) {label}.</p>"
        + (f"<p>{html.escape(mission.error_message)}</p>" if detail else "")
        + f'<p><a href="{html.escape(link)}">Open the mission</a></p>'
    )
    return Email(to=recipient, subject=subject, text=text, html=body)


class ResendClient:
    """Thin HTTP client; one retry on transport failure, never raises to callers."""

    def __init__(self, api_key: str | None = None, sender: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or settings.resend_api_key
        self.sender = sender or settings.resend_from_address
        self.timeout = timeout

    async def send(self, email: Email) -> str | None:
        """Return the provider message id, or None when the send failed."""
        payload = {"from": self.sender, "to": [email.to], "subject": email.subject, "text": email.text, "html": email.html}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(RESEND_ENDPOINT, json=payload, headers=headers)
                if response.status_code < 300:
                    return str(response.json().get("id", ""))
                logger.warning("Resend rejected an email (attempt %s): %s %s", attempt, response.status_code, response.text[:200])
                if response.status_code < 500:
                    return None
            except httpx.HTTPError as exc:
                logger.warning("Resend transport failure (attempt %s): %s", attempt, exc)
            if attempt == 1:
                await asyncio.sleep(1.0)
        return None


def _already_notified(mission: Mission) -> bool:
    """True once this status is claimed for an email, whether or not the send has finished."""
    record = (mission.execution_metadata or {}).get("notification")
    return isinstance(record, dict) and record.get("status") == mission.status


def pending_terminal_notification(db: Session, mission_id: UUID, *, lock: bool = False) -> tuple[Mission, Email] | None:
    """The email to send for this mission's current status, or None when nothing is due."""
    if not notifications_configured():
        return None
    query = db.query(Mission).filter(Mission.id == mission_id)
    mission = (query.with_for_update() if lock else query).first()
    if mission is None or mission.status not in NOTIFY_STATUSES or _already_notified(mission) or mission.owner_id is None:
        return None
    owner = db.query(User).filter(User.id == mission.owner_id).first()
    if owner is None or not owner.is_active or not owner.email_notifications_enabled:
        return None
    return mission, build_terminal_email(mission, owner.email)


def _write_notification(db: Session, mission: Mission, record: dict | None) -> None:
    metadata = dict(mission.execution_metadata or {})
    if record is None:
        metadata.pop("notification", None)
    else:
        metadata["notification"] = record
    mission.execution_metadata = metadata
    db.commit()


def claim_terminal_notification(db: Session, mission_id: UUID) -> tuple[Mission, Email, dict] | None:
    """Reserve this status's one email under a row lock, so a duplicate webhook finds it taken."""
    due = pending_terminal_notification(db, mission_id, lock=True)
    if due is None:
        db.rollback()  # releases the row lock
        return None
    mission, email = due
    claim = {"status": mission.status, "to": email.to, "claimed_at": datetime.now(UTC).isoformat()}
    _write_notification(db, mission, claim)
    return mission, email, claim


def finish_notification(db: Session, mission: Mission, claim: dict, message_id: str | None) -> None:
    """Record the sent email, or release the claim after a failed send; never overwrite a newer record."""
    db.refresh(mission)
    if (mission.execution_metadata or {}).get("notification") != claim:
        return
    record = None if message_id is None else {**claim, "sent_at": datetime.now(UTC).isoformat(), "message_id": message_id}
    _write_notification(db, mission, record)


async def notify_terminal_status(mission_id: UUID, client: ResendClient | None = None) -> bool:
    """Background task: send at most one email per terminal status. Returns True when a mail went out."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        due = await asyncio.to_thread(claim_terminal_notification, db, mission_id)
        if due is None:
            return False
        mission, email, claim = due
        message_id = await (client or ResendClient()).send(email)
        # A failed send releases the claim, leaving the mission unmarked for a later webhook.
        await asyncio.to_thread(finish_notification, db, mission, claim, message_id)
        if message_id is None:
            return False
        logger.info("Notified %s that mission %s %s", email.to, mission.mission_id, mission.status)
        return True
    except Exception:  # noqa: BLE001 - a notification must never surface as a webhook failure
        logger.exception("Mission notification failed for %s", mission_id)
        return False
    finally:
        db.close()
