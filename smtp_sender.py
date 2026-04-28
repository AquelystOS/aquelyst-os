"""SMTP email sender - send emails directly via Gmail/Outlook with App Password.

REQUIRES:
- For Gmail: 2FA enabled + App Password (free, takes 5 min)
  https://support.google.com/accounts/answer/185833

- For Outlook: App Password from account.live.com
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import json
import os
from pathlib import Path

CONFIG_FILE = "smtp_config.json"

SMTP_PRESETS = {
    'gmail': {
        'server': 'smtp.gmail.com',
        'port': 587,
        'use_tls': True,
        'name': 'Gmail',
        'help_url': 'https://support.google.com/accounts/answer/185833',
        'help_text': 'Enable 2FA, then create App Password at myaccount.google.com'
    },
    'outlook': {
        'server': 'smtp-mail.outlook.com',
        'port': 587,
        'use_tls': True,
        'name': 'Outlook / Hotmail',
        'help_url': 'https://account.live.com/proofs/AppPassword',
        'help_text': 'Create App Password at account.live.com'
    },
    'yahoo': {
        'server': 'smtp.mail.yahoo.com',
        'port': 587,
        'use_tls': True,
        'name': 'Yahoo Mail',
        'help_url': 'https://help.yahoo.com/kb/SLN15241.html',
        'help_text': 'Generate App Password in Yahoo Account Security'
    },
    'icloud': {
        'server': 'smtp.mail.me.com',
        'port': 587,
        'use_tls': True,
        'name': 'iCloud Mail',
        'help_url': 'https://support.apple.com/en-us/102654',
        'help_text': 'Create App-Specific Password at appleid.apple.com'
    }
}


def _current_user_email():
    """Return the currently-logged-in user's email, or None."""
    try:
        import streamlit as _st
        return (_st.session_state.get('logged_in_user_email') or '').lower() or None
    except Exception:
        return None


def save_smtp_config(provider, email, app_password, sender_name=""):
    """Save SMTP config for the CURRENT logged-in user (per-user DB row).
    Falls back to the legacy global JSON file if no logged-in user (dev mode)."""
    user_email = _current_user_email()

    if user_email:
        try:
            import database
            preset = SMTP_PRESETS.get(provider, {})
            database.smtp_save(user_email, {
                'provider': provider,
                'server': preset.get('server'),
                'port': preset.get('port'),
                'email': email,
                'app_password': app_password,
                'use_tls': preset.get('use_tls', True),
                'imap_server': IMAP_PRESETS.get(provider, {}).get('server')
                                if 'IMAP_PRESETS' in globals() else None,
                'imap_port': IMAP_PRESETS.get(provider, {}).get('port')
                              if 'IMAP_PRESETS' in globals() else 993,
            })
            try:
                import audit_log
                audit_log.log_login_event(email)
            except Exception:
                pass
            return
        except Exception:
            pass

    # Legacy fallback: global file (dev mode / no logged-in user)
    import base64
    config = {
        'provider': provider,
        'email': email,
        'sender_name': sender_name,
        'app_password': base64.b64encode(app_password.encode()).decode()
    }
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except Exception:
        pass
    try:
        import audit_log
        audit_log.log_login_event(email)
    except Exception:
        pass


def load_smtp_config():
    """Load SMTP config for the CURRENTLY LOGGED-IN user.

    If a user is logged in but has no SMTP saved, returns None — does NOT
    silently fall back to anyone else's smtp_config.json. That fallback
    was the root cause of Danielle's emails sending FROM Joseph's address.

    The legacy global file is only used when nobody is logged in (dev mode
    / background context with no session_state)."""
    user_email = _current_user_email()
    if user_email:
        # Logged-in user: their own config or NOTHING. No silent leak to others.
        try:
            import database
            cfg = database.smtp_get(user_email)
            if cfg and cfg.get('smtp_email'):
                return {
                    'provider': cfg.get('provider', 'gmail'),
                    'email': cfg['smtp_email'],
                    'sender_name': '',
                    'app_password': cfg.get('app_password', ''),
                }
        except Exception:
            pass
        return None

    # Nobody logged in — fall back to the legacy global file (dev / background)
    import base64
    if not Path(CONFIG_FILE).exists():
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        config['app_password'] = base64.b64decode(config['app_password']).decode()
        return config
    except Exception:
        return None


