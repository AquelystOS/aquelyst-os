import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import os

import db_backend  # universal SQLite/Postgres backend

DB_PATH = "aquelyst_hunter.db"

STATUSES = [
    "new",
    "researched",
    "drafted",
    "contacted",
    "follow_up_due",
    "interested",
    "trial_offered",
    "sample_sent",
    "closed_won",
    "closed_lost",
    "opted_out"
]

BUSINESS_TYPES = [
    "horse barn",
    "stable",
    "equestrian center",
    "horse boarding facility",
    "trainer",
    "breeder",
    "rescue",
    "tack shop",
    "feed store",
    "other equine business"
]

def init_db():
    """Initialize the database with schema. Works on both SQLite and Postgres
    via the db_backend abstraction layer."""
    import db_backend
    conn = db_backend.get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_name TEXT NOT NULL,
        contact_name TEXT,
        email TEXT UNIQUE,
        phone TEXT,
        website TEXT,
        social_url TEXT,
        city TEXT,
        state TEXT,
        business_type TEXT,
        lead_source TEXT,
        source_channel TEXT,
        message TEXT,
        pain_hypothesis TEXT,
        product_fit TEXT,
        lead_score INTEGER DEFAULT 0,
        status TEXT DEFAULT 'new',
        last_contacted TEXT,
        next_follow_up_date TEXT,
        notes TEXT,
        opt_out BOOLEAN DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS outreach_drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        message_type TEXT,
        subject TEXT,
        content TEXT,
        approved BOOLEAN DEFAULT 0,
        sent BOOLEAN DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS follow_ups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        follow_up_type TEXT,
        scheduled_date TEXT,
        completed BOOLEAN DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        activity_type TEXT,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS suppression_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        reason TEXT,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Captures every email that comes IN — full body of what the prospect said
    c.execute('''CREATE TABLE IF NOT EXISTS inbound_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        from_email TEXT,
        from_name TEXT,
        to_email TEXT,
        subject TEXT,
        body TEXT,
        received_at TEXT,
        message_id_rfc TEXT UNIQUE,
        intent TEXT,
        sentiment TEXT,
        summary TEXT,
        draft_response_id INTEGER,
        read_status INTEGER DEFAULT 0,
        is_junk INTEGER DEFAULT 0,
        junk_reason TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id),
        FOREIGN KEY (draft_response_id) REFERENCES outreach_drafts(id)
    )''')

    # Best-effort schema upgrade for older DBs that pre-date is_junk
    for col_name, col_def in [('is_junk', 'INTEGER DEFAULT 0'),
                                ('junk_reason', 'TEXT')]:
        try:
            c.execute(f'ALTER TABLE inbound_messages ADD COLUMN {col_name} {col_def}')
        except Exception:
            pass

    c.execute('CREATE INDEX IF NOT EXISTS idx_inbound_lead ON inbound_messages(lead_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_inbound_received ON inbound_messages(received_at DESC)')

    # Junk-pattern memory — every "not a real prospect" dismissal teaches the system.
    # Future inbound from matching domains/keywords auto-marks as junk.
    c.execute('''CREATE TABLE IF NOT EXISTS junk_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        value TEXT NOT NULL,
        source_msg_id INTEGER,
        reason TEXT,
        match_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(kind, value)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_junk_signal_kind ON junk_signals(kind)')

    # Aqua's persistent chat memory — per team-member, survives across sessions/redeploys
    c.execute('''CREATE TABLE IF NOT EXISTS aqua_chat_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_aqua_chat_user ON aqua_chat_log(user_email, id DESC)')

    # Aqua's per-user fact memory — things Aqua has learned about each team member
    c.execute('''CREATE TABLE IF NOT EXISTS aqua_user_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        fact TEXT NOT NULL,
        category TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_email, fact)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_aqua_memory_user ON aqua_user_memory(user_email)')

    # Team-member API key pool — each team member's personal Cerebras/Groq/Claude keys.
    # When the team's shared free quota gets throttled, Aqua rotates through everyone's
    # personal keys so capacity scales with team size.
    c.execute('''CREATE TABLE IF NOT EXISTS team_api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        provider TEXT NOT NULL,
        api_key TEXT NOT NULL,
        label TEXT,
        last_ok_at TEXT,
        last_err_at TEXT,
        last_err TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_email, provider)
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_team_keys_provider ON team_api_keys(provider)')

    # Admin allowlist — Joseph is always root admin (enforced in code).
    # Joseph can grant/revoke admin to other team members through this table.
    c.execute('''CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL UNIQUE,
        granted_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Per-user authentication — each team member has their own password.
    # Stored as PBKDF2-hashed with a per-user salt (no plaintext).
    c.execute('''CREATE TABLE IF NOT EXISTS user_accounts (
        email TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        last_login TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Per-user SMTP config — each user connects their own email.
    # Replaces the old global smtp_config.json so logins don't share senders.
    c.execute('''CREATE TABLE IF NOT EXISTS user_smtp_configs (
        user_email TEXT PRIMARY KEY,
        provider TEXT,
        smtp_server TEXT,
        smtp_port INTEGER,
        smtp_email TEXT,
        smtp_app_password_b64 TEXT,
        imap_server TEXT,
        imap_port INTEGER,
        use_tls INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # Federal bid opportunities — SAM.gov + future state procurement portals.
    # Each entry is one RFP/RFQ/sources-sought notice scored against AqueLyst products.
    c.execute('''CREATE TABLE IF NOT EXISTS bid_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        external_id TEXT UNIQUE,
        title TEXT,
        agency TEXT,
        naics TEXT,
        description TEXT,
        posted_at TEXT,
        deadline TEXT,
        place TEXT,
        contact_email TEXT,
        contact_name TEXT,
        contact_phone TEXT,
        url TEXT,
        product_fit TEXT,
        match_score INTEGER,
        match_reasoning TEXT,
        status TEXT DEFAULT 'new',
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_bid_score ON bid_opportunities(match_score DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_bid_deadline ON bid_opportunities(deadline)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_bid_product ON bid_opportunities(product_fit)')

    # Connection-test history + request counters per baseline provider.
    # Used both for showing "connected" status AND for load-balancing across providers.
    c.execute('''CREATE TABLE IF NOT EXISTS provider_connection_log (
        provider TEXT PRIMARY KEY,
        last_ok_at TEXT,
        last_err_at TEXT,
        last_err TEXT,
        last_model TEXT,
        last_used_at TEXT,
        total_requests INTEGER DEFAULT 0,
        ok_requests INTEGER DEFAULT 0,
        err_requests INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    # Best-effort schema upgrade for older databases that don't have the new columns
    for col in ('last_used_at', 'total_requests', 'ok_requests', 'err_requests'):
        try:
            c.execute(f'ALTER TABLE provider_connection_log ADD COLUMN {col} '
                      f'{"INTEGER DEFAULT 0" if col != "last_used_at" else "TEXT"}')
        except Exception:
            pass  # column already exists

    # Per-user attribution columns (added 2026-04-28 — multi-tenancy audit).
    # Each row gets stamped with the team member who created/sent it so two
    # users' Aquas can't blindly double-contact the same lead and so admin
    # views can show "who did what." Idempotent — silently skip if the
    # column is already there.
    for table, col in (
        ('leads',           'last_contacted_by'),
        ('outreach_drafts', 'created_by'),
        ('outreach_drafts', 'sent_by'),
        ('activities',      'created_by'),
        ('inbound_messages','assigned_to'),
    ):
        try:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {col} TEXT')
        except Exception:
            pass

    conn.commit()
    conn.close()


def _current_actor_email():
    """Return the logged-in user's email for attribution columns. Returns
    None if no session_state user exists (background threads, dev mode,
    autopilot without an active user, etc.) — callers should pass an
    explicit actor in those cases."""
    try:
        import streamlit as _st
        return (_st.session_state.get('logged_in_user_email') or '').lower() or None
    except Exception:
        return None


def aqua_save_message(user_email, role, content, source=None):
    """Persist a chat turn for a specific team member."""
    if not user_email or not content:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO aqua_chat_log (user_email, role, content, source)
                 VALUES (?,?,?,?)''', (user_email.lower(), role, content, source))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def aqua_get_chat_history(user_email, limit=40):
    """Get recent chat turns for a user, oldest-first (chronological for the LLM)."""
    if not user_email:
        return []
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT role, content, source, created_at FROM aqua_chat_log
                 WHERE user_email = ?
                 ORDER BY id DESC LIMIT ?''', (user_email.lower(), limit))
    rows = c.fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))


def aqua_clear_chat(user_email):
    """Wipe a user's Aqua chat history (they hit Clear)."""
    if not user_email:
        return 0
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM aqua_chat_log WHERE user_email = ?', (user_email.lower(),))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n


def aqua_remember_fact(user_email, fact, category=None):
    """Aqua learns something about a user. Idempotent — duplicates ignored."""
    if not user_email or not fact:
        return None
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO aqua_user_memory (user_email, fact, category)
                     VALUES (?,?,?)''', (user_email.lower(), fact, category))
        conn.commit()
        new_id = c.lastrowid
    except db_backend.IntegrityError:
        new_id = None
    conn.close()
    return new_id


def aqua_get_user_facts(user_email, limit=50):
    """Return facts Aqua has remembered about this user, newest first."""
    if not user_email:
        return []
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT fact, category, created_at FROM aqua_user_memory
                 WHERE user_email = ?
                 ORDER BY id DESC LIMIT ?''', (user_email.lower(), limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def aqua_forget_fact(fact_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM aqua_user_memory WHERE id = ?', (fact_id,))
    conn.commit()
    conn.close()


# ============================================================================
# Team API key pool — each team member adds their own free Cerebras/Groq/Claude
# key. Aqua rotates through all of them when the shared quota is throttled.
# ============================================================================
def team_keys_save(user_email, provider, api_key, label=None):
    """Save (or replace) one team member's key for a given provider."""
    if not user_email or not provider or not api_key:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO team_api_keys (user_email, provider, api_key, label)
                 VALUES (?,?,?,?)
                 ON CONFLICT(user_email, provider)
                 DO UPDATE SET api_key=excluded.api_key,
                               label=excluded.label,
                               last_err=NULL,
                               last_err_at=NULL''',
              (user_email.lower(), provider, api_key.strip(), label))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def team_keys_get_for_user(user_email, provider):
    """Get one team member's key for a given provider (or None)."""
    if not user_email or not provider:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT api_key FROM team_api_keys
                 WHERE user_email = ? AND provider = ?''',
              (user_email.lower(), provider))
    row = c.fetchone()
    conn.close()
    return row['api_key'] if row else None


def team_keys_get_pool(provider):
    """Get ALL connected team keys for a provider, ordered by least-recently-failed."""
    if not provider:
        return []
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT user_email, api_key, label, last_ok_at, last_err_at
                 FROM team_api_keys
                 WHERE provider = ?
                 ORDER BY COALESCE(last_err_at, '0') ASC,
                          COALESCE(last_ok_at, '0') DESC''', (provider,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def team_keys_list_all():
    """List all team keys for the Setup UI (without exposing the actual secret)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT user_email, provider, label, last_ok_at, last_err_at, last_err,
                          created_at,
                          substr(api_key, 1, 8) || '...' || substr(api_key, -4) as masked_key
                 FROM team_api_keys
                 ORDER BY provider, user_email''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def team_keys_delete(user_email, provider):
    if not user_email or not provider:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM team_api_keys WHERE user_email = ? AND provider = ?',
              (user_email.lower(), provider))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def team_keys_mark_ok(user_email, provider):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''UPDATE team_api_keys
                 SET last_ok_at = CURRENT_TIMESTAMP, last_err = NULL, last_err_at = NULL
                 WHERE user_email = ? AND provider = ?''',
              (user_email.lower(), provider))
    conn.commit()
    conn.close()


def team_keys_mark_err(user_email, provider, error_text):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''UPDATE team_api_keys
                 SET last_err_at = CURRENT_TIMESTAMP, last_err = ?
                 WHERE user_email = ? AND provider = ?''',
              ((error_text or '')[:200], user_email.lower(), provider))
    conn.commit()
    conn.close()


# ============================================================================
# Admin allowlist — Joseph is the root admin (hardcoded). He can grant or
# revoke admin to other team members via this table.
# ============================================================================
def global_search(query, limit_per_kind=20):
    """Search across leads, inbound messages, and outreach drafts.
    Returns dict with three lists: leads, inbound, drafts."""
    if not query or not query.strip():
        return {'leads': [], 'inbound': [], 'drafts': []}
    q = f"%{query.strip()}%"
    conn = get_connection()
    c = conn.cursor()

    c.execute('''SELECT id, business_name, contact_name, email, business_type,
                          city, state, status, lead_score
                 FROM leads
                 WHERE business_name LIKE ? OR contact_name LIKE ?
                       OR email LIKE ? OR notes LIKE ? OR website LIKE ?
                       OR pain_hypothesis LIKE ? OR product_fit LIKE ?
                 ORDER BY lead_score DESC LIMIT ?''',
              (q, q, q, q, q, q, q, limit_per_kind))
    leads = [dict(r) for r in c.fetchall()]

    c.execute('''SELECT i.id, i.lead_id, i.from_email, i.from_name, i.subject,
                          i.body, i.received_at, i.intent, i.sentiment,
                          l.business_name
                 FROM inbound_messages i
                 LEFT JOIN leads l ON i.lead_id = l.id
                 WHERE COALESCE(i.is_junk, 0) = 0 AND
                       (i.subject LIKE ? OR i.body LIKE ? OR i.from_email LIKE ?
                        OR i.from_name LIKE ?)
                 ORDER BY i.received_at DESC LIMIT ?''',
              (q, q, q, q, limit_per_kind))
    inbound = [dict(r) for r in c.fetchall()]

    c.execute('''SELECT d.id, d.lead_id, d.message_type, d.subject, d.content,
                          d.sent, d.created_at, l.business_name
                 FROM outreach_drafts d
                 LEFT JOIN leads l ON d.lead_id = l.id
                 WHERE d.subject LIKE ? OR d.content LIKE ?
                 ORDER BY d.id DESC LIMIT ?''',
              (q, q, limit_per_kind))
    drafts = [dict(r) for r in c.fetchall()]

    conn.close()
    return {'leads': leads, 'inbound': inbound, 'drafts': drafts}


def admin_grant(user_email, granted_by):
    if not user_email:
        return False
    conn = get_connection()
    c = conn.cursor()
    try:
        # Use ON CONFLICT instead of INSERT OR IGNORE so it works on both
        # Postgres and modern SQLite (3.24+). The previous INSERT OR IGNORE
        # form crashed with "syntax error" on Postgres.
        c.execute('''INSERT INTO admin_users (user_email, granted_by)
                     VALUES (?, ?)
                     ON CONFLICT(user_email) DO NOTHING''',
                  (user_email.lower(), (granted_by or '').lower()))
        conn.commit()
        ok = c.rowcount > 0
    finally:
        conn.close()
    return ok


def admin_revoke(user_email):
    if not user_email:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM admin_users WHERE user_email = ?', (user_email.lower(),))
    n = c.rowcount
    conn.commit()
    conn.close()
    return n > 0


def admin_is_granted(user_email):
    """True if this email has been granted admin (does NOT check root-admin rule)."""
    if not user_email:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM admin_users WHERE user_email = ?', (user_email.lower(),))
    found = c.fetchone() is not None
    conn.close()
    return found


# ============================================================================
# Per-user authentication
# ============================================================================
def _hash_password(password, salt=None):
    """PBKDF2-HMAC-SHA256, 200k iterations. Returns (hash_b64, salt_b64)."""
    import hashlib
    import os
    import base64
    if salt is None:
        salt_bytes = os.urandom(16)
    else:
        salt_bytes = base64.b64decode(salt)
    h = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                              salt_bytes, 200000)
    return base64.b64encode(h).decode(), base64.b64encode(salt_bytes).decode()


def user_set_password(email, password):
    """Create or update a user account with the given password."""
    if not email or not password:
        return False
    pwd_hash, salt = _hash_password(password)
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO user_accounts (email, password_hash, salt)
                 VALUES (?, ?, ?)
                 ON CONFLICT(email) DO UPDATE SET
                   password_hash = excluded.password_hash,
                   salt = excluded.salt''',
              (email.lower(), pwd_hash, salt))
    conn.commit()
    conn.close()
    return True


def user_check_password(email, password):
    """Verify a user's password. Returns True/False."""
    if not email or not password:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT password_hash, salt FROM user_accounts WHERE email = ?',
              (email.lower(),))
    row = c.fetchone()
    conn.close()
    if not row:
        return False
    expected_hash = row['password_hash']
    salt = row['salt']
    actual_hash, _ = _hash_password(password, salt=salt)
    import hmac as _hmac
    return _hmac.compare_digest(expected_hash, actual_hash)


def user_account_exists(email):
    if not email:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM user_accounts WHERE email = ?', (email.lower(),))
    found = c.fetchone() is not None
    conn.close()
    return found


def user_record_login(email):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE user_accounts SET last_login = CURRENT_TIMESTAMP '
              'WHERE email = ?', (email.lower(),))
    conn.commit()
    conn.close()


def user_account_list():
    """Every user account in the table — used to merge self-registered users
    into the team roster so admins can see who's on the OS."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT email, last_login, created_at FROM user_accounts '
              'ORDER BY created_at DESC')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def user_delete_account(email):
    """Wipes the password — they have to set a new one next login."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM user_accounts WHERE email = ?', (email.lower(),))
    conn.commit()
    conn.close()


# ============================================================================
# Per-user SMTP configs
# ============================================================================
def smtp_save(user_email, config):
    """Save SMTP config for a user. config is a dict with keys:
    provider, server, port, email, app_password (raw), imap_server, imap_port, use_tls."""
    import base64
    if not user_email:
        return False
    raw_pw = config.get('app_password') or config.get('smtp_app_password_b64', '')
    # If they passed already-encoded password (legacy), keep it; else encode now
    if raw_pw and not config.get('skip_encode'):
        try:
            base64.b64decode(raw_pw, validate=True)
            encoded_pw = raw_pw  # already b64
        except Exception:
            encoded_pw = base64.b64encode(raw_pw.encode()).decode()
    else:
        encoded_pw = raw_pw
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO user_smtp_configs
                 (user_email, provider, smtp_server, smtp_port, smtp_email,
                   smtp_app_password_b64, imap_server, imap_port, use_tls,
                   updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                 ON CONFLICT(user_email) DO UPDATE SET
                   provider = excluded.provider,
                   smtp_server = excluded.smtp_server,
                   smtp_port = excluded.smtp_port,
                   smtp_email = excluded.smtp_email,
                   smtp_app_password_b64 = excluded.smtp_app_password_b64,
                   imap_server = excluded.imap_server,
                   imap_port = excluded.imap_port,
                   use_tls = excluded.use_tls,
                   updated_at = CURRENT_TIMESTAMP''',
              (user_email.lower(),
                config.get('provider'),
                config.get('server') or config.get('smtp_server'),
                config.get('port') or config.get('smtp_port'),
                config.get('email') or config.get('smtp_email'),
                encoded_pw,
                config.get('imap_server'),
                config.get('imap_port'),
                1 if config.get('use_tls', True) else 0))
    conn.commit()
    conn.close()
    return True


def smtp_get(user_email):
    """Get SMTP config for a user. Returns dict or None.
    Returns app_password as decoded plaintext for use in smtplib."""
    import base64
    if not user_email:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM user_smtp_configs WHERE user_email = ?',
              (user_email.lower(),))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    cfg = dict(row)
    if cfg.get('smtp_app_password_b64'):
        try:
            cfg['app_password'] = base64.b64decode(
                cfg['smtp_app_password_b64']).decode()
        except Exception:
            cfg['app_password'] = ''
    return cfg


def smtp_delete(user_email):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM user_smtp_configs WHERE user_email = ?',
              (user_email.lower(),))
    conn.commit()
    conn.close()


def smtp_list_all():
    """Admin view: every user with a connected SMTP."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT user_email, provider, smtp_email, updated_at
                 FROM user_smtp_configs ORDER BY updated_at DESC''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def admin_list():
    """List all granted admins (not including the hardcoded root)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT user_email, granted_by, created_at FROM admin_users
                 ORDER BY created_at''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ============================================================================
# Provider connection log — last-tested status of each baseline provider key.
# ============================================================================
def provider_log_ok(provider, model=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO provider_connection_log
                   (provider, last_ok_at, last_used_at, last_model, last_err, last_err_at,
                    total_requests, ok_requests, err_requests)
                 VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?, NULL, NULL, 1, 1, 0)
                 ON CONFLICT(provider) DO UPDATE SET
                   last_ok_at = CURRENT_TIMESTAMP,
                   last_used_at = CURRENT_TIMESTAMP,
                   last_model = excluded.last_model,
                   last_err = NULL,
                   last_err_at = NULL,
                   total_requests = COALESCE(provider_connection_log.total_requests, 0) + 1,
                   ok_requests = COALESCE(provider_connection_log.ok_requests, 0) + 1,
                   updated_at = CURRENT_TIMESTAMP''',
              (provider, model))
    conn.commit()
    conn.close()


def provider_log_err(provider, error_text):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO provider_connection_log
                   (provider, last_err_at, last_err, last_used_at,
                    total_requests, ok_requests, err_requests)
                 VALUES (?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, 1, 0, 1)
                 ON CONFLICT(provider) DO UPDATE SET
                   last_err_at = CURRENT_TIMESTAMP,
                   last_err = excluded.last_err,
                   last_used_at = CURRENT_TIMESTAMP,
                   total_requests = COALESCE(provider_connection_log.total_requests, 0) + 1,
                   err_requests = COALESCE(provider_connection_log.err_requests, 0) + 1,
                   updated_at = CURRENT_TIMESTAMP''',
              (provider, (error_text or '')[:200]))
    conn.commit()
    conn.close()


# ============================================================================
# Bid opportunities (federal procurement)
# ============================================================================
def save_bid_opportunity(opp):
    """Insert a bid opportunity. Returns 1 if new, 0 if duplicate."""
    if not opp.get('external_id'):
        return 0
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO bid_opportunities
            (source, external_id, title, agency, naics, description,
             posted_at, deadline, place, contact_email, contact_name,
             contact_phone, url, product_fit, match_score, match_reasoning)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (opp.get('source'), opp.get('external_id'), opp.get('title'),
              opp.get('agency'), opp.get('naics'), opp.get('description'),
              opp.get('posted_at'), opp.get('deadline'), opp.get('place'),
              opp.get('contact_email'), opp.get('contact_name'),
              opp.get('contact_phone'), opp.get('url'),
              opp.get('product_fit'), opp.get('match_score'),
              opp.get('match_reasoning')))
        conn.commit()
        return 1
    except db_backend.IntegrityError:
        return 0
    finally:
        conn.close()


def get_bid_opportunities(product_filter=None, status_filter=None,
                           min_score=0, limit=200):
    conn = get_connection()
    c = conn.cursor()
    where = ['match_score >= ?']
    params = [min_score]
    if product_filter:
        where.append('product_fit = ?')
        params.append(product_filter)
    if status_filter:
        where.append('status = ?')
        params.append(status_filter)
    sql = (f"SELECT * FROM bid_opportunities WHERE {' AND '.join(where)} "
           f"ORDER BY match_score DESC, posted_at DESC LIMIT ?")
    params.append(limit)
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_bid_opportunity(opp_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM bid_opportunities WHERE id = ?', (opp_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_bid_opportunity(opp_id, **fields):
    if not fields:
        return
    conn = get_connection()
    c = conn.cursor()
    cols = ', '.join(f"{k} = ?" for k in fields.keys())
    params = list(fields.values()) + [opp_id]
    c.execute(f"UPDATE bid_opportunities SET {cols}, "
               f"updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    conn.commit()
    conn.close()


def delete_bid_opportunity(opp_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM bid_opportunities WHERE id = ?', (opp_id,))
    conn.commit()
    conn.close()


def bid_opportunities_stats():
    """Summary stats for the Bid Opportunities tab."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) as n FROM bid_opportunities")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) as n FROM bid_opportunities WHERE status = 'new'")
        new = c.fetchone()[0]
        c.execute("SELECT COUNT(*) as n FROM bid_opportunities WHERE match_score >= 60")
        hot = c.fetchone()[0]
        c.execute("SELECT product_fit, COUNT(*) as n FROM bid_opportunities "
                   "GROUP BY product_fit ORDER BY n DESC")
        by_product = [(r['product_fit'], r['n']) for r in c.fetchall()]
    except Exception:
        # Table may not exist yet on a fresh DB before init_db has run on PG
        total = new = hot = 0
        by_product = []
    finally:
        conn.close()
    return {'total': total, 'new': new, 'hot': hot, 'by_product': by_product}


def provider_log_pick(provider):
    """Mark provider as 'just chosen for a request' even before we know the result.
    Used by the load-balancer to bump its last_used_at so it goes to the back of
    the rotation queue."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO provider_connection_log (provider, last_used_at)
                 VALUES (?, CURRENT_TIMESTAMP)
                 ON CONFLICT(provider) DO UPDATE SET
                   last_used_at = CURRENT_TIMESTAMP''',
              (provider,))
    conn.commit()
    conn.close()


def provider_log_get(provider):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM provider_connection_log WHERE provider = ?', (provider,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def provider_log_all():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM provider_connection_log ORDER BY provider')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def save_inbound_message(lead_id, from_email, from_name, to_email, subject, body,
                         received_at, message_id_rfc, intent=None, sentiment=None,
                         summary=None, draft_response_id=None):
    """Save an incoming email to the inbound_messages table.
    Auto-flags as junk if it matches a learned junk signal."""
    # Check if this matches a learned junk pattern BEFORE saving
    is_junk_flag = 0
    junk_reason = None
    try:
        is_junk_match, signal = is_likely_junk(from_email, subject, body)
        if is_junk_match:
            is_junk_flag = 1
            junk_reason = f"Auto-flagged: matched {signal}"
    except Exception:
        pass

    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO inbound_messages
                     (lead_id, from_email, from_name, to_email, subject, body,
                      received_at, message_id_rfc, intent, sentiment, summary,
                      draft_response_id, is_junk, junk_reason)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (lead_id, from_email, from_name, to_email, subject, body,
                   received_at, message_id_rfc, intent, sentiment, summary,
                   draft_response_id, is_junk_flag, junk_reason))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except db_backend.IntegrityError:
        # Already saved (duplicate message_id)
        conn.close()
        return None


