"""Lead Discovery Engine — find horse businesses across the open web.

No paid APIs. Uses:
- DuckDuckGo HTML search (no API key needed)
- Bing HTML search (backup)
- YellowPages directory
- Direct site scraping

Each discovered candidate goes to ai_research.py for Cerebras-powered qualification.
"""

import re
import time
import requests
from urllib.parse import urlparse, urljoin, quote_plus
from html.parser import HTMLParser


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 12
POLITE_DELAY = 1.5  # seconds between requests to same source


# Domains to skip — directories, marketplaces, social, news
SKIP_DOMAINS = {
    'yelp.com', 'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'linkedin.com', 'youtube.com', 'pinterest.com', 'tiktok.com',
    'wikipedia.org', 'wikiwand.com', 'reddit.com', 'quora.com',
    'amazon.com', 'ebay.com', 'craigslist.org', 'tripadvisor.com',
    'yellowpages.com', 'mapquest.com', 'whitepages.com', 'manta.com',
    'better-business-bureau.com', 'bbb.org', 'angi.com',
    'duckduckgo.com', 'google.com', 'bing.com',
    'horsefinders.com', 'horseclicks.com', 'equine.com',
    'usef.org', 'ushja.org', 'ahaa.com',
    'youtube-nocookie.com', 't.co', 'lnkd.in',
    'apple.com', 'microsoft.com', 'gov',
}


class DuckDuckGoResultParser(HTMLParser):
    """Parse DuckDuckGo HTML search results."""

    def __init__(self):
        super().__init__()
        self.results = []
        self.current_url = None
        self.current_title = None
        self.current_snippet = None
        self.in_result_link = False
        self.in_snippet = False
        self.collecting_text = False
        self.text_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get('class', '')

        if tag == 'a' and 'result__a' in cls:
            self.in_result_link = True
            self.current_url = attrs_dict.get('href', '')
            self.collecting_text = True
            self.text_buffer = []
        elif tag == 'a' and 'result__snippet' in cls:
            self.in_snippet = True
            self.collecting_text = True
            self.text_buffer = []

    def handle_endtag(self, tag):
        if tag == 'a':
            if self.in_result_link:
                self.current_title = ' '.join(self.text_buffer).strip()
                self.in_result_link = False
                self.collecting_text = False
            elif self.in_snippet:
                self.current_snippet = ' '.join(self.text_buffer).strip()
                self.in_snippet = False
                self.collecting_text = False

                # Save complete result
                if self.current_url and self.current_title:
                    cleaned_url = self._clean_ddg_url(self.current_url)
                    if cleaned_url:
                        self.results.append({
                            'url': cleaned_url,
                            'title': self.current_title,
                            'snippet': self.current_snippet
                        })
                self.current_url = None
                self.current_title = None
                self.current_snippet = None

    def handle_data(self, data):
        if self.collecting_text:
            self.text_buffer.append(data)

    def _clean_ddg_url(self, url):
        """DuckDuckGo wraps real URLs as /l/?uddg=encoded. Unwrap them."""
        if not url:
            return None

        if 'uddg=' in url:
            try:
                from urllib.parse import unquote, parse_qs, urlparse as p
                parsed = p(url)
                params = parse_qs(parsed.query)
                if 'uddg' in params:
                    return unquote(params['uddg'][0])
            except Exception:
                return None

        if url.startswith('http'):
            return url
        return None


def _domain_of(url):
    """Get clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace('www.', '')
        return domain
    except Exception:
        return None


def _should_skip(url):
    """Skip directories, social, irrelevant sites."""
    domain = _domain_of(url)
    if not domain:
        return True
    for skip in SKIP_DOMAINS:
        if skip in domain:
            return True
    # Skip subdomains of major directories
    if any(domain.endswith(d) for d in ['.gov', '.edu']):
        return True
    return False


def search_duckduckgo(query, max_results=30):
    """Search DuckDuckGo HTML interface (no API key) — robust against rate limits."""

    # Try multiple endpoints in order
    endpoints = [
        ("https://html.duckduckgo.com/html/", "POST"),
        ("https://duckduckgo.com/html/", "POST"),
        ("https://html.duckduckgo.com/html/", "GET"),
    ]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Referer": "https://duckduckgo.com/",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    }

    for endpoint, method in endpoints:
        try:
            if method == "POST":
                response = requests.post(
                    endpoint,
                    data={"q": query, "kl": "us-en", "df": ""},
                    headers=headers,
                    timeout=REQUEST_TIMEOUT
                )
            else:
                response = requests.get(
                    endpoint,
                    params={"q": query, "kl": "us-en"},
                    headers=headers,
                    timeout=REQUEST_TIMEOUT
                )

            if response.status_code != 200:
                continue

            # Check if we got actual results page
            if "result__a" not in response.text and "results_links" not in response.text:
                continue

            parser = DuckDuckGoResultParser()
            parser.feed(response.text)

            seen_domains = set()
            candidates = []
            for r in parser.results[:max_results * 2]:
                if _should_skip(r['url']):
                    continue
                domain = _domain_of(r['url'])
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)
                candidates.append(r)
                if len(candidates) >= max_results:
                    break

            if candidates:
                return candidates

        except Exception:
            continue

    return []


def search_searxng(query, max_results=20):
    """
    Search via public SearXNG instances — meta-search aggregator.
    Hits Google + Bing + DDG + others all at once. Usually not rate-limited.

    Tries multiple known public instances in order until one works.
    """
    # Public SearXNG instances (community-run; rotated to avoid burdening any one)
    instances = [
        "https://search.inetol.net",
        "https://searx.tiekoetter.com",
        "https://opnxng.com",
        "https://baresearch.org",
        "https://search.rhscz.eu",
        "https://search.sapti.me",
        "https://priv.au",
    ]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,*/*",
    }

    import random
    random.shuffle(instances)

    for instance in instances:
        try:
            # Try JSON API first (cleaner)
            json_url = f"{instance}/search"
            response = requests.get(
                json_url,
                params={
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "engines": "google,bing,duckduckgo,brave,qwant",
                },
                headers=headers,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    results = []
                    seen_domains = set()

                    for item in data.get('results', [])[:max_results * 2]:
                        url_match = item.get('url', '')
                        if _should_skip(url_match):
                            continue
                        domain = _domain_of(url_match)
                        if not domain or domain in seen_domains:
                            continue
                        seen_domains.add(domain)

                        results.append({
                            'url': url_match,
                            'title': item.get('title', domain)[:120],
                            'snippet': item.get('content', '')[:200]
                        })

                        if len(results) >= max_results:
                            break

                    if results:
                        return results
                except (ValueError, KeyError):
                    pass  # JSON parse failed, try next

        except (requests.RequestException, requests.Timeout):
            continue  # Try next instance

    return []


def discover_via_openstreetmap(business_type, location=None, max_results=50):
    """
    Discover horse businesses via OpenStreetMap Overpass API.
    UNLIMITED FREE — no API key, no rate limits to speak of.

    Every horse facility on Earth is tagged in OSM. This is the most powerful
    free source available.

    Searches for OSM nodes/ways tagged with horse-related amenities.
    """

    # OSM tags by business vertical. If no mapping matches, OSM is skipped
    # entirely for that business type (no more "default to equestrian" trap
    # that was making 'oil refinery' searches return horse barns).
    osm_tag_queries = {
        # Equine
        'horse boarding facility': '["sport"="equestrian"]',
        'equestrian center':       '["sport"="equestrian"]',
        'horse stable':            '["leisure"="horse_riding"]',
        'horse riding':            '["leisure"="horse_riding"]',
        'horse trainer':           '["sport"="equestrian"]',
        'horse breeder':           '["sport"="equestrian"]',
        'horse rescue':            '["amenity"="animal_shelter"]["animal"="horse"]',
        'tack shop':               '["shop"="pet"]',
        'feed store':              '["shop"="agrarian"]',
        # Pets
        'kennel':                  '["amenity"="animal_boarding"]',
        'dog boarding':            '["amenity"="animal_boarding"]',
        'doggy daycare':           '["amenity"="animal_boarding"]',
        'pet hotel':               '["amenity"="animal_boarding"]',
        'animal shelter':          '["amenity"="animal_shelter"]',
        'humane society':          '["amenity"="animal_shelter"]',
        'animal rescue':           '["amenity"="animal_shelter"]',
        'veterinary':              '["amenity"="veterinary"]',
        'vet clinic':              '["amenity"="veterinary"]',
        'pet store':               '["shop"="pet"]',
        'grooming':                '["shop"="pet_grooming"]',
        # SpillMaster (industrial / commercial)
        'oil refinery':            '["industrial"="oil"]',
        'refinery':                '["industrial"="oil"]',
        'food processing':         '["industrial"="food"]',
        'meat processing':         '["industrial"="slaughterhouse"]',
        'meat packing':            '["industrial"="slaughterhouse"]',
        'dairy processing':        '["industrial"="dairy"]',
        'brewery':                 '["craft"="brewery"]',
        'winery':                  '["craft"="winery"]',
        'distillery':              '["craft"="distillery"]',
        'hospital':                '["amenity"="hospital"]',
        'nursing home':            '["amenity"="nursing_home"]',
        'assisted living':         '["amenity"="social_facility"]["social_facility"="assisted_living"]',
        'manufacturing':           '["industrial"="factory"]',
        'chemical plant':          '["industrial"="chemical"]',
        'water treatment':         '["man_made"="wastewater_plant"]',
        'wastewater':              '["man_made"="wastewater_plant"]',
        'sewage':                  '["man_made"="wastewater_plant"]',
        'landfill':                '["landuse"="landfill"]',
        # AMR
        'car dealer':              '["shop"="car"]',
        'auto dealer':             '["shop"="car"]',
        'rv':                      '["shop"="caravan"]',
        'rv dealer':               '["shop"="caravan"]',
        'boat dealer':             '["shop"="boat"]',
        'marina':                  '["leisure"="marina"]',
        'truck stop':              '["amenity"="truck_stop"]',
        'gas station':             '["amenity"="fuel"]',
        'fuel':                    '["amenity"="fuel"]',
        'aviation':                '["aeroway"="aerodrome"]',
        'airport':                 '["aeroway"="aerodrome"]',
        # HouseHold
        'apartment':               '["building"="apartments"]',
        'condo':                   '["building"="apartments"]',
        'hotel':                   '["tourism"="hotel"]',
        'motel':                   '["tourism"="motel"]',
        # Inversion Misting / agriculture
        'poultry farm':            '["landuse"="farmyard"]["produce"="poultry"]',
        'dairy farm':              '["landuse"="farmyard"]["produce"="milk"]',
        'farm':                    '["landuse"="farmyard"]',
        'feedlot':                 '["landuse"="farmyard"]["produce"="livestock"]',
        'cattle':                  '["landuse"="farmyard"]["produce"="livestock"]',
        'aquaculture':             '["landuse"="aquaculture"]',
        'fish farm':               '["landuse"="aquaculture"]',
        'greenhouse':              '["building"="greenhouse"]',
        'warehouse':               '["building"="warehouse"]',
        'cold storage':            '["industrial"="cold_storage"]',
    }

    tag_query = None
    bt_lower = business_type.lower().strip()
    # Most specific match first (longer keys first so e.g. "oil refinery"
    # wins over a hypothetical generic "oil" entry).
    for key in sorted(osm_tag_queries.keys(), key=len, reverse=True):
        if key in bt_lower:
            tag_query = osm_tag_queries[key]
            break
    if not tag_query:
        # No OSM tag mapping for this business type — skip OSM entirely.
        # Other sources (DDG/Bing/AI knowledge) will handle it. Returning
        # empty list keeps callers happy.
        return []

    # Geocode location → bounding box, or use country-wide search
    bbox = None
    if location:
        bbox = _geocode_to_bbox(location)

    # Build Overpass QL query
    if bbox:
        # Search within bounding box
        area_clause = f"({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']})"
    else:
        # Default to USA bounding box
        area_clause = "(24.5,-125.0,49.4,-66.9)"

    query = f"""[out:json][timeout:30];
