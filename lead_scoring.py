"""Lead scoring engine for AqueLyst Hunter."""

def calculate_lead_score(lead_data):
    """
    Calculate lead score 0-100 based on fit and engagement signals.
    Higher score = more qualified.
    """
    score = 0

    # Business type scoring (0-30 points)
    target_business_types = {
        "horse barn": 30,
        "stable": 30,
        "equestrian center": 30,
        "horse boarding facility": 30,
        "boarding": 28,
        "trainer": 25,
        "breeder": 20,
        "rescue": 25,
        "tack shop": 15,
        "feed store": 15,
        "equine business": 20,
    }

    business_type = (lead_data.get('business_type') or '').lower()
    for key, value in target_business_types.items():
        if key in business_type:
            score += value
            break

    # Problem signals (0-25 points)
    problem_keywords = {
        "ammonia": 10,
        "flies": 8,
        "odor": 10,
        "smell": 8,
        "manure": 8,
        "stalls": 10,
        "trailer": 7,
        "bedding": 7,
        "urine": 10,
        "barn": 5,
        "fly control": 8,
        "barn air": 8,
    }

    problem_text = (
        f"{lead_data.get('message', '')} {lead_data.get('pain_hypothesis', '')} {lead_data.get('notes', '')}"
    ).lower()

    problem_score = 0
    for keyword, value in problem_keywords.items():
        if keyword in problem_text:
            problem_score = max(problem_score, value)

    score += problem_score

    # Contact completeness (0-20 points)
    contact_score = 0
    if lead_data.get('email'):
        contact_score += 7
    if lead_data.get('phone'):
        contact_score += 7
    if lead_data.get('website'):
        contact_score += 3
    if lead_data.get('social_url'):
        contact_score += 3
    score += contact_score

    # Engagement signals (0-15 points)
    if lead_data.get('contact_name'):
        score += 5
    if lead_data.get('website'):
        score += 5

    # Number of stalls (commercial potential) - bonus
    try:
        stalls = int(lead_data.get('number_of_stalls', 0) or 0)
        if stalls >= 10:
            score += 10
        elif stalls >= 5:
            score += 5
    except (ValueError, TypeError):
        pass

    # Cap at 100
    return min(score, 100)


def match_product(lead_data):
    """
    Determine product fit for a lead.
    Currently only Duo Equine, but structured for future product additions.
    """
    problem_text = (
        f"{lead_data.get('message', '')} {lead_data.get('pain_hypothesis', '')} {lead_data.get('notes', '')}"
    ).lower()

    # Duo Equine indicators
    duo_keywords = [
        "ammonia", "flies", "fly", "odor", "smell", "horse stalls",
        "barn smell", "manure", "trailers", "bedding", "equine facility",
        "urine", "stall", "barn air", "fly control"
    ]

    duo_fit = any(keyword in problem_text for keyword in duo_keywords)

    if duo_fit:
        return "Duo Equine", 0.9
    elif "equine" in problem_text or "horse" in problem_text:
        return "Duo Equine", 0.6
    else:
        return "Not determined", 0.0


def get_lead_score_explanation(score):
    """Return human-readable score explanation."""
    if score >= 80:
        return "🔥 Hot lead - high priority"
    elif score >= 60:
        return "⭐ Qualified lead - good fit"
    elif score >= 40:
        return "👍 Potential - needs research"
    elif score >= 20:
        return "❓ Early stage - gather more info"
    else:
        return "📋 New - not yet scored"
