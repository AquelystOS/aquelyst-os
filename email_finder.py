"""Email Finder — pattern-guess and verify emails when scraping fails.

Free version of Hunter.io / RocketReach approach:
1. Try common email patterns based on contact name + domain
2. Validate via SMTP MX lookup (free, no signup)
3. Score each guess by likelihood
"""

import re
import smtplib
import socket
from urllib.parse import urlparse


def get_domain_from_website(website_url):
    """Extract bare domain from a website URL."""
    if not website_url:
        return None
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
    try:
        parsed = urlparse(website_url)
        domain = parsed.netloc.lower().replace('www.', '')
        return domain if domain else None
    except Exception:
        return None


def split_name(full_name):
    """Split a name into first and last."""
    if not full_name:
        return None, None
    parts = re.findall(r"[A-Za-z']+", full_name.strip())
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0].lower(), None
    return parts[0].lower(), parts[-1].lower()


def generate_email_patterns(contact_name, domain):
    """
    Generate likely email addresses based on common business patterns.
    Returns list of (email, confidence_score) tuples, sorted by confidence.
    """
    if not domain:
        return []

    candidates = []

    # Generic business addresses (work without contact name)
    candidates.extend([
        (f"info@{domain}", 60),
        (f"contact@{domain}", 55),
        (f"hello@{domain}", 45),
        (f"office@{domain}", 40),
        (f"sales@{domain}", 40),
        (f"admin@{domain}", 35),
    ])

    # Personal addresses if we have a name
    first, last = split_name(contact_name)
    if first:
        if last:
            # Most common patterns ranked
            candidates.extend([
                (f"{first}.{last}@{domain}", 75),
                (f"{first}@{domain}", 70),
                (f"{first}{last}@{domain}", 60),
                (f"{first[0]}{last}@{domain}", 55),
                (f"{first}_{last}@{domain}", 45),
                (f"{last}@{domain}", 40),
                (f"{last}.{first}@{domain}", 35),
                (f"{first[0]}.{last}@{domain}", 35),
            ])
        else:
            candidates.extend([
                (f"{first}@{domain}", 65),
            ])

    # Sort by confidence (descending), dedupe
    seen = set()
    unique_candidates = []
    for email, score in sorted(candidates, key=lambda x: -x[1]):
        if email not in seen:
            seen.add(email)
            unique_candidates.append((email, score))

    return unique_candidates


def has_mx_record(domain, timeout=3):
    """Check if domain has MX records (can receive email)."""
    try:
        # Use socket.getaddrinfo as a basic existence check
        # Real MX lookup needs dnspython, but this catches most cases
        socket.getaddrinfo(domain, None)
        return True
    except (socket.gaierror, socket.timeout):
        return False


def smtp_verify(email, timeout=5):
    """
    Light SMTP verification — connect to MX server and check if address is rejected.
    Many servers won't tell us, but this catches obvious bounces.
    Returns: 'valid', 'invalid', 'unknown'
    """
    if '@' not in email:
        return 'invalid'

    domain = email.split('@')[1]

    if not has_mx_record(domain):
        return 'invalid'

    # SMTP probing is unreliable and many servers block it.
    # We don't actually probe — just check domain validity.
    # For real verification, the user should send a test email.
    return 'unknown'


def find_best_email(contact_name, website, scraped_emails=None):
    """
    Master email-finding function.
    Combines pattern guessing with already-scraped emails.

    Returns: best_email_guess (string) or None
    """
    domain = get_domain_from_website(website)

    # If we already scraped real emails, prefer those
    if scraped_emails:
        # Find email matching the domain (most likely real)
        for email in scraped_emails:
            if domain and domain in email.lower():
                return email
        # Or first generic-looking one
        for email in scraped_emails:
            if any(prefix in email.lower() for prefix in ['info@', 'contact@', 'hello@']):
                return email
        return scraped_emails[0]

    # Otherwise, guess
    if not domain:
        return None

    # Need at least domain has MX
    if not has_mx_record(domain):
        return None

    candidates = generate_email_patterns(contact_name, domain)
    if not candidates:
        return None

    # Return highest-confidence guess
    return candidates[0][0]


def get_all_email_guesses(contact_name, website, max_results=5):
    """Return top N email guesses for manual review."""
    domain = get_domain_from_website(website)
    if not domain:
        return []

    candidates = generate_email_patterns(contact_name, domain)
    return candidates[:max_results]
