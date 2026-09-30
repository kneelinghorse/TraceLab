"""Run isolated guard mutations sequentially and always restore both source files."""

import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
mutants = [
    ("bypass-caller-binding", "app/services/librarian_collections.py",
     'if proposal["sub"] != str(user.user_id) or proposal["project_id"] != str(project.id):',
     'if proposal["project_id"] != str(project.id):',
     "test_wrong_user_and_service_cannot_accept_another_principals_group"),
    ("bypass-project-scope", "app/services/librarian_collections.py",
     'filter(Document.project_id == project.id, Document.deleted_at.is_(None))',
     'filter(Document.deleted_at.is_(None))',
     "test_privileged_caller_is_still_scoped_before_provider_and_acceptance"),
    ("bypass-attachment-recheck", "app/services/collection.py",
     '_validate_sources(session, source_user, project, f"Reviewed excerpt [{source[\'marker\']}].", [source])',
     'pass  # intentional test mutant',
     "test_source_changed_between_validation_and_attachment_stays_partial"),
]
results = []
for name, filename, before, after, test in mutants:
    source = root / filename
    original = source.read_text()
    try:
        if original.count(before) != 1:
            raise AssertionError(f"Mutation target changed: {name}")
        source.write_text(original.replace(before, after))
        result = subprocess.run(  # noqa: S603 — fixed local isolated pytest nodes
            [str(root / ".venv/bin/pytest"), f"tests/test_librarian_collections.py::{test}", "-q", "--disable-warnings", "--show-capture=no"],
            cwd=root, env={**os.environ, "QDRANT_URL": "http://127.0.0.1:9"}, capture_output=True, text=True,
        )
        (out / f"{name}.log").write_text(result.stdout + result.stderr)
        results.append({"mutation": name, "test": test, "exit_code": result.returncode})
        if result.returncode != 1:
            raise AssertionError(f"Mutation not killed: {name}")
    finally:
        source.write_text(original)
    results[-1]["source_restored"] = source.read_text() == original
(out / "mutation-proof.json").write_text(json.dumps({"mutants": results}, indent=2) + "\n")
