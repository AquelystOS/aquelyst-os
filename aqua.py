"""Aqua — the single brain that orchestrates the inbox watcher,
auto-engagement, and auto-send timer subsystems behind ONE three-state
toggle: OFF / DRAFTING / AUTONOMOUS.

Joseph's 2026-04-30 directive: "aqua and the auto watcher and auto
reply and sales bot is all really confusing and can be streamlined."

This module is the unified API. The underlying email_responder,
auto_engagement, and database modules still hold the actual state; this
just routes the user's intent through them in the right order.

States:
  • OFF — every autonomous worker stopped. Pure manual.
  • DRAFTING — watcher polls + drafts replies; engagement finds + drafts;
    user approves every send.
  • AUTONOMOUS — watcher polls + auto-replies (with countdown); engagement
    finds + auto-sends (with countdown). End-to-end.

Configurable knobs (kept as user-tunable but with sane defaults):
  • watcher_interval_min  — how often to poll IMAP (default 1)
  • engagement_min_score  — hot-lead threshold (default 70)
  • engagement_max_per_run — max new touches per heavy cycle (default 5)
  • engagement_heavy_min  — minutes between heavy hunt cycles (default 15)
  • engagement_followups_enabled — schedule Day 3/7/14/21 (default True)
  • send_delay_min_sec / send_delay_max_sec — randomized natural delay
    before any auto-send fires (default 60 / 180)
"""
import json
from pathlib import Path

CONFIG_FILE = "aqua_config.json"

DEFAULTS = {
    'watcher_interval_min': 1,
    'engagement_min_score': 70,
    'engagement_max_per_run': 5,
    'engagement_heavy_min': 15,
    'engagement_followups_enabled': True,
    'send_delay_min_sec': 60,
    'send_delay_max_sec': 180,
}


def load_config():
    """Return the merged config (file values overlaid on DEFAULTS)."""
    cfg = dict(DEFAULTS)
    try:
        if Path(CONFIG_FILE).exists():
            with open(CONFIG_FILE) as f:
                stored = json.load(f) or {}
            if isinstance(stored, dict):
                cfg.update(stored)
    except Exception:
        pass
    # Coerce numeric fields so the UI's text inputs can't poison downstream
    for k in ('watcher_interval_min', 'engagement_min_score',
              'engagement_max_per_run', 'engagement_heavy_min',
              'send_delay_min_sec', 'send_delay_max_sec'):
        try:
            cfg[k] = int(cfg.get(k, DEFAULTS[k]))
        except Exception:
            cfg[k] = DEFAULTS[k]
    cfg['engagement_followups_enabled'] = bool(
        cfg.get('engagement_followups_enabled', True))
    return cfg


def save_config(updates):
    """Merge `updates` into the persisted config and write to disk."""
    cfg = load_config()
    cfg.update(updates or {})
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


def get_mode():
    """Derive the current Aqua mode from the underlying subsystems.
    Returns one of 'off', 'drafting', 'autonomous'."""
    try:
        import email_responder
        import auto_engagement
    except Exception:
        return 'off'
    watcher_running = email_responder.is_running()
    engagement_running = auto_engagement.is_running()
    if not watcher_running and not engagement_running:
        return 'off'
    # If either subsystem is in send mode, treat the whole thing as
    # autonomous. Mismatches (e.g. watcher in send but engagement in
    # draft) are reconciled at set time — see set_mode below.
    watcher_send = (email_responder.get_state().get('auto_reply_mode')
                    == 'send')
    eng_send = bool(auto_engagement.get_state()
                    .get('config', {}).get('auto_send'))
    if watcher_send or eng_send:
        return 'autonomous'
    return 'drafting'