(
  node{tag_query}{area_clause};
  way{tag_query}{area_clause};
  relation{tag_query}{area_clause};
);
out body center {max_results * 3};
"""

    # Multiple Overpass instances for redundancy
    overpass_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.fr/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]

    for endpoint in overpass_endpoints:
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=45
            )

            if response.status_code != 200:
                continue

            data = response.json()
            elements = data.get('elements', [])

            results = []
            seen_domains = set()
            seen_names = set()

            for el in elements:
                tags = el.get('tags', {})
                name = tags.get('name', '').strip()
                website = (tags.get('website') or tags.get('contact:website')
                           or tags.get('url') or '').strip()
                phone = (tags.get('phone') or tags.get('contact:phone') or '').strip()
                email = (tags.get('email') or tags.get('contact:email') or '').strip()
                city = (tags.get('addr:city') or tags.get('city') or '').strip()
                state = (tags.get('addr:state') or '').strip()

                # Skip if no name
                if not name or len(name) < 2:
                    continue

                # Skip duplicates
                name_key = name.lower()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                # If we have a website, validate it
                if website:
                    if not website.startswith(('http://', 'https://')):
                        website = 'https://' + website
                    domain = _domain_of(website)
                    if not domain or domain in seen_domains or _should_skip(website):
                        continue
                    seen_domains.add(domain)
                    url_to_use = website
                else:
                    # Even without website, this is useful info
                    # Use a synthetic OSM url so we can still process it
                    osm_id = el.get('id', 0)
                    osm_type = el.get('type', 'node')
                    url_to_use = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"

                # Build snippet from OSM data
                snippet_parts = []
                if city: snippet_parts.append(city)
                if state: snippet_parts.append(state)
                if phone: snippet_parts.append(f"📞 {phone}")
                if email: snippet_parts.append(f"📧 {email}")
                snippet = " · ".join(snippet_parts)

                results.append({
                    'url': url_to_use,
                    'title': name,
                    'snippet': snippet,
                    '_osm_phone': phone,
                    '_osm_email': email,
                    '_osm_city': city,
                    '_osm_state': state,
                    '_osm_website': website,
                    '_osm_data': True,
                })

                if len(results) >= max_results:
                    break

            return results

        except (requests.RequestException, ValueError, KeyError):
            continue

    return []


def _geocode_to_bbox(location):
    """Convert location string to bounding box via Nominatim (free, no key)."""
    if not location:
        return None

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": "AqueLyst-Hunter/1.0"},
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()
        if not data:
            return None

        bbox_arr = data[0].get('boundingbox')
        if not bbox_arr or len(bbox_arr) < 4:
            return None

        # Nominatim format: [south, north, west, east]
        return {
            'south': float(bbox_arr[0]),
            'north': float(bbox_arr[1]),
            'west': float(bbox_arr[2]),
            'east': float(bbox_arr[3]),
        }
    except Exception:
        return None


AI_CACHE_FILE = "ai_discovery_cache.json"


def _load_ai_cache():
    """Load AI-generated business cache (accumulates over runs)."""
    try:
        from pathlib import Path
        if Path(AI_CACHE_FILE).exists():
            with open(AI_CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_ai_cache(cache):
    """Persist AI-generated business cache."""
    try:
        with open(AI_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def get_cached_ai_results(business_type, location):
    """Get previously-generated results from cache."""
    cache = _load_ai_cache()
    key = f"{business_type}::{location or 'all'}".lower()
    return cache.get(key, [])


def cache_ai_results(business_type, location, results):
    """Append new AI results to cache (deduplicated by domain)."""
    cache = _load_ai_cache()
    key = f"{business_type}::{location or 'all'}".lower()

    existing = cache.get(key, [])
    existing_domains = {_domain_of(r['url']) for r in existing}

    for r in results:
        domain = _domain_of(r['url'])
        if domain and domain not in existing_domains:
            existing.append(r)
            existing_domains.add(domain)

    cache[key] = existing
    _save_ai_cache(cache)


def discover_via_ai_knowledge(business_type, location, max_results=30):
    """
    Use Cerebras's built-in knowledge to generate candidate businesses.
    This bypasses search-engine rate limits entirely.

    The LLM knows about real horse businesses across the US.
    We ask it for a list, then validate each one by visiting its website.
    """
    try:
        import api_keys
    except ImportError:
        return []

    api_key = api_keys.get_key('cerebras')
    if not api_key:
        return []

    # Pick best available Cerebras model
    try:
        # Get live model list
        model_resp = requests.get(
            "https://api.cerebras.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if model_resp.status_code == 200:
            available = [m['id'] for m in model_resp.json().get('data', [])]
            preferences = ['qwen-3-235b-a22b-instruct-2507', 'gpt-oss-120b',
                            'zai-glm-4.7', 'llama-3.3-70b', 'llama3.1-8b']
            model = next((m for m in preferences if m in available), available[0] if available else 'llama3.1-8b')
        else:
            model = 'llama3.1-8b'
    except Exception:
        model = 'llama3.1-8b'

    location_str = f"in {location}" if location else "across the United States"

    # Few-shot prompt — examples are FORMAT-only placeholders so the model
    # isn't biased toward horse businesses regardless of business_type.
    prompt = f"""List {max_results} REAL {business_type}s {location_str}. Output ONLY a JSON array — no other text.

Required format (start with [ and end with ]):
[
{{"name":"Real Business Name 1","city":"City","state":"ST","website":"example1.com"}},
{{"name":"Real Business Name 2","city":"City","state":"ST","website":"example2.com"}}
]