def link_inbound_to_draft(inbound_id, draft_id):
    """Link an inbound message to the draft we generated in response."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE inbound_messages SET draft_response_id = ? WHERE id = ?',
              (draft_id, inbound_id))
    conn.commit()
    conn.close()


def mark_inbound_junk(msg_id, reason=None):
    """Flag an inbound message as junk + extract pattern signals so future
    similar messages get auto-flagged."""
    conn = get_connection()
    c = conn.cursor()

    # Pull the message so we can extract junk-pattern signals
    c.execute('SELECT * FROM inbound_messages WHERE id = ?', (msg_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    msg = dict(row)

    # Mark this specific message as junk
    c.execute('UPDATE inbound_messages SET is_junk = 1, junk_reason = ? WHERE id = ?',
              ((reason or 'Manually dismissed')[:200], msg_id))

    # Learn pattern signals for future auto-detection
    signals = _extract_junk_signals(msg, reason)
    for kind, value in signals:
        try:
            c.execute('''INSERT INTO junk_signals (kind, value, source_msg_id, reason)
                         VALUES (?,?,?,?)
                         ON CONFLICT(kind, value)
                         DO UPDATE SET match_count = COALESCE(junk_signals.match_count, 0) + 1''',
                      (kind, value, msg_id, (reason or '')[:200]))
        except Exception:
            pass

    conn.commit()
    conn.close()
    return True


def unmark_inbound_junk(msg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE inbound_messages SET is_junk = 0, junk_reason = NULL WHERE id = ?',
              (msg_id,))
    conn.commit()
    conn.close()


def _extract_junk_signals(msg, reason=None):
    """From an inbound message, distill 1-N signals other messages can match against:
    - sender_domain: bounce future emails from this domain
    - sender_email: exact match
    - subject_keyword: low-frequency tokens from the subject (proper nouns, brand names)
    """
    signals = []
    from_email = (msg.get('from_email') or '').lower()
    if from_email:
        signals.append(('sender_email', from_email))
        domain = from_email.split('@', 1)[-1] if '@' in from_email else ''
        if domain and '.' in domain and domain not in (
            'gmail.com', 'outlook.com', 'yahoo.com', 'icloud.com',
            'hotmail.com', 'aol.com', 'protonmail.com', 'live.com'):
            signals.append(('sender_domain', domain))

    subject = (msg.get('subject') or '').lower()
    body_preview = (msg.get('body') or '').lower()[:600]

    # Tokenize meaningful keywords (length 4+, alphabetic) from subject
    import re as _re
    subj_tokens = [t for t in _re.findall(r'[a-z][a-z0-9\-]{3,}', subject)
                   if t not in {'this', 'that', 'with', 'from', 'your',
                                  'have', 'will', 'about', 'just', 'only',
                                  'best', 'free', 'time', 'over', 'when',
                                  'into', 'them', 'they', 'what', 'been',
                                  'were', 'some', 'than', 'more', 'like',
                                  'subject', 'email'}]
    # Top 3 distinctive tokens from subject as signals
    for tok in subj_tokens[:3]:
        signals.append(('subject_keyword', tok))

    # Common spam/vendor-pitch phrases in body
    spam_phrases = [
        'seo services', 'rank higher', 'web design', 'leads guaranteed',
        'increase your sales', 'verified leads', 'unsubscribe',
        'limited time offer', 'crypto', 'bitcoin', 'ethereum',
        'investment opportunity', 'business proposal', 'collaborate',
        'guest post', 'backlink', 'website audit', 'lead generation',
        'partnership opportunity', 'we noticed your website',
    ]
    for phrase in spam_phrases:
        if phrase in body_preview or phrase in subject:
            signals.append(('body_phrase', phrase))

    return list(set(signals))


def is_likely_junk(from_email, subject, body):
    """Check if an incoming message matches any learned junk signal.
    Returns (True, matched_signal) or (False, None)."""
    if not from_email and not subject:
        return False, None
    conn = get_connection()
    c = conn.cursor()
    try:
        # Exact sender_email match
        if from_email:
            c.execute('SELECT id FROM junk_signals WHERE kind = ? AND value = ?',
                      ('sender_email', from_email.lower()))
            if c.fetchone():
                return True, f"sender_email:{from_email}"
            # Domain match
            domain = from_email.split('@', 1)[-1].lower() if '@' in from_email else ''
            if domain:
                c.execute('SELECT id FROM junk_signals WHERE kind = ? AND value = ?',
                          ('sender_domain', domain))
                if c.fetchone():
                    return True, f"sender_domain:{domain}"

        # Body phrase match
        body_l = (body or '').lower()
        c.execute('SELECT value FROM junk_signals WHERE kind = ?', ('body_phrase',))
        for row in c.fetchall():
            if row['value'] in body_l or row['value'] in (subject or '').lower():
                return True, f"body_phrase:{row['value']}"

        # Subject keyword: requires 2+ matching keywords to be conservative
        subj_l = (subject or '').lower()
        c.execute('SELECT value FROM junk_signals WHERE kind = ?', ('subject_keyword',))
        sk_rows = [r['value'] for r in c.fetchall()]
        matches = [v for v in sk_rows if v in subj_l]
        if len(matches) >= 2:
            return True, f"subject_keywords:{','.join(matches[:3])}"
    finally:
        conn.close()
    return False, None


def get_junk_signals(limit=200):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM junk_signals ORDER BY match_count DESC, id DESC LIMIT ?',
              (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_junk_signal(signal_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM junk_signals WHERE id = ?', (signal_id,))
    conn.commit()
    conn.close()


def get_inbound_for_lead(lead_id, limit=20):
    """Get all incoming messages from a specific lead."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM inbound_messages WHERE lead_id = ?
                 ORDER BY received_at DESC LIMIT ?''', (lead_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_inbound_by_draft(draft_id):
    """Get the incoming message that a draft is responding to (if any)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM inbound_messages WHERE draft_response_id = ? LIMIT 1', (draft_id,))
    row = c.fetchone()
    conn.close()
    return row


def get_all_inbound(limit=100, include_junk=False):
    """Get all incoming messages, newest first, joined with lead info.
    By default filters out junk-flagged messages; set include_junk=True to see them."""
    conn = get_connection()
    c = conn.cursor()
    where = "" if include_junk else "WHERE COALESCE(i.is_junk, 0) = 0"
    c.execute(f'''SELECT i.*, l.business_name, l.contact_name, l.lead_score
                  FROM inbound_messages i
                  LEFT JOIN leads l ON i.lead_id = l.id
                  {where}
                  ORDER BY i.received_at DESC LIMIT ?''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_conversation_thread(lead_id):
    """Build a unified chronological conversation thread for a lead.

    Merges outbound emails (drafts that were sent) with inbound replies into
    a single timeline. Each item has a 'direction' field ('out' or 'in').

    Returns a list of dicts ordered oldest → newest, each with:
        direction: 'out' | 'in'
        subject, body, timestamp, type
        For inbound: intent, sentiment, summary
        For outbound: message_type, status (sent/draft), draft_id
    """
    conn = get_connection()
    c = conn.cursor()

    # Outbound: sent drafts + pending drafts
    c.execute('''SELECT id, message_type, subject, content, created_at, sent, approved
                 FROM outreach_drafts WHERE lead_id = ?''', (lead_id,))
    outbound = c.fetchall()

    # Inbound: messages received from the lead
    c.execute('''SELECT id, from_email, from_name, subject, body, received_at,
                        intent, sentiment, summary, draft_response_id
                 FROM inbound_messages WHERE lead_id = ?''', (lead_id,))
    inbound = c.fetchall()

    conn.close()

    thread = []
    for d in outbound:
        thread.append({
            'direction': 'out',
            'id': d['id'],
            'subject': d['subject'] or '',
            'body': d['content'] or '',
            'timestamp': d['created_at'] or '',
            'message_type': d['message_type'] or '',
            'sent': bool(d['sent']),
            'approved': bool(d['approved']),
        })

    for m in inbound:
        thread.append({
            'direction': 'in',
            'id': m['id'],
            'subject': m['subject'] or '',
            'body': m['body'] or '',
            'timestamp': m['received_at'] or '',
            'from_email': m['from_email'] or '',
            'from_name': m['from_name'] or '',
            'intent': m['intent'] or '',
            'sentiment': m['sentiment'] or '',
            'summary': m['summary'] or '',
            'draft_response_id': m['draft_response_id'],
        })

    # Sort chronologically (oldest first — like chat history).
    # Normalize timestamps so naive UTC and aware datetimes sort correctly.
    def _sort_key(item):
        ts = item.get('timestamp', '') or ''
        # Strip timezone marker for consistent sorting (all stored as UTC)
        if 'T' in ts and ('+' in ts or 'Z' in ts):
            ts = ts.split('+')[0].rstrip('Z')
        return ts
    thread.sort(key=_sort_key)
    return thread


