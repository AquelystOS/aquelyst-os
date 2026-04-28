"""IMAP-based inbox poller + auto-responder.

Every 30 minutes (configurable), this:
1. Connects to Joseph's email inbox via IMAP
2. Reads unread messages
3. For each, finds the matching lead in our CRM (by sender email)
4. Classifies the intent via Cerebras (interested/question/objection/etc.)
5. Generates an NEPQ-aligned reply
6. Either auto-sends OR queues as draft for human approval (configurable)
7. Updates the lead status accordingly

Runs as a background thread, controlled from the UI.
"""

import imaplib
import email
import re
import json
import time
import threading
from email.utils import parseaddr, parsedate_to_datetime
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path

import smtp_sender
import database
import nepq_engine


STATE_FILE = "email_responder_state.json"
LOG_FILE = "email_responder_log.json"


# IMAP server presets matching SMTP providers
IMAP_PRESETS = {
    'gmail': {'server': 'imap.gmail.com', 'port': 993},
    'outlook': {'server': 'outlook.office365.com', 'port': 993},
    'yahoo': {'server': 'imap.mail.yahoo.com', 'port': 993},
    'icloud': {'server': 'imap.mail.me.com', 'port': 993},
}


# ============================================================================
# Shared state
# ============================================================================
def get_state():
    if not Path(STATE_FILE).exists():
        return {
            'running': False,
            'started_at': None,
            'last_check': None,
            'next_check': None,
            'auto_reply_mode': 'draft',  # 'draft' or 'send'
            'check_interval_minutes': 30,
            'stats': {
                'checks_completed': 0,
                'emails_processed': 0,
                'replies_drafted': 0,
                'replies_auto_sent': 0,
                'leads_updated': 0,
                'escalations': 0,
                'errors': 0,
            },
        }
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {'running': False, 'stats': {}}


def set_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


def update_state(**kw):
    s = get_state()
    s.update(kw)
    set_state(s)


def increment_stat(key, by=1):
    s = get_state()
    s.setdefault('stats', {})[key] = s['stats'].get(key, 0) + by
    set_state(s)


def log_event(event_type, message, details=None):
    log = read_log()
    entry = {
        'time': datetime.now().isoformat(),
        'type': event_type,
        'message': message,
    }
    if details:
        entry['details'] = details
    log.insert(0, entry)
    log = log[:200]
    try:
        with open(LOG_FILE, 'w') as f:
            json.dump(log, f, indent=2, default=str)
    except Exception:
        pass


def read_log():
    if not Path(LOG_FILE).exists():
        return []
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return []


# ============================================================================
# IMAP fetching
# ============================================================================
def _decode_header(header_value):
    """Decode an email header that may have RFC 2047 encoding."""
    if not header_value:
        return ''
    try:
        decoded_parts = decode_header(header_value)
        result = []
        for text, charset in decoded_parts:
            if isinstance(text, bytes):
                try:
                    text = text.decode(charset or 'utf-8', errors='replace')
                except Exception:
                    text = text.decode('utf-8', errors='replace')
            result.append(text)
        return ''.join(result)
    except Exception:
        return str(header_value)


def _extract_body(msg):
    """Extract plain text body from email.message.Message."""
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition', ''))
            if ctype == 'text/plain' and 'attachment' not in disp:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    break
                except Exception:
                    continue
        if not body:
            # Fallback to HTML, strip tags
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or 'utf-8'
                        html = payload.decode(charset, errors='replace')
                        body = re.sub(r'<[^>]+>', ' ', html)
                        body = re.sub(r'\s+', ' ', body).strip()
                        break
                    except Exception:
                        continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
        except Exception:
            body = str(msg.get_payload())

    return body[:10000]  # Cap at 10KB


def _strip_quoted_reply(body):
    """Remove quoted previous-email content so we focus on what they actually wrote."""
    # Common quote markers
    markers = [
        r'\n\s*On .+ wrote:\s*',
        r'\n\s*From:\s*',
        r'\n\s*-----Original Message-----',
        r'\n\s*>\s*',
        r'\n\s*--\s*\n',  # signature delimiter
    ]
    for marker in markers:
        match = re.search(marker, body)
        if match:
            body = body[:match.start()]
            break
    return body.strip()


PROCESSED_FILE = "processed_message_ids.json"


def _load_processed_ids():
    """Load set of Message-IDs we've already processed."""
    if not Path(PROCESSED_FILE).exists():
        return set()
    try:
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_processed_ids(ids):
    """Persist processed Message-ID set (cap at 5000 entries)."""
    try:
        # Keep newest 5000
        ids_list = list(ids)[-5000:]
        with open(PROCESSED_FILE, 'w') as f:
            json.dump(ids_list, f)
    except Exception:
        pass


