"""Test-only provider boundary, installed before application imports.

The only real Qdrant origin allowed is registered by the disposable-container
fixture. Environment variables and command-line flags cannot grant remote access.
"""

from __future__ import annotations

import inspect
import os
import sys
from functools import wraps
from uuid import uuid4

import httpx
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.async_qdrant_remote import AsyncQdrantRemote
from qdrant_client.qdrant_remote import QdrantRemote

MEMORY_URL = "http://pytest-qdrant.invalid"
_container_origins: set[str] = set()
_installed = False


def install() -> None:
    """Force safe settings and intercept real SDK transports before singletons."""
    global _installed
    if _installed:
        return
    if "app.core.config" in sys.modules:
        raise RuntimeError("Test isolation must load before application settings")

    prefix = f"test_{uuid4().hex}"
    safe_environment = dict(
        QDRANT_URL=MEMORY_URL,
        QDRANT_API_KEY="",
        QDRANT_PREFER_GRPC="false",
        QDRANT_COLLECTION_NAME=f"{prefix}_chunks",
        SEMANTIC_CACHE_COLLECTION_NAME=f"{prefix}_cache",
        OPENAI_API_KEY="test",
        OPENAI_BASE_URL="https://pytest-provider.invalid/v1",
        LIBRARIAN_API_KEY="test",
        LIBRARIAN_BASE_URL="https://pytest-provider.invalid/v1",
        RESEND_API_KEY="",
        RESEND_INBOUND_API_KEY="",
        RESEND_WEBHOOK_SECRET="",
        RESEND_FROM_ADDRESS="",
        SUPPORT_FORWARD_TO="",
        DEEPSEARCH_API_KEY="",
        DEEPSEARCH_API_URL="",
    )
    # Settings is case-insensitive; a lower-case shell key must not win later.
    for key in list(os.environ):
        if key.upper() in safe_environment:
            del os.environ[key]
    os.environ.update(safe_environment)

    for cls in (QdrantClient, AsyncQdrantClient):
        _wrap_client(cls)
    for cls in (QdrantRemote, AsyncQdrantRemote):
        _wrap_remote(cls)

    sync_send = httpx.HTTPTransport.handle_request
    async_send = httpx.AsyncHTTPTransport.handle_async_request

    def isolated_send(self, request):
        _check_origin(request.url)
        return sync_send(self, request)

    async def isolated_async_send(self, request):
        _check_origin(request.url)
        return await async_send(self, request)

    # MockTransport, pytest-httpx and Starlette's in-process transport still work.
    httpx.HTTPTransport.handle_request = isolated_send
    httpx.AsyncHTTPTransport.handle_async_request = isolated_async_send
    _installed = True


def _check_origin(url: httpx.URL) -> None:
    origin = str(url.copy_with(path="/", query=None, fragment=None)).rstrip("/")
    if origin not in _container_origins:
        raise RuntimeError("Tests require isolated transport; inject a provider fake")


def _wrap_client(cls) -> None:
    original = cls.__init__
    signature = inspect.signature(original)

    @wraps(original)
    def initialize(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        if bound.arguments.get("url") == MEMORY_URL:
            original(self, location=":memory:")
        else:
            original(self, *args, **kwargs)

    cls.__init__ = initialize


def _wrap_remote(cls) -> None:
    original = cls.__init__
    signature = inspect.signature(original)

    @wraps(original)
    def initialize(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        url = bound.arguments.get("url")
        if (url not in _container_origins or bound.arguments.get("api_key")
                or bound.arguments.get("prefer_grpc")):
            raise RuntimeError("Qdrant tests require an isolated disposable fixture")
        original(self, *args, **kwargs)

    cls.__init__ = initialize
