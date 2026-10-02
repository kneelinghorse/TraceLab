"""S64-VENDOR: immutable structural parity and strict preview runtime boundary."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.contract_compiler import (
    compile_canonical_contract_from_state,
    compile_contract_from_state,
)
from app.services.contract_compiler.compiler_provenance import (
    build_contract_compiler_manifest,
    canonical_json,
)
from app.services.contract_compiler.scope import ScopeAdmission, compile_authored_scope
from app.services.deepsearch_preview_client import (
    _build_preview_state,
    build_mission_context_from_mission,
)

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/authored_scope_v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())
STATE = json.loads((FIXTURES / "canonical-input.json").read_text())


def test_all_immutable_upstream_bytes_and_local_source_provenance():
    for filename, expected in MANIFEST["file_sha256"].items():
        assert hashlib.sha256((FIXTURES / filename).read_bytes()).hexdigest() == expected
    provenance = build_contract_compiler_manifest(enrichment_mode="none")
    assert provenance["source_revision"] == "79ef84842fb84259bafe59924b21fe2f5ad05d7d"
    assert provenance["source_dirty"] is False
    assert provenance["compiler_revision"] == 3
    assert len(provenance["required_source_files"]) == 6
    assert provenance["enrichment"] == {"mode": "none", "backend": None, "model": None}


def test_canonical_contract_matches_every_byte_without_field_exclusions():
    contract = compile_canonical_contract_from_state(STATE)
    assert canonical_json(contract).encode() == (FIXTURES / "canonical-contract.json").read_bytes()
    assert contract.contract_id == "8ca1ebfaa604dc7e"
    assert contract.contract_schema_version == "1.2"
    assert contract.compiler_revision == 3


def test_authoring_adapter_reconciles_worker_semantic_defaults():
    authored = json.loads((FIXTURES / "postgresql-authored.json").read_text())
    state = _build_preview_state(build_mission_context_from_mission(SimpleNamespace(**authored)))
    # Ignore no contract fields: trace UUID/queue timestamps are transport-only.
    assert canonical_json(compile_canonical_contract_from_state(state)) == (
        FIXTURES / "canonical-contract.json"
    ).read_text()
    assert state["min_loops"] == 2
    assert state["max_loops"] == 3
    assert state["depth_config"] == {}
    assert state["project_id"] is None
    assert state["research_depth"] == "baseline"


@pytest.mark.parametrize("minimum", [0, 1, 4])
def test_preview_preserves_explicit_minimum_instead_of_truthy_default(minimum):
    assert _build_preview_state({"min_loops": minimum})["min_loops"] == minimum


@pytest.mark.parametrize("change", ["url", "bound"])
def test_authored_page_or_bound_changes_contract_identity(change):
    state = copy.deepcopy(STATE)
    if change == "url":
        state["mission_context"]["references"][0]["url"] = "https://www.postgresql.org/docs/18/functions-datetime.html"
    else:
        state["mission_context"]["authored_scope"] = {"max_words": 450}
    assert compile_canonical_contract_from_state(state).contract_id != MANIFEST["fixture_contract_id"]


def test_seeds_domain_and_exact_pages_have_distinct_meanings():
    url = "https://www.postgresql.org/docs/current/functions-datetime.html"
    seed = {"references": [{"url": url}], "background": "Use only example.com"}
    assert compile_authored_scope(seed).restriction == "unrestricted"
    domains = compile_authored_scope({**seed, "authored_scope": {"restriction": "domains", "allowed_domains": ["postgresql.org"]}})
    exact = compile_authored_scope({**seed, "authored_scope": {"restriction": "exact_pages", "allowed_urls": [url]}})
    assert domains.allows("https://www.postgresql.org/docs/18/functions-datetime.html")
    assert not exact.allows("https://www.postgresql.org/docs/18/functions-datetime.html")
    assert not exact.allows(url.replace("www.", ""))
    assert compile_authored_scope({"objective": "A short interesting note"}).max_words is None


@pytest.mark.parametrize("scope", [
    {"min_words": 501, "max_words": 500},
    {"restriction": "exact_pages", "allowed_urls": []},
    {"restriction": "exact_pages", "allowed_urls": ["not-a-url"]},
    {"max_sources": 0},
    {"max_words": "500"},
    {"invented_bound": 2},
])
def test_invalid_scope_fails_before_extraction(scope, monkeypatch):
    from app.services.contract_compiler import contract as compiler

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid scope reached entity extraction")

    monkeypatch.setattr(compiler, "_extract_named_entities", forbidden)
    with pytest.raises(ValueError):
        compile_canonical_contract_from_state({"mission_context": {"authored_scope": scope}})


@pytest.mark.parametrize("case", MANIFEST["actions"], ids=lambda case: case["name"])
def test_eight_shared_admission_cases_use_upstream_policy_without_worker(case):
    scope = compile_canonical_contract_from_state(STATE).authored_scope
    admission = ScopeAdmission(scope)
    for url in case["already_consulted"]:
        assert admission.admit(url, "fixture")
    result = (admission.search_refusal(case["tool"], case["input"])
              if case["tool"] in {"web_search", "scholar_search"}
              else admission.refusal(case["input"]))
    assert result == case["refusal"]


def test_configured_mode_is_unavailable_even_if_worker_is_installed():
    with pytest.raises(ValueError, match="enrichment mode"):
        compile_contract_from_state(STATE, origin="preview", enrichment_mode="configured")
    with pytest.raises(ValueError, match="enrichment mode"):
        build_contract_compiler_manifest(enrichment_mode="configured")


@pytest.mark.parametrize("hostile_package", [False, True], ids=["clean", "hostile-installed"])
def test_fresh_preview_process_cannot_import_runtime_or_perform_io(tmp_path, hostile_package):
    if hostile_package:
        package = tmp_path / "deepsearch"
        package.mkdir()
        (package / "__init__.py").write_text('raise AssertionError("DeepSearch runtime imported")')
    # The hook is installed before importing the compiler/preview facade. It
    # rejects runtime imports, network/DNS, subprocesses, and all file writes.
    script = r'''
import builtins, json, sys
from types import SimpleNamespace
real_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in {'deepsearch', 'openai', 'httpx', 'smtplib', 'qdrant_client', 'redis'}:
        raise AssertionError('Runtime import: ' + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
def audit(event, args):
    if event.startswith(('socket.', 'subprocess.', 'smtplib.')):
        raise AssertionError('External IO: ' + event)
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & 0x643):
            raise AssertionError('File write: ' + str(args[0]))
sys.addaudithook(audit)
from app.services.deepsearch_preview_client import preview_mission_contract
from app.services.contract_compiler.compiler_provenance import build_contract_compiler_manifest
for entities in (None, [], ['NASA', 'PyTorch']):
    mission = SimpleNamespace(mission_id='offline', title='Compare NASA and PyTorch', objective='Compare NASA and PyTorch', success_criteria=[], deliverables=[], required_entities=entities)
    result = preview_mission_contract(mission)
    assert result.named_entities == ['NASA', 'PyTorch']
assert build_contract_compiler_manifest(enrichment_mode='none')['source_dirty'] is False
print('offline preview accepted')
'''
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT)]), "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "offline preview accepted"
