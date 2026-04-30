"""Autopilot — autonomous lead generation engine.

Runs in background. Continuously:
1. Discovers horse businesses via web search
2. AI-researches each one (Cerebras)
3. Finds/guesses emails
4. Scores and qualifies
5. Adds high-quality leads to CRM
6. Auto-drafts personalized outreach for each

Live progress streamed to UI via shared state file.
"""

import json
import time
import threading
from pathlib import Path
from datetime import datetime

import lead_discovery
import ai_research
import email_finder
import database
import lead_scoring
import outreach


STATE_FILE = "autopilot_state.json"
LOG_FILE = "autopilot_log.json"


# ============================================================================
# Shared state — Streamlit reads this; worker writes to it
# ============================================================================
def get_state():
    """Read current autopilot state."""
    if not Path(STATE_FILE).exists():
        return {
            "running": False,
            "started_at": None,
            "stopped_at": None,
            "config": {},
            "stats": {
                "discovered": 0,
                "researched": 0,
                "qualified": 0,
                "added_to_crm": 0,
                "skipped": 0,
                "errors": 0,
            },
            "sources_used": {},
            "current_action": "idle",
            "current_target": None,
            "recent_leads": [],
        }
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"running": False, "stats": {}}


def set_state(state):
    """Persist state for UI to read."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


def update_state(**updates):
    """Partial state update."""
    state = get_state()
    state.update(updates)
    set_state(state)


def increment_stat(key, by=1):
    """Increment a counter in state."""
    state = get_state()
    state['stats'][key] = state['stats'].get(key, 0) + by
    set_state(state)


def track_source(source_name):
    """Increment count for a discovery source."""
    state = get_state()
    state.setdefault('sources_used', {})
    state['sources_used'][source_name] = state['sources_used'].get(source_name, 0) + 1
    set_state(state)


def add_recent_lead(lead_summary):
    """Add a lead to the recent-leads showcase (last 12)."""
    state = get_state()
    state.setdefault('recent_leads', [])
    state['recent_leads'].insert(0, lead_summary)
    state['recent_leads'] = state['recent_leads'][:12]
    set_state(state)


# ============================================================================
# Activity log — shows live what's happening
# ============================================================================
def aggregate_recent_activity(hours_back=24):
    """Number-crunch the autopilot log + DB for the last N hours.
    Used by Aqua's daily brief on the Today page."""
    from datetime import datetime as _dt, timedelta as _td
    cutoff_dt = _dt.utcnow() - _td(hours=hours_back)
    cutoff = cutoff_dt.isoformat()

    log = read_log()
    recent = [e for e in log if (e.get('time') or '') >= cutoff]
    counts = {'added': 0, 'drafted': 0, 'sent': 0, 'queued': 0,
              'blocked': 0, 'skipped': 0, 'error': 0, 'discovery': 0,
              'research': 0}
    for e in recent:
        t = e.get('type', '')
        if t in counts:
            counts[t] += 1

    state = get_state()
    return {
        'hours': hours_back,
        'is_running': state.get('running', False),
        'counts': counts,
        'total_log_events': len(recent),
        'sources_used': state.get('sources_used', {}),
    }


def log_event(event_type, message, lead_data=None):
    """Append to activity log (capped at 200 events)."""
    log = read_log()
    entry = {
        "time": datetime.now().isoformat(),
        "type": event_type,  # discovery, research, added, skipped, error
        "message": message,
    }
    if lead_data:
        entry['lead'] = {
            "business_name": lead_data.get('business_name'),
            "score": lead_data.get('lead_score') or lead_data.get('_ai_match_score'),
            "city": lead_data.get('city'),
            "state": lead_data.get('state'),
        }
    log.insert(0, entry)
    log = log[:200]
    try:
        with open(LOG_FILE, 'w') as f:
            json.dump(log, f, indent=2, default=str)
    except Exception:
        pass


def read_log():
    """Read activity log."""
    if not Path(LOG_FILE).exists():
        return []
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def clear_log():
    """Wipe the log."""
    try:
        if Path(LOG_FILE).exists():
            Path(LOG_FILE).unlink()
    except Exception:
        pass


