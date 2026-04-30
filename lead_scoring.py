"""Lead scoring engine for AqueLyst Hunter.

Scoring strategy (in priority order):
1. If the AI research stage has assigned a `_ai_match_score` (0-100) → use that as the base
2. Else fall back to keyword-based scoring across ALL six product verticals
3. Add bonus points from the intelligence_layer (burden tags + need-probability)
4. Add bonus points for contact completeness
5. Cap at 100

This replaces the old equine-only scorer that scored everything else in the single digits.
"""


# Keyword scoring per vertical — used as fallback when AI hasn't scored yet
VERTICAL_KEYWORDS = {
    'Duo Equine': {
        'biz_types': [
            'horse boarding', 'equestrian', 'horse stable', 'horse rescue',
            'horse trainer', 'horse breeder', 'thoroughbred', 'standardbred',
            'racing stable', 'racetrack', 'polo club', 'rodeo', 'riding school',
            'dressage', 'show jumping', 'equine vet', 'equine therapy',
            'horse show', 'trail riding', 'dude ranch', 'guest ranch',
            'horse', 'equine', 'stable',
        ],
        'pain_keywords': [
            'ammonia', 'flies', 'fly control', 'odor', 'manure', 'stalls',
            'urine', 'barn air', 'bedding', 'biosecurity', 'fly season',
            'shavings', 'muck',
        ],
    },
    'Pets': {
        'biz_types': [
            'kennel', 'doggy daycare', 'dog boarding', 'cat boarding', 'pet hotel',
            'animal shelter', 'humane society', 'animal rescue', 'breed-specific',
            'veterinary clinic', 'vet hospital', 'emergency vet', 'spay neuter',
            'grooming salon', 'mobile groomer', 'dog training', 'agility training',
            'pet store', 'pet daycare', 'guide dog', 'k9 unit', 'pet care',
        ],
        'pain_keywords': [
            'kennel cough', 'multi-pet', 'cat urine', 'dog urine', 'pet odor',
            'biosecurity', 'parvo', 'bordetella', 'shelter', 'review', 'turn',
            'turnover', 'sanitiz',
        ],
    },
    'SpillMaster': {
        'biz_types': [
            'waste management', 'industrial cleanup', 'hazmat', 'environmental',
            'biohazard cleanup', 'crime scene cleanup', 'food processing',
            'meat processing', 'poultry processing', 'dairy processing',
            'commercial kitchen', 'catering', 'restaurant chain',
            'hospital', 'nursing home', 'assisted living', 'urgent care',
            'manufacturing plant', 'chemical plant', 'recycling facility',
            'composting facility', 'water treatment', 'sewage treatment',
            'landfill', 'airport', 'transit authority', 'correctional facility',
            'pharmaceutical', 'biotech', 'medical device manufacturer',
        ],
        'pain_keywords': [
            'osha', 'haccp', 'fda', 'usda', 'compliance', 'audit', 'biohazard',
            'hazmat', 'spill', 'sanitation', 'decon', 'pathogen', 'mrsa', 'c-diff',
            'food safety', 'environmental health', 'microbial', 'organic buildup',
            'washdown',
        ],
    },
    'AMR': {
        'biz_types': [
            'rv dealer', 'rv park', 'rv rental', 'campground', 'marina',
            'yacht club', 'boat dealer', 'boat rental', 'charter boat',
            'charter fishing', 'car dealership', 'auto dealer', 'used car',
            'auto detail', 'car wash', 'rideshare', 'limo service', 'taxi',
            'school bus', 'bus transit', 'charter bus', 'truck stop',
            'trucking', 'freight', 'delivery fleet', 'amazon delivery',
            'moving company', 'rental car', 'rental truck', 'aviation',
            'jet operator', 'fbo', 'helicopter charter', 'food truck',
            'shuttle service', 'powersports',
        ],
        'pain_keywords': [
            'mildew', 'bilge', 'holding tank', 'recon', 'reconditioning',
            'trade-in', 'cabin smell', 'interior odor', 'used car odor',
            'smoke smell', 'fleet wash', 'between trip', 'turnaround time',
            'cruise', 'fleet management',
        ],
    },
    'HouseHold': {
        'biz_types': [
            'property management', 'airbnb cleaning', 'vacation rental',
            'short-term rental', 'corporate housing', 'hoa', 'apartment complex',
            'condo association', 'townhouse', 'senior living', 'retirement community',
            'group home', 'co-living', 'student housing', 'university housing',
            'military housing', 'house cleaning', 'maid service', 'janitorial',
            'commercial cleaning', 'post-construction', 'mold remediation',
            'water damage restoration', 'fire damage restoration', 'smoke damage',
            'sewage cleanup', 'odor remediation', 'pet odor specialist',
            'pest control', 'carpet cleaning', 'duct cleaning', 'crawl space',
        ],
        'pain_keywords': [
            'pet odor', 'turnover', 'review', 'mold', 'mildew', 'water damage',
            'fire damage', 'smoke', 'biohazard', 'tenant', 'leased',
            'vacation rental', 'cleaning crew', 'turnaround', 'deep clean',
        ],
    },
    'Inversion Misting': {
        'biz_types': [
            'warehouse distribution', 'cold storage', 'food storage warehouse',
            'large manufacturing', 'agricultural processing', 'fruit packing',
            'vegetable processing', 'meat locker', 'rendering plant',
            'pet food manufacturer', 'animal feed manufacturer', 'grain elevator',
            'silo', 'ethanol', 'biodiesel', 'composting site',
            'agricultural fairground', 'livestock auction', 'poultry farm',
            'broiler', 'layer hen', 'turkey farm', 'duck farm', 'dairy farm',
            'goat dairy', 'sheep farm', 'swine operation', 'hog farm', 'feedlot',
            'cattle ranch', 'beef cattle', 'aquaculture', 'fish farm',
            'commercial greenhouse', 'hydroponic', 'commercial nursery',
            'cannabis cultivation', 'large indoor equestrian',
        ],
        'pain_keywords': [
            'cafo', 'afo', 'mortality', 'fly load', 'manure management', 'lagoon',
            'nuisance', 'lawsuit', 'permit', 'environmental impact', 'expansion',
            'osha air', 'pathogen pressure', 'bird flu', 'biosecurity',
            'feed conversion', 'parlor',
        ],
    },
}


