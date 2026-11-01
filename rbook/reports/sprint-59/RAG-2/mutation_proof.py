"""RAG-2 mutation proof: each fix, reverted on its own, turns its own test red.

Run from the repository root with the project interpreter:

    .venv/bin/python cmos/reports/sprint-59/RAG-2/mutation_proof.py

For every mutation the script rewrites app/services/rag_service.py with one fix
reverted, runs the three RAG-2 tests in a fresh pytest process that writes no
bytecode, and puts the file back. It refuses to start unless the file matches
HEAD and checks that it matches HEAD again at the end.

M1 and M2 restore code byte-for-byte from the pre-fix file (each restored
snippet is asserted to occur exactly once in BASE). M3 restores the fallback
through the new one-argument _build_citation, which builds the same dict for a
retrieved chunk that the old three-argument call built.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # cmos/reports/sprint-59/RAG-2 -> repository root
TARGET = "app/services/rag_service.py"
BASE = "659a08a"  # main before RAG-2

TESTS = {
    "T1 empty retrieval": "tests/test_rag_service.py::test_empty_retrieval_returns_nothing_found_without_asking_the_model",
    "T2 unresolved label": "tests/test_rag_service.py::test_citation_to_an_unretrieved_document_is_dropped",
    "T3 no fallback": "tests/test_rag_service.py::test_uncited_answer_gets_no_citation_to_the_top_chunk",
}

FIXED_SHORT_CIRCUIT = '''            threshold=self.compression_threshold,
        )

        if not compressed_chunks:
            # Nothing to cite, so nothing is asserted: the model is not asked. The
            # result also skips the semantic cache, where it would hide a document
            # indexed later for the cache's whole TTL.
            return self._no_evidence_result(
                search_mode=normalized_mode,
                project_id=project_id,
                compression=compression_metrics,
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        graph_context = None
'''
BASE_NO_SHORT_CIRCUIT = '''            threshold=self.compression_threshold,
        )

        graph_context = None
'''

FIXED_BUILD_MESSAGES = '''        """Compose chat messages incorporating retrieved context.

        Only called with at least one chunk: an empty retrieval returns the
        nothing-found result before any prompt is built.
        """
        context_blocks = []
        for chunk in chunks:
            document_id = chunk.get("document_id") or "Unknown"
            chunk_index = chunk.get("chunk_index")
            chunk_label = f"[Document: {document_id}, Chunk: {chunk_index if chunk_index is not None else 'N/A'}]"
            content = (chunk.get("content") or "").strip()
            context_blocks.append(f"{chunk_label}\\n{content}")
        context_text = "\\n\\n".join(context_blocks)
'''
BASE_BUILD_MESSAGES = '''        """Compose chat messages incorporating retrieved context."""
        if chunks:
            context_blocks = []
            for chunk in chunks:
                document_id = chunk.get("document_id") or "Unknown"
                chunk_index = chunk.get("chunk_index")
                chunk_label = f"[Document: {document_id}, Chunk: {chunk_index if chunk_index is not None else 'N/A'}]"
                content = (chunk.get("content") or "").strip()
                context_blocks.append(f"{chunk_label}\\n{content}")
            context_text = "\\n\\n".join(context_blocks)
        else:
            context_text = (
                "No relevant context was retrieved. If the query cannot be answered, "
                "state that the repository does not contain sufficient information."
            )
'''

FIXED_APPEND = '''            chunk = self._match_chunk(document_label, chunk_label, chunks)
            if chunk is not None:
                citations.append(self._build_citation(chunk))
'''
BASE_APPEND = '''            chunk = self._match_chunk(document_label, chunk_label, chunks)
            citations.append(self._build_citation(chunk, document_label, chunk_label))
'''

FIXED_BUILD_CITATION = '''    @staticmethod
    def _build_citation(chunk: dict[str, Any]) -> dict[str, Any]:
        """Create a structured citation payload for a retrieved chunk."""
        content = chunk.get("content")
        return {
            "document_id": chunk.get("document_id"),
            "chunk_id": chunk.get("chunk_id"),
            "chunk_index": chunk.get("chunk_index"),
            "source_type": chunk.get("source_type"),
            "score": chunk.get("score"),
            "snippet": content[:280] if content else None,
        }
'''
BASE_BUILD_CITATION = '''    @staticmethod
    def _build_citation(
        chunk: dict[str, Any] | None,
        document_label: str,
        chunk_label: str,
    ) -> dict[str, Any]:
        """Create a structured citation payload."""
        chunk_index: int | None = None
        if chunk is not None:
            chunk_index = chunk.get("chunk_index")
        else:
            try:
                chunk_index = int(chunk_label)
            except (ValueError, TypeError):
                chunk_index = None

        return {
            "document_id": (
                chunk.get("document_id")
                if chunk is not None
                else (document_label or None)
            ),
            "chunk_id": chunk.get("chunk_id") if chunk is not None else None,
            "chunk_index": chunk_index,
            "source_type": chunk.get("source_type") if chunk is not None else None,
            "score": chunk.get("score") if chunk is not None else None,
            "snippet": (
                chunk.get("content")[:280]
                if chunk is not None and chunk.get("content")
                else None
            ),
        }
'''

FIXED_RETURN = '''            if chunk is not None:
                citations.append(self._build_citation(chunk))

        return citations
'''
FALLBACK_RETURN = '''            if chunk is not None:
                citations.append(self._build_citation(chunk))

        if not citations and chunks:
            # Provide a fallback citation anchored to the highest-scoring chunk.
            top_chunk = chunks[0]
            citations.append(self._build_citation(top_chunk))

        return citations
'''

MUTATIONS = [
    {
        "id": "M1",
        "reverts": "empty-retrieval short-circuit (the model is asked with no context again)",
        "expect_red": "T1 empty retrieval",
        "verbatim_in_base": True,
        "replacements": [
            (FIXED_SHORT_CIRCUIT, BASE_NO_SHORT_CIRCUIT),
            (FIXED_BUILD_MESSAGES, BASE_BUILD_MESSAGES),
        ],
    },
    {
        "id": "M2",
        "reverts": "dropping unresolved labels (a label becomes a citation with chunk_id None again)",
        "expect_red": "T2 unresolved label",
        "verbatim_in_base": True,
        "replacements": [
            (FIXED_APPEND, BASE_APPEND),
            (FIXED_BUILD_CITATION, BASE_BUILD_CITATION),
        ],
    },
    {
        "id": "M3",
        "reverts": "removal of the top-chunk fallback citation",
        "expect_red": "T3 no fallback",
        "verbatim_in_base": False,
        "replacements": [(FIXED_RETURN, FALLBACK_RETURN)],
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
            outcome[name] = "FAIL at " + _failing_assertion(lines, node.split("::")[1])
        else:
            outcome[name] = "missing"
    return {"label": label, "pytest_exit": proc.returncode, "tests": outcome}


def _failing_assertion(lines: list[str], test_name: str) -> str:
    """The failing statement and pytest's first explanation line for one test."""
    start = next(i for i, line in enumerate(lines) if line.startswith("_") and f" {test_name} " in line)
    statement = next(line for line in lines[start:] if line.startswith(">"))
    explanation = next(line for line in lines[start:] if line.startswith("E "))
    return f"{statement[1:].strip()} ({explanation[1:].strip()})"