# ============================================================================
# The actual autopilot worker
# ============================================================================
def dedupe_existing_leads(dry_run=False):
    """One-shot cleanup: collapse duplicate leads created before the
    name-based dedup fix. Two leads are 'the same' if they share a
    normalized name + (when both have one) city/state.

    Keeps the OLDEST record (lowest id) and merges info from duplicates
    into it (e.g. if any duplicate has an email and the keeper doesn't,
    copy the email over). Then deletes the duplicates via
    database.delete_lead so child rows (drafts, activities, inbound)
    are detached cleanly.

    Returns (kept_count, deleted_count, merged_email_count).
    """
    leads = database.get_all_leads()
    by_key = {}
    for l in leads:
        name = l['business_name'] or ''
        if not name:
            continue
        norm = _normalize_business_name(name)
        if not norm:
            continue
        # City/state included only when BOTH the candidate and prior
        # have them — same logic as is_already_in_crm to avoid
        # collapsing different-city same-name businesses.
        key = (norm, (l['city'] or '').lower(), (l['state'] or '').lower())
        by_key.setdefault(key, []).append(l)

    kept_count = 0
    deleted_count = 0
    merged_emails = 0
    for key, group in by_key.items():
        if len(group) < 2:
            kept_count += 1
            continue
        # Sort: oldest id first → that's the keeper
        group.sort(key=lambda l: l['id'])
        keeper = group[0]
        kept_count += 1

        # Best-effort merge: pull email/phone/website from any dup if
        # keeper is missing them
        updates = {}
        for dup in group[1:]:
            if not keeper['email'] and dup['email']:
                updates['email'] = dup['email']
                merged_emails += 1
            if not keeper['phone'] and dup['phone']:
                updates['phone'] = dup['phone']
            if not keeper['website'] and dup['website']:
                updates['website'] = dup['website']
        if updates and not dry_run:
            try:
                database.update_lead(keeper['id'], **updates)
            except Exception:
                pass

        # Now delete the dupes
        for dup in group[1:]:
            if not dry_run:
                try:
                    database.delete_lead(dup['id'])
                except Exception:
                    continue
            deleted_count += 1

    return kept_count, deleted_count, merged_emails


def is_already_in_crm(website_url, business_name=None, city=None, state=None):
    """Check if we've already added this business to the CRM.

    Joseph's 2026-04-30 testing: Canterbury Park (a Minnesota racetrack)
    kept getting re-added every cycle because the dedup was domain-only,
    and OSM-discovered leads frequently have NO website. The
    domain-based check returned False instantly for them, letting
    duplicates back in.

    Now layered: (1) match by website domain when one exists; (2)
    fallback match by normalized business name (case-insensitive,
    punctuation-stripped) optionally tightened by city/state for
    common-name collisions.
    """
    leads = database.get_all_leads()

    # Layer 1: domain match (kept — strongest signal when both sides
    # have a real website)
    if website_url:
        domain = email_finder.get_domain_from_website(website_url)
        if domain and domain not in ('openstreetmap.org',
                                     'osm.org', 'maps.google.com',
                                     'google.com'):
            for l in leads:
                if not l['website']:
                    continue
                lead_domain = email_finder.get_domain_from_website(l['website'])
                if lead_domain and lead_domain == domain:
                    return True

    # Layer 2: normalized name match (works when website is None or
    # is a synthetic OSM URL like https://www.openstreetmap.org/node/123).
    if business_name:
        norm_target = _normalize_business_name(business_name)
        if norm_target:
            for l in leads:
                if not l['business_name']:
                    continue
                if _normalize_business_name(l['business_name']) != norm_target:
                    continue
                # Same normalized name. We use city+state to disambiguate
                # legitimately-different businesses that happen to share
                # a name (Smith Farm in TX vs Smith Farm in VT).
                # Audit caught a null-handling bug in the previous code:
                # if EITHER side had a null city, the check skipped and
                # we'd merge unrelated leads. Now we treat "candidate
                # has city, stored has none" (or vice versa) as a
                # MISMATCH, not a free pass — safer to keep two records
                # than to silently merge two different businesses.
                cand_city = (city or '').strip().lower()
                cand_state = (state or '').strip().lower()
                stored_city = (l['city'] or '').strip().lower()
                stored_state = (l['state'] or '').strip().lower()
                # If we have any location data on either side, require
                # a positive match to call it a duplicate.
                if cand_city or stored_city:
                    if cand_city != stored_city:
                        continue
                if cand_state or stored_state:
                    if cand_state != stored_state:
                        continue
                return True

    return False


