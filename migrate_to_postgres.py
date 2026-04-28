"""One-shot migration: copy every row from local SQLite to a target Postgres DB.

Usage:
    DATABASE_URL='postgresql://user:pw@host:5432/dbname' python3 migrate_to_postgres.py

Steps:
1. Reads from `aquelyst_hunter.db` (the local SQLite file).
2. Initializes the schema in the Postgres target via `database.init_db()`.
3. Copies every row from every table verbatim.

Safe to re-run: uses INSERT ... ON CONFLICT DO NOTHING so duplicates are skipped.
"""

import os
import sys
import sqlite3 as _sqlite
from pathlib import Path


SQLITE_PATH = "aquelyst_hunter.db"

# Tables to migrate, in dependency order (parents before children).
# `id`-keyed tables on Postgres use SERIAL — when we INSERT with explicit `id`
# values, we then have to bump the sequence to max(id)+1 so future inserts
# don't collide.
TABLES = [
    'leads', 'outreach_drafts', 'follow_ups', 'activities',
    'suppression_list', 'inbound_messages', 'junk_signals',
    'aqua_chat_log', 'aqua_user_memory', 'team_api_keys',
    'admin_users', 'user_accounts', 'user_smtp_configs',
    'provider_connection_log', 'audit_log', 'knowledge_base',
]


def main():
    db_url = os.environ.get('DATABASE_URL', '').strip()
    if not db_url:
        print("ERROR: set DATABASE_URL env var to your Postgres connection string.")
        print("Example: DATABASE_URL='postgresql://user:pw@host:5432/dbname' python3 migrate_to_postgres.py")
        sys.exit(1)

    if not Path(SQLITE_PATH).exists():
        print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)

    # Force the app to use Postgres for init_db
    os.environ['DATABASE_URL'] = db_url
    print(f"📦 Migrating {SQLITE_PATH} → Postgres")
    print(f"   Target: {db_url.split('@')[-1]}")
    print()

    # 1. Initialize Postgres schema
    print("→ Creating schema on Postgres...")
    import database
    database.init_db()
    print("  ✅ Schema created")
    print()

    # 2. Copy every row from every table
    sqlite_conn = _sqlite.connect(SQLITE_PATH)
    sqlite_conn.row_factory = _sqlite.Row

    import db_backend
    pg_conn = db_backend.get_connection()  # uses DATABASE_URL

    total_copied = 0
    for table in TABLES:
        try:
            sc = sqlite_conn.cursor()
            sc.execute(f"SELECT * FROM {table}")
            rows = sc.fetchall()
        except _sqlite.OperationalError as e:
            print(f"  ⚠️  Skipped {table}: {e}")
            continue

        if not rows:
            print(f"  ∅  {table}: empty")
            continue

        # Build the column list once
        cols = list(rows[0].keys())
        col_list = ", ".join(cols)
        ph = ", ".join(["?"] * len(cols))

        # Use ON CONFLICT DO NOTHING for idempotency
        # Detect what conflict target each table uses (primary key or unique)
        # — for safety just do "ON CONFLICT DO NOTHING" without specifying a target,
        # which Postgres allows when there's any unique constraint.
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({ph}) ON CONFLICT DO NOTHING"

        copied = 0
        for r in rows:
            values = tuple(r[col] for col in cols)
            try:
                pc = pg_conn.cursor()
                pc.execute(sql, values)
                copied += 1
            except Exception as e:
                print(f"  ⚠️  Row error in {table}: {e}")
                pg_conn.rollback()
                continue
        pg_conn.commit()
        print(f"  ✅ {table}: copied {copied}/{len(rows)}")
        total_copied += copied

    # 3. Bump sequences to max(id) so future SERIAL inserts don't collide
    print()
    print("→ Resetting Postgres sequences...")
    for table in TABLES:
        try:
            pc = pg_conn.cursor()
            pc.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            )
            pg_conn.commit()
        except Exception:
            pg_conn.rollback()
            continue
    print("  ✅ Sequences aligned")

    sqlite_conn.close()
    pg_conn.close()

    print()
    print(f"🎉 Migration complete — {total_copied} total rows copied.")
    print()
    print("Next: in Streamlit Cloud → Settings → Secrets, add:")
    print(f'    DATABASE_URL = "{db_url}"')
    print("Then redeploy. The app will read/write Postgres from now on.")


if __name__ == "__main__":
    main()