def log_activity(lead_id, activity_type, description, actor=None):
    """Log an activity for the activity feed. `actor` defaults to the logged-in
    user's email so the activity feed can show "who did what" per row."""
    conn = get_connection()
    c = conn.cursor()
    actor = (actor or _current_actor_email() or '').lower() or None
    c.execute('''INSERT INTO activities (lead_id, activity_type, description, created_by)
                 VALUES (?, ?, ?, ?)''',
              (lead_id, activity_type, description, actor))
    conn.commit()
    conn.close()


def get_recent_activities(limit=20):
    """Get recent activity feed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT a.*, l.business_name FROM activities a
                 LEFT JOIN leads l ON a.lead_id = l.id
                 ORDER BY a.created_at DESC LIMIT ?''', (limit,))
    activities = c.fetchall()
    conn.close()
    return activities


def add_to_suppression(email, reason="manual"):
    """Add email to suppression list."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO suppression_list (email, reason)
                     VALUES (?, ?)''', (email, reason))
        c.execute("UPDATE leads SET opt_out = 1, status = 'opted_out' WHERE email = ?", (email,))
        conn.commit()
        return True
    except db_backend.IntegrityError:
        return False
    finally:
        conn.close()


def is_suppressed(email):
    """Check if email is on suppression list."""
    if not email:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id FROM suppression_list WHERE email = ?', (email,))
    result = c.fetchone()
    conn.close()
    return result is not None


def get_suppression_list():
    """Get all suppressed emails."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM suppression_list ORDER BY added_at DESC')
    results = [dict(r) for r in c.fetchall()]
    conn.close()
    return results


def remove_from_suppression(email):
    """Remove an email from the suppression list. Restores their lead status to 'new'."""
    if not email:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM suppression_list WHERE LOWER(email) = LOWER(?)', (email,))
    n = c.rowcount
    # Also reset opt_out flag on any matching lead
    c.execute("UPDATE leads SET opt_out = 0 WHERE LOWER(email) = LOWER(?)", (email,))
    conn.commit()
    conn.close()
    return n > 0


def bulk_update_status(lead_ids, new_status):
    """Update status for multiple leads at once."""
    if not lead_ids:
        return 0
    conn = get_connection()
    c = conn.cursor()
    placeholders = ','.join(['?'] * len(lead_ids))
    c.execute(f'UPDATE leads SET status = ?, updated_at = ? WHERE id IN ({placeholders})',
              [new_status, datetime.now().isoformat()] + list(lead_ids))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected


def bulk_schedule_follow_up(lead_ids, days_from_now, follow_up_type="bulk"):
    """Schedule follow-ups for multiple leads."""
    if not lead_ids:
        return 0
    scheduled_date = (datetime.now() + timedelta(days=days_from_now)).strftime('%Y-%m-%d')
    conn = get_connection()
    c = conn.cursor()
    for lead_id in lead_ids:
        c.execute('''INSERT INTO follow_ups (lead_id, follow_up_type, scheduled_date)
                     VALUES (?, ?, ?)''', (lead_id, follow_up_type, scheduled_date))
        c.execute('UPDATE leads SET next_follow_up_date = ? WHERE id = ?',
                  (scheduled_date, lead_id))
    conn.commit()
    conn.close()
    return len(lead_ids)


def get_pipeline_view():
    """Get leads grouped by status for kanban view."""
    conn = get_connection()
    c = conn.cursor()

    pipeline = {}
    for status in STATUSES:
        c.execute('SELECT * FROM leads WHERE status = ? ORDER BY lead_score DESC LIMIT 50', (status,))
        pipeline[status] = c.fetchall()

    conn.close()
    return pipeline


def search_leads(search_term):
    """Full-text search across leads."""
    conn = get_connection()
    c = conn.cursor()
    search_pattern = f'%{search_term}%'
    c.execute('''SELECT * FROM leads
                 WHERE business_name LIKE ?
                 OR contact_name LIKE ?
                 OR email LIKE ?
                 OR notes LIKE ?
                 OR pain_hypothesis LIKE ?
                 ORDER BY lead_score DESC LIMIT 100''',
              (search_pattern,) * 5)
    results = c.fetchall()
    conn.close()
    return results


def update_drafts_with_lead_changes(lead_id):
    """Mark old drafts as stale when lead info changes significantly."""
    pass

def get_connection():
    """Get a database connection — Postgres if DATABASE_URL is configured,
    otherwise local SQLite. The connection mimics sqlite3 API either way."""
    import db_backend
    return db_backend.get_connection()

def add_lead(business_name, contact_name=None, email=None, phone=None, website=None,
             social_url=None, city=None, state=None, business_type=None, lead_source=None,
             source_channel=None, message=None, pain_hypothesis=None, product_fit=None, notes=None):
    """Add a new lead to database."""
    conn = get_connection()
    c = conn.cursor()

    try:
        c.execute('''INSERT INTO leads
            (business_name, contact_name, email, phone, website, social_url, city, state,
             business_type, lead_source, source_channel, message, pain_hypothesis, product_fit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (business_name, contact_name, email, phone, website, social_url, city, state,
             business_type, lead_source, source_channel, message, pain_hypothesis, product_fit, notes))
        conn.commit()
        lead_id = c.lastrowid
        conn.close()

        # Audit log
        try:
            import audit_log
            audit_log.log_lead_change(
                lead_id=lead_id,
                action=f"Lead created: {business_name}",
                lead_name=business_name,
                after={'email': email, 'lead_source': lead_source},
            )
        except Exception:
            pass

        return lead_id
    except db_backend.IntegrityError:
        conn.close()
        return None

