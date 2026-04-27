"""AI Research Engine — Cerebras-powered deep-dive on each discovered lead.

For each candidate business:
1. Scrape their website (homepage + about + contact pages)
2. Send the content to Cerebras to extract structured intelligence
3. Generate a personalized outreach hook based on what AI saw
4. Score the lead with reasoning

This is the "Clay/Apollo killer" piece — AI reads the site like a salesperson would.
"""

import json
import re
import requests
from urllib.parse import urlparse, urljoin

import enrichment
import api_keys


CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _strip_html(html_text):
    """Strip HTML tags and clean whitespace, keeping only readable text."""
    if not html_text:
        return ""
    # Remove scripts and styles entirely
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip tags
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    # Decode common entities
    cleaned = cleaned.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    cleaned = cleaned.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _fetch_page(url, timeout=10):
    """Fetch a page and return cleaned text."""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if r.status_code == 200:
            return _strip_html(r.text)[:8000]  # Cap at 8KB of text
    except Exception:
        pass
    return ""


def gather_site_intelligence(website_url):
    """
    Scrape multiple pages of a business website and combine into a research dossier.
    """
    if not website_url:
        return {"text": "", "pages_scanned": [], "raw_data": {}}

    url = enrichment.normalize_url(website_url)
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    pages_to_check = [
        url,
        urljoin(base, '/about'),
        urljoin(base, '/about-us'),
        urljoin(base, '/services'),
        urljoin(base, '/contact'),
        urljoin(base, '/facility'),
        urljoin(base, '/boarding'),
    ]
    pages_to_check = list(dict.fromkeys(pages_to_check))[:5]

    combined_text = []
    pages_scanned = []

    for page_url in pages_to_check:
        text = _fetch_page(page_url)
        if text and len(text) > 100:
            pages_scanned.append(page_url)
            combined_text.append(f"[Page: {page_url}]\n{text[:3000]}")

    full_text = "\n\n---\n\n".join(combined_text)[:15000]

    # Also gather contact info via existing enrichment
    contact_info = enrichment.enrich_from_website(website_url)

    return {
        "text": full_text,
        "pages_scanned": pages_scanned,
        "contact_info": contact_info,
    }


RESEARCH_SYSTEM_PROMPT = """You are an elite B2B sales researcher for AqueLyst LLC, a company selling molecular odor-elimination and biosecurity products across SIX product lines (not just equine).

Your job: read a business's website, decide which AqueLyst product (if any) fits them, and score the fit. Be open-minded — many businesses outside the horse industry are excellent prospects.

You'll receive raw text scraped from a business's website. Extract structured intelligence as JSON.

CRITICAL RULES:
- Output ONLY valid JSON, no markdown fences, no preamble
- Use null for any field you genuinely cannot determine
- Don't invent facts — if it's not in the text, return null
- Return scores as integers 0-100 with honest reasoning
- Do NOT default to equine — pick the product that genuinely fits"""