Continue with {max_results} REAL {business_type}s {location_str}. Use real, specific businesses you know about — not generic placeholders. Match the business type exactly.
Just the JSON array, no markdown fences:"""

    try:
        response = requests.post(
            "https://api.cerebras.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 4096,
                "temperature": 0.5,
            },
            timeout=90
        )

        if response.status_code != 200:
            return []

        data = response.json()
        content = data['choices'][0]['message']['content']

        # Strip markdown fences and any preamble before the array
        content = re.sub(r'^```(?:json)?\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)

        # Find the JSON array — model sometimes prefixes with explanation
        array_match = re.search(r'\[.*\]', content, re.DOTALL)
        if array_match:
            content = array_match.group(0)

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                for key in ['businesses', 'results', 'data', 'list']:
                    if key in parsed and isinstance(parsed[key], list):
                        parsed = parsed[key]
                        break
                else:
                    for v in parsed.values():
                        if isinstance(v, list):
                            parsed = v
                            break
        except json.JSONDecodeError:
            # Try line-by-line JSONL parsing as last resort
            parsed = []
            for line in content.split('\n'):
                line = line.strip().rstrip(',')
                if line.startswith('{') and line.endswith('}'):
                    try:
                        parsed.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not isinstance(parsed, list):
            return []

        results = []
        seen_domains = set()

        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = item.get('name', '')
            website = item.get('website', '')
            city = item.get('city', '')
            state = item.get('state', '')

            if not name or not website:
                continue

            # Normalize website
            if not website.startswith(('http://', 'https://')):
                website = 'https://' + website

            domain = _domain_of(website)
            if not domain or domain in seen_domains or _should_skip(website):
                continue
            seen_domains.add(domain)

            results.append({
                'url': website,
                'title': name,
                'snippet': f'{business_type} in {city}, {state}'.strip(),
                '_ai_known_city': city,
                '_ai_known_state': state,
            })

        return results

    except Exception as e:
        print(f"AI discovery error: {e}")
        return []


import json  # used by discover_via_ai_knowledge


def search_brave(query, max_results=20):
    """
    Search via Brave Search API (free tier: 2,000 queries/month).
    Requires user to add BRAVE_API_KEY to api_keys.
    """
    try:
        import api_keys
        api_key = api_keys.get_key('brave')
    except Exception:
        return []

    if not api_key:
        return []

    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code != 200:
            return []

        data = response.json()
        results = []
        seen_domains = set()

        for item in data.get('web', {}).get('results', []):
            url_match = item.get('url', '')
            if _should_skip(url_match):
                continue
            domain = _domain_of(url_match)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)

            results.append({
                'url': url_match,
                'title': item.get('title', domain)[:120],
                'snippet': item.get('description', '')[:200]
            })

        return results
    except Exception:
        return []


def search_google_scrape(query, max_results=20):
    """
    Scrape Google search results directly. Light volume only — Google may CAPTCHA.
    Used as backup when DDG is rate-limited.
    """
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={max_results * 2}&hl=en"

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code != 200:
            return []

        # Google's result links: <a href="/url?q=https://realsite.com&...">
        # Or sometimes: <a href="https://realsite.com">
        results = []
        seen_domains = set()

        # Pattern 1: /url?q= wrapper
        wrapped = re.findall(r'<a\s+href="/url\?q=([^&"]+)[^"]*"[^>]*>(.*?)</a>', response.text, re.DOTALL)
        # Pattern 2: direct link in result block
        direct = re.findall(r'<a\s+href="(https?://[^"]+)"\s+[^>]*data-ved', response.text, re.DOTALL)

        all_matches = wrapped + [(url, '') for url in direct]

        for match in all_matches:
            url_match = match[0] if isinstance(match, tuple) else match
            title = match[1] if isinstance(match, tuple) and len(match) > 1 else ''

            from urllib.parse import unquote
            url_match = unquote(url_match)

            if _should_skip(url_match):
                continue
            domain = _domain_of(url_match)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)

            title_clean = re.sub(r'<[^>]+>', '', title).strip()[:120] or domain

            results.append({
                'url': url_match,
                'title': title_clean,
                'snippet': ''
            })

            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"Google search error: {e}")
        return []


def search_bing(query, max_results=30):
    """Search Bing HTML interface (backup, no API key)."""
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count={max_results}"
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return []

        results = []
        seen_domains = set()

        # Bing has multiple HTML structures — try several patterns
        patterns = [
            # Standard b_algo result
            r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>.*?<a\s+href="([^"]+)"[^>]*>([^<]+)</a>(.*?)</li>',
            # H2 anchor pattern
            r'<h2[^>]*>\s*<a\s+href="(https?://[^"]+)"[^>]*>(.*?)</a>\s*</h2>',
            # Cite + anchor pattern
            r'<a\s+href="(https?://[^"]+)"[^>]*><h2[^>]*>(.*?)</h2></a>',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response.text, re.DOTALL)
            for match in matches:
                if len(match) >= 2:
                    url_match = match[0]
                    title = match[1]
                    rest = match[2] if len(match) > 2 else ''

                    if _should_skip(url_match):
                        continue
                    domain = _domain_of(url_match)
                    if not domain or domain in seen_domains:
                        continue
                    seen_domains.add(domain)

                    title_clean = re.sub(r'<[^>]+>', '', title).strip()[:120]
                    if not title_clean:
                        title_clean = domain

                    # Try to find snippet
                    snippet = ''
                    if rest:
                        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', rest, re.DOTALL)
                        if snippet_match:
                            snippet = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()[:200]

                    results.append({
                        'url': url_match,
                        'title': title_clean,
                        'snippet': snippet
                    })

                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break

        return results
    except Exception as e:
        print(f"Bing search error: {e}")
        return []


def scrape_yellowpages(business_type, location):
    """Scrape YellowPages.com listings — extracts real business websites."""
    if not location:
        location = "United States"
    url = f"https://www.yellowpages.com/search?search_terms={quote_plus(business_type)}&geo_location_terms={quote_plus(location)}"

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return []

        results = []
        seen_domains = set()

        # Multiple patterns YellowPages uses (their HTML changes)
        # Pattern 1: Direct website link with track-visit-website class
        # Pattern 2: Generic href to external sites
        patterns = [
            r'class="[^"]*track-visit-website[^"]*"[^>]*href="(https?://[^"]+)"[^>]*>([^<]*)',
            r'href="(https?://[^"]+)"\s+class="[^"]*track-visit-website',
            # Generic external link in business card
            r'<div[^>]*class="[^"]*info[^"]*"[^>]*>.*?href="(https?://(?!www\.yellowpages)[^"]+)"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response.text, re.DOTALL)
            for match in matches:
                url_match = match if isinstance(match, str) else match[0]
                title = match[1] if isinstance(match, tuple) and len(match) > 1 else ''

                if _should_skip(url_match):
                    continue
                domain = _domain_of(url_match)
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)

                results.append({
                    'url': url_match,
                    'title': title.strip() or domain,
                    'snippet': f'Listed on YellowPages as {business_type}'
                })

        return results
    except Exception as e:
        print(f"YellowPages error: {e}")
        return []


def scrape_manta(business_type, location, max_results=30):
    """Scrape Manta.com — business directory with company websites."""
    if not location:
        location = ""
    q = quote_plus(f"{business_type} {location}".strip())
    url = f"https://www.manta.com/search?search={q}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                         "Accept": "text/html"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        results = []
        seen_domains = set()
        # Manta business profile cards have website links and titles
        patterns = [
            r'<a[^>]+href="(https?://[^"]+)"[^>]+class="[^"]*business-website[^"]*"[^>]*>([^<]+)',
            r'<a[^>]+class="[^"]*website[^"]*"[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)',
            r'href="(https?://(?!(?:www\.)?manta\.com)[^"]+)"[^>]*>([A-Z][^<]{3,80})</a>',
        ]
        for pat in patterns:
            for m in re.findall(pat, r.text):
                u, t = (m, '') if isinstance(m, str) else (m[0], m[1] if len(m) > 1 else '')
                if _should_skip(u):
                    continue
                d = _domain_of(u)
                if not d or d in seen_domains:
                    continue
                seen_domains.add(d)
                results.append({'url': u, 'title': (t.strip() or d)[:80],
                                'snippet': f'Listed on Manta as {business_type}'})
                if len(results) >= max_results:
                    return results
        return results
    except Exception:
        return []


def scrape_bbb(business_type, location, max_results=30):
    """Scrape Better Business Bureau — listings include business websites."""
    if not location:
        location = "USA"
    q = quote_plus(business_type)
    loc = quote_plus(location)
    url = f"https://www.bbb.org/search?find_country=USA&find_text={q}&find_loc={loc}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                         "Accept": "text/html"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        results = []
        seen_domains = set()
        # BBB business profile cards link to /us/state/city/category/{slug} pages
        # which then link to the business's actual website
        profile_pattern = r'href="(https?://www\.bbb\.org/us/[^"]+)"'
        profiles = re.findall(profile_pattern, r.text)[:max_results]
        for prof_url in profiles[:max_results]:
            try:
                pr = requests.get(prof_url, headers={"User-Agent": USER_AGENT},
                                   timeout=REQUEST_TIMEOUT)
                if pr.status_code != 200:
                    continue
                # Extract business website from profile page
                m = re.search(r'href="(https?://(?!(?:www\.)?bbb\.org)[^"]+)"[^>]*>'
                              r'\s*(?:Visit\s+Website|Website)\s*<', pr.text)
                if not m:
                    m = re.search(r'<a[^>]+rel="[^"]*nofollow[^"]*"[^>]+'
                                  r'href="(https?://[^"]+)"', pr.text)
                if m:
                    u = m.group(1)
                    if _should_skip(u):
                        continue
                    d = _domain_of(u)
                    if not d or d in seen_domains:
                        continue
                    seen_domains.add(d)
                    # Extract business name from <title>
                    name_m = re.search(r'<title>([^<|]+)\s*[\|<]', pr.text)
                    name = (name_m.group(1).strip() if name_m else d)[:80]
                    results.append({'url': u, 'title': name,
                                    'snippet': f'BBB-listed {business_type}'})
                if len(results) >= max_results:
                    break
                time.sleep(0.3)
            except Exception:
                continue
        return results
    except Exception:
        return []


def scrape_superpages(business_type, location, max_results=30):
    """Scrape SuperPages.com — yellow pages alternative with direct websites."""
    if not location:
        location = "United States"
    q = quote_plus(business_type)
    loc = quote_plus(location)
    url = f"https://www.superpages.com/search?search_terms={q}&geo_location_terms={loc}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        results = []
        seen_domains = set()
        for m in re.findall(
            r'href="(https?://[^"]+)"[^>]+class="[^"]*website-link[^"]*"', r.text):
            if _should_skip(m):
                continue
            d = _domain_of(m)
            if not d or d in seen_domains:
                continue
            seen_domains.add(d)
            results.append({'url': m, 'title': d, 'snippet': f'SuperPages {business_type}'})
            if len(results) >= max_results:
                break
        # Generic external links if specific class didn't match
        if len(results) < 5:
            for m in re.findall(r'href="(https?://(?!(?:www\.)?superpages)[^"]+)"', r.text):
                if _should_skip(m):
                    continue
                d = _domain_of(m)
                if not d or d in seen_domains:
                    continue
                seen_domains.add(d)
                results.append({'url': m, 'title': d, 'snippet': f'SuperPages {business_type}'})
                if len(results) >= max_results:
                    break
        return results
    except Exception:
        return []


# ============================================================================
# REGULATORY / GOVERNMENT DATA SOURCES (the Industrial Intelligence Layer)
# These query free public datasets to find operationally-active facilities.
# ============================================================================
def scrape_usda_aphis(business_type, location, max_results=30):
    """USDA APHIS Animal Care licensees — kennels, breeders, exhibitors,
    research facilities. Public regulatory data. Gold for Pets + equine breeders."""
    if not _is_animal_related(business_type):
        return []
    # APHIS publishes annual licensee lists as PDFs/CSVs; scraping their search UI
    # is unstable. Best approach: hit their inspection-results search which DOES
    # surface licensee names + states.
    state_code = _extract_state_code(location)
    if not state_code:
        return []
    url = ("https://acis.aphis.edc.usda.gov/ords/f?p=118:201::::::"
           f"P201_STATE:{state_code}")
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        results = []
        seen = set()
        # Licensee table rows have entity name in <td>
        for m in re.findall(r'<td[^>]*>([A-Z][A-Z0-9 .,&\'/-]{4,80})</td>', r.text):
            name = m.strip()
            if name in seen or len(name) < 5:
                continue
            seen.add(name)
            results.append({
                'url': f"https://www.google.com/search?q={quote_plus(name + ' ' + state_code)}",
                'title': name,
                'snippet': f'USDA APHIS Animal Care licensee in {state_code}',
                'requires_website_lookup': True,
                'tags': ['REGULATED', 'ANIMAL_FACILITY'],
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def scrape_epa_envirofacts(business_type, location, max_results=30):
    """EPA EnviroFacts — public REST API for facilities under EPA regulation.
    Datasets used:
    - RCRAINFO: hazardous waste generators (ideal for SpillMaster prospects)
    - PCS: water/wastewater permit holders (ideal for SpillMaster + Inversion Misting)
    """
    state_code = _extract_state_code(location) or 'US'
    facilities = []
    seen_names = set()
    burden_tags = []

    # RCRAINFO — hazardous waste generators
    if _is_industrial_type(business_type):
        try:
            rurl = (f"https://data.epa.gov/efservice/RCR_HD_HANDLER/"
                    f"LOCATION_STATE/=/{state_code}/JSON")
            r = requests.get(rurl, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                for f in r.json()[:max_results // 2]:
                    name = f.get('HD_HANDLER_NAME') or ''
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    city = f.get('LOCATION_CITY') or ''
                    facilities.append({
                        'url': f"https://www.google.com/search?q={quote_plus(name + ' ' + city + ' ' + state_code)}",
                        'title': name.title()[:80],
                        'snippet': f'EPA RCRA hazardous waste generator in {city}, {state_code}',
                        'requires_website_lookup': True,
                        'tags': ['EPA_REGULATED', 'HAZMAT', 'INDUSTRIAL_CLEANING'],
                        'burden': ['MICROBIAL_RISK', 'RUNOFF_RISK'],
                    })
        except Exception:
            pass

    # PCS — water permit holders (NPDES wastewater)
    if _is_water_or_industrial_type(business_type):
        try:
            wurl = (f"https://data.epa.gov/efservice/PCS_PERMIT_FACILITY/"
                    f"STATE_CODE/=/{state_code}/JSON")
            r = requests.get(wurl, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                for f in r.json()[:max_results // 2]:
                    name = f.get('FACILITY_NAME') or ''
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)
                    city = f.get('CITY_NAME') or ''
                    facilities.append({
                        'url': f"https://www.google.com/search?q={quote_plus(name + ' ' + city + ' ' + state_code)}",
                        'title': name.title()[:80],
                        'snippet': f'NPDES wastewater permit holder in {city}, {state_code}',
                        'requires_website_lookup': True,
                        'tags': ['EPA_REGULATED', 'WASTEWATER'],
                        'burden': ['MICROBIAL_RISK', 'AMMONIA_RISK', 'RUNOFF_RISK'],
                    })
        except Exception:
            pass

    return facilities[:max_results]


def scrape_fmcsa_safer(business_type, location, max_results=30):
    """FMCSA SAFER — every registered motor carrier in the US. Gold for AMR
    (trucking, bus, fleets, hazmat haulers)."""
    if not _is_fleet_related(business_type):
        return []
    # FMCSA QC by name search
    state_code = _extract_state_code(location)
    q = quote_plus(business_type)
    url = ("https://safer.fmcsa.dot.gov/keywordx.asp?searchstring="
           f"{q}&SEARCHTYPE=name")
    try:
        r = requests.post(
            "https://safer.fmcsa.dot.gov/keywordx.asp",
            data={
                'searchstring': business_type,
                'SEARCHTYPE': 'name',
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return []
        results = []
        seen = set()
        for m in re.findall(
            r'<a[^>]+href="[^"]*pkg_carrquery[^"]*"[^>]*>([^<]{3,80})</a>',
            r.text):
            name = m.strip()
            if name in seen or len(name) < 4:
                continue
            seen.add(name)
            results.append({
                'url': f"https://www.google.com/search?q={quote_plus(name)}",
                'title': name,
                'snippet': f'FMCSA-registered motor carrier ({business_type})',
                'requires_website_lookup': True,
                'tags': ['DOT_REGULATED', 'FLEET'],
                'burden': ['SANITATION_INTENSITY', 'INTERIOR_ODOR'],
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def search_reddit(business_type, location, max_results=20):
    """Reddit public JSON search — finds owner self-promo posts mentioning
    the business type + location."""
    q_parts = [business_type]
    if location:
        q_parts.append(location)
    q = quote_plus(' '.join(q_parts))
    url = (f"https://www.reddit.com/search.json?q={q}&sort=relevance&t=year"
           f"&limit={min(max_results, 100)}")
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT + " AqueLystOS/1.0"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        seen_domains = set()
        for child in data.get('data', {}).get('children', []):
            post = child.get('data', {})
            link = post.get('url_overridden_by_dest') or post.get('url') or ''
            title = post.get('title', '')[:80]
            if not link or 'reddit.com' in link:
                continue
            if _should_skip(link):
                continue
            d = _domain_of(link)
            if not d or d in seen_domains:
                continue
            seen_domains.add(d)
            results.append({
                'url': link,
                'title': title or d,
                'snippet': f'Reddit r/{post.get("subreddit", "?")}: '
                           f'{title[:80]}',
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


# ----------------------------------------------------------------------------
# Helpers used by the regulatory scrapers above
# ----------------------------------------------------------------------------
def _extract_state_code(location):
    """Pull a 2-letter US state code from a location string."""
    if not location:
        return None
    upper = location.upper()
    m = re.search(r'\b([A-Z]{2})\b', upper)
    if m:
        return m.group(1)
    state_names = {
        'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR',
        'CALIFORNIA': 'CA', 'COLORADO': 'CO', 'CONNECTICUT': 'CT',
        'DELAWARE': 'DE', 'FLORIDA': 'FL', 'GEORGIA': 'GA', 'HAWAII': 'HI',
        'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA',
        'KANSAS': 'KS', 'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME',
        'MARYLAND': 'MD', 'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI',
        'MINNESOTA': 'MN', 'MISSISSIPPI': 'MS', 'MISSOURI': 'MO',
        'MONTANA': 'MT', 'NEBRASKA': 'NE', 'NEVADA': 'NV',
        'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM',
        'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND',
        'OHIO': 'OH', 'OKLAHOMA': 'OK', 'OREGON': 'OR', 'PENNSYLVANIA': 'PA',
        'RHODE ISLAND': 'RI', 'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD',
        'TENNESSEE': 'TN', 'TEXAS': 'TX', 'UTAH': 'UT', 'VERMONT': 'VT',
        'VIRGINIA': 'VA', 'WASHINGTON': 'WA', 'WEST VIRGINIA': 'WV',
        'WISCONSIN': 'WI', 'WYOMING': 'WY',
    }
    for name, code in state_names.items():
        if name in upper:
            return code
    return None


def _is_animal_related(business_type):
    if not business_type:
        return False
    t = business_type.lower()
    return any(k in t for k in [
        'kennel', 'animal', 'pet', 'horse', 'equine', 'breeder',
        'shelter', 'humane', 'vet', 'zoo', 'rescue', 'boarding',
        'cattle', 'dairy', 'poultry', 'swine', 'hog', 'sheep', 'goat',
        'livestock', 'farm',
    ])


def _is_industrial_type(business_type):
    if not business_type:
        return False
    t = business_type.lower()
    return any(k in t for k in [
        'industrial', 'manufacturing', 'factory', 'plant', 'processing',
        'chemical', 'hazmat', 'cleanup', 'food processing', 'meat',
        'dairy processing', 'brewery', 'rendering', 'recycling',
        'waste', 'remediation', 'crematorium', 'mortuary',
    ])


def _is_water_or_industrial_type(business_type):
    if not business_type:
        return False
    t = business_type.lower()
    return _is_industrial_type(business_type) or any(k in t for k in [
        'wastewater', 'water treatment', 'sewage', 'dairy', 'poultry',
        'feedlot', 'hog', 'swine', 'cafo', 'pulp', 'paper',
    ])


def _is_fleet_related(business_type):
    if not business_type:
        return False
    t = business_type.lower()
    return any(k in t for k in [
        'trucking', 'truck', 'fleet', 'bus', 'taxi', 'limo', 'rideshare',
        'transit', 'delivery', 'rv', 'recreational vehicle', 'moving',
        'rental car', 'transport', 'school bus', 'shuttle', 'freight',
        'haul', 'amazon delivery',
    ])


def scrape_yelp(business_type, location, max_results=20):
    """Scrape Yelp search results.
    Yelp doesn't surface direct business websites in search HTML — it surfaces
    Yelp profile URLs. We follow each profile to extract the actual website.
    Quality is high (vetted businesses with reviews). Slower than other sources."""
    if not location:
        location = "United States"
    q = quote_plus(business_type)
    loc = quote_plus(location)
    url = f"https://www.yelp.com/search?find_desc={q}&find_loc={loc}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                         "Accept": "text/html"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        # Extract /biz/{slug} profile URLs from search results
        profile_slugs = list(set(re.findall(r'href="(/biz/[^"?]+)"', r.text)))[:max_results]
        results = []
        seen_domains = set()
        for slug in profile_slugs:
            try:
                pr = requests.get(f"https://www.yelp.com{slug}",
                                   headers={"User-Agent": USER_AGENT},
                                   timeout=REQUEST_TIMEOUT)
                if pr.status_code != 200:
                    continue
                # Yelp's "Business website" link
                m = re.search(
                    r'<a[^>]+href="(https?://(?!(?:www\.)?yelp\.com)[^"]+)"[^>]*>'
                    r'\s*[a-zA-Z0-9.-]+\.(?:com|net|org|co|us|biz|info|farm)\b',
                    pr.text)
                if not m:
                    m = re.search(
                        r'class="[^"]*biz-website[^"]*"[^>]*href="([^"]+)"', pr.text)
                if not m:
                    continue
                u = m.group(1)
                # Yelp redirects through biz_redir; extract the actual url query param
                redir_m = re.search(r'url=([^&]+)', u)
                if redir_m:
                    from urllib.parse import unquote
                    u = unquote(redir_m.group(1))
                if not u.startswith('http'):
                    continue
                if _should_skip(u):
                    continue
                d = _domain_of(u)
                if not d or d in seen_domains:
                    continue
                seen_domains.add(d)
                # Extract name from <title>
                name_m = re.search(r'<title>([^<|]+)\s*[\|<]', pr.text)
                name = (name_m.group(1).strip() if name_m else d)[:80]
                results.append({'url': u, 'title': name,
                                'snippet': f'Yelp-listed {business_type}'})
                time.sleep(0.4)
                if len(results) >= max_results:
                    break
            except Exception:
                continue
        return results
    except Exception:
        return []


def search_foursquare(business_type, location, max_results=30):
    """Foursquare Places API (free tier 50 calls/day, paid scales up).
    Requires user-provided API key in Setup → API Keys → Foursquare."""
    try:
        import api_keys as _ak
        api_key = _ak.get_key('foursquare')
    except Exception:
        api_key = None
    if not api_key:
        return []
    try:
        params = {
            'query': business_type,
            'limit': min(max_results, 50),
        }
        if location:
            params['near'] = location
        r = requests.get(
            "https://api.foursquare.com/v3/places/search",
            params=params,
            headers={
                "Authorization": api_key,
                "Accept": "application/json",
            },
            timeout=15,
        )
        if r.status_code != 200:
            return []
        results = []
        seen_domains = set()
        for place in r.json().get('results', []):
            website = place.get('website') or ''
            if not website:
                continue
            if not website.startswith('http'):
                website = 'https://' + website
            if _should_skip(website):
                continue
            d = _domain_of(website)
            if not d or d in seen_domains:
                continue
            seen_domains.add(d)
            name = place.get('name', d)[:80]
            results.append({
                'url': website,
                'title': name,
                'snippet': f'Foursquare {business_type} in '
                           f'{place.get("location", {}).get("locality", location or "")}',
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def scrape_opencorporates(business_type, location, max_results=20):
    """Scrape OpenCorporates — public business registry.
    Returns company names + states for follow-up website discovery (no direct URLs)."""
    q = quote_plus(business_type)
    if location:
        loc_param = quote_plus(location)
        url = f"https://opencorporates.com/companies?q={q}&jurisdiction_code=us&utf8=%E2%9C%93&commit=Go&place={loc_param}"
    else:
        url = f"https://opencorporates.com/companies?q={q}&jurisdiction_code=us&utf8=%E2%9C%93&commit=Go"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT,
                                         "Accept": "text/html"},
                          timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        # Company names are listed in /companies/us_xx/ links
        results = []
        seen_names = set()
        for m in re.findall(
            r'<a[^>]+href="/companies/us_[a-z]+/[^"]+"[^>]*>([^<]+)</a>', r.text):
            name = m.strip()
            if len(name) < 3 or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            # Build a search-style "candidate" — autopilot's discovery layer
            # will do a website lookup based on the name
            results.append({
                'url': f"https://www.google.com/search?q={quote_plus(name)}",
                'title': name,
                'snippet': f'OpenCorporates US registry: {business_type}',
                'requires_website_lookup': True,
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


def scrape_merchantcircle(business_type, location, max_results=30):
    """Scrape MerchantCircle.com — small business directory."""
    if not location:
        location = ""
    q = quote_plus(f"{business_type} {location}".strip())
    url = f"https://www.merchantcircle.com/search.html?qs={q}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return []
        results = []
        seen_domains = set()
        for m in re.findall(
            r'href="(https?://(?!(?:www\.)?merchantcircle)[^"]+)"[^>]*>([^<]{3,80})</a>',
            r.text):
            u, t = m[0], m[1].strip()
            if _should_skip(u):
                continue
            d = _domain_of(u)
            if not d or d in seen_domains:
                continue
            seen_domains.add(d)
            results.append({'url': u, 'title': t or d,
                            'snippet': f'MerchantCircle {business_type}'})
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


# ============================================================================
# Per-vertical industry directories — high-quality, niche-specific lists
# ============================================================================
INDUSTRY_DIRECTORIES = {
    'Duo Equine': [
        'https://www.equinenow.com/horsefarms.htm',
        'https://www.usef.org/find-recognized-competitions',
        'https://www.aqha.com/aqha-find-horse-show',
        'https://www.usdf.org/about/about-the-sport/where-to-ride.asp',
    ],
    'Pets': [
        'https://www.aaha.org/aaha-accreditation/find-an-aaha-hospital/',
        'https://www.petsithq.com/directory',
        'https://www.ibpsa.com/find-a-pet-care-business',
        'https://www.petfinder.com/animal-shelters-and-rescues/search/',
    ],
    'SpillMaster': [
        'https://www.issa.com/find-a-member',
        'https://www.iicrc.org/locator/showmap.php',
        'https://www.restorationindustry.org/page/MemberDirectory',
        'https://www.crcl-online.com/cleaning-companies-directory',
    ],
    'AMR': [
        'https://www.nada.org/dealer-search',
        'https://www.rvda.org/find-a-rv-dealer',
        'https://www.nmma.org/marina-finder',
        'https://www.gomarinas.com',
    ],
    'HouseHold': [
        'https://www.armaclean.org/find-a-cleaning-company',
        'https://homecouncil.org/find-a-cleaner',
        'https://www.iicrc.org/locator/showmap.php',
    ],
    'Inversion Misting': [
        'https://www.uspoultry.org/membership/find-a-member',
        'https://www.nationaldairy.org/find-a-dairy',
        'https://www.pork.org/farms-near-me',
        'https://www.beefusa.org/find-a-cattle-rancher',
    ],
}


def discover_via_industry_directories(product_fit, max_results=30):
    """Scrape niche industry directories specific to a product line.
    Returns business website URLs found on association/regulator pages."""
    if not product_fit or product_fit not in INDUSTRY_DIRECTORIES:
        return []
    results = []
    seen_domains = set()
    for directory_url in INDUSTRY_DIRECTORIES[product_fit]:
        try:
            r = requests.get(directory_url,
                              headers={"User-Agent": USER_AGENT},
                              timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                continue
            # Generic external-link extraction
            for u in re.findall(r'href="(https?://[^"]+)"', r.text):
                if _should_skip(u):
                    continue
                d = _domain_of(u)
                if not d or d in seen_domains:
                    continue
                # Skip the directory site itself
                if d in directory_url:
                    continue
                seen_domains.add(d)
                results.append({'url': u, 'title': d,
                                'snippet': f'{product_fit} industry directory'})
                if len(results) >= max_results:
                    return results
            time.sleep(0.5)
        except Exception:
            continue
    return results


def scrape_equine_directory(directory_url):
    """Scrape an equine industry directory for member businesses."""
    try:
        response = requests.get(
            directory_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return []

        # Pull all outbound links that look like business sites
        # Skip social media, common platforms
        link_matches = re.findall(r'href="(https?://[^"]+)"[^>]*>([^<]*)</a>', response.text)

        results = []
        seen_domains = set()
        for url_match, title in link_matches:
            if _should_skip(url_match):
                continue
            domain = _domain_of(url_match)
            if not domain or domain in seen_domains:
                continue
            # Skip the directory itself
            if domain in directory_url:
                continue
            seen_domains.add(domain)

            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            if not clean_title or len(clean_title) < 3:
                clean_title = domain

            results.append({
                'url': url_match,
                'title': clean_title,
                'snippet': f'Listed in equine industry directory'
            })

        return results[:30]
    except Exception:
        return []


# Curated equine directories (free public listings)
EQUINE_DIRECTORIES = [
    "https://horsefinders.com/category/horse-boarding/",
    "https://horsefinders.com/category/equestrian-centers/",
    "https://horsefinders.com/category/horse-trainers/",
    "https://www.equinehits.com/horse-boarding/",
    "https://www.equinehits.com/horse-training/",
]


def _generate_query_variations(business_type, location):
    """Generate many query variations to maximize discovery coverage."""
    location_part = f" {location}" if location else ""
    type_singular = business_type.rstrip('s') if business_type.endswith('s') else business_type

    queries = [
        # Direct
        f"{business_type}{location_part}",
        f"{type_singular}{location_part}",
        f"\"{business_type}\"{location_part}",
        # With contact intent
        f"{business_type}{location_part} contact owner",
        f"{business_type}{location_part} phone email",
        # Local-business-style
        f"best {business_type}{location_part}",
        f"top {business_type}{location_part}",
        # Site-restricted (catches business directories)
        f"{business_type}{location_part} site:.com",
        # Regional variations
        f"{business_type} near{location_part}" if location else f"{business_type} near me",
        # Long-tail
        f"{business_type}{location_part} family owned",
        f"{business_type}{location_part} private",
    ]

    # Vertical-aware synonyms: only add equestrian terms for actual equine
    # business types — for "oil refinery" / "kennel" / "warehouse" etc. these
    # would just pollute the results with unrelated horse stuff.
    product = _guess_product_from_type(business_type)
    if product == 'Duo Equine':
        queries.extend([
            f"barn{location_part} {business_type}",
            f"equestrian{location_part} {type_singular}",
            f"horse facility{location_part}",
        ])
    elif product == 'Pets':
        queries.extend([
            f"animal{location_part} {business_type}",
            f"pet care{location_part} {type_singular}",
        ])
    elif product == 'SpillMaster':
        queries.extend([
            f"industrial{location_part} {business_type}",
            f"commercial{location_part} {type_singular}",
        ])
    elif product == 'AMR':
        queries.extend([
            f"fleet{location_part} {business_type}",
            f"dealership{location_part} {type_singular}",
        ])
    elif product == 'HouseHold':
        queries.extend([
            f"residential{location_part} {business_type}",
            f"property{location_part} {type_singular}",
        ])
    elif product == 'Inversion Misting':
        queries.extend([
            f"agricultural{location_part} {business_type}",
            f"farm operation{location_part} {type_singular}",
        ])
    return queries


def _guess_product_from_type(business_type):
    """Map a hunt-category business_type string to its product line."""
    if not business_type:
        return None
    t = business_type.lower()
    EQUINE = ['horse', 'equestrian', 'equine', 'stable', 'thoroughbred', 'standardbred',
              'polo', 'rodeo', 'dressage', 'trail riding', 'pony', 'tack', 'feed store',
              'mule', 'donkey', 'racing', 'racetrack', 'breeder', 'hunter jumper',
              'foxhunting', 'carriage', 'mounted police']
    PETS = ['kennel', 'doggy daycare', 'dog boarding', 'cat boarding', 'pet hotel',
             'animal shelter', 'humane society', 'rescue', 'veterinary', 'vet ',
             'grooming', 'pet store', 'dog park', 'pet daycare', 'spay neuter',
             'animal control', 'guide dog', 'k9', 'aquarium store', 'reptile']
    SPILL = ['waste management', 'industrial cleanup', 'hazmat', 'environmental',
              'biohazard', 'crime scene', 'food processing', 'meat processing',
              'dairy processing', 'brewery', 'winery', 'distillery', 'commercial kitchen',
              'catering', 'hospital', 'nursing home', 'assisted living', 'urgent care',
              'manufacturing', 'chemical', 'recycling', 'composting', 'water treatment',
              'sewage', 'landfill', 'public transit', 'correctional', 'jail',
              'pharmaceutical', 'biotech', 'laboratory', 'medical', 'school district',
              'university food', 'mortuary', 'funeral', 'crematorium', 'casino',
              'convention', 'stadium', 'hotel chain', 'food storage', 'cold storage']
    AMR = ['rv ', ' rv', 'marina', 'yacht', 'boat', 'car dealer', 'auto detail',
           'car wash', 'rideshare', 'limo', 'taxi', 'bus transit', 'school bus',
           'truck stop', 'trucking', 'delivery fleet', 'moving company', 'rental car',
           'powersports', 'motorcycle', 'aviation', 'jet operator', 'fbo',
           'truck dealer', 'used car', 'auto body', 'restoration shop', 'tow truck',
           'food truck', 'parking', 'amazon delivery', 'campground']
    HOUSEHOLD = ['property management', 'airbnb cleaning', 'vacation rental',
                  'apartment complex', 'condo', 'senior living', 'house cleaning',
                  'maid service', 'janitorial', 'commercial cleaning', 'mold remediation',
                  'water damage restoration', 'fire damage', 'odor remediation',
                  'pet odor', 'pest control', 'carpet cleaning', 'duct cleaning',
                  'crawl space', 'window cleaning', 'pressure washing', 'real estate',
                  'home inspector', 'hoa', 'student housing', 'group home']
    INVERSION = ['warehouse distribution', 'cold storage', 'food storage warehouse',
                  'large manufacturing', 'agricultural processing', 'meat locker',
                  'rendering plant', 'pet food manufacturer', 'animal feed manufacturer',
                  'grain elevator', 'silo', 'ethanol', 'biodiesel', 'composting site',
                  'agricultural fairground', 'livestock auction', 'poultry farm',
                  'broiler farm', 'layer hen', 'turkey farm', 'duck farm',
                  'dairy farm', 'goat dairy', 'sheep farm', 'swine', 'hog farm',
                  'feedlot', 'cattle ranch', 'beef cattle', 'aquaculture', 'fish farm',
                  'commercial greenhouse', 'commercial nursery', 'cannabis cultivation',
                  'large indoor equestrian', 'dairy parlor']
    if any(k in t for k in INVERSION):
        return 'Inversion Misting'
    if any(k in t for k in AMR):
        return 'AMR'
    if any(k in t for k in PETS):
        return 'Pets'
    if any(k in t for k in SPILL):
        return 'SpillMaster'
    if any(k in t for k in HOUSEHOLD):
        return 'HouseHold'
    if any(k in t for k in EQUINE):
        return 'Duo Equine'
    return None


def discover_horse_businesses(business_type, location=None, max_results=20, on_progress=None):
    """
    AGGRESSIVELY discover horse businesses from many sources:
    - DuckDuckGo HTML (10+ query variations)
    - Bing HTML (multiple queries)
    - YellowPages directory
    - Equine industry directories
    - Per-city expansion (if no city specified, hits multiple cities in state)

    on_progress: optional callback(source_name, detail_msg)
    Returns list of candidates: [{url, title, snippet, source}, ...]
    """
    all_candidates = []
    seen_urls = set()
    seen_domains = set()

    def add_candidate(c, source):
        domain = _domain_of(c['url'])
        if c['url'] in seen_urls or (domain and domain in seen_domains):
            return False
        seen_urls.add(c['url'])
        if domain:
            seen_domains.add(domain)
        c['source'] = source
        c['source_query'] = c.get('source_query', source)
        all_candidates.append(c)
        return True

    queries = _generate_query_variations(business_type, location)

    # ===== SOURCE 0: OpenStreetMap (UNLIMITED, FREE, KING) =====
    if on_progress:
        on_progress("OpenStreetMap", f"querying global database for {business_type}")
    try:
        osm_results = discover_via_openstreetmap(business_type, location, max_results=max_results * 2)
        added = 0
        for r in osm_results:
            if add_candidate(r, "OpenStreetMap"):
                added += 1
        if on_progress:
            on_progress("OpenStreetMap", f"+{added} businesses from OSM (with phone/email metadata)")
    except Exception as e:
        if on_progress:
            on_progress("OpenStreetMap", f"failed: {str(e)[:50]}")

    # ===== SOURCE 0b: AI Cache (accumulated from prior runs — instant) =====
    cached = get_cached_ai_results(business_type, location)
    if cached:
        if on_progress:
            on_progress("AI Cache", f"loading {len(cached)} previously-discovered businesses")
        added = 0
        for r in cached:
            if add_candidate(r, "AI Cache"):
                added += 1
        if on_progress:
            on_progress("AI Cache", f"+{added} from cache")

    # ===== SOURCE 1: Cerebras AI Knowledge (live generation) =====
    if len(all_candidates) < max_results:
        if on_progress:
            on_progress("Cerebras AI", f"asking AI for real {business_type}s")
        try:
            ai_results = discover_via_ai_knowledge(business_type, location, max_results=max_results)
            added = 0
            new_ai_results = []
            for r in ai_results:
                if add_candidate(r, "AI Knowledge"):
                    added += 1
                    new_ai_results.append(r)
            if on_progress:
                on_progress("Cerebras AI", f"+{added} businesses from AI memory")

            # Persist newly-discovered to cache for future runs
            if new_ai_results:
                cache_ai_results(business_type, location, new_ai_results)
        except Exception as e:
            if on_progress:
                on_progress("Cerebras AI", f"failed: {str(e)[:50]}")

    # ===== SOURCE 0b: Brave Search API (if user provided key — best quality) =====
    try:
        import api_keys as _ak
        if _ak.has_key('brave'):
            for q in queries[:5]:
                if on_progress:
                    on_progress("Brave Search", f"query: {q[:50]}")
                results = search_brave(q, max_results=20)
                added = 0
                for r in results:
                    if add_candidate(r, "Brave Search"):
                        added += 1
                if on_progress:
                    on_progress("Brave Search", f"+{added} new (total: {len(all_candidates)})")
                time.sleep(0.3)
                if len(all_candidates) >= max_results * 2:
                    break
    except Exception:
        pass

    # ===== SOURCE 1: SearXNG (meta-search, usually not blocked) =====
    if len(all_candidates) < max_results:
        for q in queries[:6]:
            if on_progress:
                on_progress("SearXNG (meta)", f"query: {q[:50]}")
            results = search_searxng(q, max_results=20)
            added = 0
            for r in results:
                if add_candidate(r, "SearXNG"):
                    added += 1
            if on_progress:
                on_progress("SearXNG (meta)", f"+{added} new (total: {len(all_candidates)})")
            time.sleep(POLITE_DELAY)
            if len(all_candidates) >= max_results * 2:
                break

    # ===== SOURCE 2: DuckDuckGo (may rate-limit) =====
    if len(all_candidates) < max_results:
        for q in queries[:5]:
            if on_progress:
                on_progress("DuckDuckGo", f"query: {q[:50]}")
            results = search_duckduckgo(q, max_results=20)
            added = 0
            for r in results:
                if add_candidate(r, "DuckDuckGo"):
                    added += 1
            if on_progress:
                on_progress("DuckDuckGo", f"+{added} new (total: {len(all_candidates)})")
            time.sleep(POLITE_DELAY)
            if len(all_candidates) >= max_results * 2:
                break

    # ===== SOURCE 2: Bing (catches what DDG misses) =====
    if len(all_candidates) < max_results * 1.5:
        for q in queries[:5]:
            if on_progress:
                on_progress("Bing", f"query: {q[:50]}")
            results = search_bing(q, max_results=20)
            added = 0
            for r in results:
                if add_candidate(r, "Bing"):
                    added += 1
            if on_progress:
                on_progress("Bing", f"+{added} new (total: {len(all_candidates)})")
            time.sleep(POLITE_DELAY)
            if len(all_candidates) >= max_results * 2:
                break

    # ===== SOURCE 2b: Google (when others come up dry) =====
    if len(all_candidates) < max_results // 2:
        for q in queries[:3]:
            if on_progress:
                on_progress("Google", f"query: {q[:50]}")
            results = search_google_scrape(q, max_results=20)
            added = 0
            for r in results:
                if add_candidate(r, "Google"):
                    added += 1
            if on_progress:
                on_progress("Google", f"+{added} new (total: {len(all_candidates)})")
            time.sleep(POLITE_DELAY * 2)  # Be especially polite to Google
            if len(all_candidates) >= max_results:
                break

    # ===== SOURCE 3: YellowPages =====
    if on_progress:
        on_progress("YellowPages", f"scraping {business_type} in {location or 'US'}")
    try:
        yp_results = scrape_yellowpages(business_type, location)
        added = 0
        for r in yp_results:
            if add_candidate(r, "YellowPages"):
                added += 1
        if on_progress:
            on_progress("YellowPages", f"+{added} new (total: {len(all_candidates)})")
    except Exception as e:
        if on_progress:
            on_progress("YellowPages", f"failed: {str(e)[:50]}")
    time.sleep(POLITE_DELAY)

    # ===== SOURCE 3b: Manta business directory =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("Manta", f"scraping {business_type}")
        try:
            for r in scrape_manta(business_type, location, max_results=30):
                add_candidate(r, "Manta")
            if on_progress:
                on_progress("Manta", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("Manta", f"failed: {str(e)[:40]}")
        time.sleep(POLITE_DELAY)

    # ===== SOURCE 3c: Better Business Bureau =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("BBB", f"scraping BBB-listed {business_type}")
        try:
            for r in scrape_bbb(business_type, location, max_results=20):
                add_candidate(r, "BBB")
            if on_progress:
                on_progress("BBB", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("BBB", f"failed: {str(e)[:40]}")
        time.sleep(POLITE_DELAY)

    # ===== SOURCE 3d: SuperPages =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("SuperPages", f"scraping {business_type}")
        try:
            for r in scrape_superpages(business_type, location, max_results=30):
                add_candidate(r, "SuperPages")
            if on_progress:
                on_progress("SuperPages", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("SuperPages", f"failed: {str(e)[:40]}")
        time.sleep(POLITE_DELAY)

    # ===== SOURCE 3e: MerchantCircle =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("MerchantCircle", f"scraping {business_type}")
        try:
            for r in scrape_merchantcircle(business_type, location, max_results=30):
                add_candidate(r, "MerchantCircle")
            if on_progress:
                on_progress("MerchantCircle", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("MerchantCircle", f"failed: {str(e)[:40]}")
        time.sleep(POLITE_DELAY)

    # ===== SOURCE 3g: Yelp (slower but high signal) =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("Yelp", f"scraping vetted {business_type}s")
        try:
            for r in scrape_yelp(business_type, location, max_results=20):
                add_candidate(r, "Yelp")
            if on_progress:
                on_progress("Yelp", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("Yelp", f"failed: {str(e)[:40]}")

    # ===== SOURCE 3h: Foursquare Places API (if user has key) =====
    try:
        import api_keys as _ak
        if _ak.has_key('foursquare'):
            if on_progress:
                on_progress("Foursquare", f"querying Places API for {business_type}")
            for r in search_foursquare(business_type, location, max_results=30):
                add_candidate(r, "Foursquare")
            if on_progress:
                on_progress("Foursquare", f"total now: {len(all_candidates)}")
    except Exception as e:
        if on_progress:
            on_progress("Foursquare", f"failed: {str(e)[:40]}")

    # ===== SOURCE 3i: OpenCorporates (public US business registry) =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("OpenCorporates", f"public business registry for {business_type}")
        try:
            for r in scrape_opencorporates(business_type, location, max_results=20):
                add_candidate(r, "OpenCorporates")
            if on_progress:
                on_progress("OpenCorporates", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("OpenCorporates", f"failed: {str(e)[:40]}")

    # ===== SOURCE 4a: USDA APHIS Animal Care licensees =====
    if _is_animal_related(business_type):
        if on_progress:
            on_progress("USDA APHIS", f"federally-licensed animal facilities")
        try:
            for r in scrape_usda_aphis(business_type, location, max_results=30):
                add_candidate(r, "USDA APHIS")
            if on_progress:
                on_progress("USDA APHIS", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("USDA APHIS", f"failed: {str(e)[:40]}")

    # ===== SOURCE 4b: EPA EnviroFacts (RCRA + NPDES) =====
    if _is_industrial_type(business_type) or _is_water_or_industrial_type(business_type):
        if on_progress:
            on_progress("EPA EnviroFacts", f"hazmat + wastewater permit holders")
        try:
            for r in scrape_epa_envirofacts(business_type, location, max_results=30):
                add_candidate(r, "EPA EnviroFacts")
            if on_progress:
                on_progress("EPA EnviroFacts", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("EPA EnviroFacts", f"failed: {str(e)[:40]}")

    # ===== SOURCE 4c: FMCSA SAFER (motor carriers — fleets) =====
    if _is_fleet_related(business_type):
        if on_progress:
            on_progress("FMCSA SAFER", f"DOT-registered motor carriers")
        try:
            for r in scrape_fmcsa_safer(business_type, location, max_results=30):
                add_candidate(r, "FMCSA SAFER")
            if on_progress:
                on_progress("FMCSA SAFER", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("FMCSA SAFER", f"failed: {str(e)[:40]}")

    # ===== SOURCE 4d: Reddit (owner self-promotion posts) =====
    if len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("Reddit", f"public posts mentioning {business_type}")
        try:
            for r in search_reddit(business_type, location, max_results=20):
                add_candidate(r, "Reddit")
            if on_progress:
                on_progress("Reddit", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("Reddit", f"failed: {str(e)[:40]}")

    # ===== SOURCE 3f: Vertical-aware industry directories =====
    # Map business_type → product fit, then pull from the right industry pack
    product_for_type = _guess_product_from_type(business_type)
    if product_for_type and len(all_candidates) < max_results * 2:
        if on_progress:
            on_progress("Industry directories",
                         f"scraping {product_for_type} associations & regulators")
        try:
            for r in discover_via_industry_directories(product_for_type, max_results=40):
                add_candidate(r, f"{product_for_type} industry directory")
            if on_progress:
                on_progress("Industry directories", f"total now: {len(all_candidates)}")
        except Exception as e:
            if on_progress:
                on_progress("Industry directories", f"failed: {str(e)[:40]}")

    # ===== SOURCE 4: Equine industry directories — ONLY for equine business types =====
    # Critical: this used to fire for every hunt, polluting non-equine searches
    # (memory care, kennels, marinas, etc.) with unrelated horse business URLs.
    if product_for_type == 'Duo Equine':
        for directory_url in EQUINE_DIRECTORIES:
            if on_progress:
                on_progress("Equine Directory", urlparse(directory_url).netloc)
            try:
                dir_results = scrape_equine_directory(directory_url)
                added = 0
                for r in dir_results:
                    if add_candidate(r, "Equine Directory"):
                        added += 1
                if on_progress:
                    on_progress("Equine Directory", f"+{added} new (total: {len(all_candidates)})")
            except Exception:
                pass
            time.sleep(POLITE_DELAY)
            if len(all_candidates) >= max_results * 2:
                break

    # ===== SOURCE 5: Curated seed list — ONLY for equine (the seed list is equine-only) =====
    if product_for_type == 'Duo Equine' and len(all_candidates) < max_results // 2:
        if on_progress:
            on_progress("Curated Seeds", f"loading verified {business_type}s")
        try:
            from seed_businesses import get_seeds_for_filter
            # Match state from location string
            state_code = None
            if location:
                # Try to find 2-letter state code
                state_match = re.search(r'\b([A-Z]{2})\b', location.upper())
                if state_match:
                    state_code = state_match.group(1)
                else:
                    # Match full state name
                    state_names = {
                        'KENTUCKY': 'KY', 'TEXAS': 'TX', 'CALIFORNIA': 'CA',
                        'FLORIDA': 'FL', 'VIRGINIA': 'VA', 'COLORADO': 'CO',
                        'NEW YORK': 'NY', 'OREGON': 'OR', 'TENNESSEE': 'TN',
                        'MASSACHUSETTS': 'MA', 'OHIO': 'OH'
                    }
                    for full, code in state_names.items():
                        if full in location.upper():
                            state_code = code
                            break

            seeds = get_seeds_for_filter(business_type=business_type, state=state_code, max_count=20)
            added = 0
            for s in seeds:
                if add_candidate(s, "Curated Seeds"):
                    added += 1
            if on_progress:
                on_progress("Curated Seeds", f"+{added} verified businesses")
        except Exception as e:
            if on_progress:
                on_progress("Curated Seeds", f"failed: {str(e)[:50]}")

    return all_candidates[:max_results]


def discover_from_directory(directory_url, max_results=20):
    """Scrape a directory page for business listings."""
    try:
        response = requests.get(
            directory_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code != 200:
            return []

        # Extract all outbound links that look like business websites
        links = re.findall(r'href="(https?://[^"]+)"', response.text)
        candidates = []
        seen_domains = set()

        for link in links:
            if _should_skip(link):
                continue
            domain = _domain_of(link)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            candidates.append({
                'url': link,
                'title': domain,
                'snippet': '',
                'source_query': f'directory:{directory_url}'
            })
            if len(candidates) >= max_results:
                break

        return candidates
    except Exception:
        return []


# Equine business types to discover
DISCOVERY_TARGETS = [
    {
        'type': 'horse boarding facility',
        'priority': 1,
        'reason': 'Daily ammonia/manure issues, multiple stalls'
    },
    {
        'type': 'equestrian center',
        'priority': 1,
        'reason': 'Premium facilities, large operations'
    },
    {
        'type': 'horse stable',
        'priority': 2,
        'reason': 'Smaller but persistent odor issues'
    },
    {
        'type': 'horse rescue',
        'priority': 2,
        'reason': 'Multiple horses, fly control critical'
    },
    {
        'type': 'horse trainer',
        'priority': 3,
        'reason': 'Often have stables + trailers'
    },
    {
        'type': 'horse breeder',
        'priority': 3,
        'reason': 'Premium operations, quality-focused'
    },
    {
        'type': 'tack shop',
        'priority': 4,
        'reason': 'Distribution partner potential'
    },
    {
        'type': 'feed store',
        'priority': 4,
        'reason': 'Distribution partner potential'
    },
]


def get_discovery_targets():
    """Return business types to search for, ordered by priority."""
    return sorted(DISCOVERY_TARGETS, key=lambda x: x['priority'])


if __name__ == "__main__":
    # Quick test
    print("Testing DuckDuckGo discovery...")
    results = discover_horse_businesses("horse boarding facility", "Lexington KY", max_results=5)
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['snippet'][:120]}...")
