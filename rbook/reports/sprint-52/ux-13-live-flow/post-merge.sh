#!/bin/zsh
# Post-merge validation for UX-13. Every must-pass step is guarded with || exit 1 (set -e is inert here).
OUT=/private/tmp/claude-501/-Users-systemsystems-portfolio-TraceLab/f57b0397-720d-4d21-a15b-ad4fa81feecb/scratchpad/ux13
REPO=/Users/systemsystems/portfolio/TraceLab
PR=${PR:-302}
cd $REPO || exit 1
MERGE_SHA=$(gh pr view $PR --json mergeCommit --jq .mergeCommit.oid) || exit 1
[[ -n "$MERGE_SHA" ]] || { echo "no merge commit"; exit 1; }
echo "merge=$MERGE_SHA"
echo "$MERGE_SHA" > $OUT/merge-sha.txt
git fetch -q origin main || exit 1

# 1. Both Railway services must report SUCCESS for the merge commit.
for i in {1..80}; do
  railway status --json > $OUT/railway.json 2>/dev/null || { sleep 15; continue; }
  state=$(python3 - "$MERGE_SHA" <<'PY'
import json, sys
sha = sys.argv[1]
d = json.load(open("/private/tmp/claude-501/-Users-systemsystems-portfolio-TraceLab/f57b0397-720d-4d21-a15b-ad4fa81feecb/scratchpad/ux13/railway.json"))
rows = {}
for env in d["environments"]["edges"]:
    if env["node"]["name"] != "production": continue
    for si in env["node"]["serviceInstances"]["edges"]:
        n = si["node"]
        if n["serviceName"] in ("TraceLab", "frontend"):
            ld = n["latestDeployment"]; rows[n["serviceName"]] = ((ld.get("meta") or {}).get("commitHash"), ld["status"], ld["id"])
ok = all(v[0] == sha and v[1] == "SUCCESS" for v in rows.values()) and len(rows) == 2
failed = any(v[0] == sha and v[1] in ("FAILED", "CRASHED", "REMOVED") for v in rows.values())
print("ok" if ok else ("failed" if failed else "waiting"), json.dumps(rows))
PY
)
  echo "railway: $state"
  case "$state" in
    ok*) break ;;
    failed*) echo "deployment failed"; exit 1 ;;
  esac
  sleep 15
done
[[ "$state" == ok* ]] || { echo "railway timeout"; exit 1; }
date -u +%Y-%m-%dT%H:%M:%SZ > $OUT/railway-checked-at.txt
DEPLOYMENT_IDS=$(python3 -c "
import json; d=json.load(open('$OUT/railway.json')); ids=[]
for env in d['environments']['edges']:
    for si in env['node']['serviceInstances']['edges']:
        n=si['node']
        if n['serviceName'] in ('TraceLab','frontend'): ids.append((n['serviceName'], n['latestDeployment']['id']))
print(','.join(i for _,i in sorted(ids)))")
echo "deployments=$DEPLOYMENT_IDS"

# 2. Main-push CI runs for the merge commit must all complete.
for i in {1..80}; do
  gh run list --branch main --commit $MERGE_SHA --limit 30 --json databaseId,workflowName,conclusion,status,event,headSha,headBranch,url,createdAt > $OUT/runs.json || { sleep 20; continue; }
  total=$(jq 'length' $OUT/runs.json); done_count=$(jq '[.[] | select(.status=="completed")] | length' $OUT/runs.json)
  echo "ci runs: $done_count/$total completed"
  if [[ "$total" -ge 7 && "$done_count" -eq "$total" ]]; then break; fi
  sleep 30
done
[[ "$done_count" -eq "$total" && "$total" -ge 7 ]] || { echo "ci runs incomplete"; exit 1; }
mkdir -p $OUT/jobs
for id in $(jq -r '.[].databaseId' $OUT/runs.json); do gh run view $id --json jobs > $OUT/jobs/$id.json || exit 1; done
jq -r '.[] | "\(.conclusion)\t\(.workflowName)\t\(.databaseId)"' $OUT/runs.json

# 3. Public smoke.
cd $REPO/frontend || exit 1
PLAYWRIGHT_SKIP_SERVER=1 PLAYWRIGHT_BASE_URL=https://tracelab.aquex.ai PLAYWRIGHT_TELEMETRY_OUTPUT=$OUT/public-smoke.json npx playwright test tests/e2e/production-smoke.spec.ts > $OUT/logs/public-smoke.log 2>&1 || { echo "public smoke failed"; exit 1; }
tail -2 $OUT/logs/public-smoke.log

# 4. Direct-browser production baseline (read-only).
rm -rf $OUT/baseline; UI_BASE=https://tracelab.aquex.ai UI_OUT=$OUT/baseline node scripts/ui-shell-smoke.mjs > $OUT/logs/production-baseline.log 2>&1 || { echo "baseline failed"; tail -5 $OUT/logs/production-baseline.log; exit 1; }
python3 -c "import json; s=json.load(open('$OUT/baseline/summary.json')); print('baseline', s['checks'], 'checks', s['routes'], 'routes', 'failures', s['failures'])"

# 5. Inbox read-only checks, then the own-account live flow.
rm -rf $OUT/inbox $OUT/liveflow
INBOX_MODE=readonly UI_OUT=$OUT/inbox DEPLOYMENT_IDS=$DEPLOYMENT_IDS SOURCE_COMMIT=$MERGE_SHA node $OUT/inbox-production.mjs > $OUT/logs/inbox-readonly.log 2>&1 || { echo "inbox readonly failed"; tail -3 $OUT/logs/inbox-readonly.log; exit 1; }
tail -1 $OUT/logs/inbox-readonly.log
INBOX_MODE=liveflow UI_OUT=$OUT/liveflow DEPLOYMENT_IDS=$DEPLOYMENT_IDS SOURCE_COMMIT=$MERGE_SHA node $OUT/inbox-production.mjs > $OUT/logs/inbox-liveflow.log 2>&1 || { echo "inbox live flow failed"; tail -3 $OUT/logs/inbox-liveflow.log; exit 1; }
tail -1 $OUT/logs/inbox-liveflow.log
echo "POST-MERGE VALIDATION COMPLETE"
