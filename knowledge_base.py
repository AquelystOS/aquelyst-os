"""Knowledge Base — documents Aqua learns from.

Stores docs (sales scripts, product manuals, FAQs, customer stories, etc) that
the bot reads when crafting messages. Documents are injected into the AI's
system prompt so every message benefits from the team's accumulated wisdom.

Joseph (and any team member) can paste text, upload files, or scrape URLs.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "aquelyst_hunter.db"


def _ensure_table():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge_base (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT,
        added_by TEXT,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP,
        usage_count INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()


def add_document(title, content, source='manual', added_by=None):
    _ensure_table()
    if added_by is None:
        try:
            import team
            added_by = team.get_current_user().get('email', 'unknown')
        except Exception:
            added_by = 'unknown'

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO knowledge_base (title, content, source, added_by)
                 VALUES (?, ?, ?, ?)''', (title, content, source, added_by))
    conn.commit()
    new_id = c.lastrowid
    conn.close()

    # Audit log
    try:
        import audit_log
        audit_log.log(
            event_type='knowledge_added',
            action=f"Added KB doc: {title}",
            target_type='knowledge_base',
            target_id=new_id,
            target_label=title,
            details={'source': source, 'size_chars': len(content)},
        )
    except Exception:
        pass

    return new_id


def list_documents():
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, title, source, added_by, added_at, usage_count, content FROM knowledge_base ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return [{**dict(r), 'size': len(r['content'] or '')} for r in rows]


def get_document(doc_id):
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM knowledge_base WHERE id = ?', (doc_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_document(doc_id):
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT title FROM knowledge_base WHERE id = ?', (doc_id,))
    title_row = c.fetchone()
    title = title_row[0] if title_row else f"Doc #{doc_id}"

    c.execute('DELETE FROM knowledge_base WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()

    try:
        import audit_log
        audit_log.log(
            event_type='knowledge_removed',
            action=f"Removed KB doc: {title}",
            target_type='knowledge_base',
            target_id=doc_id,
            target_label=title,
        )
    except Exception:
        pass


def increment_usage(doc_id):
    """Track that a doc was used (so we can see what's actually helping)."""
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE knowledge_base SET usage_count = usage_count + 1 WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()


def format_for_bot_prompt(max_total_chars=8000):
    """Render the knowledge base as system-prompt context for the bot.

    Cap total length so we don't blow up context window. Prioritize most-used docs.
    """
    docs = list_documents()
    if not docs:
        return ""

    # Sort by usage_count desc (most-useful first), then by recency
    docs.sort(key=lambda d: (-d.get('usage_count', 0), d.get('id', 0)), reverse=False)

    lines = ["## TEAM KNOWLEDGE BASE (use these when crafting messages)"]
    used = 0
    included = 0
    for d in docs:
        block = f"\n### {d['title']}\n{d['content']}\n"
        if used + len(block) > max_total_chars:
            break
        lines.append(block)
        used += len(block)
        included += 1

    if included < len(docs):
        lines.append(f"\n_(Showing {included} of {len(docs)} docs — older/less-used omitted to save context)_")

    return "\n".join(lines)


def search(query, limit=5):
    """Simple LIKE-based search through knowledge."""
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    pat = f'%{query}%'
    c.execute('''SELECT * FROM knowledge_base
                 WHERE title LIKE ? OR content LIKE ?
                 ORDER BY usage_count DESC, id DESC LIMIT ?''',
              (pat, pat, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]
