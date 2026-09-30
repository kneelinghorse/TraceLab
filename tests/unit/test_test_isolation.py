"""Prove pytest boot cannot inherit a developer's production providers."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_production_sentinels_cannot_escape_test_boot(tmp_path, source):
    # A fresh interpreter is essential: monkeypatching settings after import
    # would miss both .env precedence and factories holding cached settings.
    probe = r'''
import asyncio
import runpy
import socket
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
attempts = []
def no_network(*args, **kwargs):
    attempts.append("unexpected transport")
    raise AssertionError("test boot reached network transport")
socket.socket.connect = no_network
socket.getaddrinfo = no_network
# A caller may hold an SDK class reference before conftest loads.
from qdrant_client import QdrantClient as EarlyClient
runpy.run_path(str(root / "tests/conftest.py"))

from app.core.config import settings, Settings
from app.core.qdrant_client import get_qdrant_client, prewarm_qdrant
from app.services.semantic_cache import get_semantic_cache_service
from app.services.rag_service import RagService, build_empty_scope_result
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.qdrant_remote import QdrantRemote
from qdrant_client.models import Distance, VectorParams
import httpx

assert settings.qdrant_api_key == ""
assert settings.qdrant_url == "http://pytest-qdrant.invalid"
assert settings.qdrant_collection_name.startswith("test_")
assert settings.semantic_cache_collection_name.startswith("test_")
assert settings.semantic_cache_enabled
assert Settings().qdrant_api_key == ""
assert settings.openai_api_key == settings.librarian_api_key == "test"
assert settings.resend_api_key == settings.resend_inbound_api_key == ""
client = get_qdrant_client()
assert client is get_qdrant_client()
assert asyncio.run(prewarm_qdrant())
# Force the destructive dimension-mismatch path on an isolated collection.
client.create_collection(settings.semantic_cache_collection_name,
                         vectors_config=VectorParams(size=2, distance=Distance.COSINE))
cache = get_semantic_cache_service()
assert cache.enabled and cache.client is client
assert cache is get_semantic_cache_service()
vector = [1.0] + [0.0] * (settings.openai_embedding_dimension - 1)
result = build_empty_scope_result(search_mode="semantic")
metadata = {"project_id": "test-project", "max_tokens": 500}
cache.store_in_cache(vector, result, metadata)
assert client.count(cache.collection_name).count == 1
assert cache.check_cache(vector, metadata)["cache"]["hit"]
assert cache.check_cache(vector, {"project_id": "another-project"}) is None
rag = RagService(pedr_orchestrator=object(), embedding_service=object(),
                 client=object(), cost_monitor=None)
assert rag.cache_service is cache
assert rag.run_query("test", allowed_project_ids=[])['no_evidence']
for constructor in (EarlyClient, QdrantClient, AsyncQdrantClient, QdrantRemote):
    for url in ("https://production-sentinel.invalid", "http://localhost:6333"):
        try:
            constructor(url=url, api_key="test-sentinel-not-a-secret")
        except RuntimeError as exc:
            assert "isolated" in str(exc)
            assert "test-sentinel-not-a-secret" not in str(exc)
        else:
            raise AssertionError("remote client was accepted")
try:
    httpx.post("https://api.resend.com/emails", json={})
except RuntimeError as exc:
    assert "isolated" in str(exc)
else:
    raise AssertionError("real provider transport was accepted")
async def async_provider():
    async with httpx.AsyncClient() as http:
        try:
            await http.post("https://api.openai.com/v1/responses", json={})
        except RuntimeError as exc:
            assert "isolated" in str(exc)
        else:
            raise AssertionError("real async transport was accepted")
asyncio.run(async_provider())
assert attempts == []
print("isolated settings, singleton, enabled cache recreate/write/read, RAG and providers")
'''
    env = os.environ.copy()
    env.update(
        DATABASE_URL="sqlite:///:memory:",
        QDRANT_URL="https://production-sentinel.invalid",
        QDRANT_API_KEY="test-sentinel-not-a-secret",
        QDRANT_COLLECTION_NAME="production_chunks",
        SEMANTIC_CACHE_COLLECTION_NAME="production_cache",
        OPENAI_API_KEY="test-sentinel-not-a-secret",
        LIBRARIAN_API_KEY="test-sentinel-not-a-secret",
        RESEND_API_KEY="test-sentinel-not-a-secret",
        RESEND_INBOUND_API_KEY="test-sentinel-not-a-secret",
    )
    env["qdrant_url"] = "https://lowercase-sentinel.invalid"
    if source == "dotenv":
        for key in list(env):
            if key.upper().startswith(("QDRANT_", "SEMANTIC_CACHE_")):
                del env[key]
    # Also exercise values originating in .env, rather than just the shell.
    (tmp_path / ".env").write_text(
        'QDRANT_URL=https://dotenv-sentinel.invalid\n'
        'QDRANT_API_KEY=test-dotenv-not-a-secret\n'
        'SEMANTIC_CACHE_ENABLED=true\n'
    )
    (tmp_path / "tests").mkdir()
    completed = subprocess.run(  # noqa: S603 - fixed local probe, no user input
        [sys.executable, "-c", probe, str(ROOT)],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=45,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "enabled cache recreate/write/read" in completed.stdout


@pytest.mark.unit
def test_late_installation_fails_instead_of_claiming_cached_settings_are_safe():
    probe = (
        "import sys; sys.modules['app.core.config'] = object(); "
        "from scripts.pytest_isolation import install; install()"
    )
    result = subprocess.run(  # noqa: S603 - fixed local probe
        [sys.executable, "-c", probe], cwd=ROOT, text=True,
        capture_output=True, timeout=15,
    )
    assert result.returncode != 0
    assert "before application settings" in result.stderr
