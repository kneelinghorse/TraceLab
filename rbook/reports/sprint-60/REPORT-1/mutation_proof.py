"""Prove REPORT-1 guards matter, restoring each source file even on failure."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
mutants = [
    ("fabricated-marker", "app/services/synthesis.py",
     "        validate_citation_coverage(content, set(citation_map))",
     '        content = content.replace("[99]", "[1]")\n        validate_citation_coverage(content, set(citation_map))',
     "fabricated_or_uncited_claims", "Invented support [99]"),
    ("removed-support", "app/services/report_citations.py",
     '    """Recheck the generated mapping in the report transaction; never infer one."""',
     '    """Recheck the generated mapping in the report transaction; never infer one."""\n    return result["citations"]',
     "source_removed_during_generation", "source_removed_during_generation"),
]
results = []
for name, file, old, new, selection, expected_failure in mutants:
    path = ROOT / file
    original = path.read_text()
    if original.count(old) != 1:
        raise RuntimeError("Mutation anchor changed")
    try:
        path.write_text(original.replace(old, new))
        run = subprocess.run(  # noqa: S603 - fixed local pytest command
            [str(ROOT / ".venv/bin/python"), "-m", "pytest", "tests/test_report_citations.py", "-q",
             "-k", selection, "--tb=short", "--show-capture=no", "-p", "no:warnings"],
            cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "DEBUG": "false", "QDRANT_URL": "http://127.0.0.1:9", "QDRANT_API_KEY": "test"},
        )
        output = run.stdout + run.stderr
        (OUT / f"mutation-{name}.log").write_text(output)
        results.append({"mutant": name, "detected": run.returncode == 1 and expected_failure in output})
    finally:
        path.write_text(original)
(OUT / "mutation-proof.json").write_text(json.dumps(results, indent=2) + "\n")
if not all(result["detected"] for result in results):
    raise RuntimeError(results)
print(json.dumps(results))
