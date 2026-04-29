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
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
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
        # Cooldown: skip if anyone touched this lead recently
        last = l.get('last_contacted')
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last).replace('Z', '+00:00'))
                if last_dt.tzinfo is not None:
                    last_dt = last_dt.replace(tzinfo=None)
                if last_dt > cutoff:
                    continue  # touched too recently — let it breathe
            except Exception:
                pass
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
        try:
            if database.has_inbound_messages(l['id']):
                continue
        except Exception:
            pass
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

    # Aqua quality gate — review the draft before it goes out.
    # score 7+ → send, 5-6 → queue for human, <5 → kill (no send).
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
        if review['verdict'] == 'queue':
            database.update_lead(lead['id'], status='drafted')
            database.log_activity(lead['id'], 'auto_engagement_drafted',
                                   f"⚠️ Queued for review (Aqua score "
                                   f"{review['score']}/10): {review['reason']}")
            increment_stat('initial_emails_drafted')
            log_event('queued',
                       f"⚠️ Queued for human review ({review['score']}/10) — {lead['business_name']}: {review['reason']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score']})
            return draft_id
        # else: verdict == 'send' — fall through to actual send

    if auto_send:
        # Approve + send
        database.approve_draft(draft_id)
        success, send_msg = smtp_sender.send_email(
            lead['email'], result['subject'], result['body']
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

    # Aqua quality gate on followups too
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
            database.log_activity(lead['id'], 'auto_followup_drafted',
                                   f"⚠️ Followup #{touch_number} queued (Aqua score {review['score']}/10)")
            increment_stat('followups_drafted')
            log_event('queued',
                       f"⚠️ Followup #{touch_number} queued for review ({review['score']}/10) — {lead['business_name']}",
                       details={'lead_id': lead['id'], 'draft_id': draft_id,
                                'score': review['score']})
            return draft_id

    if auto_send:
        database.approve_draft(draft_id)
        success, _ = smtp_sender.send_email(
            lead['email'], result['subject'], result['body']
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

    # 1. Engage new hot leads
    candidates = find_engagement_candidates(min_score)
    for lead in candidates[:max_per_run]:
        engage_lead_initial(lead, auto_send=auto_send)
        time.sleep(2)  # Be polite to AI provider

    # 2. Send follow-ups
    if fu_enabled:
        followups = find_followup_candidates()
        for lead in followups[:max_per_run]:
            engage_lead_followup(lead, auto_send=auto_send)
            time.sleep(2)

    increment_stat('runs_completed')
    log_event('cycle_done',
               f"✓ Cycle complete: {len(candidates)} initial candidates, "
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

        interval = state.get('config', {}).get('check_interval_minutes', 15)
        for _ in range(interval * 12):
            if not get_state().get('running', False):
                return
            time.sleep(5)


def start_engagement(min_score=70, auto_send=False, check_interval_minutes=15,
                      max_per_run=5, follow_up_enabled=True):
    """Start the auto-engagement bot in background."""
    if get_state().get('running'):
        return False, "Already running"

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
