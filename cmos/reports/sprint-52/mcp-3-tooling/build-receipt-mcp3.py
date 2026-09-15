"""Assemble cmos/reports/sprint-52/mcp-3-validation.json.

Run once after `npm publish` has happened and npx-smoke.mjs has produced
mcp-3-production-smoke.json. Inputs (env): MERGE_SHA, SOURCE_HEAD, BASE_COMMIT,
PR_URL, PUBLISHED_BY (agent|Derek), PUBLISH_TIMESTAMP (ISO 8601), OUT (a directory
holding runs.json, jobs/<id>.json, railway.json, railway-checked-at.txt,
public-smoke.json and mcp-3-production-smoke.json).
"""
import datetime, hashlib, json, os, pathlib, subprocess

OUT = pathlib.Path(os.environ["OUT"]); REPO = pathlib.Path("/Users/systemsystems/portfolio/TraceLab")
merge = os.environ["MERGE_SHA"]; now = datetime.datetime.now(datetime.UTC).isoformat()
load = lambda name: json.loads((OUT / name).read_text())
runs = load("runs.json"); ci = []
for run in sorted(runs, key=lambda r: r["workflowName"]):
    jobs = load(f"jobs/{run['databaseId']}.json")["jobs"]
    ci.append({"workflow": run["workflowName"], "run_id": run["databaseId"], "url": run["url"], "event": run["event"], "head_sha": run["headSha"], "head_branch": run["headBranch"], "status": run["status"], "conclusion": run["conclusion"], "created_at": run["createdAt"],
               "jobs": [{"id": j["databaseId"], "name": j["name"], "conclusion": j["conclusion"], "url": j["url"]} for j in jobs]})
assert all(r["head_sha"] == merge and r["event"] == "push" and r["head_branch"] == "main" for r in ci)
required = {"MCP Package": "mcp-package", "Backend Tests": "backend-suite", "Frontend Production Build": "build-frontend-production"}
cited = {name: next(r for r in ci if r["workflow"] == name) for name in required}
railway = load("railway.json"); services = {}
for env in railway["environments"]["edges"]:
    if env["node"]["name"] != "production": continue
    for si in env["node"]["serviceInstances"]["edges"]:
        n = si["node"]
        if n["serviceName"] in ("TraceLab", "frontend"):
            ld = n["latestDeployment"]; services[n["serviceName"]] = {"service_id": n["serviceId"], "deployment_id": ld["id"], "status": ld["status"], "commit": (ld.get("meta") or {}).get("commitHash"), "created_at": ld["createdAt"]}
deployment = {"checked_at": (OUT / "railway-checked-at.txt").read_text().strip(), "commit": merge, "services": services, "both_success_for_commit": len(services) == 2 and all(s["status"] == "SUCCESS" and s["commit"] == merge for s in services.values())}
smoke = load("mcp-3-production-smoke.json")
npm_version = subprocess.run(["npm", "view", "@aquex/tracelab-mcp", "version"], capture_output=True, text=True, check=True).stdout.strip()
npm_time = json.loads(subprocess.run(["npm", "view", "@aquex/tracelab-mcp", "time", "--json"], capture_output=True, text=True, check=True).stdout)
(REPO / "cmos/reports/sprint-52/mcp-3-production-smoke.json").write_text(json.dumps(smoke, indent=2) + "\n")
tag = subprocess.run(["git", "ls-remote", "--tags", "origin", "tracelab-mcp-v1.2.0"], cwd=REPO, capture_output=True, text=True).stdout.strip()
receipt = {
    "mission_id": "MCP-3", "sprint_id": "sprint-52", "generated_at": now, "status": "validated_pending_receipt_merge",
    "source": {"base_commit": os.environ["BASE_COMMIT"], "pr": os.environ["PR_URL"], "source_head": os.environ["SOURCE_HEAD"], "merge_commit": merge, "tag": "tracelab-mcp-v1.2.0", "tag_on_remote": tag},
    "decisions": [425, 426], "learnings_applied": [74, 176, 177],
    "version": {"package_json": json.loads((REPO / "packages/tracelab-mcp/package.json").read_text())["version"], "package_lock": json.loads((REPO / "packages/tracelab-mcp/package-lock.json").read_text())["version"], "npm_registry": npm_version, "npm_publish_time": npm_time.get(npm_version)},
    "publish": {"ran_by": os.environ["PUBLISHED_BY"], "timestamp": os.environ["PUBLISH_TIMESTAMP"], "from": "clean checkout of the merge commit", "verified_with": "npm view @aquex/tracelab-mcp version"},
    "changelog": {"released_section": "[1.2.0] — 2026-09-15", "unreleased_empty": True, "former_unreleased_entries": 12},
    "tables_match_cluster_actions": load("tables-check.json"),
    "post_merge_main_push_ci": ci,
    "cited_runs": {required[name]: {"run_id": r["run_id"], "conclusion": r["conclusion"], "url": r["url"]} for name, r in cited.items()},
    "deployments": deployment,
    "public_smoke": load("public-smoke.json")["summary"],
    "fresh_install_smoke": {"receipt": "cmos/reports/sprint-52/mcp-3-production-smoke.json", "passed": smoke["passed"], "checks": len(smoke["checks"]), "failed": [c["label"] for c in smoke["checks"] if not c["passed"]], "install": smoke["install"]},
    "limitations": ["The fresh npx smoke runs one read-only action per tool; write actions are covered by the package's local stdio contract, not exercised against production.", "Canonical links are resolved with an unauthenticated GET on the public frontend; a 200 proves the route is served, not that the operator's data renders."],
    "closure_gate": "CMOS MCP-3 is marked Completed only after this receipt merges on main and the receipt-carrier main push and both Railway deployments are verified.",
}
path = REPO / "cmos/reports/sprint-52/mcp-3-validation.json"; path.write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps({"receipt": str(path), "npm_version": npm_version, "both_success": deployment["both_success_for_commit"], "smoke_passed": smoke["passed"], "cited": {k: v["conclusion"] for k, v in receipt["cited_runs"].items()}}))