RESEARCH_USER_TEMPLATE = """Analyze this business website and return a JSON dossier.

AQUELYST PRODUCTS — pick the SINGLE best fit for this business (or "none"):

1. **Duo Equine** — Equine biosecurity. Eliminates barn ammonia, reduces flies, kills pathogens at the molecular level.
   Fits: horse boarding facilities, equestrian centers, horse stables, racing/breeding farms, equine vets, riding schools, polo/rodeo/dressage facilities, racetracks, thoroughbred farms.

2. **Pets** — Pet odor + biosecurity for facilities housing multiple animals.
   Fits: dog boarding, doggy daycare, kennels, animal shelters, humane societies, veterinary clinics, grooming salons, pet stores, multi-pet rescues.

3. **SpillMaster** — Industrial / commercial cleanup, food, healthcare, transit hygiene.
   Fits: industrial cleanup contractors, hazmat services, food/meat/dairy processing, breweries/wineries, hospitals, nursing homes, manufacturing plants, schools, correctional facilities, transit authorities, airports.

4. **AMR** — Auto / Marine / RV / Aviation / Mass Transit interior odor + biosecurity.
   Fits: car dealerships, RV dealers, boat dealers, marinas, yacht clubs, rideshare/limo/taxi/bus fleets, trucking, school bus operators, aviation hangars, rental car companies.

5. **HouseHold** — Residential & residential-adjacent commercial cleaning.
   Fits: property management, Airbnb/vacation rental cleaning, apartment complexes, senior living, house cleaning services, mold/water/fire-damage restoration.

6. **Inversion Misting System** — Custom large-facility installation for big spaces.
   Fits: large warehouses, large manufacturing plants, agricultural processing, poultry / dairy / swine / cattle operations, feedlots, large greenhouses.

If NO product fits this business (e.g. solo lawyer's blog, coffee shop, gym, unrelated SaaS), set product_fit="none", should_pursue=false, and explain in skip_reason.

WEBSITE CONTENT:
{site_text}

Return JSON with these exact fields:
{{
  "business_name": "official business name from the site",
  "business_type": "concise description, e.g. 'horse boarding facility', 'industrial waste management', 'apartment property management', 'multi-location auto dealership'",
  "owner_or_contact_name": "first and last name if mentioned, else null",
  "city": "city if mentioned",
  "state": "2-letter state code if mentioned",
  "size_signal": "any scale indicator — stalls, units, fleet size, employees, locations, sq ft — else null",
  "services_offered": ["short list of key services they offer"],
  "product_fit": "Duo Equine | Pets | SpillMaster | AMR | HouseHold | Inversion Misting | none",
  "product_fit_reasoning": "one sentence on why this product fits this business",
  "likely_pain_points": ["specific pain points relevant to the chosen product, citing evidence from the text"],
  "personalized_hook": "ONE specific factual sentence referencing something concrete from their site you'd open a cold email with. Must reference a real fact from the text, not generic.",
  "match_score": "0-100 integer based on how well the chosen product fits",
  "match_reasoning": "one sentence explaining the score",
  "is_real_business": true/false,
  "should_pursue": true/false,
  "skip_reason": "if should_pursue is false, why? else null"
}}

Output JSON only:"""


def _pick_best_cerebras_model():
    """Dynamically find the best Cerebras model this account has access to."""
    import ai_providers
    models = ai_providers.get_cerebras_models()
    if not models:
        return "llama3.1-8b"  # safe fallback

    # Preference order: bigger/smarter models first, then fall back to faster ones
    preferences = [
        'qwen-3-235b-a22b-instruct-2507',  # 235B parameters — most capable
        'gpt-oss-120b',                     # 120B parameters — strong reasoning
        'zai-glm-4.7',                      # ZAI's flagship
        'llama-3.3-70b',
        'llama3.3-70b',
        'qwen-3-32b',
        'llama-4-scout-17b-16e-instruct',
        'deepseek-r1-distill-llama-70b',
        'llama3.1-70b',
        'llama3.1-8b',                      # Fastest fallback
    ]
    for pref in preferences:
        if pref in models:
            return pref
    return models[0]


