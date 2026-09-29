"""Run only against isolated tests; always restore source after each mutation."""

import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[4]
source = root / "app/services/librarian_description.py"
original = source.read_text()
out = Path(__file__).resolve().parent
mutants = [
    (
        "bypass-source-revalidation",
        '_validate_sources(db, user, project, proposal["description"], sources)',
        'pass  # intentional test mutant',
        "test_corpus_citations_are_scoped_and_rechecked",
    ),
    (
        "bypass-caller-binding",
        'proposal["sub"] != str(user.user_id)',
        'False',
        "test_human_project_authorization_precedes_model_and_signed_caller_is_required",
    ),
]
results = []
try:
    for name, before, after, test in mutants:
        if original.count(before) != 1:
            raise AssertionError(f"Mutation target changed: {name}")
        source.write_text(original.replace(before, after))
        result = subprocess.run(  # noqa: S603 — fixed local pytest nodes, no external input
            [str(root / ".venv/bin/pytest"), f"tests/test_librarian_descriptions.py::{test}",
             "-q", "--disable-warnings", "--show-capture=no"], cwd=root,
            env={**os.environ, "QDRANT_URL": "http://127.0.0.1:9"},
            capture_output=True, text=True,
        )
        (out / f"{name}.log").write_text(result.stdout + result.stderr)
        results.append({"mutation": name, "test": test, "exit_code": result.returncode})
        if result.returncode != 1:
            raise AssertionError(f"Mutation not killed: {name}")
        source.write_text(original)
finally:
    source.write_text(original)
(out / "mutation-proof.json").write_text(json.dumps({"mutants": results, "source_restored": source.read_text() == original}, indent=2) + "\n")
