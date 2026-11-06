"""MCP-6 mutation proof: break one ask rule at a time and run every check that guards it.

Each mutation must turn exactly its expected checks red, and nothing else. Three
suites run for every mutation: the backend tests for POST /search/ask, the MCP
package's ask and cluster-surface tests, and the UI parity audit. The script
refuses to start unless every target file matches HEAD, restores each file after
its run, and checks the files match HEAD again at the end.

Run from the repository root with the backend's interpreter:
    .venv/bin/python cmos/reports/sprint-59/MCP-6/mutation_proof.py
"""

import json
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET  # noqa: S405

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).resolve().parent
MCP = ROOT / "packages" / "tracelab-mcp"
ROUTE = "app/api/v1/search.py"
SCHEMA = "app/schemas/rag.py"
KINDS = "app/models/usage_record.py"
CLIENT = "packages/tracelab-mcp/src/api-client.ts"
INDEX = "packages/tracelab-mcp/src/index.ts"
PROJECT = "00000000-0000-4000-8000-000000000001"
TURN_ROW = "frontend/src/lib/api/librarian.ts#librarianApi.turn:POST:/librarian/turns"


def ask_case(**fields):
    """vitest's name for one it.each row of the invalid-input table (%j is JSON.stringify)."""
    return "MCP-6 tracelab_search ask rejects invalid ask input before HTTP: " + json.dumps(fields, separators=(",", ":"))


OWNER_ANSWERED = "TestAccess::test_the_projects_owner_gets_an_answer_whose_citations_resolve"
NOTHING_FOUND = "TestAnswer::test_nothing_found_is_the_refusal_and_asserts_nothing"
CITES_NOTHING = "TestAnswer::test_an_answer_that_cites_nothing_is_refused_not_shown"
METERED = "TestAnswer::test_each_paid_call_is_metered_to_the_caller_and_a_cached_answer_is_not"
REQUEST_RULES = "TestAnswer::test_request_rules"
MCP_ASKS = "MCP-6 tracelab_search ask asks through POST /search/ask and links every citation to its chunk"

MUTATIONS = [
    {
        "id": "M1",
        "disables": "the project is authorized for the caller before the Q&A service runs",
        "file": ROUTE,
        "old": '    authorize_or_403(current_user, "read", project, db)\n',
        "new": "",
        "red": ["TestAccess::test_a_caller_cannot_get_an_answer_from_a_project_they_cannot_read"],
    },
    {
        "id": "M2",
        "disables": "a soft-deleted project is 404, like an unknown one",
        "file": ROUTE,
        "old": "Project.id == payload.project_id, Project.deleted_at.is_(None)",
        "new": "Project.id == payload.project_id",
        "red": ["TestAccess::test_an_unknown_or_deleted_project_is_404"],
    },
    {
        "id": "M3",
        "disables": "the route reaches the pipeline only through corpus_qa.answer_question (a parallel path)",
        "file": ROUTE,
        "old": "    answer = answer_question(db, current_user, project.id,",
        "new": "    get_rag_service()\n    answer = answer_question(db, current_user, project.id,",
        "red": [OWNER_ANSWERED, NOTHING_FOUND, CITES_NOTHING, METERED],
    },
    {
        "id": "M4",
        "disables": "each paid model call is recorded as usage",
        "file": ROUTE,
        "old": "    for model, usage in answer.usage:\n",
        "new": "    for model, usage in []:\n",
        "red": [METERED],
    },
    {
        "id": "M5",
        "disables": "asks are metered under their own kind, apart from Librarian turns",
        "file": KINDS,
        "old": 'USAGE_KIND_SEARCH_ASK = "search_ask"',
        "new": 'USAGE_KIND_SEARCH_ASK = "librarian_turn"',
        "red": [METERED],
    },
    {
        "id": "M6",
        "disables": "the answer budget is bounded 64-4000",
        "file": SCHEMA,
        "old": "        ge=ANSWER_MIN_TOKENS,\n        le=ANSWER_MAX_TOKENS,\n        description=\"Answer budget.",
        "new": "        description=\"Answer budget.",
        "red": [REQUEST_RULES],
    },
    {
        "id": "M7",
        "disables": "a blank question is refused before retrieval",
        "file": SCHEMA,
        "old": "        if not value.strip():\n",
        "new": "        if False:\n",
        "red": [REQUEST_RULES],
    },
    {
        "id": "M8",
        "disables": "the npm client sends POST /api/v1/search/ask (the verb the server serves)",
        "file": CLIENT,
        "old": "this.request<AskResponse>('POST', '/api/v1/search/ask', query)",
        "new": "this.request<AskResponse>('PUT', '/api/v1/search/ask', query)",
        "red": ["TestMcpContract::test_the_npm_client_asks_through_post_search_ask", MCP_ASKS],
    },
    {
        "id": "M9",
        "disables": "each citation gains the browser url that opens its chunk",
        "file": INDEX,
        "old": "citations: result.citations.map(withHrefUrl) });",
        "new": "citations: result.citations });",
        "red": [MCP_ASKS],
    },
    {
        "id": "M10",
        "disables": "the MCP rejects an answer budget the API would refuse, before any request",
        "file": INDEX,
        "old": "  max_tokens: z.number().int().min(64).max(4000).optional(),\n",
        "new": "  max_tokens: z.number().optional(),\n",
        "red": [
            ask_case(project_id=PROJECT, question="Cost?", max_tokens=63),
            ask_case(project_id=PROJECT, question="Cost?", max_tokens=4001),
            ask_case(project_id=PROJECT, question="Cost?", max_tokens=600.5),
        ],
    },
    {
        "id": "M11",
        "disables": "ask is a registered tracelab_search action, which the parity manifest's Librarian turn row maps to",
        "file": INDEX,
        "old": "const SEARCH_ACTIONS = ['knowledge', 'navigate', 'pedr', 'ask'] as const;",
        "new": "const SEARCH_ACTIONS = ['knowledge', 'navigate', 'pedr'] as const;",
        "red": [
            "T41.7 — cluster surface exposes exactly 9 tracelab_* tools and keeps descriptors aligned with action enums",
            f"audit: Missing CLUSTER_ACTIONS action tracelab_search.ask: {TURN_ROW}",
        ],
    },
]