def get_all_leads(include_team_internal=False):
    """Retrieve all leads. Excludes team-internal by default."""
    conn = get_connection()
    c = conn.cursor()
    if include_team_internal:
        c.execute('SELECT * FROM leads ORDER BY created_at DESC')
    else:
        c.execute("""SELECT * FROM leads
                     WHERE (lead_source IS NULL OR lead_source != 'team_internal')
                     AND (status IS NULL OR status != 'team_internal')
                     ORDER BY created_at DESC""")
    leads = c.fetchall()
    conn.close()
    return leads


def get_team_internal_leads():
    """Get only team-internal leads (used for tracking team-to-team email)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT * FROM leads
                 WHERE lead_source = 'team_internal' OR status = 'team_internal'
                 ORDER BY created_at DESC""")
    leads = c.fetchall()
    conn.close()
    return leads

def get_lead(lead_id):
    """Get a specific lead."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM leads WHERE id = ?', (lead_id,))
    lead = c.fetchone()
    conn.close()
    return lead

def update_lead(lead_id, **kwargs):
    """Update lead fields."""
    conn = get_connection()
    c = conn.cursor()

    allowed_fields = {
        'business_name', 'contact_name', 'email', 'phone', 'website', 'social_url',
        'city', 'state', 'business_type', 'lead_source', 'source_channel', 'message',
        'pain_hypothesis', 'product_fit', 'lead_score', 'status', 'last_contacted',
        'next_follow_up_date', 'notes', 'opt_out', 'last_contacted_by',
    }

    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        conn.close()
        return False

    # Auto-stamp last_contacted_by whenever last_contacted is updated,
    # unless the caller explicitly passed last_contacted_by.
    if 'last_contacted' in updates and 'last_contacted_by' not in updates:
        actor = _current_actor_email()
        if actor:
            updates['last_contacted_by'] = actor

    updates['updated_at'] = datetime.now().isoformat()

    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [lead_id]

    c.execute(f'UPDATE leads SET {set_clause} WHERE id = ?', values)
    conn.commit()

    # Get business name for audit
    try:
        c.execute('SELECT business_name FROM leads WHERE id = ?', (lead_id,))
        biz_row = c.fetchone()
        biz_name = biz_row['business_name'] if biz_row else None
    except Exception:
        biz_name = None

    conn.close()

    # Audit log only meaningful field changes (skip pure metadata like updated_at)
    try:
        meaningful = {k: v for k, v in kwargs.items()
                      if k not in ('updated_at',) and k in allowed_fields}
        if meaningful:
            import audit_log
            audit_log.log_lead_change(
                lead_id=lead_id,
                action=f"Updated lead {biz_name}: {', '.join(meaningful.keys())}",
                lead_name=biz_name,
                after=meaningful,
            )
    except Exception:
        pass

    return True

def get_leads_by_status(status):
    """Get all leads with a specific status."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC', (status,))
    leads = c.fetchall()
    conn.close()
    return leads

