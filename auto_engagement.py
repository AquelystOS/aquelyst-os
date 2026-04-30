"""Auto-Engagement Engine — autonomously sends initial NEPQ outreach
to hot leads, then follows up on schedule.

Workflow:
1. Background loop scans CRM every N minutes
2. Finds leads that:
   - Have score >= threshold
   - Have an email
   - Are not on suppression list
   - Are in 'new', 'researched', or 'drafted' status (not contacted yet)
   - Have not been suppressed
3. For each, generates NEPQ-style initial outreach
4. Sends (if SMTP configured) OR queues as draft
5. Updates status to 'contacted', schedules Day 3, 7, 14, 21 follow-ups
6. Follow-up loop also fires when scheduled date arrives (and no reply)
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

import database
import smtp_sender
import nepq_engine


STATE_FILE = "auto_engagement_state.json"
LOG_FILE = "auto_engagement_log.json"


def get_state():
    if not Path(STATE_FILE).exists():
        return {
            'running': False,
            'started_at': None,
            'last_run': None,
            'config': {
                'min_score': 70,
                'auto_send': False,
                'check_interval_minutes': 15,
                'max_per_run': 5,  # be polite — don't blast 50 in one go
                'follow_up_enabled': True,
            },
            'stats': {
                'runs_completed': 0,
                'initial_emails_drafted': 0,
                'initial_emails_sent': 0,
                'followups_drafted': 0,
                'followups_sent': 0,
                'errors': 0,
            },
        }
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {'running': False, 'stats': {}}


def set_state(s):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(s, f, indent=2, default=str)
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
    entry = {'time': datetime.now().isoformat(), 'type': event_type, 'message': message}
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
# Engagement logic
# ============================================================================
def find_engagement_candidates(min_score, cooldown_minutes=10):
    """Find leads ready for initial outreach.

    Skips leads any user has touched within `cooldown_minutes` so two
    teammates' Aquas can't blindly double-contact the same prospect.
    Default 10 min — enough buffer that human-sent + auto-engagement
    don't pile on the same inbox."""
    from datetime import datetime, timedelta, timezone
    # Use timezone-aware UTC throughout — comparing aware-vs-naive datetimes
    # raises TypeError, which the prior code swallowed with a bare `pass`,
    # silently bypassing the cooldown. Every datetime here is now aware.
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    leads = database.get_all_leads()
    candidates = []
    for l in leads:
        if (l['lead_score'] or 0) < min_score:
            continue
        if not l['email']:
            continue
        if l['opt_out']:
            continue
        if l['status'] not in ('new', 'researched', 'drafted'):
            continue
        if database.is_suppressed(l['email']):
            continue
        # Already have a pending autopilot draft (sent=False) for this lead?
        # If yes, skip — otherwise the engager creates a duplicate draft on
        # every cycle while we're outside business hours, piling up clones
        # in the queue. drain_pending_auto_drafts will ship the existing
        # one when the window opens.
        try:
            existing = database.get_drafts_for_lead(l['id'])
            has_pending_auto = any(
                (not d.get('sent'))
                and (d.get('message_type') or '').startswith(
                    ('nepq_initial', 'nepq_followup_', 'aqua_intro'))
                for d in existing
            )
            if has_pending_auto:
                continue
        except Exception:
            pass
        # Cooldown: skip if anyone touched this lead recently
        last = l.get('last_contacted')
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last).replace('Z', '+00:00'))
                if last_dt.tzinfo is None:
                    # Treat naive timestamps as UTC (the DB writes UTC ISO).
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                if last_dt > cutoff:
                    continue  # touched too recently — let it breathe
            except Exception as e:
                # Don't swallow silently — log so a parsing bug doesn't
                # invisibly bypass the cooldown. Conservative: skip the
                # lead so we don't risk double-touching.
                log_event('warn',
                           f"cooldown parse failed for {l.get('email')}: "
                           f"{str(e)[:80]} — skipping conservatively")
                continue
        candidates.append(l)
    candidates.sort(key=lambda x: -(x['lead_score'] or 0))
    return candidates