def main() -> int:
    if git("status", "--porcelain", "--", TARGET).strip():
        print(f"ABORT: {TARGET} differs from HEAD; commit the fix first")
        return 1
    target = REPO / TARGET
    fixed = target.read_text()
    base = git("show", f"{BASE}:{TARGET}")
    runs = []
    try:
        runs.append(run_tests("baseline-before"))
        for mutation in MUTATIONS:
            text = fixed
            for old, new in mutation["replacements"]:
                if text.count(old) != 1:
                    raise RuntimeError(f"{mutation['id']}: fixed snippet is not unique")
                if mutation["verbatim_in_base"] and base.count(new) != 1:
                    raise RuntimeError(f"{mutation['id']}: revert is not verbatim pre-fix code")
                text = text.replace(old, new)
            target.write_text(text)
            run = run_tests(mutation["id"])
            run["reverts"] = mutation["reverts"]
            run["expect_red"] = mutation["expect_red"]
            runs.append(run)
            target.write_text(fixed)
        runs.append(run_tests("baseline-after"))
    finally:
        target.write_text(fixed)

    restored = not git("status", "--porcelain", "--", TARGET).strip()
    verdicts = []
    for run in runs:
        red = {name for name, outcome in run["tests"].items() if outcome != "pass"}
        expected = {run["expect_red"]} if "expect_red" in run else set()
        run["as_expected"] = red == expected
        verdicts.append(run["as_expected"])
    report = {
        "head": git("rev-parse", "HEAD").strip(),
        "base": BASE,
        "file_restored_to_head": restored,
        "all_as_expected": all(verdicts) and restored,
        "runs": runs,
    }
    (HERE / "mutation-proof.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["all_as_expected"] else 1


if __name__ == "__main__":
    sys.exit(main())
