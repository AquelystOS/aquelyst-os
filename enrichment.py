"""Lead enrichment - auto-pull contact info from business websites."""

import re
import requests
from urllib.parse import urlparse, urljoin

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
# NANP-aware: area code must start 2-9 (no leading 0 or 1), exchange
# code must also start 2-9. This stops obvious garbage like '041' from
# being scraped into the CRM. Optional +1 / 1- country code allowed.
PHONE_PATTERN = re.compile(r'(?:\+?1[-.\s]?)?\(?([2-9][0-9]{2})\)?[-.\s]?([2-9][0-9]{2})[-.\s]?([0-9]{4})')

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

EXCLUDED_EMAILS = {
    'example.com', 'sentry.io', 'sentry-next.wixpress.com',
    'wixpress.com', 'godaddy.com', 'domain.com', 'email.com',
    'png', 'jpg', 'gif', 'svg', 'webp'
}

CONTACT_PAGES = ['/contact', '/contact-us', '/about', '/about-us', '/get-in-touch', '/reach-us']


def normalize_url(url):
    """Ensure URL has scheme."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


def fetch_page(url, timeout=10):
    """Fetch page content with timeout."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True
        )
        if response.status_code == 200:
            return response.text
    except (requests.RequestException, requests.ConnectionError, requests.Timeout):
        pass
    return None


def extract_emails(text, exclude_domains=None):
    """Extract valid email addresses from text."""
    if not text:
        return []

    exclude_domains = exclude_domains or EXCLUDED_EMAILS
    emails = EMAIL_PATTERN.findall(text)

    valid_emails = []
    seen = set()

    for email in emails:
        email_lower = email.lower()
        if email_lower in seen:
            continue

        # Skip excluded
        skip = False
        for exclude in exclude_domains:
            if exclude in email_lower:
                skip = True
                break

        if skip:
            continue

        # Skip image filenames mistakenly matching
        if any(email_lower.endswith(ext) for ext in ['.png', '.jpg', '.gif', '.svg', '.webp']):
            continue

        seen.add(email_lower)
        valid_emails.append(email)

    return valid_emails


_FAKE_AREA_CODES = {
    # Movie / TV / fiction reservations + obvious junk
    '555', '000', '111', '222', '333', '444', '666', '777', '888', '999',
    # Toll-free patterns are valid but bias them downward in get_best_phone
}


def is_valid_us_phone(phone):
    """Strict NANP validation. Returns True only for plausibly real US/CA
    phone numbers. Used both at scrape time and as a final guard before
    a number is written into the CRM."""
    if not phone:
        return False
    digits = ''.join(filter(str.isdigit, str(phone)))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return False
    area, exch, line = digits[:3], digits[3:6], digits[6:]
    # Area code: first digit 2-9, no fake-area-code reservations
    if area[0] in '01':
        return False
    if area in _FAKE_AREA_CODES:
        return False
    # Exchange (second 3 digits): NANP requires first digit 2-9
    if exch[0] in '01':
        return False
    # Reject all-same-digit lines (e.g. 555-1111) — usually placeholder
    if len(set(digits)) == 1:
        return False
    return True


def normalize_phone(phone):
    """Format a valid US phone as (XXX) YYY-ZZZZ. Returns None for
    anything that doesn't pass is_valid_us_phone."""
    if not is_valid_us_phone(phone):
        return None
    digits = ''.join(filter(str.isdigit, str(phone)))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def extract_phones(text):
    """Extract US phone numbers (NANP-validated)."""
    if not text:
        return []

    matches = PHONE_PATTERN.findall(text)
    phones = []
    seen = set()

    for area, prefix, line in matches:
        # Belt-and-suspenders: regex is already restrictive but run the
        # full validator so obvious-junk numbers can't slip through.
        if area in _FAKE_AREA_CODES:
            continue
        formatted = f"({area}) {prefix}-{line}"
        if not is_valid_us_phone(formatted):
            continue
        if formatted not in seen:
            seen.add(formatted)
            phones.append(formatted)

    return phones


def find_social_links(text, base_url=None):
    """Find social media URLs in HTML."""
    if not text:
        return {}

    socials = {
        'facebook': re.compile(r'(https?://(?:www\.)?facebook\.com/[a-zA-Z0-9._/-]+)', re.I),
        'instagram': re.compile(r'(https?://(?:www\.)?instagram\.com/[a-zA-Z0-9._/-]+)', re.I),
        'linkedin': re.compile(r'(https?://(?:www\.)?linkedin\.com/[a-zA-Z0-9._/-]+)', re.I),
        'twitter': re.compile(r'(https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9._/-]+)', re.I),
        'youtube': re.compile(r'(https?://(?:www\.)?youtube\.com/[a-zA-Z0-9._/@-]+)', re.I),
    }

    found = {}
    for name, pattern in socials.items():
        matches = pattern.findall(text)
        if matches:
            # Take first non-share-link result
            for match in matches:
                if 'sharer' not in match.lower() and 'share' not in match.lower():
                    found[name] = match
                    break

    return found


def enrich_from_website(website_url):
    """
    Visit a business website and extract:
    - Email addresses
    - Phone numbers
    - Social media links
    """
    result = {
        'emails': [],
        'phones': [],
        'socials': {},
        'pages_checked': [],
        'success': False
    }

    if not website_url:
        return result

    url = normalize_url(website_url)
    if not url:
        return result

    parsed = urlparse(url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    # Check homepage and common contact pages
    pages_to_check = [url] + [urljoin(base_domain, page) for page in CONTACT_PAGES]
    pages_to_check = list(dict.fromkeys(pages_to_check))[:4]  # Limit to 4 pages

    all_emails = set()
    all_phones = set()
    all_socials = {}

    for page_url in pages_to_check:
        html = fetch_page(page_url)
        if html:
            result['pages_checked'].append(page_url)
            result['success'] = True

            # Filter out emails matching the website domain that are wix/system noise
            domain_filter = set(EXCLUDED_EMAILS)

            for email in extract_emails(html, domain_filter):
                all_emails.add(email)

            for phone in extract_phones(html):
                all_phones.add(phone)

            socials = find_social_links(html, base_domain)
            for name, link in socials.items():
                if name not in all_socials:
                    all_socials[name] = link

    result['emails'] = sorted(list(all_emails))
    result['phones'] = sorted(list(all_phones))
    result['socials'] = all_socials

    return result


def get_best_email(emails, business_domain=None):
    """Pick the best email from a list (prefer business domain, info@, contact@)."""
    if not emails:
        return None

    if business_domain:
        for email in emails:
            if business_domain.lower() in email.lower():
                return email

    priority_prefixes = ['info@', 'contact@', 'hello@', 'sales@', 'admin@', 'office@']
    for prefix in priority_prefixes:
        for email in emails:
            if email.lower().startswith(prefix):
                return email

    return emails[0] if emails else None


def get_best_phone(phones):
    """Pick the first VALID phone from a list. Filters out garbage like
    '041-...' that older scraping passes might have stored. If everything
    fails validation, returns None — better empty than wrong."""
    if not phones:
        return None
    for p in phones:
        normalized = normalize_phone(p)
        if normalized:
            return normalized
    return None
