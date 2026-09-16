#!/usr/bin/env python3
"""Wait until both production services SERVE a given commit, then exit 0.

Railway reports a deployment as SUCCESS before the new process is actually serving
traffic, so its status field cannot answer "is this commit live?". Both services
expose the commit they are running -- the backend from its runtime environment, the
frontend from a value inlined at build time -- so polling those is the only signal
that proves a deploy landed.

Exits non-zero on timeout or on a service that never reports the sha. Silence is
never success: every outcome is printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

USER_AGENT = "TraceLab-post-deploy-check/1.0"
BACKEND_DEFAULT = "https://api.tracelab.aquex.ai/api/v1/health"
FRONTEND_DEFAULT = "https://tracelab.aquex.ai/api/version"


def probe(url: str, timeout: float = 15.0) -> tuple[str | None, str | None]:
    """Return (commit, error). A reachable service with no commit yields (None, None)."""
    if not url.startswith(("http://", "https://")):
        return None, f"refusing non-HTTP(S) url: {url}"
    # Cloudflare fronts the frontend domain and answers 403 to the default Python-urllib
    # user-agent, which would read as "the deploy never landed" forever. Identify honestly.
    request = urllib.request.Request(  # noqa: S310 -- scheme checked above
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- scheme checked above
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, str(exc)
    commit = payload.get("commit")
    return (commit if isinstance(commit, str) and commit else None), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True, help="The commit both services must serve")
    parser.add_argument("--backend-url", default=BACKEND_DEFAULT)
    parser.add_argument("--frontend-url", default=FRONTEND_DEFAULT)
    parser.add_argument("--budget-seconds", type=int, default=1200)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--output", help="Write a JSON summary here")
    args = parser.parse_args()

    targets = {"backend": args.backend_url, "frontend": args.frontend_url}
    deadline = time.monotonic() + args.budget_seconds
    started = time.time()
    observed: dict[str, str | None] = dict.fromkeys(targets)
    landed: dict[str, float] = {}

    while True:
        for name, url in targets.items():
            if name in landed:
                continue
            commit, error = probe(url)
            observed[name] = commit
            if error:
                print(f"{name}: unreachable ({error})", flush=True)
            elif commit is None:
                print(f"{name}: reachable but serves no commit marker", flush=True)
            elif commit == args.sha:
                landed[name] = round(time.time() - started, 1)
                print(f"{name}: serving {commit} after {landed[name]}s", flush=True)
            else:
                print(f"{name}: still serving {commit[:10]}, want {args.sha[:10]}", flush=True)

        remaining = deadline - time.monotonic()
        if len(landed) == len(targets) or remaining <= 0:
            break
        time.sleep(min(args.interval_seconds, max(remaining, 1)))

    ok = len(landed) == len(targets)
    summary = {
        "sha": args.sha,
        "ok": ok,
        "observed": observed,
        "seconds_to_serve": landed,
        "budget_seconds": args.budget_seconds,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    if args.output:
        with open(args.output, "w") as handle:
            json.dump(summary, handle, indent=2)
    print(json.dumps(summary, indent=2), flush=True)

    if not ok:
        missing = sorted(set(targets) - set(landed))
        print(
            f"FAILED: {', '.join(missing)} never served {args.sha} within "
            f"{args.budget_seconds}s. Production is NOT running the merged commit.",
            file=sys.stderr,
        )
        return 1
    print(f"Both services serve {args.sha}.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
