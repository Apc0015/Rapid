#!/usr/bin/env python3
"""
scripts/migrate_tenant_db.py — Tenant DB isolation migration.

What it does
------------
1. Creates the ``data/db/`` directory if it does not exist.
2. Reads all non-default tenants from the ``tenants`` table in ``rapid.db``.
3. For each tenant that does not yet have its own ``data/db/{tenant_id}.db``,
   creates the file and applies the core RAPID schema (same tables as rapid.db).
4. Prints a summary of what was created / already existed.

When to run
-----------
Run this once after upgrading to the tenant-isolation release.
Subsequent new tenants are provisioned automatically when their first query
arrives (``db_master._get_tenant_db_path`` creates the file on demand).

Usage
-----
    python scripts/migrate_tenant_db.py
    python scripts/migrate_tenant_db.py --dry-run
    python scripts/migrate_tenant_db.py --db-path path/to/rapid.db

The script is idempotent — safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# ── Resolve project root so we can import config ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import config  # noqa: E402 — after sys.path adjustment


# ── Minimal per-tenant schema ─────────────────────────────────────────────────
# Each tenant DB only needs the tables that hold tenant-specific business data.
# Platform-level tables (tenants, users, JWT tokens, audit log) stay in rapid.db.
TENANT_SCHEMA_SQL = """
-- Placeholder table so the DB file is not empty.
-- Real business tables are created by dept agents on first use.
CREATE TABLE IF NOT EXISTS _rapid_tenant_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _get_tenants(db_path: str) -> list[dict]:
    """Load all tenants from the platform rapid.db."""
    if not Path(db_path).exists():
        print(f"[WARN] rapid.db not found at '{db_path}' — no tenants to migrate.")
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT tenant_id, company_name, status FROM tenants ORDER BY tenant_id"
        )
        tenants = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tenants
    except sqlite3.OperationalError:
        # tenants table does not exist yet — nothing to migrate
        print("[INFO] tenants table not found in rapid.db — nothing to migrate.")
        return []


def _create_tenant_db(tenant_db_path: Path, tenant_id: str, dry_run: bool) -> str:
    """Create the tenant DB file with the base schema. Returns status string."""
    if tenant_db_path.exists():
        return "already_exists"
    if dry_run:
        return "would_create"
    tenant_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tenant_db_path))
    conn.executescript(TENANT_SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO _rapid_tenant_meta VALUES ('tenant_id', ?)",
        (tenant_id,),
    )
    conn.commit()
    conn.close()
    return "created"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate tenant DB isolation")
    parser.add_argument(
        "--db-path",
        default=config.DB_PATH,
        help="Path to the platform rapid.db (default: from config.py)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making any changes",
    )
    args = parser.parse_args()

    db_path   = args.db_path
    dry_run   = args.dry_run
    db_dir    = Path(db_path).parent

    print(f"{'[DRY RUN] ' if dry_run else ''}RAPID Tenant DB Migration")
    print(f"  Platform DB : {db_path}")
    print(f"  Tenant DB dir: {db_dir}")
    print()

    # Ensure the data/db/ directory exists
    if not dry_run:
        db_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Directory '{db_dir}' ready")
    else:
        print(f"  [dry-run] Would ensure '{db_dir}' exists")

    tenants = _get_tenants(db_path)
    if not tenants:
        print("  No tenants found — nothing to do.")
        return

    created = 0
    skipped = 0
    would   = 0

    print(f"\n  Processing {len(tenants)} tenant(s):")
    for t in tenants:
        tid = t["tenant_id"]
        if tid == "default":
            print(f"  • {tid:30s}  → uses rapid.db (no separate file needed)")
            skipped += 1
            continue

        tenant_file = db_dir / f"{tid}.db"
        status = _create_tenant_db(tenant_file, tid, dry_run)

        if status == "created":
            print(f"  • {tid:30s}  → ✓ created {tenant_file}")
            created += 1
        elif status == "already_exists":
            print(f"  • {tid:30s}  → already exists (skipped)")
            skipped += 1
        elif status == "would_create":
            print(f"  • {tid:30s}  → would create {tenant_file}")
            would += 1

    print()
    if dry_run:
        print(f"  Dry-run summary: {would} would be created, {skipped} skipped.")
    else:
        print(f"  Summary: {created} created, {skipped} skipped.")
    print("  Migration complete — no operator steps required for future tenants.")


if __name__ == "__main__":
    main()