def fetch_unread_messages():
    """Connect to IMAP and fetch messages from leads.

    For Gmail, searches [Gmail]/All Mail (catches self-replies which never hit INBOX).
    Falls back to INBOX otherwise.
    Filters out already-processed messages and bot's own outbound emails.

    Returns: list of dicts with {message_id, from_email, from_name, subject, date, body}
    """
    smtp_cfg = smtp_sender.load_smtp_config()
    if not smtp_cfg:
        return [], "Email not configured"

    provider = smtp_cfg['provider']
    if provider not in IMAP_PRESETS:
        return [], f"IMAP not supported for provider: {provider}"

    preset = IMAP_PRESETS[provider]
    bot_email = smtp_cfg['email'].lower().strip()

    # Folder selection per provider
    if provider == 'gmail':
        # Gmail puts self-replies in All Mail, not INBOX. Search All Mail.
        folder = '"[Gmail]/All Mail"'
        # All Mail has both inbox + sent — we'll filter our own outbound below
    else:
        folder = 'INBOX'

    processed_ids = _load_processed_ids()

    try:
        mail = imaplib.IMAP4_SSL(preset['server'], preset['port'])
        mail.login(smtp_cfg['email'], smtp_cfg['app_password'])

        status, _ = mail.select(folder)
        if status != 'OK':
            # Fall back to INBOX
            mail.select('INBOX')

        # Get messages from last 7 days (don't filter by UNSEEN — All Mail messages are often "read")
        since_date = (datetime.now() - timedelta(days=7)).strftime('%d-%b-%Y')
        status, data = mail.search(None, f'(SINCE {since_date})')

        if status != 'OK':
            mail.logout()
            return [], f"IMAP search failed: {status}"

        messages = []
        new_processed = []
        msg_ids = data[0].split()

        for msg_id in msg_ids[-200:]:  # Look at most recent 200
            try:
                # Fetch only headers first to filter quickly
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != 'OK':
                    continue

                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # Extract Message-ID for dedup
                rfc_msg_id = msg.get('Message-ID', '').strip()
                if not rfc_msg_id:
                    rfc_msg_id = f"imap-{msg_id.decode()}"

                # Skip if already processed
                if rfc_msg_id in processed_ids:
                    continue

                from_header = msg.get('From', '')
                from_name, from_email = parseaddr(from_header)
                from_email = from_email.lower().strip()
                from_name = _decode_header(from_name)

                to_header = msg.get('To', '')
                _, to_email = parseaddr(to_header)
                to_email = to_email.lower().strip()

                subject = _decode_header(msg.get('Subject', ''))
                date_header = msg.get('Date', '')
                try:
                    date = parsedate_to_datetime(date_header)
                except Exception:
                    date = datetime.now()

                body = _extract_body(msg)
                body_clean = _strip_quoted_reply(body)

                # === Determine if this is a SELF-REPLY (joseph→joseph for testing) ===
                # If FROM==bot AND TO==bot, this is a self-test reply
                is_self_reply = (from_email == bot_email and to_email == bot_email)

                # === Skip the bot's own outbound emails (FROM bot, TO different) ===
                if from_email == bot_email and not is_self_reply:
                    new_processed.append(rfc_msg_id)
                    continue

                messages.append({
                    'message_id': rfc_msg_id,
                    'imap_id': msg_id.decode(),
                    'from_email': from_email,
                    'to_email': to_email,
                    'from_name': from_name,
                    'subject': subject,
                    'date': date.isoformat(),
                    'body': body_clean,
                    'body_full': body,
                    'is_self_reply': is_self_reply,
                })
            except Exception as e:
                log_event('error', f"Failed to parse message: {str(e)[:80]}")
                continue

        # Save outbound message IDs as processed (so we never reprocess)
        if new_processed:
            processed_ids.update(new_processed)
            _save_processed_ids(processed_ids)

        mail.logout()
        return messages, None

    except imaplib.IMAP4.error as e:
        return [], f"IMAP login failed: {str(e)[:120]}"
    except Exception as e:
        return [], f"IMAP error: {str(e)[:120]}"


# ============================================================================
# Reply processing
# ============================================================================
def find_lead_by_email(from_email):
    """Find a lead in our CRM by their email address.
    Includes team-internal leads so teammate replies are matched.
    """
    if not from_email:
        return None
    # include_team_internal=True so we find teammates too
    leads = database.get_all_leads(include_team_internal=True)
    for lead in leads:
        if lead['email'] and lead['email'].lower() == from_email.lower():
            return lead
    return None


