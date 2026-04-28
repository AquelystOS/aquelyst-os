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


def search_sam_gov(naics_codes=None, keywords=None, days=30,
                    limit=100, api_key=None):
    """Search SAM.gov for opportunities. Returns (opps_list, err)."""
    if not api_key:
        return [], (
            "SAM.gov API key required. Get a free one at "
            "https://open.gsa.gov/api/get-opportunities-public-api/ then add it "
            "in Admin → API Keys → SAM.gov."
        )

    posted_from = (datetime.now() - timedelta(days=days)).strftime('%m/%d/%Y')
    posted_to = datetime.now().strftime('%m/%d/%Y')

    params = {
        'api_key': api_key,
        'postedFrom': posted_from,
        'postedTo': posted_to,
        'limit': min(limit, 1000),
        'offset': 0,
    }
    if naics_codes:
        params['ncode'] = ','.join(naics_codes[:50])  # SAM.gov caps at 50
    if keywords:
        params['q'] = ' OR '.join([f'"{k}"' for k in keywords[:8]])

    try:
        r = requests.get(SAM_GOV_BASE, params=params, timeout=30)
        if r.status_code == 401 or r.status_code == 403:
            return [], "SAM.gov rejected the API key (401/403)."
        if r.status_code != 200:
            return [], f"SAM.gov returned {r.status_code}: {r.text[:200]}"
        data = r.json()
        return data.get('opportunitiesData', []) or [], None
    except requests.Timeout:
        return [], "SAM.gov timeout (30s)"
    except Exception as e:
        return [], f"SAM.gov error: {str(e)[:200]}"


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


def discover_bid_opportunities(api_key=None, max_results=100, days=30,
                                 min_score=20, on_progress=None):
    """Hunt for relevant federal bid opportunities. Returns (scored_list, err)."""
    all_naics = []
    for codes in RELEVANT_NAICS.values():
        all_naics.extend(codes)
    all_naics = list(dict.fromkeys(all_naics))  # dedupe, preserve order

    if on_progress:
        on_progress(f"Querying SAM.gov for {len(all_naics)} NAICS codes...")

    raw_ops, err = search_sam_gov(naics_codes=all_naics, limit=max_results,
                                    days=days, api_key=api_key)
    if err:
        return [], err
    if on_progress:
        on_progress(f"SAM.gov returned {len(raw_ops)} opportunities — scoring…")

    scored = []
    for opp in raw_ops:
        norm = normalize_opportunity(opp)
        product, score, reasoning = score_opportunity(opp)
        if score >= min_score:
            norm['product_fit'] = product
            norm['match_score'] = score
            norm['match_reasoning'] = reasoning
            scored.append(norm)

    scored.sort(key=lambda o: -o['match_score'])
    if on_progress:
        on_progress(f"{len(scored)} opportunities matched at score ≥ {min_score}")
    return scored, None
