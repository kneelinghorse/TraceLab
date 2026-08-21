"""Regression guards for the documented, published TraceLab MCP install path."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_README = ROOT / "packages" / "tracelab-mcp" / "README.md"
ENVIRONMENT_GUIDE = ROOT / "docs" / "environment-setup.md"
MCP_GUIDE = ROOT / "docs" / "mcp-tools.md"

URL_ASSIGNMENT = re.compile(r'TRACELAB_API_URL"?\s*(?::|=|\s)\s*"?(https?://[^"\s]+)')
FENCED_CODE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def test_documented_mcp_launchers_use_stdio_and_host_only_api_urls() -> None:
    """Prevent the frontend/SSE and double-/api/v1 install failures."""
    documents = {path: path.read_text(encoding="utf-8") for path in (MCP_README, ENVIRONMENT_GUIDE, MCP_GUIDE)}

    allowed_urls = {
        "http://localhost:8000",
        "https://api.tracelab.aquex.ai",
    }
    documented_urls = {url for document in documents.values() for url in URL_ASSIGNMENT.findall(document)}

    assert documented_urls
    assert documented_urls <= allowed_urls

    for document in documents.values():
        code_examples = "\n".join(FENCED_CODE.findall(document))
        assert "npx" in code_examples
        assert "@aquex/tracelab-mcp" in code_examples
        assert "https://aquex.ai/mcp" not in code_examples

    assert 'TRACELAB_API_URL = "https://api.tracelab.aquex.ai"' in documents[MCP_README]
    assert '"TRACELAB_API_URL": "https://api.tracelab.aquex.ai"' in documents[ENVIRONMENT_GUIDE]
