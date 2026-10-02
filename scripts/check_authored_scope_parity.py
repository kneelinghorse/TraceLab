"""Verify the pinned offline compiler and all immutable fixture bytes.

Run: python -m scripts.check_authored_scope_parity (JSON receipt on stdout).
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import patch

from app.services.contract_compiler import compile_canonical_contract_from_state
from app.services.contract_compiler.compiler_provenance import canonical_json


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/authored_scope_v1"
    manifest = json.loads((fixture / "manifest.json").read_text())
    hashes = {name: hashlib.sha256((fixture / name).read_bytes()).hexdigest()
              for name in manifest["file_sha256"]}
    if hashes != manifest["file_sha256"]:
        raise RuntimeError("Immutable fixture bytes differ from upstream manifest")
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")), patch.object(
        socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")
    ):
        contract = compile_canonical_contract_from_state(json.loads((fixture / "canonical-input.json").read_text()))
        canonical = canonical_json(contract).encode()
    if canonical != (fixture / "canonical-contract.json").read_bytes():
        raise RuntimeError("Canonical contract differs; no field exclusions permitted")
    print(json.dumps({
        "fixture_version": manifest["fixture_version"], "contract_id": contract.contract_id,
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "schema": contract.contract_schema_version, "semantic_compiler_revision": contract.compiler_revision,
        "source_manifest": json.loads((root / "app/services/contract_compiler/vendor-manifest.json").read_text()),
        "fixtures_sha256": hashes, "fidelity": "structural_only", "worker_delivery_proven": False,
    }, indent=2))


if __name__ == "__main__":
    main()