def git(*args, **kwargs):
    # noqa S603/S607: fixed git argv chosen by this script, never external input.
    return subprocess.run(["git", *args], cwd=ROOT, **kwargs)  # noqa: S603, S607


def clean(files):
    return git("diff", "--quiet", "HEAD", "--", *files).returncode == 0


def backend():
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        junit = pathlib.Path(handle.name)
    # noqa S603: fixed pytest argv run through the current interpreter.
    run = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "tests/test_search_ask.py", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    # noqa S405/S314: the junit file pytest just wrote for this script, never external input.
    cases = ET.parse(junit).getroot().iter("testcase")  # noqa: S314
    junit.unlink()
    red, total = [], 0
    for case in cases:
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            red.append(f"{case.get('classname').rsplit('.', 1)[-1]}::{case.get('name')}")
    return red, total, run.stdout + run.stderr


def package():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report = pathlib.Path(handle.name)
    # noqa S603: the package's pinned vitest with a fixed argv.
    run = subprocess.run(  # noqa: S603
        [str(MCP / "node_modules/.bin/vitest"), "run", "src/ask.test.ts", "src/index.test.ts",
         "--reporter=json", f"--outputFile={report}"],
        cwd=MCP, capture_output=True, text=True,
    )
    data = json.loads(report.read_text())
    report.unlink()
    # vitest lists the file as an unnamed ancestor; drop it, or every name starts with a space.
    failed = [
        (" ".join([*filter(None, test["ancestorTitles"]), test["title"]]), test["failureMessages"])
        for result in data["testResults"]
        for test in result["assertionResults"]
        if test["status"] != "passed"
    ]
    messages = "".join(f"\n--- {name}\n" + "\n".join(failure) for name, failure in failed)
    return [name for name, _ in failed], data["numTotalTests"], run.stdout + run.stderr + messages


def audit():
    # noqa S603/S607: the repository's parity audit with a fixed argv.
    run = subprocess.run(["node", "scripts/mcp_parity_audit.mjs"], cwd=ROOT, capture_output=True, text=True)  # noqa: S603, S607
    errors = json.loads(run.stdout)["errors"]
    return [f"audit: {error}" for error in errors], run.stdout + run.stderr


def checks():
    backend_red, backend_total, backend_log = backend()
    package_red, package_total, package_log = package()
    audit_red, audit_log = audit()
    red = sorted(backend_red + package_red + audit_red)
    log = f"== backend\n{backend_log}\n== package\n{package_log}\n== audit\n{audit_log}"
    return red, {"backend": backend_total, "package": package_total}, log


def main():
    targets = sorted({m["file"] for m in MUTATIONS})
    if not clean(targets):
        sys.exit("Target files differ from HEAD; commit or stash first.")
    head = git("rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    logs = OUT / "mutation-logs"
    logs.mkdir(exist_ok=True)
    runs = []
    red, totals, log = checks()
    (logs / "baseline-before.txt").write_text(log)
    runs.append({"id": "baseline-before", "red": red, "totals": totals, "expected": [], "as_expected": red == []})
    for mutation in MUTATIONS:
        path = ROOT / mutation["file"]
        original = path.read_text()
        if original.count(mutation["old"]) != 1:
            sys.exit(f"{mutation['id']}: mutated snippet must occur exactly once")
        path.write_text(original.replace(mutation["old"], mutation["new"]))
        try:
            red, totals, log = checks()
        finally:
            path.write_text(original)
        (logs / f"{mutation['id']}.txt").write_text(log)
        expected = sorted(mutation["red"])
        runs.append({
            "id": mutation["id"], "disables": mutation["disables"], "file": mutation["file"],
            "red": red, "totals": totals, "expected": expected, "as_expected": red == expected,
        })
        print(mutation["id"], "as expected" if red == expected else f"UNEXPECTED: {red}", flush=True)
    red, totals, log = checks()
    (logs / "baseline-after.txt").write_text(log)
    runs.append({"id": "baseline-after", "red": red, "totals": totals, "expected": [], "as_expected": red == []})
    restored = clean(targets)
    result = {
        "commit": head,
        "suites": ["tests/test_search_ask.py", "packages/tracelab-mcp/src/ask.test.ts", "packages/tracelab-mcp/src/index.test.ts", "scripts/mcp_parity_audit.mjs"],
        "runs": runs,
        "files_match_head_after": restored,
        "all_as_expected": restored and all(run["as_expected"] for run in runs),
    }
    (OUT / f"mutation-proof-{head[:7]}.json").write_text(json.dumps(result, indent=2) + "\n")
    for run in runs:
        print(run["id"], "as expected" if run["as_expected"] else f"UNEXPECTED: {run['red']}")
    sys.exit(0 if result["all_as_expected"] else 1)


if __name__ == "__main__":
    main()
