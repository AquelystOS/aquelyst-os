"""Database backend abstraction.

Lets the rest of the app keep using SQLite-style queries (`?` placeholders,
`sqlite3.Row` row access) while transparently running on Postgres when a
DATABASE_URL is configured (e.g. Supabase, Neon, Render Postgres).

Detection priority:
1. `DATABASE_URL` env var
2. `st.secrets["DATABASE_URL"]`
3. Otherwise → local SQLite

This means:
- Local dev: `aquelyst_hunter.db` SQLite, zero config.
- Streamlit Cloud: set `DATABASE_URL = "postgresql://..."` in Secrets, every read
  and write hits the persistent Postgres. No code changes needed.
"""

import os
import re
import sqlite3
from pathlib import Path


DB_PATH = "aquelyst_hunter.db"


# ============================================================================
# Detection — is Postgres configured?
# ============================================================================
def _get_database_url():
    url = (os.environ.get('DATABASE_URL') or '').strip()
    if url:
        return url
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                v = st.secrets.get('DATABASE_URL', '') or ''
                v = v.strip()
                if v:
                    return v
            except Exception:
                pass
    except ImportError:
        pass
    return None


def backend_kind():
    """Returns 'postgres' or 'sqlite'."""
    return 'postgres' if _get_database_url() else 'sqlite'


# ============================================================================
# Query translation — SQLite syntax → Postgres syntax
# ============================================================================
def _translate_query(q):
    out = q
    # Placeholders
    out = out.replace('?', '%s')
    # AUTOINCREMENT
    out = re.sub(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', 'SERIAL PRIMARY KEY',
                 out, flags=re.IGNORECASE)
    # Boolean defaults
    out = re.sub(r'BOOLEAN\s+DEFAULT\s+0', 'BOOLEAN DEFAULT FALSE', out, flags=re.IGNORECASE)
    out = re.sub(r'BOOLEAN\s+DEFAULT\s+1', 'BOOLEAN DEFAULT TRUE', out, flags=re.IGNORECASE)
    # Boolean-column comparisons — SQLite stores bools as 0/1 ints and tolerates
    # `opt_out = 1`. Postgres is strict and raises UndefinedFunction on
    # boolean-vs-integer comparisons. Translate the known boolean columns.
    for col in ('opt_out', 'approved', 'sent', 'completed'):
        out = re.sub(rf'\b{col}\s*=\s*1\b', f'{col} = TRUE', out)
        out = re.sub(rf'\b{col}\s*=\s*0\b', f'{col} = FALSE', out)
        out = re.sub(rf'\b{col}\s*!=\s*1\b', f'{col} != TRUE', out)
        out = re.sub(rf'\b{col}\s*!=\s*0\b', f'{col} != FALSE', out)
        # SET col = 1 / SET col = 0 in UPDATE statements
        out = re.sub(rf'SET\s+{col}\s*=\s*1', f'SET {col} = TRUE', out, flags=re.IGNORECASE)
        out = re.sub(rf'SET\s+{col}\s*=\s*0', f'SET {col} = FALSE', out, flags=re.IGNORECASE)
    # datetime intervals
    out = re.sub(
        r"datetime\(\s*'now'\s*,\s*'-\s*(\d+)\s*days?'\s*\)",
        r"(NOW() - INTERVAL '\1 days')", out)
    out = re.sub(
        r"datetime\(\s*'now'\s*,\s*'-\s*(\d+)\s*hours?'\s*\)",
        r"(NOW() - INTERVAL '\1 hours')", out)
    out = re.sub(r"datetime\(\s*'now'\s*\)", 'NOW()', out)
    return out