def research_with_cerebras(site_text, model=None):
    """Send site content to Cerebras for structured extraction."""
    api_key = api_keys.get_key('cerebras')
    if not api_key:
        return None, "No Cerebras key configured"

    if model is None:
        model = _pick_best_cerebras_model()

    try:
        response = requests.post(
            f"{CEREBRAS_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                    {"role": "user", "content": RESEARCH_USER_TEMPLATE.format(site_text=site_text[:12000])},
                ],
                "max_tokens": 1024,
                "temperature": 0.2,  # Low temp for factual extraction
                "response_format": {"type": "json_object"},
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message']['content']
            # Strip any markdown fences
            content = re.sub(r'^```(?:json)?\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
            try:
                parsed = json.loads(content)
                return parsed, None
            except json.JSONDecodeError as e:
                return None, f"AI returned invalid JSON: {str(e)[:100]}"
        else:
            return None, f"Cerebras API error {response.status_code}: {response.text[:200]}"

    except requests.Timeout:
        return None, "Cerebras timeout"
    except Exception as e:
        return None, f"Research error: {str(e)}"


def research_with_claude(site_text, model="claude-haiku-4-5"):
    """Fallback to Claude if Cerebras unavailable."""
    api_key = api_keys.get_key('claude')
    if not api_key:
        return None, "No Claude key"

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1024,
                "system": RESEARCH_SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": RESEARCH_USER_TEMPLATE.format(site_text=site_text[:12000])
                }],
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            content = data['content'][0]['text']
            content = re.sub(r'^```(?:json)?\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
            try:
                return json.loads(content), None
            except json.JSONDecodeError as e:
                return None, f"Claude returned invalid JSON: {e}"
        return None, f"Claude error {response.status_code}"
    except Exception as e:
        return None, f"Claude error: {str(e)}"


def deep_research_lead(candidate, on_progress=None):
    """
    Full pipeline: scrape site → AI extract → enrich contact info → score.

    candidate: {url, title, snippet, source_query}
    on_progress: optional callback(stage_name, detail)

    Returns: {
        success: bool,
        website: str,
        intelligence: dict (from AI),
        contact_info: dict (from enrichment),
        error: str or None
    }
    """
    website = candidate['url']

    if on_progress:
        on_progress("scraping", f"Reading {urlparse(website).netloc}...")

    site_data = gather_site_intelligence(website)

    if not site_data['text'] or len(site_data['text']) < 200:
        return {
            "success": False,
            "website": website,
            "error": "Couldn't read enough content from site"
        }

    if on_progress:
        on_progress("analyzing", f"AI analyzing {len(site_data['pages_scanned'])} pages...")

    # Try Cerebras first (faster + cheaper), fall back to Claude
    intelligence, error = research_with_cerebras(site_data['text'])
    if not intelligence and api_keys.has_key('claude'):
        if on_progress:
            on_progress("analyzing", "Cerebras failed, trying Claude...")
        intelligence, error = research_with_claude(site_data['text'])

    if not intelligence:
        return {
            "success": False,
            "website": website,
            "error": error or "AI analysis failed"
        }

    return {
        "success": True,
        "website": website,
        "intelligence": intelligence,
        "contact_info": site_data['contact_info'],
        "pages_scanned": site_data['pages_scanned']
    }


def intelligence_to_lead_data(research_result, candidate):
    """Convert research result to lead-database-compatible dict."""
    if not research_result['success']:
        return None

    intel = research_result['intelligence']
    contact = research_result.get('contact_info', {})

    # Decide best email
    email = None
    if contact.get('emails'):
        email = enrichment.get_best_email(contact['emails'])

    # Decide best phone
    phone = None
    if contact.get('phones'):
        phone = enrichment.get_best_phone(contact['phones'])

    # Best social link
    social_url = None
    if contact.get('socials'):
        social_url = next(iter(contact['socials'].values()), None)

    # Build pain hypothesis from AI's analysis
    pain_points = intel.get('likely_pain_points', [])
    pain_text = " · ".join(pain_points) if pain_points else None

    # Notes = product fit + personalized hook + reasoning
    hook = intel.get('personalized_hook') or ""
    reasoning = intel.get('match_reasoning') or ""
    product_fit = intel.get('product_fit') or 'Duo Equine'
    if product_fit == 'none':
        product_fit = None
    fit_reason = intel.get('product_fit_reasoning') or ""

    notes_parts = []
    if product_fit:
        notes_parts.append(f"🎯 Product fit: {product_fit}{(' — ' + fit_reason) if fit_reason else ''}")
    if hook:
        notes_parts.append(f"💡 Hook: {hook}")
    if reasoning:
        notes_parts.append(f"📊 AI Score: {reasoning}")
    if intel.get('size_signal'):
        notes_parts.append(f"📐 Size: {intel['size_signal']}")
    elif intel.get('estimated_stalls'):
        notes_parts.append(f"🐴 Est. stalls: {intel['estimated_stalls']}")
    if intel.get('services_offered'):
        notes_parts.append(f"🛠 Services: {', '.join(intel['services_offered'][:5])}")
    notes = "\n\n".join(notes_parts)

    return {
        'business_name': intel.get('business_name') or candidate.get('title', 'Unknown'),
        'contact_name': intel.get('owner_or_contact_name'),
        'email': email,
        'phone': phone,
        'website': research_result['website'],
        'social_url': social_url,
        'city': intel.get('city'),
        'state': intel.get('state'),
        'business_type': intel.get('business_type'),
        'lead_source': 'autopilot',
        'source_channel': candidate.get('source_query', 'web_search'),
        'message': hook,
        'pain_hypothesis': pain_text,
        'product_fit': product_fit or 'Duo Equine',
        'notes': notes,
        '_ai_match_score': intel.get('match_score', 50),
        '_personalized_hook': hook,
        '_should_pursue': intel.get('should_pursue', True),
        '_skip_reason': intel.get('skip_reason'),
        '_is_real_business': intel.get('is_real_business', True),
    }
