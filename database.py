import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import os

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
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(DB_PATH)
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
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id),
        FOREIGN KEY (draft_response_id) REFERENCES outreach_drafts(id)
    )''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_inbound_lead ON inbound_messages(lead_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_inbound_received ON inbound_messages(received_at DESC)')

    conn.commit()
    conn.close()


def save_inbound_message(lead_id, from_email, from_name, to_email, subject, body,
                         received_at, message_id_rfc, intent=None, sentiment=None,
                         summary=None, draft_response_id=None):
    """Save an incoming email to the inbound_messages table."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO inbound_messages
                     (lead_id, from_email, from_name, to_email, subject, body,
                      received_at, message_id_rfc, intent, sentiment, summary,
                      draft_response_id)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (lead_id, from_email, from_name, to_email, subject, body,
                   received_at, message_id_rfc, intent, sentiment, summary,
                   draft_response_id))
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return new_id
    except sqlite3.IntegrityError:
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


def get_all_inbound(limit=100):
    """Get all incoming messages, newest first, joined with lead info."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT i.*, l.business_name, l.contact_name, l.lead_score
                 FROM inbound_messages i
                 LEFT JOIN leads l ON i.lead_id = l.id
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


def log_activity(lead_id, activity_type, description):
    """Log an activity for the activity feed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO activities (lead_id, activity_type, description)
                 VALUES (?, ?, ?)''',
              (lead_id, activity_type, description))
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
        c.execute('UPDATE leads SET opt_out = 1, status = "opted_out" WHERE email = ?', (email,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
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
    results = c.fetchall()
    conn.close()
    return results


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
    """Get SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_all_leads(include_team_internal=False):
    """Retrieve all leads. Excludes team-internal by default."""
    conn = get_connection()
    c = conn.cursor()
    if include_team_internal:
        c.execute('SELECT * FROM leads ORDER BY created_at DESC')
    else:
        c.execute('''SELECT * FROM leads
                     WHERE (lead_source IS NULL OR lead_source != "team_internal")
                     AND (status IS NULL OR status != "team_internal")
                     ORDER BY created_at DESC''')
    leads = c.fetchall()
    conn.close()
    return leads


def get_team_internal_leads():
    """Get only team-internal leads (used for tracking team-to-team email)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT * FROM leads
                 WHERE lead_source = "team_internal" OR status = "team_internal"
                 ORDER BY created_at DESC''')
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
        'next_follow_up_date', 'notes', 'opt_out'
    }

    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        conn.close()
        return False

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
    c.execute('''SELECT * FROM leads
                 WHERE lead_score >= 70
                 AND status != "opted_out"
                 AND status != "team_internal"
                 AND (lead_source IS NULL OR lead_source != "team_internal")
                 ORDER BY lead_score DESC''')
    leads = c.fetchall()
    conn.close()
    return leads

def get_follow_ups_due():
    """Get leads with follow-ups due today."""
    conn = get_connection()
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('''SELECT * FROM leads
                 WHERE next_follow_up_date IS NOT NULL
                 AND next_follow_up_date <= ?
                 AND status != "opted_out"
                 AND status != "closed_won"
                 AND status != "closed_lost"
                 ORDER BY next_follow_up_date ASC''', (today,))
    leads = c.fetchall()
    conn.close()
    return leads

def get_dashboard_stats():
    """Get key dashboard statistics."""
    conn = get_connection()
    c = conn.cursor()

    stats = {}

    c.execute('SELECT COUNT(*) FROM leads')
    stats['total_leads'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE status = "new"')
    stats['new_leads'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE lead_score >= 70')
    stats['hot_leads'] = c.fetchone()[0]

    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('''SELECT COUNT(*) FROM leads
                 WHERE next_follow_up_date IS NOT NULL
                 AND next_follow_up_date <= ?
                 AND status NOT IN ("opted_out", "closed_won", "closed_lost")''', (today,))
    stats['follow_ups_due'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE status = "interested"')
    stats['interested'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE status = "trial_offered"')
    stats['trial_offered'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE status = "closed_won"')
    stats['closed_won'] = c.fetchone()[0]

    c.execute('SELECT COUNT(*) FROM leads WHERE status = "closed_lost"')
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

def add_outreach_draft(lead_id, message_type, subject, content):
    """Add an outreach draft."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO outreach_drafts (lead_id, message_type, subject, content)
                 VALUES (?, ?, ?, ?)''',
              (lead_id, message_type, subject, content))
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

def mark_draft_sent(draft_id):
    """Mark a draft as sent."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE outreach_drafts SET sent = 1 WHERE id = ?', (draft_id,))
    conn.commit()
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