def get_conversation_history(lead_id):
    """Get list of prior emails between us and this lead, ordered chronologically.
    Returns list of {role: 'user'/'assistant', content: str} for AI context."""
    drafts = database.get_drafts_for_lead(lead_id)
    conversation = []
    for d in sorted(drafts, key=lambda x: x['created_at']):
        if d['sent']:
            conversation.append({
                'role': 'assistant',
                'content': f"Subject: {d['subject']}\n\n{d['content']}"
            })
    return conversation


def process_unread_message(msg, auto_send=False):
    """Handle a single unread message: classify, draft reply, optionally send.

    EVERY email is recorded to the activity log (even skipped ones) so the user
    has a complete inbox audit trail.
    """
    from_email = msg['from_email']
    if not from_email:
        return None

    # Mark processed up front so we never re-handle this message
    rfc_msg_id = msg.get('message_id', '')
    if rfc_msg_id:
        processed = _load_processed_ids()
        processed.add(rfc_msg_id)
        _save_processed_ids(processed)

    # Always log that we saw this email (responder log + audit log)
    log_event('seen',
               f"👀 Saw email from {from_email}: {msg.get('subject', '')[:80]}",
               details={'from': from_email, 'subject': msg.get('subject', '')[:120]})

    try:
        import audit_log
        audit_log.log_email_received(
            from_email=from_email,
            subject=msg.get('subject', '')[:200],
        )
    except Exception:
        pass

    # Skip auto-replies, no-reply, system notifications, etc.
    skip_patterns = [
        'noreply@', 'no-reply@', 'donotreply@', 'do-not-reply@',
        'mailer-daemon@', 'postmaster@', 'bounce@', 'bounces@',
        'notifications@', 'notification@',  # both singular and plural
        'notify@', 'alert@', 'alerts@',
        'support@web3forms.com', '@web3forms.com',
        '@accounts.google.com', '@notify.google.com',
        '@service.tiktok.com', '@notification.tiktok.com',
        '@facebookmail.com', '@notify.linkedin.com',
        '@stripe.com', '@payments.',
        'unsubscribe@',
    ]
    for pat in skip_patterns:
        if pat in from_email.lower():
            log_event('skipped', f"Skipped system/auto-sender: {from_email}")
            increment_stat('skipped_autosender')
            return None

    # === Detect team-to-team emails BUT STILL PROCESS THEM ===
    # Team members may be testing the bot or having internal threads — bot should
    # still log these and (optionally) respond. Joseph wants every reply received.
    import team
    sender_member = team.get_member_by_email(from_email)
    if sender_member:
        log_event('classified',
                   f"🤝 Internal email from teammate {sender_member['name']} — processing as test",
                   details={'from': from_email, 'subject': msg.get('subject', '')[:80]})
        increment_stat('team_internal_seen')
        # Continue processing — find or create a lead for the teammate so the
        # email shows in Inbox and gets an Aqua response.

    # === Lead matching ===
    # If self-reply (joseph→joseph for testing), look up lead by TO address (which equals FROM)
    # Otherwise look up by FROM (real prospect replying to us)
    lookup_email = from_email
    if msg.get('is_self_reply'):
        # For self-test replies: lead's email is the same as joseph's email
        lookup_email = msg.get('to_email') or from_email
        log_event('classified', f"🧪 Self-test reply detected: looking up lead by {lookup_email}")

    lead = find_lead_by_email(lookup_email)
    if not lead:
        # Auto-create as 'unsolicited' — they reached out to us cold, not a confirmed prospect.
        # Status stays 'new' until the user manually promotes them based on actual interest.
        from_name = msg.get('from_name', '') or lookup_email.split('@')[0].title()
        try:
            lead_id = database.add_lead(
                business_name=from_name,
                contact_name=from_name,
                email=lookup_email,
                lead_source='unsolicited_inbound',
                pain_hypothesis='',
                notes=f"⚠️ Auto-created from unsolicited inbound email. "
                       f"Subject: {msg.get('subject', '')[:80]}. "
                       f"Review and promote to interested ONLY if they're a real prospect for AqueLyst products.",
            )
            if lead_id:
                database.update_lead(lead_id, lead_score=20, status='new')
                database.log_activity(lead_id, 'auto_created_from_email',
                                       f"Created from inbound email reply")
                lead = database.get_lead(lead_id)
                log_event('classified',
                           f"➕ Auto-created lead for unknown sender: {lookup_email}",
                           details={'lead_id': lead_id})
            else:
                log_event('skipped',
                           f"Couldn't create lead for {lookup_email} (already exists?)")
                return None
        except Exception as e:
            log_event('error',
                       f"Failed to auto-create lead for {lookup_email}: {str(e)[:80]}")
            return None

    # Classify intent
    classification = nepq_engine.classify_inbound_intent(msg['body'])
    intent = classification.get('intent', 'other')
    suggested_status = classification.get('suggested_lead_status', 'researched')
    should_auto_reply = classification.get('should_auto_reply', True)
    escalate = classification.get('escalate_to_human', False)
    escalation_reason = classification.get('escalation_reason', '')
    sentiment = classification.get('sentiment', 'neutral')

    # NEVER escalate teammate replies — they're peer conversations, not prospects
    import team
    if team.get_member_by_email(from_email):
        escalate = False
        # Always draft a peer-mode reply for teammates, even if classifier said don't
        should_auto_reply = True
        suggested_status = 'team_internal'

    log_event('classified',
               f"📨 {lead['business_name']}: {intent} ({sentiment}) — {classification.get('summary', '')}",
               details={'lead_id': lead['id'], 'intent': intent,
                        'escalate': escalate, 'sentiment': sentiment})

    # Update lead status — but ONLY promote to "interested" if they're replying to OUR sent email
    # (not unsolicited cold inbound from random people pitching us).
    sent_count = 0
    try:
        all_drafts = database.get_drafts_for_lead(lead['id'])
        sent_count = sum(1 for d in all_drafts if d['sent'])
    except Exception:
        pass

    promotion_blocked = (
        suggested_status == 'interested'
        and sent_count == 0
        and lead['lead_source'] in ('unsolicited_inbound', 'inbound_email')
    )

    if suggested_status and suggested_status != lead['status'] and not promotion_blocked:
        old_status = lead['status']
        database.update_lead(lead['id'],
                              status=suggested_status,
                              last_contacted=datetime.now().isoformat())
        database.log_activity(lead['id'], 'inbound_reply',
                               f"Status: {old_status} → {suggested_status}. {classification.get('summary', '')}")
        increment_stat('leads_updated')
    elif promotion_blocked:
        # Note in activity that we suppressed the promotion
        database.log_activity(lead['id'], 'inbound_reply_no_promote',
                               f"Inbound reply received but NOT promoted to 'interested' "
                               f"(unsolicited — not a reply to our outreach).")

    # Special handling for unsubscribe
    if intent == 'unsubscribe':
        if lead['email']:
            database.add_to_suppression(lead['email'], 'reply_unsubscribe')
        return None

    # === ESCALATION ===
    # Route the draft to whoever originally contacted this lead — their queue,
    # their voice. Falls back to None (general queue) if no owner recorded.
    owner = (lead.get('last_contacted_by') if isinstance(lead, dict)
             else lead['last_contacted_by'] if 'last_contacted_by' in lead.keys() else None)
    if escalate:
        # Create a flagged "needs human review" entry.
        # The escalation reason is stored as activity/notes — NOT in the email body
        # (so user doesn't accidentally send "AI ESCALATED THIS" to a prospect).
        try:
            conversation = get_conversation_history(lead['id'])
            reply = nepq_engine.generate_reply_to_inbound(
                dict(lead), conversation, msg['body']
            )
            # Body = ONLY the suggested reply (clean, sendable as-is)
            # Subject prefixed with [ESCALATED] so it's visible in lists,
            # but user can edit subject before sending.
            draft_id = database.add_outreach_draft(
                lead['id'],
                f'ESCALATED_{intent}',
                f"[ESCALATED] {reply['subject']}",
                reply['body'],
                created_by=owner,
            )
            # Stash the escalation reason in lead notes for the UI to surface
            current_notes = lead['notes'] or ''
            escalation_note = (f"\n\n⚠️ ESCALATION ({intent}) at "
                               f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: "
                               f"{escalation_reason}")
            database.update_lead(lead['id'], notes=current_notes + escalation_note)
        except Exception:
            draft_id = None

        # Save the inbound regardless of whether the draft worked
        try:
            database.save_inbound_message(
                lead_id=lead['id'],
                from_email=from_email,
                from_name=msg.get('from_name', ''),
                to_email=msg.get('to_email', ''),
                subject=msg.get('subject', ''),
                body=msg.get('body', ''),
                received_at=msg.get('date', datetime.now().isoformat()),
                message_id_rfc=rfc_msg_id,
                intent=intent,
                sentiment=sentiment,
                summary=classification.get('summary', ''),
                draft_response_id=draft_id,
            )
        except Exception:
            pass

        database.log_activity(lead['id'], 'escalated',
                               f"⚠️ ESCALATED ({intent}): {escalation_reason}")
        log_event('escalated',
                   f"⚠️ ESCALATED — {lead['business_name']}: {escalation_reason}",
                   details={'lead_id': lead['id'], 'intent': intent,
                            'sentiment': sentiment, 'reason': escalation_reason})
        increment_stat('escalations')
        return draft_id

    if not should_auto_reply:
        return None

    # Generate NEPQ reply
    conversation = get_conversation_history(lead['id'])
    reply = nepq_engine.generate_reply_to_inbound(
        dict(lead), conversation, msg['body']
    )

    # Save as draft — routed to the owner who originally contacted them.
    draft_id = database.add_outreach_draft(
        lead['id'],
        f'auto_reply_to_{intent}',
        reply['subject'],
        reply['body'],
        created_by=owner,
    )

    # Save the original incoming message body (so user can SEE what they said)
    inbound_id = database.save_inbound_message(
        lead_id=lead['id'],
        from_email=from_email,
        from_name=msg.get('from_name', ''),
        to_email=msg.get('to_email', ''),
        subject=msg.get('subject', ''),
        body=msg.get('body', ''),
        received_at=msg.get('date', datetime.now().isoformat()),
        message_id_rfc=rfc_msg_id,
        intent=intent,
        sentiment=sentiment,
        summary=classification.get('summary', ''),
        draft_response_id=draft_id,
    )
    increment_stat('replies_drafted')
    log_event('drafted',
               f"✍️ Drafted reply to {lead['business_name']}: {reply['subject'][:50]}",
               details={'lead_id': lead['id'], 'draft_id': draft_id, 'source': reply['source']})

    if auto_send:
        # Approve and send immediately
        database.approve_draft(draft_id)
        success, send_msg = smtp_sender.send_email(
            lead['email'], reply['subject'], reply['body']
        )
        if success:
            database.mark_draft_sent(draft_id)
            database.log_activity(lead['id'], 'auto_reply_sent',
                                   f"Auto-replied via NEPQ bot: {reply['subject'][:40]}")
            increment_stat('replies_auto_sent')
            log_event('sent',
                       f"📤 Auto-sent reply to {lead['business_name']}",
                       details={'lead_id': lead['id']})
        else:
            log_event('error',
                       f"Failed to send auto-reply to {lead['business_name']}: {send_msg}")
            increment_stat('errors')

    return draft_id


