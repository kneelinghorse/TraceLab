"""High-level CLI command tests using CliRunner."""

import json

from click.testing import CliRunner

from cli.main import cli


def test_version_command_json_output():
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "version"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["success"] is True
    assert payload["data"]["version"] == "1.0.0"


def test_health_command_uses_api_client(monkeypatch):
    calls = []

    class FakeAPIClient:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, path):
            calls.append(path)
            return {"status": "healthy"}

    monkeypatch.setattr("cli.utils.api.APIClient", FakeAPIClient)

    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "health"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data"]["status"] == "healthy"
    assert calls == ["/api/v1/health"]


def test_documents_upload_requires_process_for_wait(tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("hello")

    runner = CliRunner()
    result = runner.invoke(cli, ["documents", "upload", "proj-123", str(doc), "--wait"])

    assert result.exit_code == 2
    assert "--wait option requires --process" in result.output
