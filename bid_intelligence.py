"""Bid Opportunity Intelligence — federal procurement matching.

Scrapes SAM.gov (the official US government contract opportunities database)
for federal RFPs / RFQs / sources-sought notices that match AqueLyst's product
portfolio. Each opportunity is matched against:

  - NAICS codes that historically require sanitation / biosecurity / odor /
    green-chemical products
  - Keyword signals in the title and description (e.g. "biohazard cleanup",
    "ammonia mitigation", "biopreferred", "USDA approved disinfectant")

Each scored opportunity is then stored in `bid_opportunities` for the team to
work as a CRM-adjacent pipeline.

API key: free at https://open.gsa.gov/api/get-opportunities-public-api/ — admins
configure under Admin → API Keys → SAM.gov.
"""

from datetime import datetime, timedelta
import requests


SAM_GOV_BASE = "https://api.sam.gov/opportunities/v2/search"


# ============================================================================
# NAICS codes that signal AqueLyst product fit
# ============================================================================
RELEVANT_NAICS = {
    'Duo Equine': ['112920', '115210'],
    'Pets': ['541940', '812910', '424910'],
    'SpillMaster': [
        '561720',  # Janitorial services
        '562910',  # Remediation services
        '562998',  # Waste management NEC
        '561210',  # Facilities support
        '311611', '311612',  # Meat processing
        '311615',  # Poultry processing
        '622110',  # General hospitals
        '623110',  # Nursing care
        '325611',  # Soap & cleaning compounds (suppliers)
        '325998',  # Misc. chemical (sanitizers)
        '423850',  # Service establishment equipment & supplies
    ],
    'AMR': [
        '441110', '441210', '441222',  # Auto/RV/Boat dealers
        '484110', '484121', '484220',  # Trucking
        '485113', '485111',  # Bus / transit
        '488', '488111',  # Aviation support
        '336411',  # Aircraft mfg (cabin maintenance contracts)
    ],
    'HouseHold': [
        '561720',  # Janitorial
        '236118',  # Residential remodelers (post-disaster)
        '562910',  # Remediation
        '624229',  # Other emergency / relief
    ],
    'Inversion Misting': [
        '112120',  # Dairy
        '112310', '112320', '112330', '112340',  # Poultry
        '112210',  # Hog & pig
        '112111', '112112',  # Cattle
        '115210',  # Animal-production support
    ],
}

# Keywords that strongly signal a procurement requires AqueLyst-style products
PRODUCT_KEYWORDS = {
    'Duo Equine': [
        'equine', 'horse', 'stable', 'biosecurity', 'stall', 'paddock',
        'mounted unit', 'barn',
    ],
    'Pets': [
        'kennel', 'animal facility', 'veterinary', 'shelter sanitation',
        'animal control', 'humane society', 'aaha', 'usda-aphis',
        'k9 facility', 'working dog',
    ],
    'SpillMaster': [
        'biohazard', 'hazmat', 'industrial cleaning', 'food safety',
        'pathogen control', 'sanitation services', 'biobased',
        'green chemicals', 'osha compliance', 'haccp', 'mrsa',
        'c. difficile', 'covid', 'decontamination', 'disinfectant',
        'janitorial', 'environmental remediation', 'hospital cleaning',
        'usda approved disinfectant', 'epa list n',
    ],
    'AMR': [
        'fleet sanitation', 'vehicle decontamination', 'marine sanitation',
        'aircraft cabin', 'transit cleaning', 'bus interior', 'fleet wash',
        'mold and mildew remediation', 'odor remediation interior',
    ],
    'HouseHold': [
        'residential cleaning contract', 'mold remediation',
        'odor remediation residential', 'turnover cleaning',
        'post-disaster cleanup', 'biohazard residential',
    ],
    'Inversion Misting': [
        'cafo', 'feedlot', 'poultry biosecurity', 'ammonia mitigation',
        'odor control livestock', 'fly mitigation', 'manure management',
        'agricultural odor', 'air quality livestock', 'dairy parlor',
        'broiler', 'layer', 'swine biosecurity',
    ],
}

# Universal "green procurement" signals — bonus points across all products
GREEN_PROCUREMENT_SIGNALS = [
    'green chemicals', 'biobased', 'biopreferred', 'eco-friendly',
    'comprehensive procurement guidelines', 'cpg', 'epa smartway',
    'sustainable acquisition', 'environmentally preferable',
    'usda biopreferred', 'green seal', 'safer choice',
]