def _normalize_business_name(name):
    """Strip punctuation, lowercase, collapse whitespace, drop common
    business suffixes (LLC, Inc, etc.) so 'Canterbury Park' and
    'Canterbury Park, LLC' compare equal."""
    if not name:
        return ''
    import re as _re
    s = name.lower().strip()
    # Drop common legal/business suffixes
    suffixes = (' llc', ' inc', ' inc.', ' ltd', ' ltd.', ' corp',
                ' corp.', ' co', ' co.', ' company', ' farm', ' farms',
                ' stables', ' stable', ' ranch', ' park', ' center',
                ' centre', ' the')
    # Iterate a couple times in case multiple suffixes stack
    for _ in range(3):
        for suf in suffixes:
            if s.endswith(suf):
                s = s[:-len(suf)].strip()
                break
        else:
            break
    # Strip punctuation, collapse whitespace
    s = _re.sub(r"[^\w\s]", "", s)
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def process_candidate(candidate, config):
    """Process a single discovered candidate end-to-end."""
    website = candidate['url']

    # Skip if already in CRM. Pass the candidate's name + city/state
    # so the no-website OSM dedup path can match by normalized name —
    # without this, Canterbury Park (no website in OSM) was being
    # re-added every cycle.
    if is_already_in_crm(
        website,
        business_name=candidate.get('title') or candidate.get('name'),
        city=candidate.get('city'),
        state=candidate.get('state'),
    ):
        log_event("skipped", f"Already in CRM: {candidate['title']}")
        increment_stat('skipped')
        return None

    # Update current action
    update_state(
        current_action="researching",
        current_target=candidate['title']
    )
    log_event("research", f"🔍 Researching: {candidate['title']}")

    # FAST PATH: OSM pre-populated metadata
    # If the candidate came from OSM with no website but has phone/email,
    # we can skip the AI website-research entirely
    osm_website = candidate.get('_osm_website', '')
    osm_data = candidate.get('_osm_data', False)

    if osm_data and not osm_website:
        # OSM has metadata but no website — create minimal lead from OSM tags.
        # The business_type / pain / product_fit come from the actual hunt
        # category the user selected (no longer hardcoded to "horse facility"
        # — that was a bug that mis-tagged every OSM lead as equine).
        biz_type_from_hunt = (candidate.get('source_query') or '').strip() or 'business'
        product_fit = lead_discovery._guess_product_from_type(biz_type_from_hunt) or None
        pain_by_product = {
            'Duo Equine':         f'{biz_type_from_hunt} — likely manages stalls, manure, fly control',
            'Pets':               f'{biz_type_from_hunt} — likely manages pet odors, kennel cough, urine',
            'SpillMaster':        f'{biz_type_from_hunt} — likely manages spills, biohazards, sanitation',
            'AMR':                f'{biz_type_from_hunt} — likely manages fleet odor, mold, smoke',
            'HouseHold':          f'{biz_type_from_hunt} — likely manages residential odor, mold, pet smells',
            'Inversion Misting':  f'{biz_type_from_hunt} — likely manages large-facility ammonia, fly burden',
        }
        lead_data = {
            'business_name': candidate.get('title', 'Unknown'),
            'contact_name': None,
            'email': candidate.get('_osm_email') or None,
            'phone': candidate.get('_osm_phone') or None,
            'website': None,
            'city': candidate.get('_osm_city') or None,
            'state': candidate.get('_osm_state') or None,
            'business_type': f"{biz_type_from_hunt} (from OSM)",
            'lead_source': 'autopilot_osm',
            'source_channel': candidate.get('source_query', 'openstreetmap'),
            'pain_hypothesis': pain_by_product.get(product_fit, f"{biz_type_from_hunt} — manual research recommended"),
            'product_fit': product_fit,
            'notes': f"📍 Discovered via OpenStreetMap. May need manual research for personalized outreach.",
        }

        clean_lead = {k: v for k, v in lead_data.items() if not k.startswith('_')}
        lead_id = database.add_lead(**clean_lead)
        if lead_id:
            score = lead_scoring.calculate_lead_score(clean_lead)
            database.update_lead(lead_id, lead_score=score, status='researched')
            database.log_activity(lead_id, "autopilot_osm",
                                   f"OSM-discovered (score: {score})")
            track_source(candidate.get('source', 'OpenStreetMap'))
            increment_stat('qualified')
            increment_stat('added_to_crm')
            add_recent_lead({
                'id': lead_id,
                'business_name': clean_lead['business_name'],
                'contact_name': None,
                'city': clean_lead.get('city'),
                'state': clean_lead.get('state'),
                'score': score,
                'hook': f"OSM-listed {biz_type_from_hunt} in {clean_lead.get('city') or 'unknown'}",
                'source': 'OpenStreetMap',
                'discovered_at': datetime.now().isoformat(),
            })
            log_event("added", f"✅ OSM-added {clean_lead['business_name']} (no AI call needed)",
                       lead_data={**clean_lead, 'lead_score': score})
            return lead_id
        else:
            log_event("skipped", f"Duplicate OSM business: {candidate['title']}")
            increment_stat('skipped')
            return None

    # Deep research with AI
    result = ai_research.deep_research_lead(candidate)
    increment_stat('researched')

    if not result['success']:
        log_event("error", f"❌ Research failed for {candidate['title']}: {result.get('error', '')[:80]}")
        increment_stat('errors')
        return None

    # Convert to lead format
    lead_data = ai_research.intelligence_to_lead_data(result, candidate)
    if not lead_data:
        log_event("skipped", f"No usable data extracted from {candidate['title']}")
        increment_stat('skipped')
        return None

    # AI says skip?
    if not lead_data.get('_should_pursue', True) or not lead_data.get('_is_real_business', True):
        reason = lead_data.get('_skip_reason', 'AI determined low fit')
        log_event("skipped", f"⏭ Skipped {lead_data['business_name']}: {reason}")
        increment_stat('skipped')
        return None

    # Score check
    ai_score = lead_data.get('_ai_match_score', 0)
    min_score = config.get('min_score', 50)
    if ai_score < min_score:
        log_event("skipped",
                  f"⏭ Skipped {lead_data['business_name']}: score {ai_score} < threshold {min_score}")
        increment_stat('skipped')
        return None

    # Try to find email if missing
    if not lead_data.get('email'):
        update_state(current_action="finding_email", current_target=lead_data['business_name'])
        scraped_emails = result.get('contact_info', {}).get('emails', [])
        guessed_email = email_finder.find_best_email(
            lead_data.get('contact_name'),
            lead_data.get('website'),
            scraped_emails=scraped_emails
        )
        if guessed_email:
            lead_data['email'] = guessed_email
            lead_data['notes'] = (lead_data.get('notes', '') +
                                  f"\n\n⚠️ Email is a best-guess pattern, not verified.")

    # Pre-pop database
    update_state(current_action="saving", current_target=lead_data['business_name'])

    # Strip internal underscore fields before insert
    clean_lead = {k: v for k, v in lead_data.items() if not k.startswith('_')}

    lead_id = database.add_lead(**clean_lead)
    if not lead_id:
        log_event("skipped", f"⏭ Duplicate email: {lead_data.get('email')} for {lead_data['business_name']}")
        increment_stat('skipped')
        return None

    # Use AI-determined score (override the basic scorer)
    final_score = max(ai_score, lead_scoring.calculate_lead_score(clean_lead))
    database.update_lead(lead_id,
                         lead_score=final_score,
                         status='researched')
    database.log_activity(lead_id, "autopilot_added",
                          f"AI-discovered & researched (score: {final_score})")

    # Auto-draft outreach if AI is available
    if config.get('auto_draft_outreach', True):
        try:
            update_state(current_action="drafting", current_target=lead_data['business_name'])

            # Use the personalized hook the AI generated
            hook = lead_data.get('_personalized_hook', '')

            full_lead = database.get_lead(lead_id)
            draft_result = outreach.generate_smart('cold_email', dict(full_lead), provider='auto')

            # Inject the hook into the message if it's not already there
            content = draft_result.get('content', '')
            if hook and hook.lower() not in content.lower():
                content = f"{hook}\n\n{content}"

            database.add_outreach_draft(
                lead_id, 'cold_email',
                draft_result.get('subject', 'Quick question about your barn'),
                content
            )
            database.log_activity(lead_id, "autopilot_drafted",
                                  f"Outreach pre-drafted by {draft_result.get('source')}")
        except Exception as e:
            log_event("error", f"Couldn't draft for {lead_data['business_name']}: {str(e)[:80]}")

    increment_stat('qualified')
    increment_stat('added_to_crm')

    log_event("added",
              f"✅ Added {lead_data['business_name']} (score {final_score})",
              lead_data={**clean_lead, 'lead_score': final_score})

    # Track source for live stats
    track_source(candidate.get('source', 'web_search'))

    # Add to recent leads showcase
    add_recent_lead({
        'id': lead_id,
        'business_name': clean_lead['business_name'],
        'contact_name': clean_lead.get('contact_name'),
        'city': clean_lead.get('city'),
        'state': clean_lead.get('state'),
        'score': final_score,
        'hook': lead_data.get('_personalized_hook', '')[:140],
        'source': candidate.get('source', 'web'),
        'discovered_at': datetime.now().isoformat(),
    })

    return lead_id