def get_hot_leads():
    """Get high-scoring leads (score >= 70). Excludes team-internal entries."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT * FROM leads
                 WHERE lead_score >= 70
                 AND status != 'opted_out'
                 AND status != 'team_internal'
                 AND (lead_source IS NULL OR lead_source != 'team_internal')
                 ORDER BY lead_score DESC""")
    leads = c.fetchall()
    conn.close()
    return leads

def get_follow_ups_due():
    """Get leads with follow-ups due today."""
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("""SELECT * FROM leads
                 WHERE next_follow_up_date IS NOT NULL
                 AND next_follow_up_date <= ?
                 AND status != 'opted_out'
                 AND status != 'closed_won'
                 AND status != 'closed_lost'
                 ORDER BY next_follow_up_date ASC""", (today,))
    leads = c.fetchall()
    conn.close()
    return leads

def init_email_tracking_table():
    """Idempotent CREATE TABLE for click + open events. Called lazily from
    the tracking helpers so we don't have to touch init_db()."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS email_tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            draft_id INTEGER,
            lead_id INTEGER,
            url TEXT,
            user_agent TEXT,
            ip_hash TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_track_draft ON email_tracking_events(draft_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_track_lead ON email_tracking_events(lead_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_track_event ON email_tracking_events(event_type)')
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def record_email_event(event_type, draft_id=None, lead_id=None, url=None,
                        user_agent=None, ip_hash=None):
    """Record an email open / click event."""
    init_email_tracking_table()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO email_tracking_events
                      (event_type, draft_id, lead_id, url, user_agent, ip_hash)
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (event_type, draft_id, lead_id,
                    (url or '')[:500], (user_agent or '')[:200],
                    (ip_hash or '')[:64]))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_tracking_for_draft(draft_id):
    """Return all tracking events for one draft (used by inbox detail view)."""
    if not draft_id:
        return []
    init_email_tracking_table()
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT event_type, url, created_at
                  FROM email_tracking_events
                  WHERE draft_id = ? ORDER BY created_at''', (draft_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def has_inbound_messages(lead_id):
    """True if this lead has ever replied (any inbound_message linked).
    Used by smart-cadence to skip auto-follow-up on already-engaged
    leads — never want to pile a cold touch on top of a warm thread."""
    if not lead_id:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM inbound_messages WHERE lead_id = ? LIMIT 1',
              (lead_id,))
    found = c.fetchone() is not None
    conn.close()
    return found


def get_recent_sends_by_sender(sender_email, limit=3):
    """Last N sent drafts by a specific user — used as few-shot voice
    examples in Aqua's prompt so she mimics each user's actual style.

    Filters out templates / fallbacks and very short bodies (< 60 chars)
    that wouldn't help a model learn voice."""
    if not sender_email:
        return []
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT subject, content, message_type, created_at
                  FROM outreach_drafts
                  WHERE sent = 1
                    AND COALESCE(sent_by, '') = ?
                    AND content IS NOT NULL
                    AND length(content) >= 60
                  ORDER BY created_at DESC
                  LIMIT ?''',
               (sender_email.lower(), limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def cold_email_performance_stats(days=30):
    """Aggregate cold-email performance for the Admin → Performance panel.

    A "reply" is any inbound_message whose lead matches a sent draft within
    the lookback window. Reply rate = unique-leads-replied / unique-leads-
    contacted. Higher is better — this is the single most important
    cold-outreach KPI.

    Returns a dict with:
      - totals: sent, leads_contacted, replies, reply_rate_pct
      - by_message_type: per cold_email / aqua_intro / followup / etc.
      - by_sender: who's sending what + how it's converting
      - by_day_of_week: when replies cluster
      - by_hour: best time-of-day to send
      - top_subjects: subject lines ranked by reply rate (min 3 sends)
    """
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    conn = get_connection()
    c = conn.cursor()
    out = {
        'days': days,
        'totals': {'sent': 0, 'leads_contacted': 0,
                    'replies': 0, 'reply_rate_pct': 0.0},
        'by_message_type': [],
        'by_sender': [],
        'by_day_of_week': [],
        'by_hour': [],
        'top_subjects': [],
    }
    try:
        # ---- TOTALS ----
        c.execute('''SELECT COUNT(*) as n_sent,
                            COUNT(DISTINCT lead_id) as n_leads
                      FROM outreach_drafts
                      WHERE sent = 1 AND created_at >= ?''', (cutoff,))
        row = c.fetchone()
        out['totals']['sent'] = (row['n_sent'] or 0) if row else 0
        out['totals']['leads_contacted'] = (row['n_leads'] or 0) if row else 0

        # Replies = unique leads we contacted that ALSO have an inbound_message
        # received after our send. Cheap approximation: any inbound_message
        # whose lead_id is in our sent set (within window).
        c.execute('''SELECT COUNT(DISTINCT i.lead_id) as n_replies
                      FROM inbound_messages i
                      WHERE i.received_at >= ?
                        AND i.lead_id IN (
                          SELECT DISTINCT lead_id FROM outreach_drafts
                          WHERE sent = 1 AND created_at >= ?
                        )''', (cutoff, cutoff))
        row = c.fetchone()
        out['totals']['replies'] = (row['n_replies'] or 0) if row else 0
        if out['totals']['leads_contacted']:
            out['totals']['reply_rate_pct'] = round(
                100.0 * out['totals']['replies']
                / out['totals']['leads_contacted'], 1)

        # ---- BY MESSAGE TYPE ----
        c.execute('''SELECT message_type, COUNT(*) as sent_n,
                            COUNT(DISTINCT lead_id) as leads_n
                      FROM outreach_drafts
                      WHERE sent = 1 AND created_at >= ?
                      GROUP BY message_type''', (cutoff,))
        types = [dict(r) for r in c.fetchall()]
        # Replies per message_type
        for t in types:
            c.execute('''SELECT COUNT(DISTINCT i.lead_id) as r
                          FROM inbound_messages i
                          WHERE i.received_at >= ?
                            AND i.lead_id IN (
                              SELECT DISTINCT lead_id FROM outreach_drafts
                              WHERE sent = 1 AND created_at >= ?
                                AND message_type = ?
                            )''', (cutoff, cutoff, t['message_type']))
            row = c.fetchone()
            t['replies'] = (row['r'] or 0) if row else 0
            t['reply_rate'] = round(100.0 * t['replies'] / t['leads_n'], 1) if t['leads_n'] else 0
        types.sort(key=lambda x: -x['reply_rate'])
        out['by_message_type'] = types

        # ---- BY SENDER (who's sending + their conversion) ----
        c.execute('''SELECT COALESCE(sent_by, '?') as sender,
                            COUNT(*) as sent_n,
                            COUNT(DISTINCT lead_id) as leads_n
                      FROM outreach_drafts
                      WHERE sent = 1 AND created_at >= ?
                      GROUP BY sent_by''', (cutoff,))
        senders = [dict(r) for r in c.fetchall()]
        for s in senders:
            c.execute('''SELECT COUNT(DISTINCT i.lead_id) as r
                          FROM inbound_messages i
                          WHERE i.received_at >= ?
                            AND i.lead_id IN (
                              SELECT DISTINCT lead_id FROM outreach_drafts
                              WHERE sent = 1 AND created_at >= ?
                                AND COALESCE(sent_by, '?') = ?
                            )''', (cutoff, cutoff, s['sender']))
            row = c.fetchone()
            s['replies'] = (row['r'] or 0) if row else 0
            s['reply_rate'] = round(100.0 * s['replies'] / s['leads_n'], 1) if s['leads_n'] else 0
        senders.sort(key=lambda x: -x['reply_rate'])
        out['by_sender'] = senders

        # ---- TOP SUBJECT LINES (min 3 sends to filter noise) ----
        c.execute('''SELECT subject, COUNT(*) as sent_n,
                            COUNT(DISTINCT lead_id) as leads_n
                      FROM outreach_drafts
                      WHERE sent = 1 AND created_at >= ?
                        AND subject IS NOT NULL AND subject != ''
                      GROUP BY subject
                      HAVING COUNT(*) >= 3
                      ORDER BY sent_n DESC LIMIT 25''', (cutoff,))
        subjects = [dict(r) for r in c.fetchall()]
        for s in subjects:
            c.execute('''SELECT COUNT(DISTINCT i.lead_id) as r
                          FROM inbound_messages i
                          WHERE i.received_at >= ?
                            AND i.lead_id IN (
                              SELECT DISTINCT lead_id FROM outreach_drafts
                              WHERE sent = 1 AND created_at >= ? AND subject = ?
                            )''', (cutoff, cutoff, s['subject']))
            row = c.fetchone()
            s['replies'] = (row['r'] or 0) if row else 0
            s['reply_rate'] = round(100.0 * s['replies'] / s['leads_n'], 1) if s['leads_n'] else 0
        subjects.sort(key=lambda x: -x['reply_rate'])
        out['top_subjects'] = subjects[:15]
    except Exception:
        pass
    finally:
        conn.close()
    return out


def get_dashboard_stats():
    """Get key dashboard statistics."""
    conn = get_connection()
    c = conn.cursor()

    stats = {}

    c.execute('SELECT COUNT(*) FROM leads')
    stats['total_leads'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE status = 'new'")
    stats['new_leads'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE lead_score >= 70')
    stats['hot_leads'] = c.fetchone()[0]

    today = datetime.now().strftime('%Y-%m-%d')
    c.execute("""SELECT COUNT(*) FROM leads
                 WHERE next_follow_up_date IS NOT NULL
                 AND next_follow_up_date <= ?
                 AND status NOT IN ('opted_out', 'closed_won', 'closed_lost')""", (today,))
    stats['follow_ups_due'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE status = 'interested'")
    stats['interested'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE status = 'trial_offered'")
    stats['trial_offered'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE status = 'closed_won'")
    stats['closed_won'] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE status = 'closed_lost'")
    stats['closed_lost'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE opt_out = 1')
    stats['opt_outs'] = c.fetchone()[0]

    if stats['total_leads'] > 0:
        conversion_rate = (stats['closed_won'] / stats['total_leads']) * 100
        stats['conversion_rate'] = round(conversion_rate, 1)
    else:
        stats['conversion_rate'] = 0

    conn.close()
    return stats

def add_outreach_draft(lead_id, message_type, subject, content, created_by=None):
    """Add an outreach draft. `created_by` defaults to the logged-in user so
    we can show whose draft it is and prevent another user's auto-engagement
    bot from generating a competing draft for the same lead."""
    conn = get_connection()
    c = conn.cursor()
    created_by = (created_by or _current_actor_email() or '').lower() or None
    c.execute('''INSERT INTO outreach_drafts
                  (lead_id, message_type, subject, content, created_by)
                 VALUES (?, ?, ?, ?, ?)''',
              (lead_id, message_type, subject, content, created_by))
    conn.commit()
    draft_id = c.lastrowid
    conn.close()
    return draft_id

def get_drafts_for_lead(lead_id):
    """Get all drafts for a lead."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM outreach_drafts WHERE lead_id = ? ORDER BY created_at DESC', (lead_id,))
    drafts = c.fetchall()
    conn.close()
    return drafts

def approve_draft(draft_id):
    """Approve a draft."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE outreach_drafts SET approved = 1 WHERE id = ?', (draft_id,))
    conn.commit()
    conn.close()

def mark_draft_sent(draft_id, sent_by=None):
    """Mark a draft as sent + record who sent it. `sent_by` defaults to the
    logged-in user."""
    conn = get_connection()
    c = conn.cursor()
    sent_by = (sent_by or _current_actor_email() or '').lower() or None
    c.execute('UPDATE outreach_drafts SET sent = 1, sent_by = ? WHERE id = ?',
              (sent_by, draft_id))
    conn.commit()
    conn.close()

def delete_draft(draft_id):
    """Discard a draft. Used by the Discard buttons on Inbox/Today/Thread."""
    if not draft_id:
        return
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM outreach_drafts WHERE id = ?', (draft_id,))
        conn.commit()
    finally:
        conn.close()

def get_all_drafts(limit=200):
    """Return ALL outreach drafts (sent + unsent) joined with lead info."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT d.*, l.business_name, l.contact_name, l.email as lead_email,
                         l.lead_score, l.status as lead_status
                 FROM outreach_drafts d
                 LEFT JOIN leads l ON d.lead_id = l.id
                 ORDER BY d.created_at DESC LIMIT ?''', (limit,))
    drafts = c.fetchall()
    conn.close()
    return drafts


