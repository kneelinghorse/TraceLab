"""Process-local, one-time device key delivery; the database remains authoritative."""

from uuid import UUID

PENDING_PLAINTEXT: dict[UUID, str] = {}


def forget_device_credentials(grant_ids: list[UUID]) -> None:
    for grant_id in grant_ids:
        PENDING_PLAINTEXT.pop(grant_id, None)