def run_autopilot(config):
    """
    Main autopilot loop. Runs in a thread.

    config: {
        'state': '2-letter state code or None',
        'city': 'city name or None',
        'business_types': [list of types to search],
        'target_leads': int (stop after this many added),
        'min_score': int (skip leads below this AI score),
        'auto_draft_outreach': bool,
    }
    """
    update_state(
        running=True,
        started_at=datetime.now().isoformat(),
        stopped_at=None,
        config=config,
        stats={
            "discovered": 0,
            "researched": 0,
            "qualified": 0,
            "added_to_crm": 0,
            "skipped": 0,
            "errors": 0,
        },
        sources_used={},
        recent_leads=[],
        current_action="starting",
        current_target=None
    )

    log_event("system", f"🚀 Autopilot started — targeting {config.get('target_leads', 25)} qualified leads")

    target_total = config.get('target_leads', 25)
    business_types = config.get('business_types') or [t['type'] for t in lead_discovery.get_discovery_targets()]
    location_str = ""
    if config.get('city'):
        location_str = config['city']
    if config.get('state'):
        location_str = f"{location_str} {config['state']}".strip()

    seen_urls = set()

    # Per-category cooldown — once a category has been searched in the
    # current run, skip it for HOURS so equine categories that all hit
    # the same OSM dataset don't churn the same Canterbury Park-style
    # leads on every cycle. Persisted to state so it survives restarts.
    from datetime import datetime as _dt, timedelta as _td
    _CATEGORY_COOLDOWN_HOURS = 6
    cooldowns = get_state().get('category_cooldowns', {}) or {}
    now_iso = _dt.utcnow().isoformat()

    def _on_cooldown(cat):
        last = cooldowns.get(cat)
        if not last:
            return False
        try:
            last_dt = _dt.fromisoformat(str(last).replace('Z', '+00:00'))
            if last_dt.tzinfo is not None:
                last_dt = last_dt.replace(tzinfo=None)
        except Exception:
            return False
        return (_dt.utcnow() - last_dt) < _td(hours=_CATEGORY_COOLDOWN_HOURS)

    try:
        for biz_type in business_types:
            # Check if user stopped us
            if not get_state().get('running'):
                log_event("system", "🛑 Autopilot stopped by user")
                break

            # Check if we hit target
            current_added = get_state()['stats'].get('added_to_crm', 0)
            if current_added >= target_total:
                log_event("system", f"🎯 Target reached: {current_added} leads added!")
                break

            # Per-category cooldown
            if _on_cooldown(biz_type):
                log_event("discovery",
                          f"⏭ Skipping {biz_type} — searched recently "
                          f"(cooldown {_CATEGORY_COOLDOWN_HOURS}h)")
                continue

            update_state(current_action="discovering", current_target=biz_type)
            log_event("discovery", f"🔎 Searching the web for: {biz_type}" +
                      (f" in {location_str}" if location_str else ""))

            def discovery_progress(source, detail):
                log_event("discovery", f"   📡 {source}: {detail}")
                update_state(current_action=f"scraping {source}", current_target=biz_type)

            try:
                candidates = lead_discovery.discover_horse_businesses(
                    biz_type, location_str, max_results=15,
                    on_progress=discovery_progress
                )
            except Exception as e:
                log_event("error", f"Search failed for {biz_type}: {str(e)[:80]}")
                continue

            log_event("discovery", f"   ✓ {len(candidates)} unique candidates from {len(set(c.get('source', '') for c in candidates))} sources")

            # Mark this category as recently-searched so we don't repeat
            # it on the next cycle (until the cooldown expires).
            cooldowns[biz_type] = now_iso
            update_state(category_cooldowns=cooldowns)

            new_candidates = [c for c in candidates if c['url'] not in seen_urls]
            for c in new_candidates:
                seen_urls.add(c['url'])

            increment_stat('discovered', by=len(new_candidates))

            # Process each candidate
            for candidate in new_candidates:
                if not get_state().get('running'):
                    break

                current_added = get_state()['stats'].get('added_to_crm', 0)
                if current_added >= target_total:
                    break

                try:
                    process_candidate(candidate, config)
                except Exception as e:
                    log_event("error", f"Failed to process {candidate.get('title', 'unknown')}: {str(e)[:100]}")
                    increment_stat('errors')

                # Polite delay between AI calls (free tier rate limits)
                time.sleep(1.5)

    except Exception as e:
        log_event("error", f"Autopilot crashed: {str(e)[:200]}")
    finally:
        update_state(
            running=False,
            stopped_at=datetime.now().isoformat(),
            current_action="stopped",
            current_target=None
        )
        final = get_state()['stats']
        log_event("system",
                  f"🏁 Autopilot finished. "
                  f"Discovered: {final.get('discovered', 0)} · "
                  f"Researched: {final.get('researched', 0)} · "
                  f"Added: {final.get('added_to_crm', 0)}")