def calculate_lead_score(lead_data):
    """
    Calculate lead score 0-100. AI-aware, multi-product.
    Higher score = more qualified.
    """
    # Path 1: AI has scored this lead (preferred — most accurate)
    ai_score = lead_data.get('_ai_match_score')
    if ai_score is not None:
        try:
            base = int(ai_score)
        except (ValueError, TypeError):
            base = 0
    else:
        base = _keyword_fallback_score(lead_data)

    # Add intelligence-layer bonus (burden tags + geography)
    burden_bonus = 0
    try:
        import intelligence_layer as _il
        burden = _il.get_burden_tags(lead_data.get('business_type', ''))
        # Each high-signal burden tag = +2 points (capped at +10)
        high_signal = {'AMMONIA', 'FECAL', 'FLY', 'CAFO', 'BIOHAZARD',
                        'BIOSECURITY', 'PATHOGEN', 'NUISANCE_LAWSUIT_RISK'}
        burden_bonus = min(10, sum(2 for t in burden if t in high_signal))
    except Exception:
        pass

    # Contact completeness bonus
    contact_bonus = 0
    if lead_data.get('email'):
        contact_bonus += 5
    if lead_data.get('phone'):
        contact_bonus += 3
    if lead_data.get('website'):
        contact_bonus += 2
    if lead_data.get('contact_name'):
        contact_bonus += 3
    contact_bonus = min(contact_bonus, 13)

    # Stall/size signal — old field, kept for compatibility
    size_bonus = 0
    try:
        stalls = int(lead_data.get('number_of_stalls', 0) or 0)
        if stalls >= 30:
            size_bonus = 5
        elif stalls >= 10:
            size_bonus = 3
        elif stalls >= 5:
            size_bonus = 1
    except (ValueError, TypeError):
        pass

    # Aqua-learning penalty: if this lead's email domain matches a
    # 'user_rejected_domain' signal (recorded when the user manually
    # deleted a lead from this domain), score the new lead down so it
    # doesn't pop back to the top of the queue. Bigger penalty for
    # multiple matches — three rejected leads from the same domain
    # is a strong "stop hunting here" signal.
    learning_penalty = 0
    email = (lead_data.get('email') or '').lower()
    if email and '@' in email:
        domain = email.split('@', 1)[-1]
        if domain not in ('gmail.com', 'outlook.com', 'yahoo.com',
                          'icloud.com', 'hotmail.com', 'aol.com',
                          'protonmail.com', 'live.com'):
            try:
                import database as _db
                conn = _db.get_connection()
                c = conn.cursor()
                try:
                    c.execute(
                        "SELECT COALESCE(match_count, 1) AS n FROM junk_signals "
                        "WHERE kind = ? AND value = ?",
                        ('user_rejected_domain', domain))
                    row = c.fetchone()
                    if row:
                        n = row['n'] if isinstance(row, dict) else row[0]
                        learning_penalty = -min(30, int(n) * 10)
                finally:
                    conn.close()
            except Exception:
                pass

    total = base + burden_bonus + contact_bonus + size_bonus + learning_penalty
    return max(0, min(100, total))


