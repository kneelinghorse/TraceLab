"""RAG-4 mutation proof: each fix, reverted on its own, turns its own tests red.

Run from the repository root with the project interpreter:

    .venv/bin/python cmos/reports/sprint-59/RAG-4/mutation_proof.py

For every mutation the script rewrites one source file with one fix reverted to
the pre-fix code, runs the RAG-4 tests in a fresh pytest process that writes no
bytecode, and puts the file back. It refuses to start unless every target file
matches HEAD, and checks that they match HEAD again at the end. Each restored
snippet is asserted to occur exactly once in BASE, main before RAG-4.

The compression test reads the setting's code default, not the environment,
because production runs the default (Railway does not set RAG_CONTEXT_THRESHOLD)
and a local .env would otherwise decide the outcome.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # cmos/reports/sprint-59/RAG-4 -> repository root
BASE = "78bbc7e"  # main before RAG-4
GRAPH = "app/services/pedr/graph_layer.py"
ORCHESTRATOR = "app/services/pedr/search_orchestrator.py"
CONFIG = "app/core/config.py"
TARGETS = (GRAPH, ORCHESTRATOR, CONFIG)

TESTS = {
    "T1 best match first, production shape": "tests/test_graph_layer.py::test_best_match_keeps_first_place_over_its_graph_neighbours",
    "T2 seeds in retrieval order": "tests/test_graph_layer.py::test_seeds_lead_the_ranking_in_retrieval_order",
    "T3 e2e seeds keep the top five": "tests/test_graph_e2e_validation.py::TestGraphSearchE2EValidation::test_graph_never_moves_a_chunk_above_its_seeds",
    "T4 updated: depth boundary [1]": "tests/test_graph_layer.py::test_depth_boundary_keeps_candidates_without_reading_their_edges[1]",
    "T5 updated: depth boundary [2]": "tests/test_graph_layer.py::test_depth_boundary_keeps_candidates_without_reading_their_edges[2]",
    "T6 updated: cycle handling": "tests/test_graph_layer.py::test_cycle_handling",
    "T7 graph still surfaces missed chunks": "tests/test_graph_e2e_validation.py::TestGraphSearchE2EValidation::test_graph_impacts_results",
    "T8 expanded count, integration": "tests/integration/test_graph_search.py::test_orchestrator_graph_candidates_expanded",
    "T9 production similarities reach the model": "tests/test_context_compression.py::test_production_similarities_reach_the_model_and_unrelated_chunks_do_not",
}

FIXED_GRAPH_CALL = """        results = self._build_results(
            session, candidates, config.max_candidates, seeds, seed_scores
        )
"""
BASE_GRAPH_CALL = """        results = self._build_results(session, candidates, config.max_candidates)
"""
FIXED_GRAPH_RANKING = """        max_candidates: int,
        seeds: Sequence[str],
        seed_scores: dict[str, float],
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        # Seeds rank first, in the order retrieval gave them, then the candidates
        # reached from them, by score. Left out, a seed's neighbours took a graph
        # share on top of their own retrieval rank and fusion put them above the
        # best match they were reached from. Position, not score, orders the seeds
        # because seed scores mix scales (lexical ts_rank_cd, semantic cosine).
        ranked = [
            (seed, CandidateInfo(seed_scores.get(seed, 1.0), 0, seed, None))
            for seed in seeds
        ]
        ranked += sorted(
            candidates.items(),
            key=lambda item: (-item[1].score, item[0]),
        )

        chunk_urns = {urn for urn, _ in ranked if URNParser.parse_chunk_urn(urn)}
        chunk_id_map = self._resolve_chunk_urns(session, chunk_urns)

        results: list[dict[str, Any]] = []
        for urn, info in ranked[:max_candidates]:
"""
BASE_GRAPH_RANKING = """        max_candidates: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        chunk_urns = {urn for urn in candidates if URNParser.parse_chunk_urn(urn)}
        chunk_id_map = self._resolve_chunk_urns(session, chunk_urns)

        sorted_candidates = sorted(
            candidates.items(),
            key=lambda item: (-item[1].score, item[0]),
        )
        results: list[dict[str, Any]] = []
        for urn, info in sorted_candidates[:max_candidates]:
"""

FIXED_EXPANDED_COUNT = """                # The graph layer also ranks its seeds (depth 0); only reached
                # chunks count as expanded.
                graph_layer.metadata["total_candidates"] = sum(
                    1 for entry in graph_layer.results if entry.get("depth") != 0
                )
"""
BASE_EXPANDED_COUNT = """                graph_layer.metadata["total_candidates"] = len(graph_layer.results)
"""

FIXED_THRESHOLD = """    # Cosine floor for a chunk to reach the model (RAG-4, decision #541): on
    # production text-embedding-3-large gave answering chunks 0.425-0.664 and
    # unrelated ones 0.399 at most, so 0.7 let only compression's one survivor through.
    rag_context_threshold: float = 0.4
"""
BASE_THRESHOLD = """    rag_context_threshold: float = 0.7
"""

MUTATIONS = [
    {
        "id": "M1",
        "target": GRAPH,
        "reverts": "seeds ranked first in the graph layer (it ranks only the chunks it reached again)",
        "expect_red": [
            "T1 best match first, production shape",
            "T2 seeds in retrieval order",
            "T3 e2e seeds keep the top five",
            "T4 updated: depth boundary [1]",
            "T5 updated: depth boundary [2]",
            "T6 updated: cycle handling",
        ],
        "replacements": [
            (FIXED_GRAPH_CALL, BASE_GRAPH_CALL),
            (FIXED_GRAPH_RANKING, BASE_GRAPH_RANKING),
        ],
    },
    {
        "id": "M2",
        "target": ORCHESTRATOR,
        "reverts": "counting only reached chunks as expanded (the seeds are counted again)",
        "expect_red": ["T1 best match first, production shape", "T8 expanded count, integration"],
        "replacements": [(FIXED_EXPANDED_COUNT, BASE_EXPANDED_COUNT)],
    },
    {
        "id": "M3",
        "target": CONFIG,
        "reverts": "the 0.4 compression threshold (0.7 again)",
        "expect_red": ["T9 production similarities reach the model"],
        "replacements": [(FIXED_THRESHOLD, BASE_THRESHOLD)],
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