def start_autopilot(config):
    """Start autopilot in background thread.

    IMPORTANT: We set `running=True` SYNCHRONOUSLY in the main thread before
    spawning the worker thread. Otherwise the Streamlit page reruns before the
    worker thread has had a chance to update state, the page reads
    `running=False`, and the user sees the idle view despite their click —
    which forces them to click Launch a second time.
    """
    state = get_state()
    if state.get('running'):
        return False, "Autopilot is already running"

    # Synchronously flip the running flag and seed the config so the next
    # st.rerun() reads the correct state.
    update_state(
        running=True,
        started_at=datetime.now().isoformat(),
        config=config,
        current_action="initializing",
        stats={
            "discovered": 0,
            "researched": 0,
            "qualified": 0,
            "added_to_crm": 0,
            "skipped": 0,
            "errors": 0,
        },
        recent_leads=[],
        sources_used={},
    )

    thread = threading.Thread(target=run_autopilot, args=(config,), daemon=True)
    thread.start()
    return True, "Autopilot started"


def stop_autopilot():
    """Signal autopilot to stop after current task."""
    update_state(running=False, current_action="stopping")
    log_event("system", "🛑 Stop requested — finishing current task...")
    return True


def is_running():
    return get_state().get('running', False)


_HAS_RESET_STALE = False

def reset_stale_state():
    """On fresh container boot, the state file may say running=true even though
    no thread is alive (previous container died, threads don't survive). Force-clear
    it once per process so the UI doesn't show a phantom running autopilot."""
    global _HAS_RESET_STALE
    if _HAS_RESET_STALE:
        return
    _HAS_RESET_STALE = True
    state = get_state()
    if state.get('running'):
        update_state(running=False, current_action='idle',
                     stopped_at=datetime.now().isoformat())