def get_sent_drafts(limit=100):
    """Drafts that have been sent (i.e. real outbound emails)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT d.*, l.business_name, l.contact_name, l.email as lead_email,
                         l.lead_score
                 FROM outreach_drafts d
                 LEFT JOIN leads l ON d.lead_id = l.id
                 WHERE d.sent = 1
                 ORDER BY d.created_at DESC LIMIT ?''', (limit,))
    drafts = c.fetchall()
    conn.close()
    return drafts


def get_pending_drafts(limit=100):
    """Drafts that need approval (created but not sent)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT d.*, l.business_name, l.contact_name, l.email as lead_email,
                         l.lead_score
                 FROM outreach_drafts d
                 LEFT JOIN leads l ON d.lead_id = l.id
                 WHERE d.sent = 0
                 ORDER BY d.created_at DESC LIMIT ?''', (limit,))
    drafts = c.fetchall()
    conn.close()
    return drafts


def get_approved_drafts():
    """Get all approved but unsent drafts."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM outreach_drafts WHERE approved = 1 AND sent = 0 ORDER BY created_at DESC')
    drafts = c.fetchall()
    conn.close()
    return drafts

def schedule_follow_up(lead_id, follow_up_type, days_from_now):
    """Schedule a follow-up."""
    conn = get_connection()
    c = conn.cursor()

    scheduled_date = (datetime.now() + timedelta(days=days_from_now)).strftime('%Y-%m-%d')

    c.execute('''INSERT INTO follow_ups (lead_id, follow_up_type, scheduled_date)
                 VALUES (?, ?, ?)''',
              (lead_id, follow_up_type, scheduled_date))

    c.execute('UPDATE leads SET next_follow_up_date = ? WHERE id = ?',
              (scheduled_date, lead_id))

    conn.commit()
    conn.close()

def get_follow_ups_for_lead(lead_id):
    """Get all follow-ups for a lead."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM follow_ups WHERE lead_id = ? ORDER BY scheduled_date ASC', (lead_id,))
    follow_ups = c.fetchall()
    conn.close()
    return follow_ups

def complete_follow_up(follow_up_id):
    """Mark a follow-up as completed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE follow_ups SET completed = 1 WHERE id = ?', (follow_up_id,))
    conn.commit()
    conn.close()

def delete_lead(lead_id):
    """Delete a lead and its associated records."""
    conn = get_connection()
    c = conn.cursor()

    # Capture name for audit before delete
    try:
        c.execute('SELECT business_name, email FROM leads WHERE id = ?', (lead_id,))
        row = c.fetchone()
        biz_name = row['business_name'] if row else f"Lead #{lead_id}"
        email = row['email'] if row else None
    except Exception:
        biz_name = f"Lead #{lead_id}"
        email = None

    c.execute('DELETE FROM outreach_drafts WHERE lead_id = ?', (lead_id,))
    c.execute('DELETE FROM follow_ups WHERE lead_id = ?', (lead_id,))
    c.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
    conn.commit()
    conn.close()

    try:
        import audit_log
        audit_log.log_lead_change(
            lead_id=lead_id,
            action=f"DELETED lead: {biz_name}",
            lead_name=biz_name,
            before={'email': email},
        )
    except Exception:
        pass
