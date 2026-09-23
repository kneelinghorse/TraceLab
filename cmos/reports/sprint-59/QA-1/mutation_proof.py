"""QA-1 mutation proof: each rule, disabled on its own, turns exactly its own tests red.

Run from the repository root with the project interpreter:

    .venv/bin/python cmos/reports/sprint-59/QA-1/mutation_proof.py

QA-1 is mostly new code, so a mutation disables one rule in place rather than
restoring pre-QA-1 code. For each one the script rewrites one file, runs the QA-1
backend tests in a fresh pytest process that writes no bytecode and the QA-1
frontend tests through vitest's JSON reporter, and puts the file back. Every
mutated snippet is asserted to occur exactly once. The script refuses to start
unless every target matches HEAD, and checks that they match HEAD again at the end.
A run is as expected only when the set of red tests equals its expected set.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # cmos/reports/sprint-59/QA-1 -> repository root
BASE = "fff7c27"  # main before QA-1

RAG = "app/services/rag_service.py"
SEMANTIC = "app/services/semantic_cache.py"
CACHE_KEY = "app/services/cache_manager.py"
QA = "app/services/corpus_qa.py"
LIBRARIAN = "app/services/librarian.py"
ROUTE = "app/api/v1/librarian.py"
CLIENT = "frontend/src/lib/api/librarian.ts"
PAGE = "frontend/src/pages/librarian.tsx"
DOCUMENT_PAGE = "frontend/src/pages/documents/[id].tsx"
TARGETS = (RAG, SEMANTIC, CACHE_KEY, QA, LIBRARIAN, ROUTE, CLIENT, PAGE, DOCUMENT_PAGE)

BACKEND = {
    "B1 pipeline: no answer from a chunk below the floor": "tests/test_rag_service.py::test_refusing_caller_is_not_answered_from_a_chunk_below_the_floor",
    "B2 pipeline: a cached answer below the floor is a miss": "tests/test_rag_service.py::test_refusing_caller_asks_again_when_the_cached_answer_rests_below_the_floor",
    "B3 pipeline: the model is told its budget": "tests/test_rag_service.py::test_the_model_is_told_its_answer_budget",
    "B4 application cache: a refusing caller has its own entry": "tests/test_rag_service.py::test_a_refusing_caller_never_shares_an_application_cache_entry",
    "B5 semantic cache: same budget only": "tests/test_rag_service.py::test_semantic_cache_serves_only_answers_written_for_the_same_budget",
    "B6 service: passages cite only chunks the model read": "tests/test_corpus_qa.py::test_each_passage_cites_only_chunks_the_model_read",
    "B7 service: a paragraph of labels": "tests/test_corpus_qa.py::test_a_paragraph_of_labels_lends_them_to_the_paragraph_before_it",
    "B8 service: an uncited answer is refused": "tests/test_corpus_qa.py::test_an_answer_that_cites_nothing_is_refused_not_shown",
    "B9 service: a deleted document is not cited": "tests/test_corpus_qa.py::test_a_citation_into_a_deleted_document_is_dropped",
    "B10 service: no answer outside the caller's scope": "tests/test_corpus_qa.py::TestScope::test_a_member_cannot_get_an_answer_from_a_project_they_cannot_read",
    "B11 through the pipeline: supported question answered": "tests/test_corpus_qa.py::test_through_the_pipeline_a_supported_question_is_answered_with_resolving_citations",
    "B12 through the pipeline: unsupported question refused": "tests/test_corpus_qa.py::test_through_the_pipeline_an_unsupported_question_is_refused_before_the_model",
    "B13 route: answer mode goes to the Q&A service": "tests/test_librarian_api.py::TestAnswer::test_routes_to_the_qa_service_and_renders_cited_passages",
    "B14 route: the validator accepts every rendered citation": "tests/test_librarian_api.py::TestAnswer::test_every_rendered_citation_passes_the_provenance_validator",
    "B15 route: a stray citation is withheld": "tests/test_librarian_api.py::TestAnswer::test_a_citation_the_answer_was_not_written_from_is_withheld",
    "B16 route: nothing found asserts nothing": "tests/test_librarian_api.py::TestAnswer::test_nothing_found_renders_the_refusal_and_asserts_nothing",
    "B17 route: 403 before retrieval": "tests/test_librarian_api.py::TestAnswer::test_a_project_the_user_cannot_read_is_403_before_retrieval",
    "B18 route: each paid call metered": "tests/test_librarian_api.py::TestAnswer::test_each_paid_call_is_metered_and_a_cached_answer_is_not",
    "B19 service: a label naming several chunks": "tests/test_corpus_qa.py::test_a_label_naming_several_chunks_cites_each_and_leaves_no_raw_text",
}

FRONTEND_FILES = (
    "src/lib/api/librarian.test.ts",
    "src/__tests__/librarian.test.tsx",
    "src/__tests__/document-detail.test.tsx",
)
FRONTEND = {
    "F1 client: an answer turn carries its budget": "an answer turn carries answer mode and the chosen budget",
    "F2 page: the chosen budget and chunk links": "sends the chosen budget and links each citation to the chunk it came from",
    "F3 page: short answer by default": "asks for a short answer unless the user chooses a full synthesis",
    "F4 page: the refusal is a note": "renders a refusal as a note that asserts nothing, and keeps it that way after a reload",
    "F5 page: no asking without a project": "cannot ask the documents without a project",
    "F6 document page: opens the cited chunk": "opens the Chunks tab on the page holding the chunk, expanded and marked as cited",
    "F7 document page: a missing chunk is said aloud": "says the cited chunk is gone rather than showing another passage",
    "F8 document page: the cited card's top scrolls into view": "scrolls the cited card's top into view, so its header shows even on a long chunk",
}

MUTATIONS = [
    {
        "id": "M1",
        "target": RAG,
        "disables": "the relevance floor as a refusal: a refusing caller is answered from compression's best chunk",
        "replace": (
            "        if refuse_unsupported and not self._reaches_floor(compressed_chunks):\n",
            "        if False:  # mutation M1\n",
        ),
        "expect_red": [
            "B1 pipeline: no answer from a chunk below the floor",
            "B2 pipeline: a cached answer below the floor is a miss",
            "B12 through the pipeline: unsupported question refused",
        ],
    },
    {
        "id": "M2",
        "target": RAG,
        "disables": "treating a cached answer below the floor as a miss (main's condition)",
        "replace": (
            "            if cached_result and (\n"
            "                not refuse_unsupported\n"
            '                or self._reaches_floor(cached_result.get("sources"))\n'
            "            ):\n",
            "            if cached_result:\n",
        ),
        "expect_red": ["B2 pipeline: a cached answer below the floor is a miss"],
    },
    {
        "id": "M3",
        "target": RAG,
        "disables": "telling the model its length (main's prompt)",
        "replace": (
            '            f"- Keep the answer within about {budget // 4} words; citations do not count toward that.\\n"\n',
            "",
        ),
        "expect_red": [
            "B3 pipeline: the model is told its budget",
            "B11 through the pipeline: supported question answered",
        ],
    },
    {
        "id": "M4",
        "target": SEMANTIC,
        "disables": "matching the semantic cache on the answer budget",
        "replace": (
            "            filters.append(\n"
            '                FieldCondition(key="max_tokens", match=MatchValue(value=int(max_tokens)))\n'
            "            )\n",
            "            pass  # mutation M4\n",
        ),
        "expect_red": ["B5 semantic cache: same budget only"],
    },
    {
        "id": "M5",
        "target": CACHE_KEY,
        "disables": "a separate application-cache entry for a refusing caller",
        "replace": (
            '        return (*key, "refuse-unsupported") if refuse_unsupported else key\n',
            "        return key  # mutation M5\n",
        ),
        "expect_red": [
            "B1 pipeline: no answer from a chunk below the floor",
            "B2 pipeline: a cached answer below the floor is a miss",
            "B4 application cache: a refusing caller has its own entry",
        ],
    },
    {
        "id": "M6",
        "target": QA,
        "disables": "refusing an answer that cites nothing",
        "replace": (
            "    if not any(passage.citations for passage in passages):\n",
            "    if False:  # mutation M6\n",
        ),
        "expect_red": [
            "B8 service: an uncited answer is refused",
            "B9 service: a deleted document is not cited",
        ],
    },
    {
        "id": "M7",
        "target": QA,
        "disables": "the search route's scope rule in the service",
        "replace": (
            "    if allowed == [] or (allowed is not None and project_id not in set(allowed)):\n",
            "    if False:  # mutation M7\n",
        ),
        "expect_red": ["B10 service: no answer outside the caller's scope"],
    },
    {
        "id": "M8",
        "target": QA,
        "disables": "citing only chunks in documents that still exist",
        "replace": (
            '            if chunk is None or not chunk.get("chunk_id") or str(_document_uuid(chunk)) not in live_names:\n',
            '            if chunk is None or not chunk.get("chunk_id"):  # mutation M8\n',
        ),
        "expect_red": ["B9 service: a deleted document is not cited"],
    },
    {
        "id": "M9",
        "target": LIBRARIAN,
        "disables": "the provenance validator on answer turns",
        "replace": (
            "        violations = validate_provenance(reply, answer.source_chunk_ids)\n"
            "        if violations:\n"
            "            reply = withhold(reply, violations)\n",
            "        violations: list = []  # mutation M9\n",
        ),
        "expect_red": ["B15 route: a stray citation is withheld"],
    },
    {
        "id": "M10",
        "target": ROUTE,
        "disables": "routing answer mode to the Q&A service (every turn converses)",
        "replace": (
            '        if project is not None and payload.mode == "answer":\n',
            "        if False:  # mutation M10\n",
        ),
        "expect_red": [
            "B13 route: answer mode goes to the Q&A service",
            "B14 route: the validator accepts every rendered citation",
            "B15 route: a stray citation is withheld",
            "B16 route: nothing found asserts nothing",
            "B18 route: each paid call metered",
        ],
    },
    {
        "id": "M11",
        "target": QA,
        "disables": "reading a label that names several chunks (the pipeline's single-chunk form only)",
        "replace": (
            '    r"[ \\t]*\\[Document:\\s*(?P<document>[^\\],]+),\\s*Chunks?:\\s*(?P<chunks>[^\\]]+)\\]",\n',
            '    r"[ \\t]*\\[Document:\\s*(?P<document>[^\\],]+),\\s*Chunk:\\s*(?P<chunks>[^\\]]+)\\]",  # mutation M11\n',
        ),
        "expect_red": ["B19 service: a label naming several chunks"],
    },
    {
        "id": "M12",
        "target": QA,
        "disables": "expanding a range or list into the chunks it names",
        "replace": (
            '    """The chunks one label names: "9", a range "9–10" or a list "9, 10"."""\n',
            '    """The chunks one label names: "9", a range "9–10" or a list "9, 10"."""\n'
            "    return [spec.strip()]  # mutation M12\n",
        ),
        "expect_red": ["B19 service: a label naming several chunks"],
    },
    {
        "id": "F1",
        "target": CLIENT,
        "disables": "sending the budget with an answer turn",
        "replace": (
            '        ? { project_id: projectId, messages, mode: "answer", max_tokens: answer.maxTokens }\n',
            '        ? { project_id: projectId, messages, mode: "answer" }\n',
        ),
        "expect_red": ["F1 client: an answer turn carries its budget"],
    },
    {
        "id": "F2",
        "target": PAGE,
        "disables": "the user's budget choice (always the short answer)",
        "replace": (
            "        ? await librarianApi.turn(toTranscript(next), projectId, { maxTokens: ANSWER_BUDGETS[budget] })\n",
            "        ? await librarianApi.turn(toTranscript(next), projectId, { maxTokens: ANSWER_BUDGETS.short })\n",
        ),
        "expect_red": ["F2 page: the chosen budget and chunk links"],
    },
    {
        "id": "F3",
        "target": PAGE,
        "disables": "linking a chunk citation to its chunk (it links to the evidence page, as LIB-1 did)",
        "replace": (
            "                  <Link href={chunk.href} title={chunk.snippet ?? undefined}",
            "                  <Link href={`/evidence/${id}`} title={chunk.snippet ?? undefined}",
        ),
        "expect_red": ["F2 page: the chosen budget and chunk links"],
    },
    {
        "id": "F4",
        "target": PAGE,
        "disables": "rendering a refusal as a note",
        "replace": ("            if (turn.noEvidence) {\n", "            if (false) {\n"),
        "expect_red": ["F4 page: the refusal is a note"],
    },
    {
        "id": "F5",
        "target": DOCUMENT_PAGE,
        "disables": "reading a citation's chunk from the link",
        "replace": (
            "  const [cited] = useState(() => citedChunk(router.query));\n",
            "  const [cited] = useState(() => citedChunk({}));\n",
        ),
        "expect_red": [
            "F6 document page: opens the cited chunk",
            "F7 document page: a missing chunk is said aloud",
            "F8 document page: the cited card's top scrolls into view",
        ],
    },
    {
        "id": "F6",
        "target": DOCUMENT_PAGE,
        "disables": "scrolling the cited card's top into view (the chunk's text is centred instead)",
        "replace": (
            "    const card = window.document.querySelector('[data-cited=\"true\"]');\n"
            '    if (card && typeof card.scrollIntoView === "function") card.scrollIntoView({ block: "start" });\n',
            "    const card = window.document.getElementById(`chunk-${cited.id}`);\n"
            '    if (card && typeof card.scrollIntoView === "function") card.scrollIntoView({ block: "center" });\n',
        ),
        "expect_red": ["F8 document page: the cited card's top scrolls into view"],
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


def run_backend(label: str) -> dict[str, str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # -rfEsp: one summary line per test and the failures' tracebacks, without the
    # captured output of passing tests (1.8 MB a run with -rA).
    # noqa S603: fixed pytest argv run through the current interpreter.
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-B", "-m", "pytest", *BACKEND.values(), "-p", "no:cacheprovider", "-rfEsp", "-q"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )
    (HERE / "mutation-logs" / f"{label}-backend.txt").write_text(proc.stdout + proc.stderr)
    lines = proc.stdout.splitlines()
    outcome = {}
    for name, node in BACKEND.items():
        if any(line.startswith(f"PASSED {node}") for line in lines):
            outcome[name] = "pass"
        elif any(line.startswith((f"FAILED {node}", f"ERROR {node}")) for line in lines):
            outcome[name] = "red"
        else:
            outcome[name] = "missing"
    return outcome


def run_frontend(label: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as scratch:
        report_path = Path(scratch) / "vitest.json"
        # noqa S603: the repository's pinned vitest with a fixed argv.
        proc = subprocess.run(  # noqa: S603
            ["./node_modules/.bin/vitest", "run", *FRONTEND_FILES, "--reporter=json", f"--outputFile={report_path}"],
            cwd=REPO / "frontend",
            capture_output=True,
            text=True,
        )
        report = json.loads(report_path.read_text()) if report_path.exists() else {"testResults": []}
    results = [result for suite in report.get("testResults", []) for result in suite.get("assertionResults", [])]
    lines = [f"{result['status'].upper()} {result['fullName']}" for result in results]
    lines += [
        f"\n--- {result['fullName']}\n" + "\n".join(message.splitlines()[0] for message in result.get("failureMessages", []))
        for result in results
        if result["status"] != "passed"
    ]
    (HERE / "mutation-logs" / f"{label}-frontend.txt").write_text("\n".join(lines) + "\n\n" + proc.stdout + proc.stderr)
    statuses = {result["title"]: result["status"] for result in results}
    return {
        name: "pass" if statuses.get(title) == "passed" else ("missing" if title not in statuses else "red")
        for name, title in FRONTEND.items()
    }


def run_all(label: str) -> dict:
    return {"label": label, "tests": {**run_backend(label), **run_frontend(label)}}


def main() -> int:
    if git("status", "--porcelain", "--", *TARGETS).strip():
        print("ABORT: a target file differs from HEAD; commit the change first")
        return 1
    (HERE / "mutation-logs").mkdir(exist_ok=True)
    fixed = {target: (REPO / target).read_text() for target in TARGETS}
    runs = []
    try:
        runs.append(run_all("baseline-before"))
        for mutation in MUTATIONS:
            target = mutation["target"]
            old, new = mutation["replace"]
            if fixed[target].count(old) != 1:
                raise RuntimeError(f"{mutation['id']}: the snippet does not occur exactly once in {target}")
            (REPO / target).write_text(fixed[target].replace(old, new))
            run = run_all(mutation["id"])
            run.update(target=target, disables=mutation["disables"], expect_red=mutation["expect_red"])
            runs.append(run)
            (REPO / target).write_text(fixed[target])
        runs.append(run_all("baseline-after"))
    finally:
        for target, text in fixed.items():
            (REPO / target).write_text(text)

    restored = not git("status", "--porcelain", "--", *TARGETS).strip()
    for run in runs:
        red = {name for name, outcome in run["tests"].items() if outcome != "pass"}
        run["red"] = sorted(red)
        run["as_expected"] = red == set(run.get("expect_red", []))
    report = {
        "head": git("rev-parse", "HEAD").strip(),
        "base": BASE,
        "files_restored_to_head": restored,
        "all_as_expected": all(run["as_expected"] for run in runs) and restored,
        "runs": runs,
    }
    (HERE / "mutation-proof.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({run["label"]: (run["as_expected"], run["red"]) for run in runs}, indent=2))
    print("all_as_expected:", report["all_as_expected"])
    return 0 if report["all_as_expected"] else 1


if __name__ == "__main__":
    sys.exit(main())
