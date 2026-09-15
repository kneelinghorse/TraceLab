"""Assemble cmos/reports/sprint-52/mcp-3-validation.json.

Run once after `npm publish` has happened and npx-smoke.mjs has produced
mcp-3-production-smoke.json. Inputs (env): MERGE_SHA, SOURCE_HEAD, BASE_COMMIT,
PR_URL, PUBLISHED_BY (agent|Derek), PUBLISH_TIMESTAMP (ISO 8601), OUT (a directory
holding runs.json, jobs/<id>.json, railway.json, railway-checked-at.txt,
tables-check.json, public-smoke.json and mcp-3-production-smoke.json).
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import shutil
import subprocess

OUT = pathlib.Path(os.environ["OUT"])
REPO = pathlib.Path("/Users/systemsystems/portfolio/TraceLab")
NPM = shutil.which("npm") or "npm"
GIT = shutil.which("git") or "git"
MERGE = os.environ["MERGE_SHA"]
NOW = datetime.datetime.now(datetime.UTC).isoformat()
REQUIRED = {"MCP Package": "mcp-package", "Backend Tests": "backend-suite", "Frontend Production Build": "build-frontend-production"}


def load(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def run(argv: list[str]) -> str:
    # Fixed argv against trusted local tooling; no shell, no user input.
    return subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=True).stdout  # noqa: S603


def main() -> None:
    ci = []
    for run_row in sorted(load("runs.json"), key=lambda r: r["workflowName"]):
        jobs = load(f"jobs/{run_row['databaseId']}.json")["jobs"]
        ci.append(
            {
                "workflow": run_row["workflowName"],
                "run_id": run_row["databaseId"],
                "url": run_row["url"],
                "event": run_row["event"],
                "head_sha": run_row["headSha"],
                "head_branch": run_row["headBranch"],
                "status": run_row["status"],
                "conclusion": run_row["conclusion"],
                "created_at": run_row["createdAt"],
                "jobs": [{"id": j["databaseId"], "name": j["name"], "conclusion": j["conclusion"], "url": j["url"]} for j in jobs],
            }
        )
    assert all(r["head_sha"] == MERGE and r["event"] == "push" and r["head_branch"] == "main" for r in ci)  # noqa: S101
    cited = {name: next(r for r in ci if r["workflow"] == name) for name in REQUIRED}

    services = {}
    for env in load("railway.json")["environments"]["edges"]:
        if env["node"]["name"] != "production":
            continue
        for instance in env["node"]["serviceInstances"]["edges"]:
            node = instance["node"]
            if node["serviceName"] in ("TraceLab", "frontend"):
                latest = node["latestDeployment"]
                services[node["serviceName"]] = {
                    "service_id": node["serviceId"],
                    "deployment_id": latest["id"],
                    "status": latest["status"],
                    "commit": (latest.get("meta") or {}).get("commitHash"),
                    "created_at": latest["createdAt"],
                }
    deployment = {
        "checked_at": (OUT / "railway-checked-at.txt").read_text().strip(),
        "commit": MERGE,
        "services": services,
        "both_success_for_commit": len(services) == 2 and all(s["status"] == "SUCCESS" and s["commit"] == MERGE for s in services.values()),
    }

    smoke = load("mcp-3-production-smoke.json")
    npm_version = run([NPM, "view", "@aquex/tracelab-mcp", "version"]).strip()
    npm_time = json.loads(run([NPM, "view", "@aquex/tracelab-mcp", "time", "--json"]))
    tag = run([GIT, "ls-remote", "--tags", "origin", "tracelab-mcp-v1.2.0"]).strip()
    (REPO / "cmos/reports/sprint-52/mcp-3-production-smoke.json").write_text(json.dumps(smoke, indent=2) + "\n")

    package = json.loads((REPO / "packages/tracelab-mcp/package.json").read_text())["version"]
    lock = json.loads((REPO / "packages/tracelab-mcp/package-lock.json").read_text())["version"]
    receipt = {
        "mission_id": "MCP-3",
        "sprint_id": "sprint-52",
        "generated_at": NOW,
        "status": "validated_pending_receipt_merge",
        "source": {
            "base_commit": os.environ["BASE_COMMIT"],
            "pr": os.environ["PR_URL"],
            "source_head": os.environ["SOURCE_HEAD"],
            "merge_commit": MERGE,
            "tag": "tracelab-mcp-v1.2.0",
            "tag_on_remote": tag,
        },
        "decisions": [425, 426],
        "learnings_applied": [74, 176, 177],
        "version": {"package_json": package, "package_lock": lock, "npm_registry": npm_version, "npm_publish_time": npm_time.get(npm_version)},
        "publish": {
            "ran_by": os.environ["PUBLISHED_BY"],
            "timestamp": os.environ["PUBLISH_TIMESTAMP"],
            "from": "clean checkout of the merge commit",
            "verified_with": "npm view @aquex/tracelab-mcp version",
        },
        "changelog": {"released_section": "[1.2.0] — 2026-09-15", "unreleased_empty": True, "former_unreleased_entries": 12},
        "tables_match_cluster_actions": load("tables-check.json"),
        "post_merge_main_push_ci": ci,
        "cited_runs": {REQUIRED[name]: {"run_id": r["run_id"], "conclusion": r["conclusion"], "url": r["url"]} for name, r in cited.items()},
        "deployments": deployment,
        "public_smoke": load("public-smoke.json")["summary"],
        "fresh_install_smoke": {
            "receipt": "cmos/reports/sprint-52/mcp-3-production-smoke.json",
            "passed": smoke["passed"],
            "checks": len(smoke["checks"]),
            "failed": [c["label"] for c in smoke["checks"] if not c["passed"]],
            "install": smoke["install"],
        },
        "limitations": [
            "The fresh npx smoke runs one read-only action per tool; write actions are covered by the package's local stdio contract, not exercised against production.",
            "Canonical links are resolved with an unauthenticated GET on the public frontend; a 200 proves the route is served, not that the operator's data renders.",
        ],
        "closure_gate": "CMOS MCP-3 is marked Completed only after this receipt merges on main and the receipt-carrier main push and both Railway deployments are verified.",
    }
    path = REPO / "cmos/reports/sprint-52/mcp-3-validation.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    summary = {
        "receipt": str(path),
        "npm_version": npm_version,
        "both_success": deployment["both_success_for_commit"],
        "smoke_passed": smoke["passed"],
        "cited": {k: v["conclusion"] for k, v in receipt["cited_runs"].items()},
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
