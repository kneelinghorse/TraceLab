"""Reproduce S62's saved scope boundary without network or model execution.

Run from the repository root: python -m scripts.diagnose_s62_scope
This freezes diagnostic observations, not a promise that scope enforcement works.
"""

from __future__ import annotations

import hashlib
import json
import socket
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from app.services.contract_compiler import compile_contract_from_state
from app.services.deepsearch_preview_client import (
    _build_preview_state,
    build_mission_context_from_mission,
    preview_mission_contract,
)


def require(condition: object, observation: str) -> None:
    if not condition:
        raise RuntimeError(observation)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    original = root / "cmos/reports/sprint-61/LOG-2"
    output = root / "cmos/reports/sprint-62/S62-SCOPE"
    proposed = json.loads((original / "proposed-mission.json").read_text())
    saved_preview = json.loads((original / "contract-preview.json").read_text())
    worker_preview = json.loads((original / "worker-structural-contract.json").read_text())
    readback = json.loads((output / "readback.json").read_text())
    mission = readback["mission"]
    fields = ("objective", "success_criteria", "constraints", "references", "deliverables", "deliverable_format")
    require(all(proposed[field] == mission[field] for field in fields), "persisted authoring changed")

    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")), patch.object(
        socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")
    ):
        context = build_mission_context_from_mission(SimpleNamespace(**mission))
        compiled = compile_contract_from_state(_build_preview_state(context), origin="s62_scope_no_provider")
        preview = preview_mission_contract(SimpleNamespace(**mission)).to_dict()
        require(all(value == saved_preview[key] for key, value in preview.items()), "preview differs from saved evidence")
        different_urls = {**context, "references": [{**ref, "url": "https://scope-probe.invalid/changed"} for ref in context["references"]]}
        changed = compile_contract_from_state(_build_preview_state(different_urls), origin="s62_scope_no_provider")
        require(compiled.contract_id == changed.contract_id, "exact URL now affects contract: review diagnosis")

    criterion = proposed["success_criteria"][2]
    require(criterion in compiled.success_criteria and criterion in compiled.constraints, 'Frozen observation changed: criterion in compiled.success_criteria and criterion in compiled.constraints')
    require(criterion not in [item.text for item in compiled.objectives], 'Frozen observation changed: criterion not in [item.text for item in compiled.objectives]')
    require(all(criterion not in item.description for item in compiled.acceptance_checks), 'Frozen observation changed: all(criterion not in item.description for item in compiled.acceptance_checks)')
    require(all(constraint in compiled.constraints for constraint in proposed["constraints"]), 'Frozen observation changed: all(constraint in compiled.constraints for constraint in proposed["constraints"])')
    require("word" not in " ".join(type(compiled.execution_budget).model_fields), 'Frozen observation changed: "word" not in " ".join(type(compiled.execution_budget).model_fields)')
    require(worker_preview["origin"] == "s61_log2_no_provider_preview", 'Frozen observation changed: worker_preview["origin"] == "s61_log2_no_provider_preview"')
    require(worker_preview["contract_id"] != mission["execution_metadata"]["contract_id"], 'Frozen observation changed: worker_preview["contract_id"] != mission["execution_metadata"]["contract_id"]')
    require(criterion in worker_preview["constraints"] and criterion in worker_preview["success_criteria"], 'Frozen observation changed: criterion in worker_preview["constraints"] and criterion in worker_preview["success_criteria"]')

    rendered = mission["result_markdown"]
    rendered_hash = hashlib.sha256(rendered.encode()).hexdigest()
    original_acceptance = json.loads((original / "deployed-acceptance.json").read_text())
    require(rendered_hash == original_acceptance["artifacts"]["mission_result_sha256"], 'Frozen observation changed: rendered_hash == original_acceptance["artifacts"]["mission_result_sha256"]')
    words = len(rendered.split())
    worker_words = mission["telemetry"]["report_word_count"]
    require((words, worker_words) == (2285, 2240), 'Frozen observation changed: (words, worker_words) == (2285, 2240)')
    domains = Counter(urlsplit(source["url"]).hostname for source in mission["sources_collected"])
    critique = mission["telemetry"]["critique_telemetry"]
    non_official_support = [
        {"verdict": record["verdict"], "url": evidence["url"], "evidence_id": evidence["evidence_id"]}
        for record in critique["assessment"]["records"] if record["verdict"] == "supported"
        for evidence in record["evidence"] if urlsplit(evidence["url"]).hostname not in {"postgresql.org", "www.postgresql.org"}
    ]
    require(non_official_support, "critique no longer demonstrates out-of-domain evidence")
    require(mission["telemetry"]["sources_collected"] == len(mission["sources_collected"]) == 22, 'Frozen observation changed: mission["telemetry"]["sources_collected"] == len(mission["sources_collected"]) == 22')
    require(mission["execution_metadata"]["quality_record"]["distinct_urls"] == 2, 'Frozen observation changed: mission["execution_metadata"]["quality_record"]["distinct_urls"] == 2')
    require(readback["ledger"]["entry_total"] == 24, 'Frozen observation changed: readback["ledger"]["entry_total"] == 24')
    require(mission["accounting"]["observed"]["total"] == 519007, 'Frozen observation changed: mission["accounting"]["observed"]["total"] == 519007')

    result = {
        "checks_passed": True,
        "network_or_provider_calls": 0,
        "persisted_fields_equal_proposed": list(fields),
        "local_preview_equals_saved": True,
        "exact_reference_url_change_preserves_contract_id": True,
        "word_and_source_instruction_preserved_as_prose": True,
        "word_and_source_instruction_compiled_to_required_acceptance_check": False,
        "worker_structural_preview_id": worker_preview["contract_id"],
        "executed_contract_id": mission["execution_metadata"]["contract_id"],
        "executed_contract_body_available": False,
        "rendered_result_sha256": rendered_hash,
        "word_counts": {"rendered_whitespace": words, "worker_telemetry": worker_words, "delta": words - worker_words,
                        "worker_counter_algorithm_observed": False, "both_exceed_authored_maximum": words > 500 and worker_words > 500},
        "collection": {"sources": 22, "domains": dict(sorted(domains.items())), "final_reference_urls": 2,
                       "ledger_entries": 24, "ledger_dispositions": dict(Counter(entry["disposition"] for entry in readback["ledger"]["entries"]))},
        "non_official_critique_support": non_official_support,
        "usage_tokens_not_billed_dollars": mission["accounting"]["observed"],
        "quality": mission["execution_metadata"]["final_outcome"],
    }
    (output / "reproducer.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
