"""QA-2 mutation proof: disable one chunk-list rule at a time and run the Librarian tests.

Each mutation must turn exactly its expected tests red, and nothing else. The script
refuses to start unless every target file matches HEAD, restores each file after its
run, and checks the files match HEAD again at the end.

Run from the repository root: python3 cmos/reports/sprint-59/QA-2/mutation_proof.py
"""

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
FRONTEND = ROOT / "frontend"
OUT = pathlib.Path(__file__).resolve().parent
SPEC = "src/__tests__/librarian.test.tsx"
CHUNK_LIST = "frontend/src/components/librarian/ChunkList.tsx"
PAGE = "frontend/src/pages/librarian.tsx"
LISTING = "Librarian page, listing the chunks"

MUTATIONS = [
    {
        "id": "Q1",
        "disables": "a saved search's list is never refetched on focus (each execute call counts a run and spends a model call)",
        "file": CHUNK_LIST,
        "old": "    revalidateOnFocus: false,\n",
        "new": "    revalidateOnFocus: true,\n",
        "red": [f"{LISTING} runs a saved search once through the call that counts its runs, and shows no answer"],
    },
    {
        "id": "Q2",
        "disables": "a retry adds only the chunks still missing from the collection",
        "file": CHUNK_LIST,
        "old": "        if (saved.has(row.chunkId)) continue;\n",
        "new": "",
        "red": [f"{LISTING} keeps the list as one collection in rank order, and a retry adds only what is missing"],
    },
    {
        "id": "Q3",
        "disables": "a retry reuses the collection it already created",
        "file": CHUNK_LIST,
        "old": "const target = collection ?? (await",
        "new": "const target = (await",
        "red": [f"{LISTING} keeps the list as one collection in rank order, and a retry adds only what is missing"],
    },
    {
        "id": "Q4",
        "disables": "a listed phrase goes to the URL and never to the Librarian model",
        "file": PAGE,
        "old": "undefined, { shallow: true });\n      return;\n",
        "new": "undefined, { shallow: true });\n",
        "red": [f"{LISTING} puts the phrase in the URL and never sends it to the Librarian model"],
    },
    {
        "id": "Q5",
        "disables": "the list asks for twenty chunks",
        "file": CHUNK_LIST,
        "old": "export const CHUNK_LIST_SIZE = 20;",
        "new": "export const CHUNK_LIST_SIZE = 10;",
        "red": [
            f"{LISTING} lists the ranked chunks for the URL's phrase, each linking to its place in its document",
            f"{LISTING} lists across every readable project when no project is named",
            f"{LISTING} saves the phrase as a saved search with its project and list size",
        ],
    },
    {
        "id": "Q6",
        "disables": "a chunk link names the chunk's index, so the document opens on the right page",
        "file": CHUNK_LIST,
        "old": 'const index = row.chunkIndex == null ? "" : `&index=${row.chunkIndex}`;',
        "new": 'const index = "";',
        "red": [
            f"{LISTING} lists the ranked chunks for the URL's phrase, each linking to its place in its document",
            f"{LISTING} runs a saved search once through the call that counts its runs, and shows no answer",
        ],
    },
]


def clean(files):
    return subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *files], cwd=ROOT).returncode == 0


def red_tests():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        report = pathlib.Path(handle.name)
    run = subprocess.run(
        [str(FRONTEND / "node_modules/.bin/vitest"), "run", SPEC, "--reporter=json", f"--outputFile={report}"],
        cwd=FRONTEND, capture_output=True, text=True,
    )
    data = json.loads(report.read_text())
    report.unlink()
    failed = [
        (f"{' '.join(test['ancestorTitles'])} {test['title']}", test["failureMessages"])
        for result in data["testResults"]
        for test in result["assertionResults"]
        if test["status"] != "passed"
    ]
    messages = "".join(f"\n--- {name}\n" + "\n".join(failure) for name, failure in failed)
    return sorted(name for name, _ in failed), data["numTotalTests"], run.stdout + run.stderr + messages


def main():
    targets = sorted({m["file"] for m in MUTATIONS})
    if not clean(targets):
        sys.exit("Target files differ from HEAD; commit or stash first.")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    logs = OUT / "mutation-logs"
    logs.mkdir(exist_ok=True)
    runs = []
    red, total, log = red_tests()
    (logs / "baseline-before.txt").write_text(log)
    runs.append({"id": "baseline-before", "red": red, "total": total, "expected": [], "as_expected": red == []})
    for mutation in MUTATIONS:
        path = ROOT / mutation["file"]
        original = path.read_text()
        if original.count(mutation["old"]) != 1:
            sys.exit(f"{mutation['id']}: mutated snippet must occur exactly once")
        path.write_text(original.replace(mutation["old"], mutation["new"]))
        try:
            red, total, log = red_tests()
        finally:
            path.write_text(original)
        (logs / f"{mutation['id']}.txt").write_text(log)
        expected = sorted(mutation["red"])
        runs.append({"id": mutation["id"], "disables": mutation["disables"], "file": mutation["file"], "red": red, "total": total, "expected": expected, "as_expected": red == expected})
    red, total, log = red_tests()
    (logs / "baseline-after.txt").write_text(log)
    runs.append({"id": "baseline-after", "red": red, "total": total, "expected": [], "as_expected": red == []})
    restored = clean(targets)
    result = {"commit": head, "spec": f"frontend/{SPEC}", "runs": runs, "files_match_head_after": restored, "all_as_expected": restored and all(run["as_expected"] for run in runs)}
    (OUT / "mutation-proof.json").write_text(json.dumps(result, indent=2) + "\n")
    for run in runs:
        print(run["id"], "as expected" if run["as_expected"] else f"UNEXPECTED: {run['red']}")
    sys.exit(0 if result["all_as_expected"] else 1)


if __name__ == "__main__":
    main()
