"""RAG-3 mutation proof: each fix, reverted on its own, turns its own tests red.

Run from the repository root with the project interpreter:

    .venv/bin/python cmos/reports/sprint-59/RAG-3/mutation_proof.py

For every mutation the script rewrites one source file with one fix reverted to
the pre-fix code, runs the six RAG-3 tests in a fresh pytest process that writes
no bytecode, and puts the file back. It refuses to start unless every target
file matches HEAD, and checks that they match HEAD again at the end. Each
restored snippet is asserted to occur exactly once in BASE, main before RAG-3.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # cmos/reports/sprint-59/RAG-3 -> repository root
BASE = "7167a93"  # main before RAG-3
FUSION = "app/services/pedr/fusion.py"
RAG = "app/services/rag_service.py"
ORCHESTRATOR = "app/services/pedr/search_orchestrator.py"
TARGETS = (FUSION, RAG, ORCHESTRATOR)

TESTS = {
    "T1 fusion keeps text": "tests/test_pedr_unified_search.py::TestRRFFusion::test_graph_ranked_chunk_keeps_the_semantic_text_and_ids",
    "T2 search response keeps text": "tests/test_pedr_unified_search.py::TestPEDRSearchOrchestrator::test_graph_ranked_chunk_reaches_the_response_with_its_text",
    "T3 hollow chunk left out": "tests/test_rag_service.py::test_chunk_without_text_never_reaches_the_model",
    "T4 no text is nothing found": "tests/test_rag_service.py::test_retrieval_with_no_text_returns_nothing_found_without_asking_the_model",
    "T5 unfiltered None scope, no query": "tests/test_pedr_search_scope.py::test_graph_none_scope_without_filters_adds_no_resolver",
    "T6 filter holds for owner": "tests/test_pedr_search_scope.py::test_explicit_filters_apply_to_graph_results_for_an_unrestricted_caller",
}

FIXED_FUSION_COLLECT = '''        # Collect all unique result IDs and their layer contributions
        # id -> [(rank, record)], one entry per layer that returned it
        layer_records: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        layer_ranks: dict[str, dict[str, int]] = {}  # id -> {layer: rank}
        layer_scores: dict[str, dict[str, float]] = {}  # id -> {layer: score}

        for layer in layer_results:
            layer_name = layer.layer_name
            weight = self.config.layer_weights.get(layer_name, layer.weight)

            for rank_idx, result in enumerate(layer.results, start=1):
                result_id = self._extract_id(result, id_key)
                if not result_id:
                    continue

                # Initialize tracking dicts for this ID
                if result_id not in layer_ranks:
                    layer_ranks[result_id] = {}
                    layer_scores[result_id] = {}
                    layer_records[result_id] = []

                # Store rank and score
                layer_ranks[result_id][layer_name] = rank_idx
                layer_scores[result_id][layer_name] = float(
                    result.get("score") or result.get("combined_score") or 0.0
                )
                layer_records[result_id].append((rank_idx, result))

        # One record per ID: the best-ranked layer's, with every field it lacks
        # filled from the other layers
        result_data = {
            result_id: _merge_layer_records(records)
            for result_id, records in layer_records.items()
        }
'''
BASE_FUSION_COLLECT = '''        # Collect all unique result IDs and their layer contributions
        result_data: dict[str, dict[str, Any]] = {}  # id -> best result data
        layer_ranks: dict[str, dict[str, int]] = {}  # id -> {layer: rank}
        layer_scores: dict[str, dict[str, float]] = {}  # id -> {layer: score}

        for layer in layer_results:
            layer_name = layer.layer_name
            weight = self.config.layer_weights.get(layer_name, layer.weight)

            for rank_idx, result in enumerate(layer.results, start=1):
                result_id = self._extract_id(result, id_key)
                if not result_id:
                    continue

                # Initialize tracking dicts for this ID
                if result_id not in layer_ranks:
                    layer_ranks[result_id] = {}
                    layer_scores[result_id] = {}
                    result_data[result_id] = {}

                # Store rank and score
                layer_ranks[result_id][layer_name] = rank_idx
                layer_scores[result_id][layer_name] = float(
                    result.get("score") or result.get("combined_score") or 0.0
                )

                # Keep best (lowest rank) result data
                if not result_data[result_id] or rank_idx < min(
                    layer_ranks[result_id].get(ln, float("inf"))
                    for ln in layer_ranks[result_id]
                    if ln != layer_name
                ):
                    result_data[result_id] = dict(result)
'''

FIXED_RAG_FILTER = '''            for r in pedr_response.results
            if (r.content or "").strip()
        ]
'''
BASE_RAG_FILTER = '''            for r in pedr_response.results
        ]
'''

FIXED_GRAPH_SCOPE_ENTRY = '''    """Scope graph payloads using authoritative chunk ownership in one query.

    Graph expansion follows edges across projects, so an explicit project or
    document filter applies here for every caller. The authorization scope
    applies only when there is one: with a None scope and no filter, the
    payloads pass through untouched.
    """
    if allowed_project_scope is None and project_id is None and document_id is None:
        return results
    if allowed_project_scope == () or not results:
        return []

    allowed = set(allowed_project_scope) if allowed_project_scope is not None else None
'''
BASE_GRAPH_SCOPE_ENTRY = '''    """Scope graph payloads using authoritative chunk ownership in one query."""
    if allowed_project_scope is None:
        return results
    if allowed_project_scope == () or not results:
        return []

    allowed = set(allowed_project_scope)
'''
FIXED_GRAPH_SCOPE_CHECK = '''        if allowed is not None and resolved_project_id not in allowed:
'''
BASE_GRAPH_SCOPE_CHECK = '''        if resolved_project_id not in allowed:
'''

MUTATIONS = [
    {
        "id": "M1",
        "target": FUSION,
        "reverts": "the fusion merge (the best-ranked layer's record is kept whole again)",
        "expect_red": ["T1 fusion keeps text", "T2 search response keeps text"],
        "replacements": [(FIXED_FUSION_COLLECT, BASE_FUSION_COLLECT)],
    },
    {
        "id": "M2",
        "target": RAG,
        "reverts": "leaving chunks with no text out of the model's context",
        "expect_red": ["T3 hollow chunk left out", "T4 no text is nothing found"],
        "replacements": [(FIXED_RAG_FILTER, BASE_RAG_FILTER)],
    },
    {
        "id": "M3",
        "target": ORCHESTRATOR,
        "reverts": "explicit filters on graph results for a None scope (it returns them unfiltered again)",
        "expect_red": ["T6 filter holds for owner"],
        "replacements": [
            (FIXED_GRAPH_SCOPE_ENTRY, BASE_GRAPH_SCOPE_ENTRY),
            (FIXED_GRAPH_SCOPE_CHECK, BASE_GRAPH_SCOPE_CHECK),
        ],
    },
]


def git(*args: str) -> str:
    # noqa S603/S607: fixed git argv chosen by this script, never external input.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def run_tests(label: str) -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # noqa S603: fixed pytest argv run through the current interpreter.
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-B", "-m", "pytest", *TESTS.values(), "-p", "no:cacheprovider", "-rA", "-q"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )
    (HERE / "mutation-logs").mkdir(exist_ok=True)
    (HERE / "mutation-logs" / f"{label}.txt").write_text(proc.stdout + proc.stderr)
    lines = proc.stdout.splitlines()
    outcome = {}
    for name, node in TESTS.items():
        if any(line.startswith(f"PASSED {node}") for line in lines):
            outcome[name] = "pass"
        elif any(line.startswith(f"FAILED {node}") for line in lines):
            outcome[name] = "FAIL at " + _failing_assertion(lines, node.rsplit("::", 1)[1])
        else:
            outcome[name] = "missing"
    return {"label": label, "pytest_exit": proc.returncode, "tests": outcome}


def _failing_assertion(lines: list[str], test_name: str) -> str:
    """The failing statement and pytest's first explanation line for one test."""
    start = next(i for i, line in enumerate(lines) if line.startswith("_") and f"{test_name} " in line)
    statement = next(line for line in lines[start:] if line.startswith(">"))
    explanation = next(line for line in lines[start:] if line.startswith("E "))
    return f"{statement[1:].strip()} ({explanation[1:].strip()})"