def set_mode(mode):
    """Apply a top-level mode by orchestrating watcher + engagement.

    This is the single entry point for the OFF/DRAFTING/AUTONOMOUS
    toggle. It loads the user's tuning config and starts/stops/flips
    the underlying workers consistently.

    Returns (success, message) suitable for surfacing in the UI.
    """
    if mode not in ('off', 'drafting', 'autonomous'):
        return False, f"Unknown mode: {mode}"

    import email_responder
    import auto_engagement
    cfg = load_config()

    if mode == 'off':
        try:
            email_responder.stop_responder()
        except Exception:
            pass
        try:
            auto_engagement.stop_engagement()
        except Exception:
            pass
        # Clear all pending scheduled timers — when Aqua is OFF, the
        # drain isn't running, so countdowns are lying about future
        # sends that won't happen. Drafts stay; just the timer goes.
        # Toggling back to AUTONOMOUS triggers backfill which restages
        # them with fresh timers.
        try:
            import database as _db
            n = _db.clear_all_scheduled_sends()
            if n:
                return True, f"Aqua is OFF — {n} timer(s) cleared. Drafts remain pending."
        except Exception:
            pass
        return True, "Aqua is OFF — nothing automated."

    auto_send = (mode == 'autonomous')

    # If engagement requires SMTP and the user has none, refuse
    # autonomous mode (prevents the 'drafted but never sent' trap).
    if auto_send:
        try:
            import smtp_sender
            if not smtp_sender.is_configured():
                return False, ("📭 Autonomous mode needs email connected. "
                               "Set up SMTP in Setup → 📧 Email first.")
        except Exception:
            pass

    # Inbox watcher: start (or flip mode) with the configured interval.
    try:
        if email_responder.is_running():
            email_responder.set_auto_reply_mode('send' if auto_send else 'draft')
        else:
            email_responder.start_responder(
                check_interval_minutes=cfg['watcher_interval_min'],
                auto_reply_mode='send' if auto_send else 'draft',
            )
    except Exception as e:
        return False, f"Watcher failed to start: {str(e)[:120]}"

    # When flipping to AUTONOMOUS, ALWAYS run the FIFO backfill so
    # pending drafts get fresh 1-min/2-min/3-min countdowns starting
    # from now. set_auto_reply_mode triggers backfill internally,
    # but start_responder does not — calling it here unconditionally
    # covers both paths. Joseph's rule (2026-04-30): "the proper
    # order of emails for aqua to send out should be in the order in
    # which recieved that should have a one minute countdown when
    # aqua is on the second would have a two minute countdown and
    # so on."
    if auto_send:
        try:
            email_responder._backfill_schedule_unscheduled_auto_replies()
        except Exception:
            pass

    # Auto-engagement: start (or restart so config applies). Stop+start
    # is the simplest way to push new config into the running loop.
    try:
        if auto_engagement.is_running():
            # Update the config in-place so the next cycle reads new values
            auto_engagement.update_state(config={
                'min_score': cfg['engagement_min_score'],
                'auto_send': auto_send,
                'check_interval_minutes': 1,
                'engagement_interval_minutes': cfg['engagement_heavy_min'],
                'max_per_run': cfg['engagement_max_per_run'],
                'follow_up_enabled': cfg['engagement_followups_enabled'],
            })
        else:
            auto_engagement.start_engagement(
                min_score=cfg['engagement_min_score'],
                auto_send=auto_send,
                check_interval_minutes=1,
                max_per_run=cfg['engagement_max_per_run'],
                follow_up_enabled=cfg['engagement_followups_enabled'],
            )
    except Exception as e:
        return False, f"Engagement failed to start: {str(e)[:120]}"

    label = 'AUTONOMOUS' if auto_send else 'DRAFTING'
    return True, f"Aqua is {label}."


def get_status_summary():
    """Compact dict for the inbox/today status pill."""
    mode = get_mode()
    cfg = load_config()
    try:
        import email_responder
        import auto_engagement
    except Exception:
        return {'mode': mode, 'cfg': cfg, 'watcher_state': {},
                'engagement_state': {}}
    return {
        'mode': mode,
        'cfg': cfg,
        'watcher_state': email_responder.get_state() or {},
        'engagement_state': auto_engagement.get_state() or {},
    }
