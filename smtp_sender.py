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


def save_smtp_config(provider, email, app_password, sender_name=""):
    """Save SMTP config locally (encoded, not encrypted - for local use only)."""
    import base64

    config = {
        'provider': provider,
        'email': email,
        'sender_name': sender_name,
        'app_password': base64.b64encode(app_password.encode()).decode()
    }

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

    os.chmod(CONFIG_FILE, 0o600)

    # Audit: login/auth event
    try:
        import audit_log
        audit_log.log_login_event(email)
    except Exception:
        pass


def load_smtp_config():
    """Load SMTP config."""
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
    Send email via configured SMTP.
    Returns (success, message).
    """
    config = load_smtp_config()
    if not config:
        return False, "SMTP not configured. Go to Settings to set up."

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