# ============================================================================
# Postgres wrapper that mimics sqlite3 API
# ============================================================================
class _PgRowDict(dict):
    """Dict that also supports indexing by integer position so code that does
    row[0] still works."""
    def __init__(self, mapping=None):
        super().__init__(mapping or {})
        self._values = list(self.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            if isinstance(key, int):
                return self._values[key]
            return super().get(key, default)
        except (IndexError, KeyError):
            return default


class _PgCursor:
    """Wraps psycopg2 cursor with sqlite3-compatible API."""
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor
        self._lastrowid = None

    def execute(self, query, params=()):
        translated = _translate_query(query)
        stripped = translated.lstrip().upper()

        # For INSERTs without an explicit RETURNING, try to capture the id
        if stripped.startswith('INSERT') and 'RETURNING' not in translated.upper():
            try:
                augmented = translated.rstrip().rstrip(';') + ' RETURNING id'
                self._cursor.execute(augmented, params or ())
                try:
                    row = self._cursor.fetchone()
                    if row is not None:
                        # row may be a tuple or DictRow
                        try:
                            self._lastrowid = row['id']
                        except Exception:
                            self._lastrowid = row[0]
                except Exception:
                    self._lastrowid = None
                return self
            except Exception:
                # Table may not have an `id` column (e.g. provider_connection_log
                # whose primary key is `provider`). Fall through to plain execute.
                # We need to rollback the failed statement before retrying.
                try:
                    self._cursor.connection.rollback()
                except Exception:
                    pass

        try:
            self._cursor.execute(translated, params or ())
        except Exception:
            # Postgres puts the whole transaction into "aborted" state on any
            # query failure — every subsequent query then raises
            # InFailedSqlTransaction. Rolling back here clears that state so
            # the caller's `except` can keep going (e.g. best-effort ALTER
            # TABLE schema upgrades).
            try:
                self._cursor.connection.rollback()
            except Exception:
                # If rollback itself failed, the connection is in a bad state.
                # Caller's close() will evict it from the pool.
                pass
            raise
        return self

    def fetchall(self):
        rows = self._cursor.fetchall() or []
        return [_PgRowDict(r) if isinstance(r, dict) else _PgRowDict(dict(r)) for r in rows]

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return _PgRowDict(row)
        try:
            return _PgRowDict(dict(row))
        except Exception:
            # Tuple-like (count(*) etc.) — wrap in pseudo-dict that supports int access
            return _PgRowDict({i: v for i, v in enumerate(row)})

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        try:
            self._cursor.close()
        except Exception:
            pass


class _PgConnection:
    """Mimics sqlite3.Connection on top of a psycopg2 connection."""
    def __init__(self, db_url):
        import psycopg2
        from psycopg2.extras import RealDictCursor
        self._conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        # Autocommit: each statement is its own transaction. Avoids
        # InFailedSqlTransaction poisoning when an idempotent schema upgrade
        # (ALTER TABLE ADD COLUMN on a fresh DB) fails. Trade-off: multi-statement
        # atomicity is lost, but none of our code relies on rollback recovery.
        self._conn.autocommit = True

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        # No-op — we always return dict-like rows
        pass

    def cursor(self):
        return _PgCursor(self._conn.cursor())

    def execute(self, query, params=()):
        c = self.cursor()
        c.execute(query, params)
        return c

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


# ============================================================================
# Public API
# ============================================================================
# ----------------------------------------------------------------------------
# Connection pool for Postgres — reuses a small bank of connections instead of
# doing a full TCP+TLS+auth handshake on every query. Cuts page latency 5-10x
# on remote Postgres (Supabase, Neon, etc.).
# ----------------------------------------------------------------------------
_pg_pool = None


def _get_pg_pool():
    """Lazy-init a small connection pool. Sized conservatively to stay well
    under Supabase free-tier limits (~60 concurrent connections)."""
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    db_url = _get_database_url()
    if not db_url:
        return None
    try:
        from psycopg2.pool import ThreadedConnectionPool
        from psycopg2.extras import RealDictCursor
        # Streamlit Cloud + Supabase free tier: keep pool small to leave headroom
        # for background threads (watcher, auto-engagement, autopilot)
        _pg_pool = ThreadedConnectionPool(
            minconn=1, maxconn=5,
            dsn=db_url,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
        )
        return _pg_pool
    except Exception:
        return None


class _PooledPgConnection(_PgConnection):
    """Variant of _PgConnection whose close() returns the underlying connection
    to the shared pool instead of closing it."""
    def __init__(self, raw_conn, pool):
        # Skip parent __init__ — we already have a live connection
        self._conn = raw_conn
        self._pool = pool
        self._poisoned = False

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            self._poisoned = True

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            self._poisoned = True
        try:
            # If the connection is dead, return it to the pool with close=True
            # so psycopg2 evicts it instead of leaking a dead handle
            self._pool.putconn(self._conn, close=self._poisoned)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass


def _reset_pool():
    """Drop the cached pool. Next get_connection() will rebuild it."""
    global _pg_pool
    if _pg_pool is not None:
        try:
            _pg_pool.closeall()
        except Exception:
            pass
        _pg_pool = None


# When Postgres is unreachable, set this so the rest of the app can show a banner
# and so we don't keep retrying every query. SQLite kicks in as the fallback.
_pg_unreachable_reason = None


def get_pg_unreachable_reason():
    """If Postgres is configured but unreachable, returns the last error string."""
    return _pg_unreachable_reason


def _sqlite_fallback():
    """Local SQLite — used when Postgres is configured but unreachable."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_connection():
    """Return a db connection. SQLite if no DATABASE_URL OR if Postgres is
    unreachable. Postgres (pooled) when configured + reachable.

    Retries on OperationalError — Postgres connections die during Supabase
    pooler rotations, container sleeps, network blips."""
    global _pg_unreachable_reason
    db_url = _get_database_url()
    if not db_url:
        return _sqlite_fallback()

    # If Postgres was unreachable in the last 30s, don't keep hammering it —
    # use SQLite fallback so the app stays usable
    import time as _time
    if _pg_unreachable_reason and _pg_unreachable_reason.get('ts'):
        if _time.time() - _pg_unreachable_reason['ts'] < 30:
            return _sqlite_fallback()

    last_err = None
    for attempt in range(2):
        pool = _get_pg_pool()
        if pool:
            try:
                raw = pool.getconn()
                raw.autocommit = True
                with raw.cursor() as _c:
                    _c.execute("SELECT 1")
                _pg_unreachable_reason = None  # back online
                return _PooledPgConnection(raw, pool)
            except Exception as e:
                last_err = e
                _reset_pool()
                _time.sleep(0.5)
                continue
        # Pool init failed — try a direct connection
        try:
            conn = _PgConnection(db_url)
            _pg_unreachable_reason = None
            return conn
        except Exception as e:
            last_err = e
            _time.sleep(0.5)
            continue

    # Postgres is unreachable. Cache the reason + fall back to SQLite so the
    # app keeps running. The Admin → Database tab will surface this status.
    _pg_unreachable_reason = {
        'ts': _time.time(),
        'error': str(last_err)[:300],
    }
    return _sqlite_fallback()


# ---------------------------------------------------------------------------
# Exception classes — caller code uses `except db_backend.IntegrityError:`
# and gets the right exception for either backend.
# ---------------------------------------------------------------------------
_pg_integrity = ()
_pg_operational = ()
try:
    import psycopg2  # type: ignore
    _pg_integrity = (psycopg2.IntegrityError,)
    _pg_operational = (psycopg2.OperationalError, psycopg2.ProgrammingError)
except Exception:
    pass

IntegrityError = (sqlite3.IntegrityError,) + _pg_integrity
OperationalError = (sqlite3.OperationalError,) + _pg_operational


def safe_test_connection():
    """Return (ok: bool, kind: str, detail: str). For Admin → Database tab."""
    db_url = _get_database_url()
    fallback_active = bool(_pg_unreachable_reason)

    try:
        conn = get_connection()
        c = conn.cursor()
        # If Postgres was configured but we got SQLite back → fallback is active
        if db_url and fallback_active:
            err = _pg_unreachable_reason.get('error', 'unknown')
            try:
                conn.close()
            except Exception:
                pass
            return False, 'postgres-fallback', (
                f"⚠️ Postgres configured but unreachable — using local SQLite "
                f"fallback. Error: {err[:200]}"
            )
        if db_url:
            c.execute("SELECT version()")
            row = c.fetchone()
            ver = row[0] if row is not None else 'unknown'
            conn.close()
            return True, 'postgres', f"Postgres connected — {str(ver)[:80]}"
        c.execute("SELECT sqlite_version()")
        row = c.fetchone()
        ver = row[0] if row is not None else 'unknown'
        conn.close()
        return True, 'sqlite', f"SQLite {ver} (local file: {DB_PATH})"
    except Exception as e:
        return False, backend_kind(), f"Connection failed: {e}"