def main() -> int:
    if git("status", "--porcelain", "--", *TARGETS).strip():
        print("ABORT: a target file differs from HEAD; commit the fix first")
        return 1
    fixed = {target: (REPO / target).read_text() for target in TARGETS}
    base = {target: git("show", f"{BASE}:{target}") for target in TARGETS}
    runs = []
    try:
        runs.append(run_tests("baseline-before"))
        for mutation in MUTATIONS:
            target = mutation["target"]
            text = fixed[target]
            for old, new in mutation["replacements"]:
                if text.count(old) != 1:
                    raise RuntimeError(f"{mutation['id']}: fixed snippet is not unique")
                if base[target].count(new) != 1:
                    raise RuntimeError(f"{mutation['id']}: revert is not verbatim pre-fix code")
                text = text.replace(old, new)
            (REPO / target).write_text(text)
            run = run_tests(mutation["id"])
            run["target"] = target
            run["reverts"] = mutation["reverts"]
            run["expect_red"] = mutation["expect_red"]
            runs.append(run)
            (REPO / target).write_text(fixed[target])
        runs.append(run_tests("baseline-after"))
    finally:
        for target, text in fixed.items():
            (REPO / target).write_text(text)

    restored = not git("status", "--porcelain", "--", *TARGETS).strip()
    verdicts = []
    for run in runs:
        red = {name for name, outcome in run["tests"].items() if outcome != "pass"}
        run["as_expected"] = red == set(run.get("expect_red", []))
        verdicts.append(run["as_expected"])
    report = {
        "head": git("rev-parse", "HEAD").strip(),
        "base": BASE,
        "files_restored_to_head": restored,
        "all_as_expected": all(verdicts) and restored,
        "runs": runs,
    }
    (HERE / "mutation-proof.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["all_as_expected"] else 1


if __name__ == "__main__":
    sys.exit(main())
