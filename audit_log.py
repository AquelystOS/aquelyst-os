"""Audit log — comprehensive, tamper-resistant record of every transaction.

For legal + records-keeping compliance:
- Every action captured to the second
- Stored in UTC + user's local timezone (auto-detected from system)
- Attributed to the logged-in team member (from SMTP config)
- Append-only by design — entries are never edited or deleted via the app
- Hash-chained: each entry includes a hash of (previous hash + this entry) for tamper-evidence
- Exportable to CSV for legal review

Hook into this module from anywhere in the codebase:
    from audit_log import log
    log('email_sent', f'Sent to {to_email}', target_id=lead_id, details={...})
"""

import json
import sqlite3
import hashlib
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "aquelyst_hunter.db"


def _ensure_table():
    """Create audit_log table if missing."""
    import db_backend; conn = db_backend.get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp_utc TEXT NOT NULL,
        timestamp_local TEXT NOT NULL,
        timezone_name TEXT,
        timezone_offset TEXT,
        event_type TEXT NOT NULL,
        action TEXT NOT NULL,
        actor_email TEXT,
        actor_name TEXT,
        actor_role TEXT,
        target_type TEXT,
        target_id INTEGER,
        target_label TEXT,
        details TEXT,
        host_name TEXT,
        prev_hash TEXT,
        entry_hash TEXT
    )''')
    # Index for fast searching by date + actor
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp_utc DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_email)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target_type, target_id)')
    conn.commit()
    conn.close()


def _get_current_actor():
    """Get current logged-in team member (from SMTP config + team registry)."""
    try:
        import team
        member = team.get_current_user()
        return {
            'email': member.get('email', ''),
            'name': member.get('name', 'Unknown'),
            'role': member.get('role', ''),
        }
    except Exception:
        return {'email': '', 'name': 'System', 'role': ''}


def _get_local_tz_info():
    """Detect local timezone where this OS install is running."""
    now_local = datetime.now().astimezone()
    tz_name = time.tzname[time.daylight] if time.daylight else time.tzname[0]
    tz_offset = now_local.strftime('%z')  # e.g. -0400
    if tz_offset:
        # Format as +HH:MM
        tz_offset = f"{tz_offset[:3]}:{tz_offset[3:]}"
    return tz_name, tz_offset


def _get_last_hash():
    """Get hash of most recent audit entry (for hash-chain)."""
    try:
        import db_backend; conn = db_backend.get_connection()
        c = conn.cursor()
        c.execute('SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        return row[0] if row else 'GENESIS'
    except Exception:
        return 'GENESIS'


def _compute_hash(prev_hash, payload):
    """SHA-256 hash of (prev_hash + canonical payload)."""
    data = (prev_hash or '') + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:32]


def log(event_type, action, target_type=None, target_id=None, target_label=None, details=None):
    """Record an audit entry.

    Args:
        event_type: high-level category, e.g. 'email_sent', 'lead_created', 'status_change',
                    'autopilot_run', 'settings_changed', 'login', 'bot_classified'
        action: human-readable one-line description
        target_type: 'lead' | 'draft' | 'product' | 'team_member' | 'config' | None
        target_id: int (e.g. lead_id) or None
        target_label: human-readable label for the target (e.g. business name)
        details: any dict — will be JSON-serialized

    Returns the new audit entry's ID.
    """
    try:
        _ensure_table()
    except Exception:
        pass  # If DB lock or transient issue, don't break the calling action

    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now().astimezone()
    tz_name, tz_offset = _get_local_tz_info()
    actor = _get_current_actor()

    try:
        host = socket.gethostname()
    except Exception:
        host = 'unknown'

    payload = {
        'timestamp_utc': now_utc.isoformat(),
        'event_type': event_type,
        'action': action,
        'actor_email': actor['email'],
        'target_type': target_type,
        'target_id': target_id,
        'details': details or {},
    }

    prev_hash = _get_last_hash()
    entry_hash = _compute_hash(prev_hash, payload)

    try:
        import db_backend; conn = db_backend.get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO audit_log
                     (timestamp_utc, timestamp_local, timezone_name, timezone_offset,
                      event_type, action, actor_email, actor_name, actor_role,
                      target_type, target_id, target_label,
                      details, host_name, prev_hash, entry_hash)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (now_utc.isoformat(),
                   now_local.isoformat(),
                   tz_name,
                   tz_offset,
                   event_type,
                   action,
                   actor['email'],
                   actor['name'],
                   actor['role'],
                   target_type,
                   target_id,
                   target_label,
                   json.dumps(details or {}, default=str),
                   host,
                   prev_hash,
                   entry_hash))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except Exception:
        # Never let audit logging break the calling code
        return None


def query(limit=200, event_type=None, actor_email=None, target_type=None, target_id=None,
          search=None, start_date=None, end_date=None):
    """Query the audit log with filters.

    Returns list of sqlite3.Row dicts, newest first.
    """
    try:
        _ensure_table()
        import db_backend; conn = db_backend.get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        where = []
        params = []
        if event_type:
            where.append('event_type = ?')
            params.append(event_type)
        if actor_email:
            where.append('actor_email = ?')
            params.append(actor_email)
        if target_type:
            where.append('target_type = ?')
            params.append(target_type)
        if target_id:
            where.append('target_id = ?')
            params.append(target_id)
        if search:
            where.append('(action LIKE ? OR details LIKE ? OR target_label LIKE ?)')
            search_pat = f'%{search}%'
            params.extend([search_pat, search_pat, search_pat])
        if start_date:
            where.append('timestamp_utc >= ?')
            params.append(start_date)
        if end_date:
            where.append('timestamp_utc <= ?')
            params.append(end_date)

        sql = 'SELECT * FROM audit_log'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)

        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def count(event_type=None, since_iso=None):
    """Count entries matching filters."""
    try:
        _ensure_table()
        import db_backend; conn = db_backend.get_connection()
        c = conn.cursor()

        where = []
        params = []
        if event_type:
            where.append('event_type = ?')
            params.append(event_type)
        if since_iso:
            where.append('timestamp_utc >= ?')
            params.append(since_iso)

        sql = 'SELECT COUNT(*) FROM audit_log'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)

        c.execute(sql, params)
        result = c.fetchone()[0]
        conn.close()
        return result
    except Exception:
        return 0


def verify_chain():
    """Walk the entire audit chain and verify hash integrity.
    Returns (is_valid, broken_at_id_or_None)."""
    try:
        import db_backend; conn = db_backend.get_connection()
        c = conn.cursor()
        c.execute('''SELECT id, timestamp_utc, event_type, action, actor_email,
                            target_type, target_id, details, prev_hash, entry_hash
                     FROM audit_log ORDER BY id ASC''')
        rows = c.fetchall()
        conn.close()

        prev_hash = 'GENESIS'
        for row in rows:
            (rid, ts, etype, action, actor, ttype, tid, details, stored_prev, stored_hash) = row

            # Verify the stored prev_hash matches our chain
            if stored_prev != prev_hash:
                return False, rid

            # Recompute the expected hash from this entry's content
            try:
                details_dict = json.loads(details) if details else {}
            except Exception:
                details_dict = {}

            payload = {
                'timestamp_utc': ts,
                'event_type': etype,
                'action': action,
                'actor_email': actor,
                'target_type': ttype,
                'target_id': tid,
                'details': details_dict,
            }
            expected = _compute_hash(prev_hash, payload)
            if expected != stored_hash:
                return False, rid

            prev_hash = stored_hash

        return True, None
    except Exception as e:
        return False, str(e)


def export_csv(filepath, **filters):
    """Export filtered audit log to CSV for legal review."""
    import csv
    rows = query(limit=100000, **filters)
    if not rows:
        return False, "No entries to export"

    try:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ID', 'Timestamp (UTC)', 'Timestamp (Local)', 'Timezone',
                'Event', 'Action', 'Actor', 'Actor Email', 'Role',
                'Target Type', 'Target ID', 'Target', 'Details',
                'Host', 'Hash'
            ])
            for r in rows:
                writer.writerow([
                    r['id'],
                    r['timestamp_utc'],
                    r['timestamp_local'],
                    f"{r['timezone_name']} ({r['timezone_offset']})",
                    r['event_type'],
                    r['action'],
                    r['actor_name'],
                    r['actor_email'],
                    r['actor_role'],
                    r['target_type'],
                    r['target_id'],
                    r['target_label'] or '',
                    r['details'],
                    r['host_name'],
                    r['entry_hash'],
                ])
        return True, f"Exported {len(rows)} entries"
    except Exception as e:
        return False, f"Export failed: {str(e)[:120]}"


# ============================================================================
# Convenience helpers — call these from common actions
# ============================================================================
def log_email_sent(to_email, subject, lead_id=None, lead_name=None, message_type='manual'):
    """Hook: call after every email send."""
    return log(
        event_type='email_sent',
        action=f"Sent email to {to_email}: {subject[:80]}",
        target_type='lead',
        target_id=lead_id,
        target_label=lead_name,
        details={'to': to_email, 'subject': subject, 'message_type': message_type}
    )


def log_email_received(from_email, subject, lead_id=None, lead_name=None, classification=None):
    """Hook: call when inbox watcher processes an inbound email."""
    return log(
        event_type='email_received',
        action=f"Received from {from_email}: {subject[:80]}",
        target_type='lead',
        target_id=lead_id,
        target_label=lead_name,
        details={'from': from_email, 'subject': subject, 'classification': classification}
    )


def log_lead_change(lead_id, action, lead_name=None, before=None, after=None):
    """Hook: call on lead create/update/delete/status_change."""
    return log(
        event_type='lead_change',
        action=action,
        target_type='lead',
        target_id=lead_id,
        target_label=lead_name,
        details={'before': before, 'after': after}
    )


def log_login_event(actor_email):
    """Hook: call when user authenticates / changes email."""
    return log(
        event_type='auth',
        action=f"Email connected: {actor_email}",
        target_type='config',
        details={'email': actor_email}
    )


def log_settings_change(setting_name, before, after):
    """Hook: call when settings/config is modified."""
    return log(
        event_type='settings_change',
        action=f"Changed {setting_name}",
        target_type='config',
        details={'setting': setting_name, 'before': str(before)[:200], 'after': str(after)[:200]}
    )


def log_bot_action(action_desc, lead_id=None, lead_name=None, ai_provider=None):
    """Hook: any autonomous bot action (autopilot, auto-engagement, auto-reply)."""
    return log(
        event_type='bot_action',
        action=action_desc,
        target_type='lead',
        target_id=lead_id,
        target_label=lead_name,
        details={'ai_provider': ai_provider}
    )


def log_system_event(action_desc, details=None):
    """Hook: system events (autopilot started/stopped, watcher started, etc)."""
    return log(
        event_type='system',
        action=action_desc,
        details=details or {}
    )
