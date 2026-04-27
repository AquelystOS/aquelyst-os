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
def is_already_in_crm(website_url):
    """Check if we've already added this business to the CRM."""
    if not website_url:
        return False
    domain = email_finder.get_domain_from_website(website_url)
    if not domain:
        return False
    leads = database.get_all_leads()
    for l in leads:
        lead_domain = email_finder.get_domain_from_website(l['website']) if l['website'] else None
        if lead_domain == domain:
            return True
    return False


def process_candidate(candidate, config):
    """Process a single discovered candidate end-to-end."""
    website = candidate['url']

    # Skip if already in CRM
    if is_already_in_crm(website):
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
        # OSM has metadata but no website — create minimal lead from OSM tags
        lead_data = {
            'business_name': candidate.get('title', 'Unknown'),
            'contact_name': None,
            'email': candidate.get('_osm_email') or None,
            'phone': candidate.get('_osm_phone') or None,
            'website': None,
            'city': candidate.get('_osm_city') or None,
            'state': candidate.get('_osm_state') or None,
            'business_type': 'horse facility (from OSM)',
            'lead_source': 'autopilot_osm',
            'source_channel': candidate.get('source_query', 'openstreetmap'),
            'pain_hypothesis': 'Horse facility — likely manages stalls, manure, fly control',
            'product_fit': 'Duo Equine',
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
                'hook': f"OSM-listed horse facility in {clean_lead.get('city') or 'unknown'}",
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
    """Start autopilot in background thread."""
    state = get_state()
    if state.get('running'):
        return False, "Autopilot is already running"

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