def find_followup_candidates():
    """Find leads with follow-ups due that haven't replied.

    Smart cadence: skip leads that show ANY signal of engagement so we
    don't pile cold touches on top of a warm conversation.
      • opt_out / suppression list                  → skip
      • status not in (contacted, follow_up_due,
        drafted)                                    → skip (closed/won/lost)
      • has any inbound_message linked to them      → skip (they replied)
      • has an unreviewed draft from < 24hr ago     → skip (don't pile up)
    """
    from datetime import datetime as _dt, timedelta as _td
    leads = database.get_follow_ups_due()
    candidates = []
    for l in leads:
        if not l['email']:
            continue
        if l['opt_out']:
            continue
        if database.is_suppressed(l['email']):
            continue
        if l['status'] not in ('contacted', 'follow_up_due', 'drafted'):
            continue
        # Did the prospect ever reply? If yes, never auto-send a cold
        # follow-up on top — that's a critical respect-the-thread rule.
        # If the check itself fails, SKIP the lead conservatively rather
        # than continuing — better to miss a follow-up than to step on
        # someone's reply.
        try:
            if database.has_inbound_messages(l['id']):
                continue
        except Exception as e:
            log_event('warn',
                       f"has_inbound_messages failed for lead {l['id']}: "
                       f"{str(e)[:80]} — skipping conservatively")
            continue
        # Already have an unreviewed draft from the last 24 hr? Don't
        # pile a 2nd one on the human review queue.
        try:
            recent_drafts = database.get_drafts_for_lead(l['id'])
            cutoff_iso = (_dt.utcnow() - _td(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
            if any((not d.get('sent')) and (d.get('created_at') or '') >= cutoff_iso
                   for d in recent_drafts):
                continue
        except Exception:
            pass
        candidates.append(l)
    return candidates


def _within_business_hours():
    """Returns (allowed: bool, reason: str). Auto-sends are blocked
    8pm-7am ET and on weekends to:
      • protect domain reputation (bot-pattern overnight sends get
        spam-flagged by major mail systems)
      • respect prospect attention (cold emails sent at 3am EST
        almost never get read; opens cluster Tue-Thu 8-11am)
    The draft is still SAVED — just not auto-sent. Human can send
    manually anytime. Override via st.secrets['DISABLE_SEND_GUARD'] = true.
    """
    try:
        import streamlit as _st
        if hasattr(_st, 'secrets') and _st.secrets.get('DISABLE_SEND_GUARD'):
            return True, ''
    except Exception:
        pass
    try:
        import ui_kit
        now = ui_kit.now_et()
    except Exception:
        from datetime import datetime as _dt
        now = _dt.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun
    hour = now.hour
    if weekday >= 5:  # Saturday/Sunday
        return False, f"weekend ({['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][weekday]} {hour:02d}:00 ET)"
    if hour < 7 or hour >= 20:
        return False, f"outside business hours ({hour:02d}:00 ET — sends queue 7am-8pm ET Mon-Fri)"
    return True, ''


def engage_lead_initial(lead, auto_send=False):
    """Send the FIRST NEPQ-style email to a lead."""
    log_event('engaging', f"💌 Engaging {lead['business_name']} (score {lead['lead_score']})")

    try:
        result = nepq_engine.generate_initial_outreach(dict(lead))
    except Exception as e:
        log_event('error', f"Failed to generate for {lead['business_name']}: {str(e)[:80]}")
        increment_stat('errors')
        return None

    # Save draft
    draft_id = database.add_outreach_draft(
        lead['id'], 'nepq_initial',
        result['subject'], result['body']
    )

    # Send-time guardrail — even if auto_send=True, only fire during
    # business hours. Outside that window, downgrade to "drafted" so the
    # team can review + send Monday morning.
    allowed, reason = _within_business_hours()
    if auto_send and not allowed:
        database.update_lead(lead['id'], status='drafted')
        database.log_activity(lead['id'], 'auto_engagement_drafted',
                               f"NEPQ initial drafted (auto-send blocked: {reason})")
        increment_stat('initial_emails_drafted')
        log_event('queued',
                   f"⏸ Queued (not auto-sent: {reason}) — {lead['business_name']}",
                   details={'lead_id': lead['id'], 'draft_id': draft_id,
                            'reason': reason})
        return draft_id

    # Aqua quality gate — when the user has explicitly opted into auto-send,
    # only TRUE SPAM-TIER drafts are blocked. Borderline drafts (5-6) still
    # ship — Joseph chose auto-send, so trust him. Only the hallucination /
    # placeholder / wrong-name cases (score < 5) get blocked outright. Score
    # is still logged for visibility.
    if auto_send:
        try:
            review = nepq_engine.quality_review_draft(
                result['subject'], result['body'], dict(lead))
        except Exception:
            review = {'score': 7, 'verdict': 'send', 'issues': [],
                      'reason': 'review error, defaulting to send'}
        if review['verdict'] == 'kill':
            database.update_lead(lead['id'], status='drafted',
                                  notes=(lead.get('notes') or '') +
                                  f"\n\n🛑 Aqua blocked auto-send (score "
                                  f"{review['score']}/10): {review['reason']}")
            database.log_activity(lead['id'], 'auto_engagement_blocked',
                                   f"🛑 Aqua blocked: {review['reason']}")
            increment_stat('initial_emails_drafted')
            log_event('blocked',
                       f"🛑 Quality-gated ({review['score']}/10) — {lead['business_name']}: {review['reason']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score'],
                                'issues': review['issues']})
            return draft_id
        # 'queue' or 'send' both fall through and ship. Tag activity log
        # with the score so borderline-quality sends are still visible.
        if review['verdict'] == 'queue':
            log_event('borderline',
                       f"⚠️ Borderline ({review['score']}/10) but sending — {lead['business_name']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score']})

    if auto_send:
        # Approve + send (draft_id passed for click-tracking link rewriting)
        database.approve_draft(draft_id)
        success, send_msg = smtp_sender.send_email(
            lead['email'], result['subject'], result['body'],
            draft_id=draft_id,
        )
        if success:
            database.mark_draft_sent(draft_id)
            database.update_lead(lead['id'],
                                  status='contacted',
                                  last_contacted=datetime.now().isoformat())
            # Schedule Day 3 follow-up
            database.schedule_follow_up(lead['id'], 'nepq_day_3', 3)
            database.log_activity(lead['id'], 'auto_engagement_sent',
                                   f"Auto-sent NEPQ initial: {result['subject'][:40]}")
            increment_stat('initial_emails_sent')
            log_event('sent',
                       f"📤 Sent initial NEPQ to {lead['business_name']} ({result['source']})",
                       details={'lead_id': lead['id']})
            return draft_id
        else:
            log_event('error', f"Send failed for {lead['business_name']}: {send_msg}")
            increment_stat('errors')
            return None
    else:
        # Just drafted — needs human approval
        database.update_lead(lead['id'], status='drafted')
        database.log_activity(lead['id'], 'auto_engagement_drafted',
                               f"NEPQ initial drafted, awaits approval")
        increment_stat('initial_emails_drafted')
        log_event('drafted',
                   f"✍️ Drafted NEPQ initial for {lead['business_name']} ({result['source']})",
                   details={'lead_id': lead['id'], 'draft_id': draft_id})
        return draft_id


def engage_lead_followup(lead, auto_send=False):
    """Generate and (optionally) send a follow-up email.

    Smart cadence: defensive double-check on top of find_followup_candidates'
    filters. If the prospect replied between the candidate-find call and
    this call, abort cleanly — race conditions matter when multiple users
    + auto_engagement run in parallel."""
    # Defensive: did they reply between candidate selection and now?
    try:
        if database.has_inbound_messages(lead['id']):
            log_event('skipped',
                       f"Reply detected mid-cycle, skipping followup — {lead['business_name']}")
            return None
    except Exception:
        pass

    # Determine touch number based on prior drafts
    drafts = database.get_drafts_for_lead(lead['id'])
    sent_count = sum(1 for d in drafts if d['sent'])
    touch_number = sent_count + 1  # next email is touch N+1

    if touch_number > 6:
        # Too many touches — stop. Mark the lead so we don't keep
        # picking it back up every cycle.
        log_event('skipped', f"Max touches reached for {lead['business_name']}")
        try:
            database.update_lead(lead['id'], status='closed_lost',
                                  notes=(lead.get('notes') or '') +
                                  f"\n\n📭 Auto-closed after 6 silent touches "
                                  f"(no reply). Move back to 'contacted' if you "
                                  f"want to resume outreach.")
        except Exception:
            pass
        return None

    # Build conversation history for context
    conversation = []
    for d in sorted(drafts, key=lambda x: x['created_at']):
        if d['sent']:
            conversation.append({'role': 'assistant',
                                  'content': f"Subject: {d['subject']}\n\n{d['content']}"})

    try:
        result = nepq_engine.generate_followup(
            dict(lead), conversation, touch_number
        )
    except Exception as e:
        log_event('error', f"Followup gen failed for {lead['business_name']}: {str(e)[:80]}")
        increment_stat('errors')
        return None

    draft_id = database.add_outreach_draft(
        lead['id'], f'nepq_followup_{touch_number}',
        result['subject'], result['body']
    )

    # Same business-hours guardrail as the initial-engagement path
    allowed, reason = _within_business_hours()
    if auto_send and not allowed:
        database.log_activity(lead['id'], 'auto_followup_drafted',
                               f"Followup #{touch_number} drafted (auto-send blocked: {reason})")
        increment_stat('followups_drafted')
        log_event('queued',
                   f"⏸ Followup #{touch_number} queued (not auto-sent: {reason}) — {lead['business_name']}",
                   details={'lead_id': lead['id'], 'draft_id': draft_id,
                            'reason': reason})
        return draft_id

    # Aqua quality gate on followups — same lenient policy as initial:
    # only KILL verdicts (score <5, true spam-tier) block the send. Joseph
    # opted into auto-send → trust the opt-in for borderline (5-6) drafts.
    if auto_send:
        try:
            review = nepq_engine.quality_review_draft(
                result['subject'], result['body'], dict(lead))
        except Exception:
            review = {'score': 7, 'verdict': 'send', 'issues': [],
                      'reason': 'review error, defaulting to send'}
        if review['verdict'] == 'kill':
            database.log_activity(lead['id'], 'auto_followup_blocked',
                                   f"🛑 Aqua blocked followup #{touch_number}: {review['reason']}")
            increment_stat('followups_drafted')
            log_event('blocked',
                       f"🛑 Followup #{touch_number} quality-gated ({review['score']}/10) — {lead['business_name']}: {review['reason']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score']})
            return draft_id
        if review['verdict'] == 'queue':
            log_event('borderline',
                       f"⚠️ Followup #{touch_number} borderline ({review['score']}/10) but sending — {lead['business_name']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score']})

    if auto_send:
        database.approve_draft(draft_id)
        success, _ = smtp_sender.send_email(
            lead['email'], result['subject'], result['body'],
            draft_id=draft_id,
        )
        if success:
            database.mark_draft_sent(draft_id)
            database.update_lead(lead['id'],
                                  last_contacted=datetime.now().isoformat())

            # Schedule next follow-up using NEPQ cadence
            next_days = {2: 4, 3: 7, 4: 7, 5: 14, 6: 14}
            days = next_days.get(touch_number, 14)
            database.schedule_follow_up(lead['id'], f'nepq_day_{touch_number+1}', days)
            database.log_activity(lead['id'], 'auto_followup_sent',
                                   f"NEPQ followup #{touch_number} sent")
            increment_stat('followups_sent')
            log_event('sent', f"📤 Sent followup #{touch_number} to {lead['business_name']}",
                       details={'lead_id': lead['id']})
            return draft_id
    else:
        database.log_activity(lead['id'], 'auto_followup_drafted',
                               f"NEPQ followup #{touch_number} drafted")
        increment_stat('followups_drafted')
        log_event('drafted', f"✍️ Drafted followup #{touch_number} for {lead['business_name']}",
                   details={'lead_id': lead['id'], 'draft_id': draft_id})
        return draft_id


def catch_up_unanswered_threads(max_per_run=5, auto_send=False):
    """Scan our own inbox for prospects who replied but never got an
    answer back, and draft (or send) a fresh NEPQ reply that responds
    to the inbound with full thread context.

    Two failure modes this fixes:
      • Inbox watcher was down / restarted while replies came in →
        those replies have no draft attached. Catch up.
      • Reply was drafted but the human approver never sent it →
        upgrade to auto-send (only when auto_send=True) so the
        conversation doesn't go cold for days.

    Skips: leads on suppression, opted-out leads, junk-marked inbounds,
    inbounds we already drafted a reply to within the last 24hr (so
    we don't pile multiple replies on one thread).

    Returns count of new replies (drafted_or_sent_count, skipped_count).
    """
    drafted = 0
    skipped = 0
    try:
        unanswered = database.get_unanswered_inbound(limit=max_per_run * 3)
    except Exception as e:
        log_event('error', f"catch-up: get_unanswered_inbound failed: {str(e)[:80]}")
        return 0, 0

    for w in unanswered[:max_per_run]:
        lead_id = w.get('lead_id')
        if not lead_id:
            skipped += 1
            continue

        lead = database.get_lead(lead_id)
        if not lead or not lead.get('email'):
            skipped += 1
            continue
        if lead.get('opt_out') or database.is_suppressed(lead['email']):
            skipped += 1
            continue

        # Check we don't already have a recent unsent draft for this thread
        try:
            existing = database.get_drafts_for_lead(lead_id)
            from datetime import datetime as _dt, timedelta as _td
            cutoff = (_dt.utcnow() - _td(hours=24)).isoformat()
            already_drafted = any(
                (d.get('message_type') or '').startswith(('auto_reply_to_',
                                                            'ESCALATED_'))
                and (d.get('created_at') or '') >= cutoff
                for d in existing
            )
        except Exception:
            already_drafted = False
        if already_drafted:
            skipped += 1
            continue

        # Pull the inbound body so the reply has real context
        try:
            from_email = lead['email']
            inbound_body = ''
            conn = database.get_connection()
            c = conn.cursor()
            try:
                c.execute('SELECT body, message_id_rfc FROM inbound_messages '
                          'WHERE id = ?', (w.get('inbound_id'),))
                row = c.fetchone()
                if row:
                    inbound_body = (row['body'] if isinstance(row, dict)
                                    else row[0]) or ''
                    irt_msg_id = (row['message_id_rfc'] if isinstance(row, dict)
                                  else row[1])
                else:
                    irt_msg_id = None
            finally:
                conn.close()
        except Exception:
            inbound_body = ''
            irt_msg_id = None

        # Generate a context-aware reply
        try:
            conversation = []
            try:
                # Pull prior thread for memory
                conversation = [{
                    'role': 'assistant' if t.get('direction') == 'out' else 'user',
                    'content': (t.get('subject') or '') + '\n\n' + (t.get('body') or '')
                } for t in database.get_conversation_thread(lead_id)[-6:]]
            except Exception:
                conversation = []

            reply = nepq_engine.generate_reply_to_inbound(
                dict(lead), conversation, inbound_body or w.get('inbound_subject') or '')
        except Exception as e:
            log_event('error',
                       f"catch-up: generate_reply failed for {lead.get('business_name')}: {str(e)[:80]}")
            skipped += 1
            continue

        # Save as draft, threaded to the original inbound
        intent = w.get('inbound_intent') or 'question'
        draft_id = database.add_outreach_draft(
            lead_id, f'auto_reply_to_{intent}',
            reply['subject'], reply['body'])

        if auto_send:
            database.approve_draft(draft_id)
            try:
                ok, send_msg = smtp_sender.send_email(
                    lead['email'], reply['subject'], reply['body'],
                    draft_id=draft_id, in_reply_to=irt_msg_id)
            except Exception as e:
                log_event('error',
                           f"catch-up: send failed for {lead.get('business_name')}: {str(e)[:80]}")
                continue
            if ok:
                database.mark_draft_sent(draft_id)
                database.update_lead(lead_id, status='contacted',
                                      last_contacted=datetime.now().isoformat())
                database.log_activity(lead_id, 'catch_up_sent',
                                       f"📤 Caught up on stale thread: {reply['subject'][:50]}")
                log_event('catch_up',
                           f"📤 Caught up on stale thread → {lead.get('business_name')} "
                           f"(waited {w.get('days_waiting', 0):.1f}d)",
                           details={'lead_id': lead_id, 'draft_id': draft_id})
                drafted += 1
            else:
                log_event('error',
                           f"catch-up SMTP failed for {lead.get('business_name')}: "
                           f"{(send_msg or '')[:80]}")
        else:
            log_event('catch_up',
                       f"✍️ Catch-up draft for {lead.get('business_name')} "
                       f"(waited {w.get('days_waiting', 0):.1f}d)",
                       details={'lead_id': lead_id, 'draft_id': draft_id})
            drafted += 1

    if drafted or skipped:
        log_event('cycle_catchup',
                   f"🔍 Catch-up: {drafted} replies, {skipped} skipped")
    return drafted, skipped


def drain_pending_auto_drafts(max_per_run=20):
    """Send any unsent autopilot/auto-engagement drafts that are sitting
    in the queue. Skips human-created drafts (compose, manual_send) — those
    are queued intentionally for human review.

    Quality-gate is still applied at KILL threshold (placeholders /
    hallucinations get blocked even on retry) but borderline drafts are
    sent because the human opted into auto-send.

    Returns count sent + count blocked."""
    sent_count = 0
    blocked_count = 0
    try:
        pending = database.get_pending_drafts(limit=200)
    except Exception:
        return 0, 0

    AUTO_PREFIXES = ('nepq_initial', 'nepq_followup_', 'auto_reply_to_',
                      'aqua_intro', 'ESCALATED_')
    from datetime import datetime as _dt
    now_utc = _dt.utcnow()

    for d in pending[:max_per_run]:
        msg_type = d.get('message_type') or ''
        if not msg_type.startswith(AUTO_PREFIXES):
            continue  # Leave human compose/manual drafts alone

        # Scheduled-send timer: if scheduled_send_at is set and in the
        # FUTURE, skip this cycle — the drain on a later cycle will pick
        # it up when the timer hits zero. If scheduled_send_at <= now
        # (or is None for legacy drafts), proceed.
        sched = d.get('scheduled_send_at')
        if sched:
            try:
                sched_dt = _dt.fromisoformat(str(sched).replace('Z', '+00:00'))
                if sched_dt.tzinfo is not None:
                    sched_dt = sched_dt.replace(tzinfo=None)
                if sched_dt > now_utc:
                    continue  # not time yet — countdown still running
            except Exception:
                pass
        lead_id = d.get('lead_id')
        if not lead_id:
            continue
        lead = database.get_lead(lead_id)
        if not lead or not lead.get('email'):
            continue
        if lead.get('opt_out') or database.is_suppressed(lead['email']):
            continue
        # Don't pile a send on an already-replied thread
        try:
            if database.has_inbound_messages(lead_id):
                continue
        except Exception:
            pass

        # Business-hours guardrail still applies
        allowed, reason = _within_business_hours()
        if not allowed:
            log_event('queued',
                       f"⏸ Holding pending draft for {lead['business_name']} ({reason})")
            continue

        # Quality gate at KILL threshold only
        try:
            review = nepq_engine.quality_review_draft(
                d.get('subject') or '', d.get('content') or '', dict(lead))
        except Exception:
            review = {'score': 7, 'verdict': 'send'}
        if review.get('verdict') == 'kill':
            blocked_count += 1
            log_event('blocked',
                       f"🛑 Pending draft blocked ({review.get('score', 0)}/10) — {lead['business_name']}",
                       details={'lead_id': lead_id, 'draft_id': d['id']})
            continue

        # Send. If this is a reply to an inbound message, look up the
        # original Message-ID so the email is properly threaded.
        irt = None
        try:
            if msg_type.startswith('auto_reply_to_') or msg_type.startswith('ESCALATED_'):
                irt = database.get_latest_inbound_message_id(lead_id)
        except Exception:
            irt = None
        try:
            success, send_msg = smtp_sender.send_email(
                lead['email'], d.get('subject') or '',
                d.get('content') or '', draft_id=d['id'],
                in_reply_to=irt)
        except Exception as e:
            log_event('error', f"Drain send failed for {lead['business_name']}: {str(e)[:80]}")
            continue
        if success:
            database.approve_draft(d['id'])
            database.mark_draft_sent(d['id'])
            database.update_lead(lead_id, status='contacted',
                                  last_contacted=datetime.now().isoformat())
            database.log_activity(lead_id, 'auto_drain_sent',
                                   f"📤 Pending {msg_type} sent: {(d.get('subject') or '')[:50]}")
            sent_count += 1
            log_event('sent',
                       f"📤 Drained pending draft → {lead['business_name']}",
                       details={'lead_id': lead_id, 'draft_id': d['id']})
        else:
            log_event('error',
                       f"Drain SMTP failed for {lead['business_name']}: {(send_msg or '')[:80]}")
        time.sleep(1)
    return sent_count, blocked_count


def run_one_cycle():
    """Process one engagement cycle."""
    state = get_state()
    config = state.get('config', {})
    min_score = config.get('min_score', 70)
    auto_send = config.get('auto_send', False)
    max_per_run = config.get('max_per_run', 5)
    fu_enabled = config.get('follow_up_enabled', True)

    update_state(last_run=datetime.now().isoformat())
    log_event('cycle_start',
               f"🔄 Engagement cycle: min_score={min_score}, mode={'send' if auto_send else 'draft'}")

    # The engagement loop ticks every 1 min (so scheduled-send timers
    # fire on time), but we DON'T want to run heavy AI generation 60x
    # per hour. Two-tier cadence:
    #   • Cheap work (drain + scheduled dispatch + catch-up) — every tick
    #   • Heavy work (find new candidates, draft + send) — only when
    #     ENGAGEMENT_INTERVAL_MIN has elapsed since the last heavy cycle
    from datetime import datetime as _dt, timedelta as _td
    ENGAGEMENT_INTERVAL_MIN = config.get('engagement_interval_minutes', 15)
    last_heavy_iso = state.get('last_heavy_cycle')
    last_heavy = None
    if last_heavy_iso:
        try:
            last_heavy = _dt.fromisoformat(str(last_heavy_iso).replace('Z', '+00:00'))
            if last_heavy.tzinfo is not None:
                last_heavy = last_heavy.replace(tzinfo=None)
        except Exception:
            last_heavy = None
    do_heavy = (last_heavy is None
                or (_dt.utcnow() - last_heavy) >= _td(minutes=ENGAGEMENT_INTERVAL_MIN))

    # === CHEAP work — every tick ===
    # 0. Drain pending autopilot drafts (incl. scheduled-send timers
    #    that just hit zero — this is what makes the countdown timer
    #    feel responsive on a 1-min loop).
    if auto_send:
        sent_n, blocked_n = drain_pending_auto_drafts(max_per_run=max_per_run * 4)
        if sent_n or blocked_n:
            log_event('cycle_drain',
                       f"📤 Drained pending: sent {sent_n}, blocked {blocked_n}")

    # === HEAVY work — only every ENGAGEMENT_INTERVAL_MIN ===
    if not do_heavy:
        return

    update_state(last_heavy_cycle=_dt.utcnow().isoformat())

    # 1. Catch-up: scan inbox for prospects waiting on a reply that
    #    fell through. Joseph asked for this 2026-04-30.
    try:
        catch_up_unanswered_threads(max_per_run=max(2, max_per_run // 2),
                                     auto_send=auto_send)
    except Exception as e:
        log_event('error', f"Catch-up scan failed: {str(e)[:100]}")

    # 2. Engage new hot leads
    candidates = find_engagement_candidates(min_score)
    for lead in candidates[:max_per_run]:
        engage_lead_initial(lead, auto_send=auto_send)
        time.sleep(2)  # Be polite to AI provider

    # 3. Send follow-ups
    if fu_enabled:
        followups = find_followup_candidates()
        for lead in followups[:max_per_run]:
            engage_lead_followup(lead, auto_send=auto_send)
            time.sleep(2)

    increment_stat('runs_completed')
    log_event('cycle_done',
               f"✓ Heavy cycle complete: {len(candidates)} initial candidates, "
               f"{len(followups) if fu_enabled else 0} followups")


def engagement_loop():
    """Background loop."""
    while True:
        state = get_state()
        if not state.get('running', False):
            break

        try:
            run_one_cycle()
        except Exception as e:
            log_event('error', f"Loop error: {str(e)[:120]}")

        # The loop ticks frequently so the scheduled-send timer feels
        # responsive (timers are 60-180s; if we slept 15 min between
        # checks, a 60s timer could appear to wait 15+ min). Default
        # 1 min = drain runs every minute, scheduled drafts fire within
        # 60s of their target. Heavy work (find_engagement_candidates,
        # generate_initial_outreach) is gated by a per-cycle counter
        # internally so we don't 60x the API budget.
        interval = state.get('config', {}).get('check_interval_minutes', 1)
        for _ in range(max(1, interval) * 12):
            if not get_state().get('running', False):
                return
            time.sleep(5)


def start_engagement(min_score=70, auto_send=False, check_interval_minutes=1,
                      max_per_run=5, follow_up_enabled=True):
    """Start the auto-engagement bot in background.

    Default check_interval is 1 min so the scheduled-send countdown
    timers fire on time. Heavy AI work (find candidates, draft) is
    gated to once per ENGAGEMENT_INTERVAL_MIN (default 15 min) inside
    the loop — see run_one_cycle.
    """
    if get_state().get('running'):
        # Already running — but still apply the link to inbox watcher
        # if auto_send is on, so flipping the toggle doesn't silently
        # leave the watcher in draft mode (Joseph's 2026-04-30 trap).
        if auto_send:
            try:
                import email_responder
                if email_responder.is_running():
                    email_responder.set_auto_reply_mode('send')
                else:
                    try:
                        email_responder.start_responder(
                            check_interval_minutes=1,
                            auto_reply_mode='send',
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        return False, "Already running"

    # Pre-flight: if auto_send is on, bail early when no SMTP is connected.
    # Otherwise the loop will generate drafts but every send will fail and
    # the stat counters won't budge — which is exactly the "192 drafted,
    # 0 sent" mystery. Block at start so the user fixes setup first.
    if auto_send:
        try:
            import smtp_sender
            if not smtp_sender.is_configured():
                return False, ("📭 Auto-send needs email connected. Go to "
                               "Setup → 📧 Email and link your account first, "
                               "then come back. (Or start in Draft-only mode "
                               "and review before sending.)")
        except Exception:
            pass  # don't let an import error block startup

    update_state(
        running=True,
        started_at=datetime.now().isoformat(),
        config={
            'min_score': min_score,
            'auto_send': auto_send,
            'check_interval_minutes': check_interval_minutes,
            'max_per_run': max_per_run,
            'follow_up_enabled': follow_up_enabled,
        },
    )

    thread = threading.Thread(target=engagement_loop, daemon=True)
    thread.start()

    # Link to inbox watcher: in true autopilot mode (auto-send ON), inbound
    # replies should also auto-reply, not just queue drafts. Otherwise the
    # user toggles "Aqua autopilot" thinking it's end-to-end and finds her
    # politely drafting responses to every reply for them to manually
    # approve. Joseph's 2026-04-30 testing flagged this confusion.
    if auto_send:
        try:
            import email_responder
            if email_responder.is_running():
                email_responder.set_auto_reply_mode('send')
            else:
                # Auto-start the watcher in send mode if it wasn't running.
                # Skip silently on failure (e.g. no IMAP cred) — auto-engagement
                # itself can still run.
                try:
                    email_responder.start_responder(
                        check_interval_minutes=1,
                        auto_reply_mode='send',
                    )
                except Exception:
                    pass
        except Exception:
            pass

    log_event('system', f"🚀 Auto-engagement started "
              f"({'auto-send' if auto_send else 'draft-only'} mode, "
              f"min_score={min_score})")
    return True, "Started"


def stop_engagement():
    update_state(running=False)
    log_event('system', "🛑 Auto-engagement stopped")
    return True


def is_running():
    return get_state().get('running', False)