def delete_smtp_config():
    """Remove the current user's SMTP config so they can re-connect."""
    user_email = _current_user_email()
    if user_email:
        try:
            import database
            database.smtp_delete(user_email)
            return
        except Exception:
            pass
    try:
        if Path(CONFIG_FILE).exists():
            os.remove(CONFIG_FILE)
    except Exception:
        pass


def test_smtp_connection(provider, email, app_password):
    """Test SMTP connection without sending."""
    preset = SMTP_PRESETS.get(provider)
    if not preset:
        return False, "Unknown provider"

    try:
        with smtplib.SMTP(preset['server'], preset['port'], timeout=10) as server:
            if preset['use_tls']:
                server.starttls()
            server.login(email, app_password)
            return True, "Connection successful"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed - check App Password"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


def send_email(to_email, subject, body, body_html=None, reply_to=None, tracking_pixel_url=None):
    """
    Send email via configured SMTP for the CURRENTLY LOGGED-IN user.
    Returns (success, message).

    If the logged-in user has no SMTP configured, the send is BLOCKED with
    a clear message. We never silently borrow another user's SMTP — that
    was the bug that masqueraded Danielle's emails as Joseph's.
    """
    user_email = _current_user_email()
    config = load_smtp_config()
    if not config:
        if user_email:
            return False, (
                f"📭 No email connected for {user_email}. Go to "
                "**Setup → Email** and connect your Gmail (or other provider) "
                "with an App Password before sending. Aqua won't send as "
                "anyone else."
            )
        return False, "SMTP not configured. Go to Setup → Email to connect your account."

    preset = SMTP_PRESETS.get(config['provider'])
    if not preset:
        return False, "Invalid SMTP provider"

    try:
        msg = MIMEMultipart('alternative')

        sender = f"{config['sender_name']} <{config['email']}>" if config.get('sender_name') else config['email']
        msg['From'] = sender
        msg['To'] = to_email
        msg['Subject'] = subject
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid()

        if reply_to:
            msg['Reply-To'] = reply_to

        plain_part = MIMEText(body, 'plain')
        msg.attach(plain_part)

        if body_html or tracking_pixel_url:
            html_body = body_html or body.replace('\n', '<br>')
            if tracking_pixel_url:
                html_body += f'<br><img src="{tracking_pixel_url}" width="1" height="1" style="display:none">'

            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

        with smtplib.SMTP(preset['server'], preset['port'], timeout=15) as server:
            if preset['use_tls']:
                server.starttls()
            server.login(config['email'], config['app_password'])
            server.send_message(msg)

        # Audit log every successful send
        try:
            import audit_log
            audit_log.log_email_sent(
                to_email=to_email,
                subject=subject,
                lead_id=None,  # caller knows the lead_id; this is a baseline log
                lead_name=None,
                message_type='smtp_direct',
            )
        except Exception:
            pass

        return True, "Email sent successfully"

    except smtplib.SMTPRecipientsRefused:
        try:
            import audit_log
            audit_log.log('email_send_failed',
                          f"Recipient refused: {to_email}",
                          details={'to': to_email, 'subject': subject, 'error': 'recipient_refused'})
        except Exception:
            pass
        return False, f"Recipient refused: {to_email}"
    except smtplib.SMTPAuthenticationError:
        try:
            import audit_log
            audit_log.log('email_send_failed',
                          f"SMTP auth failed for {to_email}",
                          details={'to': to_email, 'error': 'auth_failed'})
        except Exception:
            pass
        return False, "Authentication failed - check App Password"
    except Exception as e:
        try:
            import audit_log
            audit_log.log('email_send_failed',
                          f"Send failed for {to_email}: {str(e)[:100]}",
                          details={'to': to_email, 'subject': subject, 'error': str(e)[:300]})
        except Exception:
            pass
        return False, f"Error: {str(e)}"


def is_configured():
    """Check if SMTP is configured."""
    return load_smtp_config() is not None
