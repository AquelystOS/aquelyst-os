"""Pre-outreach prospect research via Tavily web search.

Before Aqua drafts a cold email, she does a quick web search on the prospect's
business to find SPECIFIC facts (recent news, key personnel, location detail,
expansion announcements, etc.). The findings are injected into the NEPQ prompt
so the email can open with a real, personalized hook instead of generic
"hope this finds you well" filler.

Costs: Tavily free tier = 1000 searches / month. AqueLyst at typical autopilot
cadence will fit in the free tier; cache hits don't count.

Configuration: set `TAVILY_API_KEY` in Streamlit Secrets, OR add the key in
Admin → API Keys (it'll be saved to team_api_keys under provider='tavily').

Failure mode: if the key isn't configured or the call fails, this module
returns None — the calling code (nepq_engine.generate_initial_outreach) falls
back to its existing logic so there's never a regression.
"""

import json
import time
from pathlib import Path

import requests

import api_keys


CACHE_FILE = "lead_research_cache.json"
CACHE_TTL_SECONDS = 7 * 86400  # 7 days — drop stale research, re-fetch later
MAX_RESULTS = 5


def _load_cache():
    if not Path(CACHE_FILE).exists():
        return {}
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def _cache_key(lead_data):
    business = (lead_data.get('business_name') or '').lower().strip()
    city = (lead_data.get('city') or '').lower().strip()
    state = (lead_data.get('state') or '').lower().strip()
    return f"{business}|{city}|{state}"[:200]


def research_prospect(lead_data):
    """Fetch real-world facts about a prospect before drafting outreach.

    Args:
        lead_data: dict with at least business_name; city/state/website
                    optional but improve signal.

    Returns:
        dict with keys:
          - summary:        Tavily's auto-synthesized 1-paragraph answer
          - key_facts:      list[str] of useful snippets (max 5)
          - recent_news:    list[str] of news / press / blog mentions
          - source:         'tavily' | 'cache'
          - hook_candidates: list[str] of 1-line opener candidates Aqua
                             can quote in the email
        OR None if no Tavily key is configured / call failed (caller
        falls back to existing logic — no regression).
    """
    business = (lead_data.get('business_name') or '').strip()
    if not business:
        return None

    api_key = api_keys.get_key('tavily')
    if not api_key:
        return None  # graceful degradation

    # Cache lookup (7-day TTL)
    cache = _load_cache()
    key = _cache_key(lead_data)
    cached = cache.get(key)
    if cached and (time.time() - cached.get('ts', 0)) < CACHE_TTL_SECONDS:
        out = dict(cached.get('data', {}))
        out['source'] = 'cache'
        return out

    # Build the search query from whatever lead context we have
    location_parts = [p for p in (lead_data.get('city'), lead_data.get('state')) if p]
    query = business
    if location_parts:
        query += ' ' + ' '.join(location_parts)

    website = (lead_data.get('website') or '').strip()
    include_domains = []
    if website:
        # Tavily wants bare domain
        domain = website.replace('https://', '').replace('http://', '').strip('/').split('/')[0]
        if domain:
            include_domains.append(domain)

    try:
        body = {
            'api_key': api_key,
            'query': query,
            'max_results': MAX_RESULTS,
            'include_answer': True,
            'search_depth': 'basic',
            'topic': 'general',
        }
        if include_domains:
            body['include_domains'] = include_domains
        r = requests.post('https://api.tavily.com/search',
                           json=body, timeout=20)
        if r.status_code != 200:
            return None
        raw = r.json()
    except Exception:
        return None

    summary = (raw.get('answer') or '').strip()
    results = raw.get('results') or []

    key_facts = []
    recent_news = []
    hook_candidates = []
    for res in results[:MAX_RESULTS]:
        title = (res.get('title') or '').strip()[:140]
        url = (res.get('url') or '').strip()
        content = (res.get('content') or '').strip()
        snippet = content[:280]
        if not snippet:
            continue
        key_facts.append(snippet)
        url_low = url.lower()
        if any(x in url_low for x in ('news', 'press', 'blog', 'announce',
                                        'release', 'article')):
            recent_news.append(f"{title} — {url}")
        # First-line snippets make decent hooks
        first_line = snippet.split('. ')[0][:160]
        if 30 < len(first_line) < 160:
            hook_candidates.append(first_line)

    out = {
        'summary': summary[:600],
        'key_facts': key_facts[:5],
        'recent_news': recent_news[:3],
        'hook_candidates': hook_candidates[:5],
        'source': 'tavily',
    }
    cache[key] = {'ts': time.time(), 'data': out}
    _save_cache(cache)
    return out


def format_research_for_prompt(research):
    """Render research findings as a prompt block. Empty string if no useful
    research available."""
    if not research:
        return ''
    parts = []
    if research.get('summary'):
        parts.append(f"WEB-RESEARCHED SUMMARY:\n{research['summary']}")
    facts = research.get('key_facts') or []
    if facts:
        bullets = '\n'.join(f"  • {f[:200]}" for f in facts[:3])
        parts.append(f"SPECIFIC FACTS FOUND:\n{bullets}")
    news = research.get('recent_news') or []
    if news:
        bullets = '\n'.join(f"  • {n[:160]}" for n in news[:3])
        parts.append(f"RECENT NEWS / PRESS:\n{bullets}")
    if not parts:
        return ''
    body = '\n\n'.join(parts)
    return (
        f"\n## RESEARCHED FACTS ABOUT THIS PROSPECT (use these to personalize)\n"
        f"{body}\n\n"
        f"INSTRUCTION: Open the email with a SPECIFIC reference to one of these "
        f"facts. Quote a real detail you found — never use generic openers like "
        f"'I hope this finds you well' or 'I came across your business.' If a "
        f"recent news item is listed, leading with it is gold.\n"
    )