def _sam_gov_query(api_key, days, params, limit=1000):
    """One SAM.gov call. Returns (opps_list, err). Date params + api_key required."""
    posted_from = (datetime.now() - timedelta(days=days)).strftime('%m/%d/%Y')
    posted_to = datetime.now().strftime('%m/%d/%Y')

    full_params = {
        'api_key': api_key,
        'postedFrom': posted_from,
        'postedTo': posted_to,
        'limit': min(limit, 1000),
        'offset': 0,
    }
    full_params.update(params)

    try:
        r = requests.get(SAM_GOV_BASE, params=full_params, timeout=30)
        if r.status_code in (401, 403):
            return [], "SAM.gov rejected the API key. Re-check it in Admin → API Keys."
        if r.status_code == 429:
            return [], "SAM.gov rate-limited the request. Wait a minute and retry."
        if r.status_code != 200:
            return [], f"SAM.gov returned {r.status_code}: {r.text[:200]}"
        data = r.json()
        return data.get('opportunitiesData', []) or [], None
    except requests.Timeout:
        return [], "SAM.gov timeout (30s)"
    except Exception as e:
        return [], f"SAM.gov error: {str(e)[:200]}"


def search_sam_gov(naics_codes=None, keywords=None, days=30,
                    limit=100, api_key=None):
    """Single-shot search — used by tests + as a fallback. Most callers should
    use discover_bid_opportunities() which does multiple targeted queries."""
    if not api_key:
        return [], "SAM.gov API key required."
    params = {}
    # SAM.gov ncode takes ONE code at a time. Use only the first if multiple given.
    if naics_codes:
        params['ncode'] = naics_codes[0]
    if keywords:
        params['title'] = keywords[0]
    return _sam_gov_query(api_key, days, params, limit)


# Federal Supply Class / Product Service Codes that strongly match AqueLyst
# https://www.acquisition.gov/psc-manual
RELEVANT_PSC = [
    '6840',  # Pest control agents & disinfectants — strongest signal
    '6810',  # Chemicals
    '7930',  # Cleaning & polishing compounds
    'S201',  # Custodial / janitorial services
    'S214',  # Other special studies / services (env)
    'F999',  # Environmental services NEC
    'F108',  # Hazardous waste removal
    'F107',  # Pollution control services
    'M199',  # Operation of facilities
]

# Free-text keywords that catch high-fit opportunities even when codes don't match
SEARCH_KEYWORDS = [
    "disinfectant", "biohazard", "sanitation services",
    "decontamination", "ammonia mitigation", "odor control",
    "biosecurity", "green chemicals", "biopreferred",
    "kennel cleaning", "stable cleaning",
]


def score_opportunity(opp):
    """Score how well this opportunity matches AqueLyst's product portfolio.
    Returns (product_fit, score 0-100, reasoning_string)."""
    title = (opp.get('title') or '').lower()
    description = (opp.get('description') or '').lower()
    naics = opp.get('naicsCode') or ''
    text = f"{title} {description}"

    best_product = None
    best_score = 0
    best_reasoning = []

    for product, naics_list in RELEVANT_NAICS.items():
        score = 0
        reasons = []
        if naics in naics_list:
            score += 30
            reasons.append(f"NAICS {naics} matches {product}")
        for kw in PRODUCT_KEYWORDS.get(product, []):
            if kw in text:
                score += 10
                reasons.append(f"keyword '{kw}'")
                if score >= 80:
                    break
        for kw in GREEN_PROCUREMENT_SIGNALS:
            if kw in text:
                score += 5
                reasons.append(f"green-procurement signal: '{kw}'")
                break
        if score > best_score:
            best_score = score
            best_product = product
            best_reasoning = reasons

    return best_product, min(100, best_score), '; '.join(best_reasoning[:6])


def normalize_opportunity(opp):
    """Convert SAM.gov opportunity dict to our internal flat format."""
    poc_list = opp.get('pointOfContact') or []
    poc = poc_list[0] if isinstance(poc_list, list) and poc_list else {}
    if not isinstance(poc, dict):
        poc = {}

    place = opp.get('placeOfPerformance') or {}
    place_str = ''
    if isinstance(place, dict):
        city = place.get('city')
        state = place.get('state')
        city_name = (city.get('name') if isinstance(city, dict) else '') or ''
        state_code = (state.get('code') if isinstance(state, dict) else '') or ''
        place_str = ', '.join(filter(None, [city_name, state_code]))

    agency = ''
    fpath = opp.get('fullParentPathName') or ''
    if fpath:
        agency = fpath.split('.')[-1].strip()

    return {
        'external_id': opp.get('noticeId', '') or '',
        'source': 'sam.gov',
        'title': (opp.get('title') or '')[:500],
        'agency': agency[:200],
        'naics': opp.get('naicsCode', '') or '',
        'description': (opp.get('description') or '')[:8000],
        'posted_at': opp.get('postedDate', '') or '',
        'deadline': opp.get('responseDeadLine', '') or '',
        'place': place_str[:200],
        'contact_email': (poc.get('email') or '')[:200],
        'contact_name': (poc.get('fullName') or '')[:200],
        'contact_phone': (poc.get('phone') or '')[:50],
        'url': opp.get('uiLink', '') or '',
    }


