"""Transactional mail boundary shared with the existing Resend adapter."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.services.notifications import Email


class EmailSender(Protocol):
    async def send(self, email: "Email") -> str | None:
        """Return provider acceptance, never a claim of mailbox delivery."""
        ...
