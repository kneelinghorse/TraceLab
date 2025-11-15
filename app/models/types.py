"""Shared SQLAlchemy custom types."""
from __future__ import annotations

import uuid

from sqlalchemy import CHAR, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PGUUID, TSVECTOR as PGTSVECTOR


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.

    Persists as native UUID on PostgreSQL and as CHAR(36) on SQLite.
    """

    impl = PGUUID
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "sqlite":
            return dialect.type_descriptor(CHAR(36))
        return dialect.type_descriptor(PGUUID(as_uuid=True))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            uuid_value = value
        else:
            uuid_value = uuid.UUID(str(value))

        if dialect.name == "sqlite":
            return str(uuid_value)
        return uuid_value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class TSVector(TypeDecorator):
    """TSVECTOR on PostgreSQL, TEXT everywhere else for schema compatibility."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGTSVECTOR())
        return dialect.type_descriptor(Text)