def discover_bid_opportunities(api_key=None, max_results=200, days=30,
                                 min_score=20, on_progress=None,
                                 custom_keyword=None):
    """Hunt for relevant federal bid opportunities across multiple targeted
    queries (PSC codes, NAICS codes, keywords). Combines + dedupes + scores.

    custom_keyword: if provided, runs an extra title search with that phrase.
    Returns (scored_list, err).
    """
    if not api_key:
        return [], "SAM.gov API key required. Add one in Admin → API Keys."

    all_raw = []
    seen_ids = set()
    queries_run = 0
    queries_failed = 0
    last_err = None

    def _absorb(ops, _label):
        n = 0
        for op in ops:
            nid = op.get('noticeId')
            if nid and nid not in seen_ids:
                seen_ids.add(nid)
                all_raw.append(op)
                n += 1
        return n

    # Strategy 1: Product Service Code (PSC) queries — the strongest signal
    # for "this contract needs cleaning chemicals / disinfectants / sanitation"
    for psc in RELEVANT_PSC:
        if on_progress:
            on_progress(f"Q{queries_run + 1}: PSC {psc}…")
        ops, err = _sam_gov_query(api_key, days,
                                    {'ccode': psc}, limit=200)
        queries_run += 1
        if err:
            queries_failed += 1
            last_err = err
            if 'rate-limited' in err.lower() or 'rejected the api key' in err.lower():
                break  # don't burn through more calls
            continue
        added = _absorb(ops, f"PSC {psc}")
        if on_progress:
            on_progress(f"  → +{added} new (running total {len(all_raw)})")

    # Strategy 2: Keyword title searches
    keywords_to_try = list(SEARCH_KEYWORDS)
    if custom_keyword:
        keywords_to_try = [custom_keyword] + keywords_to_try
    for kw in keywords_to_try[:8]:  # cap to keep within rate limits
        if on_progress:
            on_progress(f"Q{queries_run + 1}: keyword '{kw}'…")
        ops, err = _sam_gov_query(api_key, days,
                                    {'title': kw}, limit=200)
        queries_run += 1
        if err:
            queries_failed += 1
            last_err = err
            if 'rate-limited' in err.lower() or 'rejected the api key' in err.lower():
                break
            continue
        added = _absorb(ops, f"kw '{kw}'")
        if on_progress:
            on_progress(f"  → +{added} new (running total {len(all_raw)})")

    # Strategy 3: high-priority NAICS codes (one query each — SAM.gov ncode is single-value)
    priority_naics = [
        '562910',  # Remediation services
        '561720',  # Janitorial
        '562998',  # Waste mgmt NEC
        '311615',  # Poultry processing
        '112310',  # Poultry production
        '112120',  # Dairy
        '622110',  # General hospitals
        '485113',  # Bus transit
    ]
    for code in priority_naics:
        if on_progress:
            on_progress(f"Q{queries_run + 1}: NAICS {code}…")
        ops, err = _sam_gov_query(api_key, days,
                                    {'ncode': code}, limit=200)
        queries_run += 1
        if err:
            queries_failed += 1
            last_err = err
            if 'rate-limited' in err.lower() or 'rejected the api key' in err.lower():
                break
            continue
        added = _absorb(ops, f"NAICS {code}")
        if on_progress:
            on_progress(f"  → +{added} new (running total {len(all_raw)})")

    if not all_raw and last_err:
        return [], f"All queries failed. Last error: {last_err}"
    if on_progress:
        on_progress(
            f"Pulled {len(all_raw)} unique opportunities across {queries_run} "
            f"queries ({queries_failed} failed) — scoring…"
        )

    scored = []
    for opp in all_raw:
        norm = normalize_opportunity(opp)
        product, score, reasoning = score_opportunity(opp)
        if score >= min_score:
            norm['product_fit'] = product
            norm['match_score'] = score
            norm['match_reasoning'] = reasoning
            scored.append(norm)

    scored.sort(key=lambda o: -o['match_score'])
    if on_progress:
        on_progress(
            f"{len(scored)} of {len(all_raw)} matched at score ≥ {min_score}"
        )
    return scored, None