def _keyword_fallback_score(lead_data):
    """Score when AI hasn't yet evaluated. Multi-vertical keyword matching."""
    biz = (lead_data.get('business_type') or '').lower()
    problem_text = (
        f"{lead_data.get('message', '')} "
        f"{lead_data.get('pain_hypothesis', '')} "
        f"{lead_data.get('notes', '')}"
    ).lower()

    best_biz = 0
    best_pain = 0
    matched_vertical = None

    for vertical, kw in VERTICAL_KEYWORDS.items():
        # Business type match
        biz_pts = 0
        for term in kw['biz_types']:
            if term in biz:
                # Longer/more-specific terms score higher
                biz_pts = max(biz_pts, min(35, len(term) // 2 + 18))
        # Pain keyword match
        pain_pts = 0
        for kw_term in kw['pain_keywords']:
            if kw_term in problem_text:
                pain_pts = max(pain_pts, 12)

        vertical_score = biz_pts + pain_pts
        if vertical_score > best_biz + best_pain:
            best_biz = biz_pts
            best_pain = pain_pts
            matched_vertical = vertical

    return best_biz + best_pain


# Map of vertical → product name (used by match_product below)
_VERTICAL_TO_PRODUCT = {
    'Duo Equine': 'Duo Equine',
    'Pets': 'Pets',
    'SpillMaster': 'SpillMaster',
    'AMR': 'AMR',
    'HouseHold': 'HouseHold',
    'Inversion Misting': 'Inversion Misting',
}


def match_product(lead_data):
    """Determine which AqueLyst product fits this lead best.
    Trusts the AI's product_fit when present, falls back to keyword inference."""
    # Path 1: AI already chose a product
    ai_pick = (lead_data.get('product_fit') or '').strip()
    if ai_pick and ai_pick.lower() not in ('', 'none', 'unknown'):
        return ai_pick, 0.9

    # Path 2: keyword inference across all verticals
    biz = (lead_data.get('business_type') or '').lower()
    problem_text = (
        f"{lead_data.get('message', '')} "
        f"{lead_data.get('pain_hypothesis', '')} "
        f"{lead_data.get('notes', '')}"
    ).lower()

    best = (None, 0)
    for vertical, kw in VERTICAL_KEYWORDS.items():
        score = 0
        for term in kw['biz_types']:
            if term in biz:
                score += 3
        for kw_term in kw['pain_keywords']:
            if kw_term in problem_text:
                score += 2
        if score > best[1]:
            best = (vertical, score)

    if best[0]:
        confidence = min(0.85, 0.4 + 0.05 * best[1])
        return _VERTICAL_TO_PRODUCT.get(best[0], 'Not determined'), confidence
    return "Not determined", 0.0


def get_lead_score_explanation(score):
    """Return human-readable score explanation."""
    if score >= 85:
        return "🔥 Hot lead — call today"
    if score >= 70:
        return "⭐ Qualified — high priority outreach"
    if score >= 55:
        return "👍 Promising — researched + contactable"
    if score >= 40:
        return "❓ Maybe — needs more info"
    if score >= 25:
        return "📋 Low fit — likely peripheral"
    return "🚫 Poor fit — likely wrong vertical"
