"""Gmail integration - compose emails directly in Gmail with one click."""

import urllib.parse


def build_gmail_compose_url(to_email, subject, body, cc=None, bcc=None):
    """
    Build a Gmail compose URL that opens Gmail with the email pre-filled.
    User clicks link → Gmail opens → email is ready → user clicks Send.
    No SMTP needed. Uses user's actual Gmail account.
    """
    base_url = "https://mail.google.com/mail/?view=cm&fs=1"

    params = {
        "to": to_email or "",
        "su": subject or "",
        "body": body or ""
    }

    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc

    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{base_url}&{query_string}"


def build_mailto_url(to_email, subject, body, cc=None, bcc=None):
    """
    Build a mailto: link that opens default email client.
    Works with Apple Mail, Outlook, Thunderbird, etc.
    """
    params = {}
    if subject:
        params["subject"] = subject
    if body:
        params["body"] = body
    if cc:
        params["cc"] = cc
    if bcc:
        params["bcc"] = bcc

    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    if query_string:
        return f"mailto:{to_email}?{query_string}"
    return f"mailto:{to_email}"


def build_outlook_compose_url(to_email, subject, body):
    """Build Outlook web compose URL."""
    base_url = "https://outlook.live.com/owa/?path=/mail/action/compose"
    params = {
        "to": to_email or "",
        "subject": subject or "",
        "body": body or ""
    }
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{base_url}&{query_string}"


def build_yahoo_compose_url(to_email, subject, body):
    """Build Yahoo Mail compose URL."""
    base_url = "https://compose.mail.yahoo.com/"
    params = {
        "to": to_email or "",
        "subject": subject or "",
        "body": body or ""
    }
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{base_url}?{query_string}"


def build_whatsapp_url(phone, message):
    """Build WhatsApp message URL (for mobile clicks)."""
    clean_phone = ''.join(filter(str.isdigit, phone or ''))
    encoded_message = urllib.parse.quote(message or '')
    return f"https://wa.me/{clean_phone}?text={encoded_message}"


def build_sms_url(phone, message):
    """Build SMS link (works on iPhone/Android)."""
    clean_phone = ''.join(filter(lambda c: c.isdigit() or c == '+', phone or ''))
    encoded_message = urllib.parse.quote(message or '')
    return f"sms:{clean_phone}?&body={encoded_message}"


def build_call_url(phone):
    """Build tel: link to initiate call."""
    clean_phone = ''.join(filter(lambda c: c.isdigit() or c == '+', phone or ''))
    return f"tel:{clean_phone}"
