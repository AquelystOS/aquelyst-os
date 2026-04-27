"""Email provider auto-detection from domain."""

import re

# Common domains → SMTP provider mapping
DOMAIN_TO_PROVIDER = {
    'gmail.com': 'gmail',
    'googlemail.com': 'gmail',
    'outlook.com': 'outlook',
    'hotmail.com': 'outlook',
    'live.com': 'outlook',
    'msn.com': 'outlook',
    'yahoo.com': 'yahoo',
    'ymail.com': 'yahoo',
    'icloud.com': 'icloud',
    'me.com': 'icloud',
    'mac.com': 'icloud',
}

# Custom domains that use Google Workspace (we'll show Gmail flow)
GOOGLE_WORKSPACE_HINT_DOMAINS = ['aquelyst.com']


def detect_provider(email):
    """Detect SMTP provider from email address. Returns provider key or None."""
    if not email or '@' not in email:
        return None

    domain = email.split('@')[1].lower().strip()

    # Direct match
    if domain in DOMAIN_TO_PROVIDER:
        return DOMAIN_TO_PROVIDER[domain]

    # Custom domain hints
    if domain in GOOGLE_WORKSPACE_HINT_DOMAINS:
        return 'gmail'

    # Default: assume custom domain might use Google Workspace
    # (since most small businesses do)
    return 'gmail'


def is_valid_email(email):
    """Quick email validation."""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def get_setup_instructions(provider):
    """Return tailored setup instructions for the provider."""
    instructions = {
        'gmail': {
            'title': '📧 Gmail / Google Workspace Setup',
            'steps': [
                "1. Make sure 2-Factor Authentication is ON for your Google account",
                "2. Click the link below to create an App Password",
                "3. App name: 'AqueLyst Hunter'",
                "4. Copy the 16-character password Google shows you",
                "5. Paste it below and click Connect",
            ],
            'app_password_url': 'https://myaccount.google.com/apppasswords',
            '2fa_url': 'https://myaccount.google.com/security',
            'time_estimate': '2 minutes'
        },
        'outlook': {
            'title': '📧 Outlook / Hotmail Setup',
            'steps': [
                "1. Go to your Microsoft account security page",
                "2. Enable 2-Factor Authentication if not already on",
                "3. Create a new App Password",
                "4. Copy the password",
                "5. Paste it below and click Connect",
            ],
            'app_password_url': 'https://account.live.com/proofs/AppPassword',
            '2fa_url': 'https://account.microsoft.com/security',
            'time_estimate': '3 minutes'
        },
        'yahoo': {
            'title': '📧 Yahoo Mail Setup',
            'steps': [
                "1. Go to Yahoo Account Security",
                "2. Click 'Generate App Password'",
                "3. Name it 'AqueLyst Hunter'",
                "4. Copy the password",
                "5. Paste it below and click Connect",
            ],
            'app_password_url': 'https://login.yahoo.com/account/security',
            '2fa_url': 'https://login.yahoo.com/account/security',
            'time_estimate': '3 minutes'
        },
        'icloud': {
            'title': '📧 iCloud Mail Setup',
            'steps': [
                "1. Sign in to appleid.apple.com",
                "2. Go to Sign-In and Security → App-Specific Passwords",
                "3. Generate a new password labeled 'AqueLyst Hunter'",
                "4. Copy the password",
                "5. Paste it below and click Connect",
            ],
            'app_password_url': 'https://appleid.apple.com',
            '2fa_url': 'https://appleid.apple.com',
            'time_estimate': '3 minutes'
        }
    }
    return instructions.get(provider, instructions['gmail'])
