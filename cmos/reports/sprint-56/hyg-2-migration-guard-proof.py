"""HYG-2 / next-step #368 proof against real PostgreSQL.

alembic/env.py:32 overrides sqlalchemy.url with settings.database_url, so each
claim runs `alembic upgrade` in its OWN subprocess with DATABASE_URL and
AUTH_USERNAME set — which is also exactly what an operator does.

  A. fresh DB + bare AUTH_USERNAME            -> FAILS at 023 (the new guard)
  B. fresh DB + email AUTH_USERNAME           -> SUCCEEDS, seeds that email
  C. DB already past 023 + bare AUTH_USERNAME -> SUCCEEDS  <- #368's worry
"""
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from testcontainers.postgres import PostgresContainer

# cmos/reports/sprint-56/<this file> -> repo root
REPO = str(Path(__file__).resolve().parents[3])


def alembic(url, auth_username, target):
    env = dict(os.environ, DATABASE_URL=url, AUTH_USERNAME=auth_username)
    # noqa S603: fixed literal argv run through the current interpreter; `target`
    # is a revision id chosen by this script, never external input.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=REPO, env=env, capture_output=True, text=True,
    )


def fresh(pg, name):
    admin = create_engine(pg.get_connection_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return pg.get_connection_url().rsplit("/", 1)[0] + "/" + name


def scalar(url, sql):
    eng = create_engine(url)
    try:
        with eng.connect() as conn:
            return conn.execute(text(sql)).scalar()
    finally:
        eng.dispose()


results = []
with PostgresContainer("postgres:15-alpine") as pg:
    # --- A ---------------------------------------------------------------
    url = fresh(pg, "claim_a")
    r = alembic(url, "tracelab-admin", "head")
    refused = r.returncode != 0 and "AUTH_USERNAME must be an email address" in (
        r.stderr + r.stdout
    )
    seeded = scalar(url, "SELECT to_regclass('public.users')")
    results.append((
        "A  fresh + bare username",
        "PASS" if refused and seeded is None else "FAIL",
        f"rc={r.returncode} guard_message={'yes' if refused else 'NO'} "
        f"users_table={seeded!r} (must be None: nothing was minted)",
    ))

    # --- B ---------------------------------------------------------------
    url = fresh(pg, "claim_b")
    r = alembic(url, "derek@deniedart.com", "head")
    email = scalar(url, "SELECT email FROM users ORDER BY created_at ASC LIMIT 1") if r.returncode == 0 else None
    rev = scalar(url, "SELECT version_num FROM alembic_version") if r.returncode == 0 else None
    results.append((
        "B  fresh + email username",
        "PASS" if r.returncode == 0 and email == "derek@deniedart.com" else "FAIL",
        f"rc={r.returncode} head={rev} seeded_owner={email!r}"
        + ("" if r.returncode == 0 else f" stderr={r.stderr[-300:]}"),
    ))

    # --- C ---------------------------------------------------------------
    url = fresh(pg, "claim_c")
    r1 = alembic(url, "legacy-admin@tracelab.local", "023_add_users_table")
    r2 = alembic(url, "kneelinghorse", "head")  # bare, as the operator has it
    rev = scalar(url, "SELECT version_num FROM alembic_version") if r2.returncode == 0 else None
    n = scalar(url, "SELECT count(*) FROM users") if r2.returncode == 0 else None
    results.append((
        "C  already past 023 + bare username",
        "PASS" if r1.returncode == 0 and r2.returncode == 0 else "FAIL",
        f"provision_rc={r1.returncode} upgrade_rc={r2.returncode} head={rev} users={n}"
        + ("" if r2.returncode == 0 else f" stderr={r2.stderr[-400:]}"),
    ))

print("\n=== next-step #368 proof (real PostgreSQL 15) ===")
for claim, verdict, detail in results:
    print(f"  {verdict}  {claim}\n        {detail}")
sys.exit(0 if all(v == "PASS" for _, v, _ in results) else 1)