def run_one_check():
    """Run a single inbox check cycle."""
    update_state(last_check=datetime.now().isoformat())
    log_event('check_start', "🔍 Checking inbox for new replies...")

    messages, error = fetch_unread_messages()

    if error:
        log_event('error', f"Inbox check failed: {error}")
        increment_stat('errors')
        return

    log_event('check_done', f"Found {len(messages)} unread messages")
    increment_stat('checks_completed')

    state = get_state()
    auto_send = state.get('auto_reply_mode') == 'send'

    for msg in messages:
        try:
            increment_stat('emails_processed')
            process_unread_message(msg, auto_send=auto_send)
        except Exception as e:
            log_event('error', f"Failed to process message from {msg.get('from_email', '?')}: {str(e)[:100]}")
            increment_stat('errors')


def responder_loop():
    """Background loop — checks inbox every N minutes."""
    while True:
        state = get_state()
        if not state.get('running', False):
            break

        try:
            run_one_check()
        except Exception as e:
            log_event('error', f"Loop error: {str(e)[:120]}")

        # Sleep until next check
        interval = state.get('check_interval_minutes', 30)
        next_check = datetime.now() + timedelta(minutes=interval)
        update_state(next_check=next_check.isoformat())

        # Sleep in 5-second chunks so stop signal is responsive
        for _ in range(interval * 12):  # interval*60/5
            if not get_state().get('running', False):
                return
            time.sleep(5)


def start_responder(check_interval_minutes=30, auto_reply_mode='draft'):
    """Start the inbox poller in a background thread."""
    state = get_state()
    if state.get('running'):
        return False, "Already running"

    update_state(
        running=True,
        started_at=datetime.now().isoformat(),
        check_interval_minutes=check_interval_minutes,
        auto_reply_mode=auto_reply_mode,
    )

    thread = threading.Thread(target=responder_loop, daemon=True)
    thread.start()

    log_event('system', f"🚀 Email responder started ({auto_reply_mode} mode, every {check_interval_minutes}min)")
    return True, "Started"


def stop_responder():
    update_state(running=False)
    log_event('system', "🛑 Email responder stopped")
    return True


def is_running():
    return get_state().get('running', False)
