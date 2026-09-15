"""The foundational-reference guard must flag stale docs/ paths without tripping on foundational-docs/ paths.

Commit 7ec2c02 recorded a real false positive: the forbidden string
``docs/technical_architecture.md`` matched inside the legitimate
``cmos/foundational-docs/technical_architecture.md``, and the fix at the time
was to reword CMOS text. Both entry points (the standalone script and
``./cmos/cli.py validate docs``) must share one boundary-aware matcher.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ["docs/roadmap.md", "docs/technical_architecture.md"]
NOT_FLAGGED = [
    "cmos/foundational-docs/technical_architecture.md",
    "foundational-docs/roadmap_template.md",
    "cmos/foundational-docs/roadmap.md",
]
FLAGGED = [
    "docs/technical_architecture.md",
    "`cmos/docs/technical_architecture.md`",
    "./docs/roadmap.md",
    "docs/roadmap.md.",
]


def _load(relative: str, name: str):
    """Load a cmos script or module by path, the way tests/conftest.py loads the telemetry plugin."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load("cmos/scripts/validate_foundational_refs.py", "validate_foundational_refs_under_test")


@pytest.fixture(scope="module")
def shared():
    return _load("cmos/context/foundational_refs.py", "foundational_refs_under_test")


def _check(script, tmp_path: Path, text: str) -> list[str]:
    target = tmp_path / "doc.md"
    target.write_text(f"See {text} for details.\n", encoding="utf-8")
    return script.validate_file(target, [], FORBIDDEN)


@pytest.mark.unit
@pytest.mark.parametrize("text", NOT_FLAGGED)
def test_legitimate_foundational_paths_are_not_flagged(script, tmp_path, text):
    assert _check(script, tmp_path, text) == []


@pytest.mark.unit
@pytest.mark.parametrize("text", FLAGGED)
def test_stale_docs_paths_are_flagged(script, tmp_path, text):
    errors = _check(script, tmp_path, text)
    assert len(errors) == 1 and "contains forbidden reference" in errors[0]


@pytest.mark.unit
def test_required_references_are_still_enforced(script, tmp_path):
    target = tmp_path / "doc.md"
    target.write_text("nothing here\n", encoding="utf-8")
    errors = script.validate_file(target, ["foundational-docs/roadmap_template.md"], [])
    assert errors == [f"{target}: missing required reference 'foundational-docs/roadmap_template.md'"]


@pytest.mark.unit
def test_script_and_cli_share_one_matcher(script, shared):
    """Both entry points must consume the shared rules, not private copies of them."""
    assert set(script.CHECKS) == {Path("agents.md"), Path("README.md"), Path("context/MASTER_CONTEXT.json")}
    assert script.CHECKS == shared.FOUNDATIONAL_CHECKS
    cli_source = (REPO_ROOT / "cmos" / "cli.py").read_text(encoding="utf-8")
    assert "from context.foundational_refs import" in cli_source
    assert "FOUNDATIONAL_CHECKS = {" not in cli_source
    assert "if needle in content" not in cli_source
    for text in NOT_FLAGGED:
        assert not shared.contains_forbidden(f"path {text} here", FORBIDDEN)
    for text in FLAGGED:
        assert shared.contains_forbidden(f"path {text} here", FORBIDDEN)
