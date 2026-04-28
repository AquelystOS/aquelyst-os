"""AqueLyst Hunter — Simple Sales OS for Joseph at AqueLyst.com

Designed for a non-technical founder. Plain English. One action per screen.
Forced step-by-step onboarding. Big buttons. No jargon.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

import database
import lead_scoring
import outreach
import import_export
import gmail_integration
import enrichment
import prospecting
import smtp_sender
import ai_providers
import api_keys
import email_helpers
import autopilot
import lead_discovery
import nepq_engine
import auto_engagement
import email_responder
import audit_log
import ui_kit

autopilot.reset_stale_state()


st.set_page_config(
    page_title="AqueLyst Hunter",
    page_icon="🐴",
    layout="centered",
    initial_sidebar_state="collapsed"
)


# ============================================================================
# PASSWORD GATE — protect the public URL when deployed to Streamlit Cloud
# Set TEAM_PASSWORD in .streamlit/secrets.toml or skip in dev (no password set)
# ============================================================================
ROOT_ADMIN_EMAIL_LOGIN = 'joseph@aquelyst.com'  # always-allowed root admin


# Initialize database BEFORE any login flow — login itself reads from DB
if "db_initialized" not in st.session_state:
    database.init_db()
    st.session_state.db_initialized = True


def _check_password():
    """Two-stage gate:
    1) Team password (one shared password gates the URL — protects from random visitors)
    2) Per-user login (each team member has their own email + password)

    Sets st.session_state.logged_in_user_email when login is complete.
    Returns True only when both gates have been passed.
    """
    import hmac

    # Get team password
    try:
        team_password = st.secrets.get("TEAM_PASSWORD", "")
    except Exception:
        team_password = ""

    # Stage 1: team password (skipped in dev mode if no team password set)
    team_ok = st.session_state.get("team_password_ok", False) or not team_password
    if not team_ok:
        st.html(
            "<div style='max-width:560px;margin:4rem auto 1.2rem;text-align:center'>"
            f"<div style='display:inline-block'>{ui_kit.brand_wordmark(size='lg', show_subtitle=True)}</div>"
            "<div style='font-family:JetBrains Mono,monospace;font-size:0.7rem;"
            "color:#64748b;letter-spacing:0.20em;text-transform:uppercase;"
            "font-weight:700;margin-top:1.5rem'>"
            "◢ STEP 1 OF 2 · TEAM ACCESS PASSWORD</div>"
            "</div>"
        )
        with st.form("team_pw_form", clear_on_submit=True):
            entered = st.text_input("Team password", type="password",
                                     placeholder="•••••••",
                                     label_visibility="collapsed")
            ok = st.form_submit_button("Continue →", type="primary",
                                         use_container_width=True)
        if ok:
            if hmac.compare_digest(entered, team_password):
                st.session_state.team_password_ok = True
                st.rerun()
            else:
                st.error("❌ Wrong team password")
        return False

    # Stage 2: per-user login
    if st.session_state.get("logged_in_user_email"):
        return True

    import team as _team
    members = _team.load_team()

    st.html(
        "<div style='max-width:580px;margin:3rem auto 1.2rem;text-align:center'>"
        f"<div style='display:inline-block'>{ui_kit.brand_wordmark(size='lg', show_subtitle=True)}</div>"
        "<div style='font-family:JetBrains Mono,monospace;font-size:0.7rem;"
        "color:#64748b;letter-spacing:0.20em;text-transform:uppercase;"
        "font-weight:700;margin-top:1.5rem'>"
        "◢ STEP 2 OF 2 · SIGN IN WITH YOUR AQUELYST EMAIL</div>"
        "</div>"
    )

    member_rows = [(m['email'].lower(), m.get('name', '?'),
                     m.get('short_role') or m.get('role', ''))
                    for m in members if m.get('email')]

    just_created = st.session_state.get('just_created_account')
    if just_created:
        st.success(
            f"✅ Account created for **{just_created}**. "
            f"Now sign in with your new password to confirm."
        )

    # Step A: pick your email — TAP-FRIENDLY BUTTON GRID instead of selectbox.
    # Streamlit's selectbox with tuple options has known iOS Safari bugs where
    # tapping an option doesn't register a value change. Buttons sidestep that
    # entirely and feel native on phones.
    picked = (st.session_state.get('login_picked_email')
              or (just_created or '').lower()
              or '')

    st.html(
        "<div style='font-family:JetBrains Mono,monospace;font-size:0.66rem;"
        "color:#94a3b8;letter-spacing:0.16em;text-transform:uppercase;"
        "font-weight:700;text-align:center;margin:0.5rem 0 0.6rem'>"
        "◢ TAP YOUR NAME"
        "</div>"
    )
    for email, name, role in member_rows:
        is_picked = picked == email
        label = f"{'✅  ' if is_picked else ''}{name}"
        if role:
            label += f" · {role}"
        if st.button(
            label,
            key=f"login_pick_{email}",
            use_container_width=True,
            type='primary' if is_picked else 'secondary',
        ):
            st.session_state.login_picked_email = email
            st.rerun()

    # Custom email path (someone not on the official team list yet)
    if st.button(
        "✏️ Other email (not on team list yet)",
        key="login_pick_custom",
        use_container_width=True,
        type='primary' if picked == '__custom__' else 'secondary',
    ):
        st.session_state.login_picked_email = '__custom__'
        st.rerun()

    custom_email = ""
    if picked == '__custom__':
        custom_email = st.text_input("Your email", key="login_custom_email")

    chosen_email = (custom_email or picked or '').strip().lower()
    if chosen_email == '__custom__':
        chosen_email = ''

    has_account = database.user_account_exists(chosen_email) if chosen_email else False

    with st.container(border=True):
        if has_account:
            st.markdown(f"##### 🔐 Sign in as `{chosen_email}`")
            with st.form("user_login_form", clear_on_submit=False):
                pw = st.text_input("Your password", type="password",
                                    placeholder="•••••••")
                login_btn = st.form_submit_button(
                    "Log in →", type="primary", use_container_width=True,
                )
            if login_btn:
                if database.user_check_password(chosen_email, pw):
                    st.session_state.logged_in_user_email = chosen_email
                    st.session_state.pop('just_created_account', None)
                    database.user_record_login(chosen_email)
                    st.rerun()
                else:
                    st.error("❌ Wrong password for that account")
        elif chosen_email:
            st.markdown(f"##### 🆕 Create account for `{chosen_email}`")
            st.caption(
                "First time signing in. Pick a password, type it twice, and confirm. "
                "After you create the account you'll log in normally with that password."
            )
            with st.form("user_create_form", clear_on_submit=False):
                pw1 = st.text_input("Choose a password (min 6 characters)",
                                     type="password",
                                     placeholder="•••••••")
                pw2 = st.text_input("Type it again to confirm", type="password",
                                     placeholder="•••••••")
                set_btn = st.form_submit_button(
                    "✅ Create my account",
                    type="primary", use_container_width=True,
                )
            if set_btn:
                if not pw1 or not pw2:
                    st.error("Both password fields are required.")
                elif len(pw1) < 6:
                    st.error("Password must be at least 6 characters.")
                elif pw1 != pw2:
                    st.error("Passwords don't match — type it the same way twice.")
                else:
                    database.user_set_password(chosen_email, pw1)
                    # Don't auto-login. Force them to log in with the new password
                    # so we know they typed it correctly.
                    st.session_state['just_created_account'] = chosen_email
                    st.rerun()
        else:
            st.info("Pick your email above to continue.")

    st.caption(
        "Forgot your password? Ask Joseph (root admin) to reset it in "
        "🛡 Admin → 👥 Team → \"Reset PW\"."
    )
    return False


if not _check_password():
    st.stop()


# ===========================================================================
# STYLES
# ===========================================================================
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&family=Playfair+Display:wght@700;800;900&display=swap" rel="stylesheet">
<style>
    /* ==================== HIGH-TECH BASE ==================== */
    :root {
        /* Dark dashboard surface — matches the Today hero so the page reads
           as one cohesive control panel. Cards remain white-glass to pop
           cleanly off the dark bg, exactly how the hero floats today. */
        --bg: #0a0f1c;
        --surface: rgba(255,255,255,0.92);   /* white card on dark bg */
        --surface-solid: #ffffff;
        --border: rgba(148,163,184,0.10);
        --border-strong: rgba(148,163,184,0.20);
        --ink: #0a0f1c;                       /* dark text — used inside white cards */
        --ink-on-bg: #e2e8f0;                /* light text — used on the dark page bg */
        --ink-soft: #475569;
        --ink-muted: #94a3b8;
        /* AqueLyst brand: cyan (Aque) → lime (Lyst). The deep variant is
           used for dark text on light backgrounds; the bright lime is for
           accents on dark surfaces. */
        --accent: #06b6d4;
        --accent-2: #a3e635;          /* lime-400 — bright brand lime */
        --accent-2-deep: #4d7c0f;     /* lime-700 — dark variant for text */
        --accent-glow: 0 0 24px rgba(163,230,53,0.40);
        --grad: linear-gradient(135deg, #06b6d4 0%, #a3e635 100%);
        --grad-soft: linear-gradient(135deg, rgba(6,182,212,0.10), rgba(163,230,53,0.12));
    }

    /* App background — same gradient as the Today hero so the page bg blends
       with the hero. Subtle radial cyan / lime washes give depth. */
    .stApp {
        background:
            radial-gradient(circle at 12% 0%, rgba(6,182,212,0.08) 0%, transparent 40%),
            radial-gradient(circle at 100% 100%, rgba(163,230,53,0.06) 0%, transparent 42%),
            linear-gradient(135deg, #0a0f1c 0%, #0f172a 55%, #0a1f24 100%) !important;
    }
    .stApp::before {
        content: "";
        position: fixed; inset: 0;
        background-image: radial-gradient(circle, rgba(148,163,184,0.06) 1px, transparent 1px);
        background-size: 28px 28px;
        pointer-events: none;
        z-index: 0;
    }
    /* Inside white card components (expander, form, metric, container) keep
       text DARK so it's readable on the white surface. Heroes, glass panels,
       and ring cards use inline color styles to stay light on dark — those
       win over these defaults. This is the fix for the hunt-categories
       white-on-white bug introduced when we flipped to a dark theme. */
    [data-testid="stExpander"],
    [data-testid="stForm"],
    [data-testid="stMetric"] {
        color: var(--ink);
    }
    [data-testid="stExpander"] [data-testid="stCaptionContainer"],
    [data-testid="stForm"] [data-testid="stCaptionContainer"],
    [data-testid="stMetric"] [data-testid="stCaptionContainer"] {
        color: var(--ink-soft) !important;
        opacity: 1;
    }
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"],
    [data-testid="stForm"] [data-testid="stMarkdownContainer"],
    [data-testid="stMetric"] [data-testid="stMarkdownContainer"] {
        color: var(--ink);
    }
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] h4,
    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] h5,
    [data-testid="stForm"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stForm"] [data-testid="stMarkdownContainer"] h4,
    [data-testid="stForm"] [data-testid="stMarkdownContainer"] h5 {
        color: var(--ink) !important;
    }
    /* Form labels (text_input / selectbox / checkbox / radio) inside white
       cards — keep them dark for legibility. */
    [data-testid="stExpander"] label,
    [data-testid="stForm"] label,
    [data-testid="stMetric"] label {
        color: var(--ink-soft) !important;
    }

    .main {padding-top: 0.5rem;}
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 4rem !important;
        max-width: 1240px;
        position: relative;
        z-index: 1;
    }

    /* Typography */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        color: var(--ink);
    }
    code, pre, .stCode, [class*="monospace"] {
        font-family: 'JetBrains Mono', ui-monospace, 'SF Mono', Monaco, monospace !important;
    }

    div[data-testid="stMarkdownContainer"] > h1:not([style*="color"]) {
        color: var(--ink);
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stMarkdownContainer"] > h2:not([style*="color"]) {
        color: var(--ink);
        font-weight: 700;
        letter-spacing: -0.02em;
        font-size: 1.45rem;
    }
    div[data-testid="stMarkdownContainer"] > h3:not([style*="color"]) {
        color: var(--ink-soft);
        font-weight: 600;
        font-size: 1.1rem;
        letter-spacing: -0.01em;
    }
    h1[data-testid="stHeading"] {
        color: var(--ink) !important;
        font-weight: 800;
        letter-spacing: -0.03em;
    }

    /* ==================== BUTTONS ==================== */
    .stButton button {
        border-radius: 12px !important;
        padding: 0.65rem 1.3rem !important;
        font-weight: 600;
        font-size: 0.93rem;
        letter-spacing: -0.005em;
        border: 1px solid var(--border-strong);
        background: var(--surface);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        color: var(--ink);
        transition: transform 0.12s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
    }
    .stButton button:hover {
        border-color: var(--accent);
        background: var(--surface-solid);
        transform: translateY(-1px);
        box-shadow: 0 4px 14px rgba(6,182,212,0.15);
    }
    .stButton button[kind="primary"] {
        background: var(--grad) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(6,182,212,0.25), inset 0 1px 0 rgba(255,255,255,0.18);
        position: relative;
    }
    .stButton button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: var(--accent-glow), 0 8px 24px rgba(26,95,63,0.3);
    }
    .stButton button[kind="primary"]:active {
        transform: translateY(0);
    }

    /* ==================== METRICS ==================== */
    div[data-testid="stMetric"] {
        background: var(--surface);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        padding: 1.1rem 1.3rem;
        border-radius: 14px;
        border: 1px solid var(--border-strong);
        box-shadow: 0 1px 2px rgba(0,0,0,0.02), 0 8px 24px rgba(15,23,42,0.04);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 1px 2px rgba(0,0,0,0.02), 0 16px 32px rgba(6,182,212,0.10);
    }
    div[data-testid="stMetricValue"] {
        color: var(--ink) !important;
        font-family: 'JetBrains Mono', ui-monospace, monospace !important;
        font-weight: 700;
        font-size: 1.85rem !important;
        letter-spacing: -0.02em;
    }
    div[data-testid="stMetricLabel"] {
        color: var(--ink-muted);
        font-weight: 500;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    div[data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', ui-monospace, monospace !important;
        font-weight: 600;
    }

    /* ==================== TABS ==================== */
    div[data-baseweb="tab-list"] {
        background: var(--surface);
        backdrop-filter: blur(12px);
        border-radius: 12px;
        padding: 0.3rem;
        border: 1px solid var(--border-strong);
        gap: 0.2rem;
    }
    button[data-baseweb="tab"] {
        font-weight: 600 !important;
        color: var(--ink-muted) !important;
        font-size: 0.92rem !important;
        border-radius: 9px !important;
        padding: 0.5rem 1.1rem !important;
        transition: all 0.18s ease;
    }
    button[data-baseweb="tab"]:hover {
        color: var(--ink) !important;
        background: rgba(6,182,212,0.06);
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important;
        background: var(--grad) !important;
        box-shadow: 0 2px 8px rgba(6,182,212,0.25);
    }
    div[data-baseweb="tab-highlight"] { display: none !important; }
    div[data-baseweb="tab-border"] { display: none !important; }

    /* ==================== INPUTS ==================== */
    input[type="text"], input[type="email"], input[type="password"],
    input[type="number"], textarea {
        border-radius: 10px !important;
        border-color: var(--border-strong) !important;
        background: var(--surface-solid) !important;
        font-size: 0.95rem !important;
        transition: all 0.18s ease;
    }
    input[type="text"]:focus, input[type="email"]:focus,
    input[type="password"]:focus, textarea:focus,
    input[type="number"]:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px rgba(6,182,212,0.15) !important;
    }
    [data-baseweb="select"] > div {
        border-radius: 10px !important;
        border-color: var(--border-strong) !important;
        background: var(--surface-solid) !important;
    }

    /* ==================== SLIDERS ==================== */
    [data-testid="stSlider"] [role="slider"] {
        background: var(--grad) !important;
        box-shadow: 0 0 12px rgba(6,182,212,0.4) !important;
    }
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div > div {
        background: var(--grad) !important;
    }

    /* ==================== EXPANDER ==================== */
    div[data-testid="stExpander"] {
        border-radius: 12px !important;
        border-color: var(--border-strong) !important;
        background: var(--surface) !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600;
    }

    /* ==================== PROGRESS ==================== */
    [data-testid="stProgress"] > div > div {
        background: rgba(15,23,42,0.06) !important;
        border-radius: 999px;
    }
    [data-testid="stProgress"] > div > div > div {
        background: var(--grad) !important;
        box-shadow: 0 0 10px rgba(6,182,212,0.4);
    }

    /* ==================== CHECKBOX ==================== */
    [data-testid="stCheckbox"] [aria-checked="true"] svg {
        background: var(--grad) !important;
    }

    /* ==================== STATUS BANNERS ==================== */
    .stSuccess {
        background: linear-gradient(135deg, rgba(34,197,94,0.10), rgba(34,197,94,0.04)) !important;
        border: 1px solid rgba(34,197,94,0.30) !important;
        border-radius: 10px !important;
    }
    .stError {
        background: linear-gradient(135deg, rgba(239,68,68,0.10), rgba(239,68,68,0.04)) !important;
        border: 1px solid rgba(239,68,68,0.30) !important;
        border-radius: 10px !important;
    }
    .stWarning {
        background: linear-gradient(135deg, rgba(245,158,11,0.10), rgba(245,158,11,0.04)) !important;
        border: 1px solid rgba(245,158,11,0.30) !important;
        border-radius: 10px !important;
    }
    .stInfo {
        background: linear-gradient(135deg, rgba(6,182,212,0.10), rgba(6,182,212,0.04)) !important;
        border: 1px solid rgba(6,182,212,0.30) !important;
        border-radius: 10px !important;
    }

    /* ==================== HIDE STREAMLIT CHROME ==================== */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent; height: 0;}

    /* ==================== ANIMATIONS ==================== */
    @keyframes pulse-glow {
        0%, 100% { box-shadow: 0 0 8px rgba(6,182,212,0.4); }
        50% { box-shadow: 0 0 24px rgba(6,182,212,0.8); }
    }
    @keyframes fade-up {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .stApp [data-testid="stVerticalBlock"] > div {
        animation: fade-up 0.35s ease both;
    }

    /* Subtle scrollbar */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: rgba(15,23,42,0.15);
        border-radius: 999px;
    }
    ::-webkit-scrollbar-thumb:hover { background: rgba(15,23,42,0.3); }

    /* ==================== MOBILE / TABLET RESPONSIVE ====================
       Strictly @media-scoped — desktop layout untouched. iPhones (390px),
       small Androids (360px), and tablets in portrait (~768px) all adapt. */

    /* Tablets in portrait + large phones */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.7rem !important;
            padding-right: 0.7rem !important;
            padding-top: 0.4rem !important;
            max-width: 100% !important;
        }

        /* ======= FORCE-STACK st.columns ON MOBILE BY DEFAULT =======
           Streamlit columns squish ugly on phones. Wrap every horizontal
           block onto multiple rows with each column taking full width. */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.5rem !important;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="column"] {
            flex: 1 1 100% !important;
            min-width: 0 !important;
            width: 100% !important;
        }

        /* ======= EXCEPTION: Top toolbar (logo + search + signout) =======
           Mobile: hide the search bar entirely, keep logo on the left and
           a small signout button on the right. Identified via the marker
           div inside its dedicated st.container(). */
        [data-testid="stVerticalBlock"]:has(> div .aqp-toprow-marker)
          > [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            display: grid !important;
            grid-template-columns: 1fr auto !important;
            gap: 0.5rem !important;
        }
        [data-testid="stVerticalBlock"]:has(> div .aqp-toprow-marker)
          > [data-testid="stHorizontalBlock"]
          > [data-testid="column"] {
            flex: unset !important;
            width: auto !important;
        }
        /* Hide the middle column (search bar) on mobile */
        [data-testid="stVerticalBlock"]:has(> div .aqp-toprow-marker)
          > [data-testid="stHorizontalBlock"]
          > [data-testid="column"]:nth-child(2) {
            display: none !important;
        }
        /* Compact the right column (signout button) so it stays small */
        [data-testid="stVerticalBlock"]:has(> div .aqp-toprow-marker)
          > [data-testid="stHorizontalBlock"]
          > [data-testid="column"]:nth-child(3) {
            justify-self: end !important;
        }

        /* ======= EXCEPTION: Nav buttons row =======
           7 buttons would stack to 7 rows under the global rule — that's
           too much vertical space. Instead, make it a 2-column grid so
           it becomes 4 rows of 2 (or 3+3+1 if 6 buttons). */
        [data-testid="stVerticalBlock"]:has(> div .aqp-navrow-marker)
          > [data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            display: grid !important;
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 0.4rem !important;
        }
        [data-testid="stVerticalBlock"]:has(> div .aqp-navrow-marker)
          > [data-testid="stHorizontalBlock"]
          > [data-testid="column"] {
            flex: unset !important;
            width: auto !important;
        }

        /* Heroes — squeeze padding + corner radius */
        [style*="background:linear-gradient(135deg,#0a0f1c"] {
            padding: 1.0rem 1.1rem !important;
            border-radius: 12px !important;
        }
        /* Hero title scales down */
        [style*="background:linear-gradient(135deg,#0a0f1c"] [style*="font-size:2rem"],
        [style*="background:linear-gradient(135deg,#0a0f1c"] [style*="font-size:2.4rem"] {
            font-size: 1.45rem !important;
            line-height: 1.15 !important;
        }
        /* Hero rows wrap so stats fall under the greeting on narrow screens */
        [style*="background:linear-gradient(135deg,#0a0f1c"]
          [style*="display:flex"][style*="justify-content:space-between"][style*="align-items:flex-end"] {
            flex-wrap: wrap !important;
            gap: 0.8rem !important;
        }
        /* Mono timestamp + eyebrow strip — tighter letter-spacing so it fits */
        [style*="background:linear-gradient(135deg,#0a0f1c"]
          [style*="letter-spacing:0.22em"] {
            letter-spacing: 0.10em !important;
            font-size: 0.58rem !important;
        }
        /* Mono OS pill in top nav */
        [style*="letter-spacing:0.18em"][style*="JetBrains Mono"],
        [style*="letter-spacing:0.20em"][style*="JetBrains Mono"] {
            letter-spacing: 0.10em !important;
        }

        /* Tabs — wrap onto multiple lines instead of horizontal scroll */
        div[data-baseweb="tab-list"] { flex-wrap: wrap !important; }
        button[data-baseweb="tab"] {
            font-size: 0.82rem !important;
            padding: 0.4rem 0.85rem !important;
        }

        /* Buttons compact */
        .stButton button {
            padding: 0.55rem 0.9rem !important;
            font-size: 0.85rem !important;
        }
        .stButton button[kind="primary"] {
            padding: 0.6rem 1rem !important;
        }

        /* Logo image (top nav + login) shrinks */
        img[alt="AqueLyst"] { max-height: 40px; height: auto; }

        /* Streamlit columns: keep min-width sane so they don't overflow */
        [data-testid="column"] { min-width: 0 !important; }

        /* KPI / provider rings shrink so 5-across stays readable */
        [style*="border-radius:50%"][style*="conic-gradient"][style*="width:96px"][style*="height:96px"] {
            width: 64px !important;
            height: 64px !important;
        }
        [style*="border-radius:50%"][style*="conic-gradient"][style*="width:96px"]
          > [style*="width:70px"][style*="height:70px"] {
            width: 46px !important;
            height: 46px !important;
        }
        [style*="border-radius:50%"][style*="conic-gradient"][style*="width:88px"][style*="height:88px"] {
            width: 60px !important;
            height: 60px !important;
        }
        [style*="border-radius:50%"][style*="conic-gradient"][style*="width:88px"]
          > [style*="width:64px"][style*="height:64px"] {
            width: 42px !important;
            height: 42px !important;
        }

        /* Pipeline funnel — narrow label column, smaller font */
        [style*="flex:0 0 140px"] {
            flex: 0 0 100px !important;
            font-size: 0.74rem !important;
        }

        /* Glass cards / chart cards — reduced padding */
        [style*="backdrop-filter:blur(12px)"][style*="border-radius:14px"] {
            padding: 0.9rem 1.0rem !important;
        }
    }

    /* iPhone-class phones (390px viewport and smaller) */
    @media (max-width: 480px) {
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }

        /* Hero title even smaller so the greeting + accent fit on one line */
        [style*="background:linear-gradient(135deg,#0a0f1c"] [style*="font-size:2rem"],
        [style*="background:linear-gradient(135deg,#0a0f1c"] [style*="font-size:2.4rem"] {
            font-size: 1.25rem !important;
        }

        /* Hero stat strip wraps to 2 rows of stats */
        [style*="background:linear-gradient(135deg,#0a0f1c"]
          [style*="display:flex"][style*="gap:1.1rem"],
        [style*="background:linear-gradient(135deg,#0a0f1c"]
          [style*="display:flex"][style*="gap:1.0rem"] {
            flex-wrap: wrap !important;
            justify-content: flex-start !important;
            gap: 0.7rem !important;
        }

        /* Logo even more compact */
        img[alt="AqueLyst"] { max-height: 32px; }

        /* Section headers shrink letter-spacing */
        [style*="letter-spacing:0.20em"][style*="JetBrains Mono"],
        [style*="letter-spacing:0.18em"][style*="JetBrains Mono"],
        [style*="letter-spacing:0.16em"][style*="JetBrains Mono"] {
            letter-spacing: 0.08em !important;
        }

        /* KPI ring labels: shorter line height so 5 stacked names fit */
        [style*="text-transform:uppercase"][style*="letter-spacing:0.12em"] {
            letter-spacing: 0.06em !important;
        }

        /* Top nav user badge — single line */
        [style*="background:#4d7c0f"][style*="border-radius:12px"][style*="font-size:0.85rem"] {
            font-size: 0.72rem !important;
            padding: 0.18rem 0.55rem !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 50vw;
        }

        /* Pipeline funnel — even narrower label */
        [style*="flex:0 0 100px"] {
            flex: 0 0 78px !important;
            font-size: 0.7rem !important;
        }
    }

    /* Touch-target friendliness: min 44px tap area on coarse-pointer devices */
    @media (pointer: coarse) {
        .stButton button { min-height: 44px; }
        button[data-baseweb="tab"] { min-height: 40px; }
    }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# STATE & ROUTING
# ===========================================================================
def needs_onboarding():
    """First-run detection — if nothing is set up AND no leads, force onboarding."""
    has_email = smtp_sender.is_configured()
    has_ai = (api_keys.has_key('cerebras') or
              api_keys.has_key('claude') or
              api_keys.has_key('openai'))
    has_leads = len(database.get_all_leads()) > 0
    onboarding_done = st.session_state.get('onboarding_done', False)

    return not (has_email or has_ai or has_leads) and not onboarding_done


# Default page
if "page" not in st.session_state:
    st.session_state.page = "home"
if "onboarding_step" not in st.session_state:
    st.session_state.onboarding_step = 0


# ===========================================================================
# STATUS-FRIENDLY MAPPING (plain English everywhere)
# ===========================================================================
STATUS_FRIENDLY = {
    "new": "🆕 New",
    "researched": "📚 Researched",
    "drafted": "✏️ Draft ready",
    "contacted": "📞 Reached out",
    "follow_up_due": "📅 Follow up today",
    "interested": "⭐ Interested",
    "trial_offered": "🎁 Offered free trial",
    "sample_sent": "📦 Trial sent",
    "closed_won": "✅ Customer!",
    "closed_lost": "❌ Said no",
    "opted_out": "🚫 Don't contact",
}

GOAL_TO_TYPE = {
    "📨 Reach out for the first time (cold email)": "cold_email",
    "👋 Just have Aqua introduce himself": "aqua_intro",
    "✏️ Custom — describe what to say (Aqua writes it)": "custom",
    "🔄 Follow up — explain how the product works": "follow_up_education",
    "🎁 Offer them a free 7-day trial": "trial_offer",
    "💡 Share a similar customer success story": "social_proof",
    "💰 Answer 'too expensive' concern": "objection_budget",
    "⏰ Answer 'not now' concern": "objection_timing",
    "📞 Phone call opening script": "phone_opener",
    "💬 Reply to someone who messaged you first": "reply_to_inbound",
}


# ===========================================================================
# MAIN ENTRY
# ===========================================================================
def main():
    if needs_onboarding() and st.session_state.page != "onboarding":
        st.session_state.page = "onboarding"

    if st.session_state.page == "onboarding":
        show_onboarding()
        return

    # Legacy deep-links: route old standalone pages through unified Operations
    legacy_to_ops = {"home": "today", "autopilot": "autopilot", "sales_bot": "sales_bot"}
    if st.session_state.page in legacy_to_ops:
        st.session_state.ops_subpage = legacy_to_ops[st.session_state.page]
        st.session_state.page = "operations"

    show_top_nav()

    # Postgres-fallback banner — only shows when Postgres is configured but unreachable
    try:
        import db_backend as _dbb
        unreachable = _dbb.get_pg_unreachable_reason()
        if unreachable:
            st.error(
                "⚠️ **Postgres database is unreachable — running on local SQLite "
                "fallback.** Data saved during this session will NOT persist across "
                "redeploys. Most likely cause: Supabase free-tier project paused "
                "from inactivity (log into supabase.com to wake it up), or password "
                "rotation needed. Detail: "
                f"`{unreachable.get('error', '?')[:160]}`"
            )
    except Exception:
        pass

    pages = {
        "operations": show_operations,
        "inbox": show_inbox,
        "customers": show_customers,
        "customer_detail": show_customer_detail,
        "send_message": show_send_message,
        "find_customers": show_find_customers,
        "add_customer": show_add_customer,
        "import_email": show_import_email,
        "audit": show_audit_log,
        "setup": show_setup,
        "admin": show_admin_console,
        "search": show_search_results,
    }
    pages.get(st.session_state.page, show_operations)()


def show_search_results():
    """Global search across leads, inbound messages, and drafts."""
    q = st.session_state.get('search_query', '').strip()
    st.markdown(f"## 🔍 Search results for: `{q}`" if q else "## 🔍 Search")

    if not q:
        st.caption("Type a search query in the top bar.")
        return

    results = database.global_search(q, limit_per_kind=25)
    n_leads = len(results['leads'])
    n_inbound = len(results['inbound'])
    n_drafts = len(results['drafts'])
    total = n_leads + n_inbound + n_drafts

    if total == 0:
        st.info(f"No matches for **{q}** across leads, inbox, or drafts.")
        return

    st.caption(f"{total} matches · {n_leads} leads · {n_inbound} messages · {n_drafts} drafts")
    st.markdown("---")

    if results['leads']:
        st.markdown(f"### 👥 Leads ({n_leads})")
        for lead in results['leads']:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{lead['business_name']}** — {lead.get('contact_name') or '—'}")
            c2.caption(
                f"{lead.get('business_type') or '?'} · "
                f"{lead.get('city') or ''} {lead.get('state') or ''} · "
                f"score {lead.get('lead_score') or 0}"
            )
            if c3.button("Open →", key=f"sr_lead_{lead['id']}", use_container_width=True):
                st.session_state.viewing_lead_id = lead['id']
                st.session_state.page = "customer_detail"
                st.rerun()

    if results['inbound']:
        st.markdown(f"### 📨 Inbox messages ({n_inbound})")
        for m in results['inbound']:
            sender = m.get('business_name') or m.get('from_name') or m['from_email']
            with st.container(border=True):
                c1, c2 = st.columns([6, 1])
                c1.markdown(f"**{sender}** · _{(m.get('subject') or '(no subject)')[:80]}_")
                c1.caption((m.get('body') or '')[:200].replace('\n', ' '))
                if c2.button("Open lead", key=f"sr_inb_{m['id']}",
                              use_container_width=True):
                    if m['lead_id']:
                        st.session_state.viewing_lead_id = m['lead_id']
                        st.session_state.page = "customer_detail"
                        st.rerun()

    if results['drafts']:
        st.markdown(f"### 📝 Drafts ({n_drafts})")
        for d in results['drafts']:
            sender = d.get('business_name') or '(unknown lead)'
            sent_label = "✓ sent" if d.get('sent') else "○ pending"
            st.markdown(
                f"**{sender}** · _{(d.get('subject') or '(no subject)')[:80]}_ · {sent_label}"
            )
            st.caption((d.get('content') or '')[:200].replace('\n', ' '))


# ============================================================================
# ADMIN — Joseph-only (or anyone whose email is in the admin allowlist).
# Lets him manage every team member's account, keys, and Aqua memory.
# ============================================================================
ROOT_ADMIN_EMAIL = 'joseph@aquelyst.com'  # cannot be removed — always admin


def is_root_admin(email=None):
    if email is None:
        try:
            import team as _team
            current = _team.get_current_user()
            email = (current.get('email') or '').lower()
        except Exception:
            return False
    return (email or '').lower() == ROOT_ADMIN_EMAIL


def is_admin():
    """Joseph is always admin. Anyone else needs an explicit grant in admin_users."""
    try:
        import team as _team
        current = _team.get_current_user()
        email = (current.get('email') or '').lower()
        if not email:
            return False
        if email == ROOT_ADMIN_EMAIL:
            return True
        return database.admin_is_granted(email)
    except Exception:
        return False


def show_admin_console():
    if not is_admin():
        st.error("🔒 Admin only. Joseph's email must be the connected SMTP email to access this page.")
        st.caption("If you're Joseph and seeing this, go to Setup → 📧 Email and connect joseph@aquelyst.com first.")
        return

    import team as _team
    st.html(
        "<div style='display:flex;align-items:center;gap:0.7rem;margin-bottom:1rem'>"
        "<div style='font-size:2rem'>🛡️</div>"
        "<div>"
        "<div style='font-size:0.8rem;color:#06b6d4;text-transform:uppercase;letter-spacing:0.08em;font-weight:700'>"
        "ADMIN CONSOLE</div>"
        "<div style='font-size:1.6rem;font-weight:800;color:#0a0f1c'>Run AqueLyst OS</div>"
        "</div></div>"
    )

    sections = st.tabs(["👥 Team", "🛡 Admins", "🔑 API Keys",
                          "🧠 Aqua Memory", "🗑 Junk Patterns",
                          "💬 Chat Logs", "📊 Usage", "🗄 Database"])

    with sections[0]:
        _admin_team_section()
    with sections[1]:
        _admin_admins_section()
    with sections[2]:
        _admin_keys_section()
    with sections[3]:
        _admin_memory_section()
    with sections[4]:
        _admin_junk_section()
    with sections[5]:
        _admin_chatlogs_section()
    with sections[6]:
        _admin_usage_section()
    with sections[7]:
        _admin_database_section()


def _admin_database_section():
    """Show backend status (SQLite vs Postgres) and migration instructions."""
    import db_backend
    st.markdown("##### Database backend")

    ok, kind, detail = db_backend.safe_test_connection()
    if ok:
        if kind == 'postgres':
            st.success(f"✅ **Postgres connected** — {detail}")
            st.caption("All data persists across redeploys. Multi-tenant ready.")
        else:
            st.warning(f"🟡 **{detail}**")
            st.caption(
                "Local SQLite — **does NOT persist on Streamlit Cloud redeploys**. "
                "Set `DATABASE_URL` in Streamlit Cloud secrets to switch to Postgres."
            )
    else:
        st.error(f"❌ {detail}")

    st.markdown("---")
    with st.expander("📖 How to switch this app to persistent Postgres (Supabase, ~10 min)",
                       expanded=(kind != 'postgres')):
        st.markdown("""
**Step 1 — create a free Supabase Postgres** (or use Neon, Render, etc.)

1. Go to **[https://supabase.com](https://supabase.com)** and sign up (free tier = 500MB, plenty for now)
2. Click **New project** → name it `aquelyst-os` → set a strong DB password → wait ~2 min while it spins up
3. In your project: **Settings → Database → Connection string → URI** — copy the long connection string. It looks like:

```
postgresql://postgres.xxxxxxxx:YOUR-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

**Step 2 — paste it into Streamlit Cloud secrets**

1. Open **[https://share.streamlit.io](https://share.streamlit.io)** → your `aquelyst-os` app → **⋮** → **Settings → Secrets**
2. Add this line to the existing block (replacing the value):

```toml
DATABASE_URL = "postgresql://postgres.xxxxxxxx:YOUR-PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
```

3. Save. The app reboots automatically.

**Step 3 — verify**

After the reboot, refresh this Admin → 🗄 Database tab. The status above should now read **✅ Postgres connected**.

**Step 4 (optional) — copy your existing local data into Postgres**

If you have leads/drafts/etc. on your Mac that you want to bring over, run this in your terminal:

```bash
cd "/Users/debraleblang/Desktop/AqueLyst-Hunter"
DATABASE_URL='postgresql://...your URL...' python3 migrate_to_postgres.py
```

It copies every row from your local SQLite to Postgres. Idempotent, safe to re-run.

---

**What changes after this:**
- Everyone's user accounts persist across redeploys (no more re-creating passwords)
- All shared baseline API keys persist (no more re-pasting)
- Aqua's memory + chat history persist
- Leads, drafts, inbox all persist
- The team can finally trust the cloud version with real data
        """)
        st.caption("ℹ️ Local SQLite continues to work for dev — the app auto-detects which backend to use based on whether `DATABASE_URL` is set.")


def _admin_junk_section():
    """Show what junk patterns Aqua has learned from team dismissals."""
    st.markdown("##### What Aqua learned from your 'Not real' clicks")
    st.caption("Each pattern blocks future inbound messages that match. "
                "Remove a pattern if it's causing false positives.")
    signals = database.get_junk_signals(limit=200)
    if not signals:
        st.caption("_No junk patterns yet. Hit '🗑 Not real' on spam in the Inbox tab "
                    "to teach Aqua._")
        return

    by_kind = {}
    for s in signals:
        by_kind.setdefault(s['kind'], []).append(s)

    for kind in ('sender_domain', 'sender_email', 'body_phrase', 'subject_keyword'):
        items = by_kind.get(kind, [])
        if not items:
            continue
        kind_label = {
            'sender_domain': 'Blocked sender domains',
            'sender_email': 'Blocked sender emails',
            'body_phrase': 'Spam body phrases',
            'subject_keyword': 'Suspicious subject keywords (need 2+ to flag)',
        }[kind]
        st.markdown(f"**{kind_label}**")
        for s in items:
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.markdown(f"`{s['value']}`")
            c2.caption(f"matched {s.get('match_count') or 0}× · "
                        f"learned {s['created_at'][:10]}")
            if c3.button("🗑", key=f"junk_pat_rm_{s['id']}",
                          help="Remove this pattern"):
                database.delete_junk_signal(s['id'])
                st.rerun()
        st.markdown("")


def _admin_admins_section():
    """Manage who has admin access. Only the ROOT admin (Joseph) can grant or revoke."""
    import team as _team
    st.markdown("##### Who can access this Admin Console")

    # Diagnostic: show who the system thinks is connected right now
    current = _team.get_current_user()
    detected_email = (current.get('email') or '').lower() or '(none — no email connected)'
    is_root = is_root_admin()
    st.caption(
        f"You are connected as: **`{detected_email}`** · "
        f"Root admin status: **{'✅ YES' if is_root else '❌ NO'}** · "
        f"Root admin email is hardcoded to: `{ROOT_ADMIN_EMAIL}`"
    )

    if not is_root:
        st.warning(
            "🔒 Only the root admin (Joseph) can grant or revoke admin access. "
            f"Your connected email is `{detected_email}` which doesn't match the root admin "
            f"email `{ROOT_ADMIN_EMAIL}`.  \n\n"
            "**To fix:** go to **Setup → 📧 Email**, disconnect any other email, "
            f"and connect `{ROOT_ADMIN_EMAIL}` instead."
        )
        granted = database.admin_list()
        st.markdown(f"**Root admin:** `{ROOT_ADMIN_EMAIL}`")
        if granted:
            for row in granted:
                st.caption(f"• `{row['user_email']}` — granted {row['created_at'][:16]}")
        return

    st.html(
        f"<div style='background:rgba(6,182,212,0.08);border-left:3px solid #06b6d4;"
        f"padding:0.7rem 1rem;border-radius:6px;margin-bottom:1rem'>"
        f"<strong style='color:#0a0f1c'>👑 Root admin:</strong> "
        f"<code>{ROOT_ADMIN_EMAIL}</code> (Joseph) — always admin, cannot be removed."
        f"</div>"
    )

    granted = database.admin_list()
    if granted:
        st.markdown("**Additional admins you've granted:**")
        for row in granted:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"`{row['user_email']}`")
            c2.caption(f"granted {row['created_at'][:16]} by {row.get('granted_by') or '?'}")
            if c3.button("Revoke", key=f"adm_revoke_{row['user_email']}"):
                database.admin_revoke(row['user_email'])
                st.success(f"Revoked admin from {row['user_email']}")
                st.rerun()
    else:
        st.caption("_Nobody else is currently an admin. You're the only one with access._")

    st.markdown("---")
    st.markdown("##### ➕ Grant admin access")
    members = _team.load_team()
    options = [('__custom__', 'Other email — type below')] + [
        (m['email'], f"{m.get('name', '?')} ({m['email']})")
        for m in members
        if m.get('email') and m['email'].lower() != ROOT_ADMIN_EMAIL
        and not database.admin_is_granted(m['email'].lower())
    ]
    with st.form("admin_grant_form", clear_on_submit=True):
        sel = st.selectbox("Who?", options, format_func=lambda o: o[1])
        custom_email = ""
        if sel and sel[0] == '__custom__':
            custom_email = st.text_input("Their email")
        if st.form_submit_button("👑 Grant admin", type="primary",
                                   use_container_width=True):
            target = (sel[0] if sel and sel[0] != '__custom__' else custom_email).strip().lower()
            if not target:
                st.error("Need an email.")
            elif target == ROOT_ADMIN_EMAIL:
                st.info("Joseph is already root admin.")
            else:
                if database.admin_grant(target, ROOT_ADMIN_EMAIL):
                    st.success(f"✅ Granted admin to {target}")
                    st.rerun()
                else:
                    st.warning(f"{target} already had admin.")


def _admin_team_section():
    import team as _team
    st.markdown("##### Team members")
    members = _team.load_team()
    for i, m in enumerate(members):
        c1, c2, c3, c4 = st.columns([2, 3, 1, 1])
        c1.markdown(f"**{m.get('name', '—')}**")
        c2.markdown(f"`{m.get('email', '—')}` · {m.get('role') or m.get('short_role') or '—'}")
        if c3.button("Reset PW", key=f"adm_resetpw_{i}",
                      help="Wipe their password — they set a new one on next login"):
            try:
                if m.get('email'):
                    database.user_delete_account(m['email'])
                    st.toast(f"Reset password for {m['email']}", icon="🔑")
                    st.rerun()
            except Exception as e:
                st.error(str(e))
        if c4.button("Remove", key=f"adm_rm_{i}"):
            try:
                _team.delete_member(i)
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.markdown("---")
    st.markdown("##### Add team member")
    with st.form("admin_add_member"):
        c1, c2, c3 = st.columns([2, 2, 2])
        n = c1.text_input("Full name")
        e = c2.text_input("Email")
        r = c3.text_input("Role")
        if st.form_submit_button("➕ Add"):
            if n and e:
                try:
                    _team.add_member(name=n, email=e, role=r or '')
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))


def _admin_keys_section():
    import team as _team

    PROVIDERS = [p['id'] for p in api_keys.PROVIDER_CATALOG]

    # ============================================================
    # ADD / REPLACE TEAM-MEMBER KEY ON THEIR BEHALF
    # ============================================================
    st.markdown("##### ➕ Add or replace a team member's personal key")
    st.caption("Use this to help someone (a co-founder, your mom, your sister) "
                "who can't paste their own key. Their key still rotates as theirs in the pool.")
    members = _team.load_team()
    member_options = [(m['email'], f"{m.get('name', '?')} ({m['email']})")
                       for m in members if m.get('email')]
    extra_option = ('__custom__', 'Other email — type below')
    member_options.append(extra_option)

    with st.form("admin_add_member_key", clear_on_submit=True):
        c1, c2 = st.columns(2)
        sel = c1.selectbox("Whose key is this?", member_options,
                            format_func=lambda o: o[1])
        prov = c2.selectbox("Provider", PROVIDERS)
        custom_email = ""
        if sel and sel[0] == '__custom__':
            custom_email = st.text_input("Their email")
        new_key = st.text_input("Paste their key", type="password",
                                 placeholder="csk-... / sk-ant-... / sk-... / gsk-...")
        label = st.text_input("Label (optional)", placeholder="e.g. Mom's account")
        submitted = st.form_submit_button("💾 Save key on their behalf",
                                            type="primary", use_container_width=True)
    if submitted:
        target_email = (sel[0] if sel and sel[0] != '__custom__' else custom_email).strip().lower()
        if not target_email or not new_key:
            st.error("Need both a target email and a key.")
        else:
            database.team_keys_save(target_email, prov, new_key.strip(), label=label or None)
            st.success(f"✅ Saved {prov} key for {target_email}")
            st.rerun()

    st.markdown("---")

    # ============================================================
    # CURRENT TEAM KEY POOL
    # ============================================================
    st.markdown("##### Every team key in the pool")
    rows = database.team_keys_list_all()
    if not rows:
        st.caption("_No team keys saved yet._")
    for r in rows:
        c1, c2, c3, c4 = st.columns([2, 1.5, 2.5, 0.8])
        c1.markdown(f"`{r['user_email']}`")
        c2.markdown(f"**{r['provider']}**")
        status_bits = [f"`{r['masked_key']}`"]
        if r.get('label'):
            status_bits.append(f"_{r['label']}_")
        if r.get('last_ok_at'):
            status_bits.append(f"✅ {r['last_ok_at'][:16]}")
        if r.get('last_err_at'):
            status_bits.append(f"⚠️ {r['last_err_at'][:16]}")
        c3.caption(" · ".join(status_bits))
        if c4.button("🗑", key=f"adm_keyrm_{r['user_email']}_{r['provider']}"):
            database.team_keys_delete(r['user_email'], r['provider'])
            st.rerun()

    st.markdown("---")

    # ============================================================
    # SHARED BASELINE KEYS — every provider with link, tier, live status
    # ============================================================
    st.markdown("##### 🌐 Shared baseline keys (team-wide fallback)")
    st.caption("Aqua tries providers in order — FREE tier first, PAID tier as backup. "
                "Adding multiple lets her keep working even if one's throttled.")

    # ── Live load distribution dashboard ────────────────────────────
    log_rows = database.provider_log_all()
    used = [(r['provider'], r.get('total_requests') or 0,
              r.get('ok_requests') or 0, r.get('err_requests') or 0)
             for r in log_rows if (r.get('total_requests') or 0) > 0]
    if used:
        total_all = sum(t for _, t, _, _ in used) or 1
        st.markdown("**📊 Load distribution (since last reset)**")
        cols = st.columns(len(used))
        for col, (pid, total, ok, err) in zip(cols, used):
            pct = round(100 * total / total_all)
            success_pct = round(100 * ok / total) if total else 0
            color = '#16a34a' if success_pct >= 90 else '#f59e0b' if success_pct >= 60 else '#dc2626'
            col.markdown(
                f"<div style='text-align:center;padding:0.4rem 0.2rem'>"
                # Conic-gradient ring — arc length = % of load, color = health
                f"<div style='width:88px;height:88px;border-radius:50%;"
                f"background:conic-gradient({color} 0% {pct}%, "
                f"rgba(15,23,42,0.08) {pct}% 100%);"
                f"display:flex;align-items:center;justify-content:center;"
                f"margin:0 auto 0.55rem;"
                f"box-shadow:0 1px 3px rgba(15,23,42,0.06)'>"
                # Inner white circle creates the donut hole + holds request count
                f"<div style='width:64px;height:64px;border-radius:50%;"
                f"background:#ffffff;display:flex;flex-direction:column;"
                f"align-items:center;justify-content:center'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.15rem;"
                f"font-weight:700;color:{color};line-height:1'>{total}</div>"
                f"<div style='font-size:0.55rem;color:#94a3b8;"
                f"text-transform:uppercase;letter-spacing:0.08em;"
                f"margin-top:0.15rem'>req</div>"
                f"</div></div>"
                # Provider name + load % + health below
                f"<div style='font-size:0.72rem;color:#64748b;text-transform:uppercase;"
                f"letter-spacing:0.06em;font-weight:700'>{pid}</div>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.25rem;"
                f"font-weight:700;color:#0a0f1c;margin-top:0.15rem;line-height:1'>"
                f"{pct}%</div>"
                f"<div style='font-size:0.65rem;color:#94a3b8;margin-top:0.1rem'>"
                f"of load</div>"
                f"<div style='font-size:0.7rem;color:{color};font-weight:600;"
                f"margin-top:0.25rem'>{success_pct}% ok</div>"
                f"</div>", unsafe_allow_html=True
            )
        if st.button("Reset counters", key="reset_load_counters"):
            conn = database.get_connection()
            conn.execute('UPDATE provider_connection_log SET total_requests = 0, '
                          'ok_requests = 0, err_requests = 0')
            conn.commit()
            conn.close()
            st.rerun()
        st.markdown("")

    # ── Health Check All ───────────────────────────────────────────
    hc_col1, hc_col2 = st.columns([3, 1])
    hc_col1.markdown(
        "**🔬 Run a live test on every connected provider** so you know nothing's broken."
    )
    if hc_col2.button("🔬 Health Check All", type="primary",
                       use_container_width=True, key="adm_health_check_all"):
        with st.spinner("Testing every connected provider..."):
            results = []
            for prov_meta in api_keys.PROVIDER_CATALOG:
                pid = prov_meta['id']
                if not api_keys.has_key(pid):
                    continue
                ok, msg, model = api_keys.test_provider_connection(pid)
                results.append((prov_meta['name'], pid, ok, msg, model))
            st.session_state['_health_check_results'] = results

    if st.session_state.get('_health_check_results'):
        st.markdown("**Latest health check results:**")
        for name, pid, ok, msg, model in st.session_state['_health_check_results']:
            if ok:
                st.success(f"✅ **{name}** working — model `{model}`")
            else:
                st.error(f"❌ **{name}** broken — {msg[:200]}")
        if st.button("Clear results", key="hc_clear"):
            st.session_state.pop('_health_check_results', None)
            st.rerun()
        st.markdown("")

    # Persistence warning — Streamlit Cloud's filesystem is ephemeral
    import cloud_mode as _cm
    if _cm.is_cloud():
        # If admin just saved a key, surface the persistence step VERY prominently
        just_saved = st.session_state.get('just_saved_baseline')
        if just_saved:
            meta = api_keys.get_provider_meta(just_saved) or {'name': just_saved}
            saved_key = api_keys.get_key(just_saved) or ''
            env_name = f"{just_saved.upper()}_API_KEY"
            st.error(
                f"⚠️ **{meta['name']} key saved BUT will vanish on next Streamlit Cloud redeploy.**  \n\n"
                "Streamlit Cloud's filesystem is ephemeral — keys live in container memory only. "
                "**To make it permanent right now**, copy this one line into "
                "Streamlit Cloud → ⋮ → Settings → Secrets (add to existing block):"
            )
            st.code(f'{env_name} = "{saved_key}"', language='toml')
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ I pasted it into Streamlit secrets", key="dismiss_save_warn",
                           type="primary", use_container_width=True):
                st.session_state.pop('just_saved_baseline', None)
                st.rerun()
            cc2.caption("Or skip if you'll re-add the key after each redeploy.")
            st.markdown("---")

        st.warning(
            "⚠️ **Streamlit Cloud has an ephemeral filesystem.** "
            "Keys saved here work for this container's lifetime, but get **wiped on each redeploy**. "
            "After saving, paste the **TOML snippet** at the bottom of this page into "
            "Streamlit Cloud → Settings → Secrets to make them permanent.  \n"
            "_(Persistent storage via Postgres is the next major upgrade — coming soon.)_"
        )

    for prov_meta in api_keys.PROVIDER_CATALOG:
        pid = prov_meta['id']
        k = api_keys.get_key(pid)
        log = database.provider_log_get(pid) or {}
        with st.container(border=True):
            top = st.columns([3, 1, 2])
            top[0].markdown(f"**{prov_meta['name']}**")
            tier_label = prov_meta['tier']
            tier_color = prov_meta['tier_color']
            top[1].markdown(
                f"<span style='background:{tier_color};color:white;"
                f"padding:0.2rem 0.6rem;border-radius:10px;font-size:0.72rem;"
                f"font-weight:700;letter-spacing:0.05em'>{tier_label}</span>",
                unsafe_allow_html=True
            )
            top[2].markdown(
                f"[**🔗 Get key →**]({prov_meta['keys_url']})",
                help=f"Sign up at {prov_meta['signup_url']} then create an API key."
            )
            st.caption(prov_meta['note'])

            # Provider-specific guidance
            if pid == 'groq':
                st.info(
                    "**Groq ToS note:** Free tier is intended for individual development use. "
                    "**Don't pool one Groq key across multiple humans.** Best practice: "
                    "each team member adds their OWN Groq key via Setup → AI (personal keys). "
                    "A single shared baseline key here is fine for admin/testing only."
                )

            # Live connection status
            status_line = ""
            if k and log.get('last_ok_at'):
                status_line = f"✅ Last verified working · {log['last_ok_at'][:16]}"
            elif k and log.get('last_err_at'):
                status_line = f"⚠️ Last test failed at {log['last_err_at'][:16]} — `{(log.get('last_err') or '')[:80]}`"
            elif k:
                status_line = "🟡 Saved but never tested — click 'Test now' below"

            row = st.columns([3, 1, 1, 1])
            if k:
                masked = k[:8] + "..." + k[-4:] if len(k) > 12 else k
                row[0].markdown(f"`{masked}`")
                if row[1].button("🧪 Test", key=f"adm_baseline_test_{pid}"):
                    with st.spinner(f"Testing {prov_meta['name']}..."):
                        ok, msg, model = api_keys.test_provider_connection(pid)
                        if ok:
                            st.success(f"✅ {prov_meta['name']} working (model: `{model}`)")
                        else:
                            st.error(f"❌ {prov_meta['name']} failed: {msg}")
                    st.rerun()
                if row[2].button("🗑", key=f"adm_baseline_rm_{pid}"):
                    api_keys.delete_key(pid)
                    st.rerun()
                if status_line:
                    st.caption(status_line)
            else:
                with row[0].popover("➕ Add key", use_container_width=True):
                    placeholder = (prov_meta['key_prefix'] + '...') if prov_meta['key_prefix'] else 'paste key'
                    new_k = st.text_input(f"{prov_meta['name']} key",
                                           type="password",
                                           placeholder=placeholder,
                                           key=f"adm_baseline_input_{pid}")
                    if st.button("Save & test", key=f"adm_baseline_save_{pid}",
                                  type="primary", use_container_width=True):
                        if new_k.strip():
                            with st.spinner(f"Saving + testing {prov_meta['name']}..."):
                                # Test FIRST, only save if it works
                                ok, msg, model = api_keys.test_provider_connection(
                                    pid, override_key=new_k.strip()
                                )
                                if ok:
                                    api_keys.set_key(pid, new_k.strip())
                                    if _cm.is_cloud():
                                        st.session_state['just_saved_baseline'] = pid
                                    st.success(
                                        f"✅ {prov_meta['name']} key saved + verified "
                                        f"(model: `{model}`)"
                                    )
                                    st.rerun()
                                else:
                                    st.error(
                                        f"❌ Key didn't work — NOT saved. "
                                        f"Reason: {msg}"
                                    )

    # ============================================================
    # LEAD DISCOVERY KEYS (different category — for autopilot, not for chat)
    # ============================================================
    st.markdown("---")
    st.markdown("##### 🔍 Lead Discovery API keys (for Autopilot)")
    st.caption("These power Autopilot's web-search and place-data sources. "
                "Each adds a new lane of leads.")

    DISCOVERY_PROVIDERS = [
        {
            'id': 'foursquare',
            'name': 'Foursquare Places',
            'tier': 'FREE',
            'tier_color': '#16a34a',
            'note': 'Comprehensive places database. Free 50/day or 1000/day with Places Pro.',
            'keys_url': 'https://foursquare.com/developers/apps',
            'signup_url': 'https://foursquare.com/developers',
            'key_prefix': '',
        },
        {
            'id': 'brave',
            'name': 'Brave Search',
            'tier': 'FREEMIUM',
            'tier_color': '#06b6d4',
            'note': 'Fast independent search index. 2000 free queries/month.',
            'keys_url': 'https://api.search.brave.com/app/keys',
            'signup_url': 'https://brave.com/search/api/',
            'key_prefix': 'BSA',
        },
        {
            'id': 'sam_gov',
            'name': 'SAM.gov',
            'tier': 'FREE',
            'tier_color': '#16a34a',
            'note': 'Federal contract opportunities (RFPs, RFQs, sources-sought) — required for the Bid Intelligence tab. Free key from GSA.',
            'keys_url': 'https://open.gsa.gov/api/get-opportunities-public-api/',
            'signup_url': 'https://sam.gov/content/api',
            'key_prefix': '',
        },
    ]
    for prov in DISCOVERY_PROVIDERS:
        pid = prov['id']
        k = api_keys.get_key(pid)
        with st.container(border=True):
            top = st.columns([3, 1, 2])
            top[0].markdown(f"**{prov['name']}**")
            top[1].markdown(
                f"<span style='background:{prov['tier_color']};color:white;"
                f"padding:0.2rem 0.6rem;border-radius:10px;font-size:0.72rem;"
                f"font-weight:700;letter-spacing:0.05em'>{prov['tier']}</span>",
                unsafe_allow_html=True
            )
            top[2].markdown(f"[**🔗 Get key →**]({prov['keys_url']})")
            st.caption(prov['note'])
            row = st.columns([5, 1])
            if k:
                masked = k[:8] + "..." + k[-4:] if len(k) > 12 else k
                row[0].markdown(f"✅ Connected · `{masked}`")
                if row[1].button("🗑", key=f"adm_disc_rm_{pid}"):
                    api_keys.delete_key(pid)
                    st.rerun()
            else:
                with row[0].popover("➕ Add key", use_container_width=True):
                    nk = st.text_input(f"{prov['name']} key", type="password",
                                        placeholder=prov['key_prefix'] + '...' if prov['key_prefix'] else 'paste key',
                                        key=f"adm_disc_input_{pid}")
                    if st.button("Save", key=f"adm_disc_save_{pid}",
                                  type="primary", use_container_width=True):
                        if nk.strip():
                            api_keys.set_key(pid, nk.strip())
                            st.success(f"✅ Saved {prov['name']} key")
                            st.rerun()

    # ============================================================
    # PERMANENT-PERSISTENCE HELPER (Streamlit Cloud ephemeral fix)
    # ============================================================
    st.markdown("---")
    with st.expander("🔐 Make these keys permanent across Streamlit Cloud restarts"):
        st.markdown(
            "Streamlit Cloud wipes the local filesystem on every redeploy / sleep cycle. "
            "To make your saved keys survive restarts, paste the block below into "
            "**Streamlit Cloud → ⋮ → Settings → Secrets → Save**.  \n\n"
            "Once that's saved, the app reads keys from `st.secrets` first (which is permanent)."
        )

        # Build a TOML block of all currently-saved baseline keys
        toml_lines = []
        existing_secrets = {}
        try:
            existing_secrets['TEAM_PASSWORD'] = st.secrets.get('TEAM_PASSWORD', '')
            existing_secrets['CLOUD_DEPLOYMENT'] = st.secrets.get('CLOUD_DEPLOYMENT', True)
            existing_secrets['WEB3FORMS_KEY'] = st.secrets.get('WEB3FORMS_KEY', '')
        except Exception:
            pass

        if existing_secrets.get('TEAM_PASSWORD'):
            toml_lines.append(f'TEAM_PASSWORD = "{existing_secrets["TEAM_PASSWORD"]}"')
        for prov_meta in api_keys.PROVIDER_CATALOG:
            kk = api_keys.get_key(prov_meta['id'])
            if kk:
                env_name = f"{prov_meta['id'].upper()}_API_KEY"
                toml_lines.append(f'{env_name} = "{kk}"')
        if existing_secrets.get('WEB3FORMS_KEY'):
            toml_lines.append(f'WEB3FORMS_KEY = "{existing_secrets["WEB3FORMS_KEY"]}"')
        toml_lines.append('CLOUD_DEPLOYMENT = true')

        st.code("\n".join(toml_lines), language='toml')
        st.caption(
            "📋 Copy the entire block above → in Streamlit Cloud open Settings → Secrets → "
            "paste it (replacing whatever's there) → Save. Done."
        )


def _admin_memory_section():
    st.markdown("##### What Aqua remembers about each team member")
    import team as _team
    members = _team.load_team()
    for m in members:
        email = (m.get('email') or '').lower()
        facts = database.aqua_get_user_facts(email, limit=100) if email else []
        if not facts:
            continue
        with st.expander(f"**{m.get('name')}** — {len(facts)} facts"):
            for f in facts:
                st.caption(f"• {f['fact']}  _(saved {f['created_at'][:16]})_")

    st.markdown("---")
    if st.button("🧹 Clear ALL Aqua memory across team", type="secondary"):
        st.session_state['confirm_clear_memory'] = True
    if st.session_state.get('confirm_clear_memory'):
        st.warning("Are you sure? This wipes every fact Aqua has learned about everyone.")
        cc1, cc2 = st.columns(2)
        if cc1.button("Yes, wipe it", type="primary"):
            for m in _team.load_team():
                if m.get('email'):
                    database.aqua_clear_chat(m['email'].lower())
            conn = database.get_connection()
            conn.execute('DELETE FROM aqua_user_memory')
            conn.commit()
            conn.close()
            st.session_state.pop('confirm_clear_memory', None)
            st.success("Wiped.")
            st.rerun()
        if cc2.button("Cancel"):
            st.session_state.pop('confirm_clear_memory', None)
            st.rerun()


def _admin_chatlogs_section():
    st.markdown("##### Chat history per team member")
    import team as _team
    members = _team.load_team()
    options = [(m['email'], m['name']) for m in members if m.get('email')]
    if not options:
        st.caption("_No team members configured._")
        return
    selected = st.selectbox("Pick a member", options, format_func=lambda o: f"{o[1]} ({o[0]})")
    if selected:
        history = database.aqua_get_chat_history(selected[0], limit=200)
        if not history:
            st.caption("_No chat history yet._")
        for msg in history:
            who = "**You**" if msg['role'] == 'user' else "**Aqua**"
            ts = (msg.get('created_at') or '')[:16]
            st.markdown(f"{who} _{ts}_  \n> {msg['content'][:400]}")
            st.markdown("")
        if history:
            if st.button(f"🗑 Wipe {selected[1]}'s chat history",
                         key=f"adm_wipe_chat_{selected[0]}"):
                database.aqua_clear_chat(selected[0])
                st.rerun()


def _admin_usage_section():
    conn = database.get_connection()
    c = conn.cursor()

    c.execute('SELECT COUNT(*) as n FROM leads')
    total_leads = c.fetchone()['n']
    c.execute('SELECT COUNT(*) as n FROM outreach_drafts WHERE sent = 1')
    total_sent = c.fetchone()['n']
    c.execute('SELECT COUNT(*) as n FROM outreach_drafts WHERE sent = 0')
    total_drafts = c.fetchone()['n']
    c.execute('SELECT COUNT(*) as n FROM inbound_messages')
    total_inbound = c.fetchone()['n']
    c.execute('SELECT COUNT(*) as n FROM aqua_chat_log')
    total_chat = c.fetchone()['n']
    c.execute('SELECT COUNT(*) as n FROM team_api_keys')
    total_keys = c.fetchone()['n']

    cols = st.columns(3)
    cols[0].metric("📇 Total leads", total_leads)
    cols[1].metric("📤 Sent emails", total_sent)
    cols[2].metric("📨 Inbound messages", total_inbound)

    cols2 = st.columns(3)
    cols2[0].metric("📝 Pending drafts", total_drafts)
    cols2[1].metric("💬 Aqua chat turns", total_chat)
    cols2[2].metric("🔑 Team keys in pool", total_keys)

    st.markdown("---")
    st.markdown("##### Per-member chat activity")
    c.execute('''SELECT user_email, COUNT(*) as n FROM aqua_chat_log
                 GROUP BY user_email ORDER BY n DESC''')
    for row in c.fetchall():
        st.caption(f"`{row['user_email']}` — {row['n']} messages with Aqua")

    conn.close()


def show_operations():
    """Unified Operations hub: Today / Autopilot / Sales Bot / Bids in one place."""
    sub = st.session_state.setdefault('ops_subpage', 'today')

    sub_cols = st.columns([1, 1, 1, 1, 4])
    options = [
        ('today', '🏠 Today'),
        ('autopilot', '🤖 Autopilot'),
        ('sales_bot', '🎯 Sales Bot'),
        ('bids', '💰 Bids'),
    ]
    for i, (key, label) in enumerate(options):
        with sub_cols[i]:
            is_active = sub == key
            if st.button(label, key=f"ops_sub_{key}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.ops_subpage = key
                st.rerun()

    st.markdown("")

    if sub == 'autopilot':
        show_autopilot()
    elif sub == 'sales_bot':
        show_sales_bot()
    elif sub == 'bids':
        show_bid_opportunities()
    else:
        show_home()


def show_bid_opportunities():
    """💰 Bid Opportunities — federal procurement intelligence."""
    import bid_intelligence

    ui_kit.page_hero(
        title="Federal contracts matching "
               "<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>AqueLyst products</span>",
        subtitle="Pulls active SAM.gov opportunities, scores them against AqueLyst's "
                  "NAICS + keyword profile, and surfaces the highest-fit bids for your "
                  "team to pursue.",
        eyebrow="💰 BID INTELLIGENCE",
    )

    api_key = api_keys.get_key('sam_gov')
    if not api_key:
        st.warning(
            "⚠️ **SAM.gov API key required.** Get a free one at "
            "[open.gsa.gov/api/get-opportunities-public-api](https://open.gsa.gov/api/get-opportunities-public-api/) "
            "→ paste it in **🛡 Admin → 🔑 API Keys → Lead Discovery → SAM.gov** → "
            "come back here."
        )
        return

    # Stats summary cards
    stats = database.bid_opportunities_stats()
    cols = st.columns(4)
    cols[0].metric("📋 Total opportunities", stats['total'])
    cols[1].metric("✨ New", stats['new'])
    cols[2].metric("🔥 Hot (score ≥ 60)", stats['hot'])
    cols[3].metric("Products covered", len(stats['by_product']))

    # Search controls
    with st.container(border=True):
        st.markdown("##### 🔍 Pull bids from SAM.gov")
        rc1, rc2, rc3 = st.columns([2, 2, 2])
        days_back = rc1.selectbox(
            "Look back (days)", [7, 14, 30, 60, 90, 180, 365], index=2,
            key="bid_days_back",
            help="Larger window = more results but slower."
        )
        min_score = rc2.slider(
            "Min match score to keep", 10, 80, 25, 5,
            key="bid_min_score",
            help="Lower = more (noisier) results. 25 is a good starting point."
        )
        custom_kw = rc3.text_input(
            "Custom keyword (optional)",
            placeholder="e.g. 'horse stable' or 'CAFO'",
            key="bid_custom_kw",
            help="Add your own phrase to the search alongside the built-ins."
        )

        if st.button("🔄 Refresh from SAM.gov", type="primary",
                      use_container_width=True, key="refresh_bids"):
            progress_msgs = []
            with st.spinner("Querying SAM.gov across multiple PSC codes, "
                              "NAICS codes, and keyword angles… (~30s)"):
                opps, err = bid_intelligence.discover_bid_opportunities(
                    api_key=api_key, days=days_back,
                    min_score=min_score,
                    custom_keyword=custom_kw.strip() if custom_kw else None,
                    on_progress=lambda m: progress_msgs.append(m),
                )
            with st.expander(f"📋 Query trace ({len(progress_msgs)} steps)",
                              expanded=False):
                for m in progress_msgs:
                    st.caption(m)
            if err:
                st.error(f"❌ {err}")
            else:
                added = sum(database.save_bid_opportunity(o) for o in opps)
                if opps:
                    st.success(
                        f"✅ Found {len(opps)} scored opportunities — "
                        f"{added} new, {len(opps) - added} already in your CRM."
                    )
                else:
                    st.warning(
                        "🟡 SAM.gov returned 0 matches at score ≥ "
                        f"{min_score}. Try: (1) lower the min match score, "
                        "(2) widen the look-back to 90 or 180 days, "
                        "(3) add a custom keyword above. "
                        "Federal bids matching AqueLyst products are real but "
                        "fairly niche — typical hit rates are 5-30 per refresh."
                    )

    st.markdown("---")

    # Filters
    f1, f2, f3 = st.columns(3)
    PRODUCT_OPTIONS = ['All', 'Duo Equine', 'Pets', 'SpillMaster', 'AMR',
                       'HouseHold', 'Inversion Misting']
    product_filter = f1.selectbox("Filter by product", PRODUCT_OPTIONS,
                                   key="bid_product_filter")
    status_filter = f2.selectbox("Filter by status",
                                  ['All', 'new', 'reviewing', 'pursuing',
                                   'won', 'lost', 'dismissed'],
                                  key="bid_status_filter")
    sort_score_min = f3.slider("Show only score ≥", 0, 100, 25, 5,
                                key="bid_show_min_score")

    opps = database.get_bid_opportunities(
        product_filter=None if product_filter == 'All' else product_filter,
        status_filter=None if status_filter == 'All' else status_filter,
        min_score=sort_score_min,
        limit=300,
    )

    if not opps:
        st.info("_No opportunities yet. Click **🔄 Refresh from SAM.gov** above to start._")
        return

    st.markdown(f"### 📋 {len(opps)} opportunities (highest fit first)")
    for opp in opps[:50]:
        _render_bid_opportunity_card(opp)


def _render_bid_opportunity_card(opp):
    score = opp.get('match_score') or 0
    score_color = '#16a34a' if score >= 70 else '#f59e0b' if score >= 50 else '#94a3b8'
    deadline = opp.get('deadline') or ''
    deadline_short = deadline[:10] if deadline else 'no deadline'
    posted_short = (opp.get('posted_at') or '')[:10]
    product = opp.get('product_fit') or 'unmatched'
    status = opp.get('status') or 'new'
    status_color = {'new': '#06b6d4', 'reviewing': '#f59e0b',
                     'pursuing': '#16a34a', 'won': '#16a34a',
                     'lost': '#94a3b8', 'dismissed': '#94a3b8'}.get(status, '#94a3b8')

    title = (opp.get('title') or '(no title)')[:120]
    agency = opp.get('agency') or '(unknown agency)'

    with st.expander(f"🎯 **{score}** · {product} · {title} · _{agency}_"):
        # Top metadata row
        st.html(
            f"<div style='display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.6rem'>"
            f"<span style='background:{score_color};color:white;padding:0.2rem 0.7rem;"
            f"border-radius:10px;font-size:0.78rem;font-weight:700'>SCORE {score}</span>"
            f"<span style='background:#4d7c0f;color:white;padding:0.2rem 0.7rem;"
            f"border-radius:10px;font-size:0.78rem;font-weight:700'>{product.upper()}</span>"
            f"<span style='background:{status_color};color:white;padding:0.2rem 0.7rem;"
            f"border-radius:10px;font-size:0.78rem;font-weight:700'>{status.upper()}</span>"
            f"<span style='color:#64748b;font-size:0.8rem'>NAICS {opp.get('naics') or '?'}</span>"
            f"<span style='color:#64748b;font-size:0.8rem'>📍 {opp.get('place') or 'nationwide'}</span>"
            f"<span style='color:#64748b;font-size:0.8rem'>📅 posted {posted_short}</span>"
            f"<span style='color:#dc2626;font-size:0.8rem;font-weight:600'>"
            f"⏰ deadline {deadline_short}</span>"
            f"</div>"
        )

        if opp.get('match_reasoning'):
            st.html(
                f"<div style='background:#fef9e7;border-left:3px solid #f59e0b;"
                f"padding:0.5rem 0.8rem;border-radius:0 6px 6px 0;font-size:0.85rem;"
                f"color:#78350f;margin-bottom:0.6rem'>"
                f"<strong>Why this matched:</strong> {opp['match_reasoning']}"
                f"</div>"
            )

        # Description
        desc = opp.get('description') or ''
        if desc:
            st.markdown("**Description:**")
            st.markdown(desc[:2000] + ("..." if len(desc) > 2000 else ""))

        # Contact info
        st.markdown("---")
        st.markdown("**Contact / Point of Contact:**")
        contact_bits = []
        if opp.get('contact_name'):
            contact_bits.append(f"👤 {opp['contact_name']}")
        if opp.get('contact_email'):
            contact_bits.append(f"✉️ `{opp['contact_email']}`")
        if opp.get('contact_phone'):
            contact_bits.append(f"📞 {opp['contact_phone']}")
        if contact_bits:
            st.markdown(" · ".join(contact_bits))
        else:
            st.caption("_No POC listed in the SAM.gov record._")

        # Actions
        st.markdown("---")
        # Open-link uses link_button so it actually navigates in a new tab
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        url = opp.get('url') or '#'
        with ac1:
            st.link_button("🌐 Open on SAM.gov", url, use_container_width=True)
        if ac2.button("📥 Add to CRM as lead", key=f"bid_to_crm_{opp['id']}",
                       use_container_width=True):
            if opp.get('contact_email'):
                try:
                    biz_name = opp.get('agency') or (opp.get('title') or '')[:80]
                    pain = f"Federal RFP for {product.lower()}-related work"
                    notes = (
                        f"From SAM.gov bid {opp.get('external_id')}\n\n"
                        f"Title: {opp.get('title')}\n"
                        f"Agency: {opp.get('agency')}\n"
                        f"Deadline: {opp.get('deadline')}\n"
                        f"URL: {opp.get('url')}\n\n"
                        f"{(opp.get('description') or '')[:1500]}"
                    )
                    lead_id = database.add_lead(
                        business_name=biz_name,
                        contact_name=opp.get('contact_name') or None,
                        email=opp.get('contact_email'),
                        phone=opp.get('contact_phone') or None,
                        business_type=f"federal procurement ({opp.get('naics', '')})",
                        lead_source='bid_intelligence',
                        product_fit=opp.get('product_fit'),
                        pain_hypothesis=pain,
                        message=opp.get('match_reasoning'),
                        notes=notes,
                    )
                    if lead_id:
                        # Score the lead with the bid's match score
                        try:
                            database.update_lead(lead_id, lead_score=int(score),
                                                 status='interested')
                        except Exception:
                            pass
                        database.update_bid_opportunity(opp['id'], status='pursuing')
                        st.success(f"✅ Added to CRM as lead #{lead_id}")
                        st.rerun()
                    else:
                        st.warning("Lead with that email is already in CRM.")
                except Exception as e:
                    st.error(f"Couldn't add to CRM: {e}")
            else:
                st.error("No contact email on this bid — can't auto-create a CRM lead.")
        if ac3.button("👀 Mark reviewing", key=f"bid_review_{opp['id']}",
                       use_container_width=True):
            database.update_bid_opportunity(opp['id'], status='reviewing')
            st.rerun()
        if ac4.button("🗑 Dismiss", key=f"bid_dismiss_{opp['id']}",
                       use_container_width=True):
            database.update_bid_opportunity(opp['id'], status='dismissed')
            st.rerun()
        if ac5.button("❌ Delete", key=f"bid_delete_{opp['id']}",
                       use_container_width=True):
            database.delete_bid_opportunity(opp['id'])
            st.rerun()


# ===========================================================================
# TOP NAV (5 buttons, plain English)
# ===========================================================================
def show_top_nav():
    import team as _team
    current = _team.get_current_user()
    user_name = current.get('name', 'Not logged in')
    user_role = current.get('short_role') or current.get('role', '')
    is_known = not current.get('_unknown', False)

    badge_color = '#4d7c0f' if is_known else '#9ca3af'
    role_html = (f"<span style='opacity:0.85;font-weight:400'> · {user_role}</span>"
                 if user_role else "")

    # st.container() gives this row its own stVerticalBlock — combined with
    # the empty marker div, mobile CSS can :has() select it specifically to
    # reshape (hide search, keep logo + signout side-by-side).
    with st.container():
        st.markdown('<div class="aqp-toprow-marker"></div>',
                     unsafe_allow_html=True)
        top_left, top_search, top_right = st.columns([3, 3, 1])
        top_left.html(
            "<div style='display:flex;align-items:center;gap:0.8rem;padding:0.2rem 0'>"
            f"{ui_kit.brand_wordmark(size='md', with_mark=True)}"
            f"<span style='font-family:JetBrains Mono,monospace;font-size:0.66rem;"
            f"color:#94a3b8;letter-spacing:0.20em;text-transform:uppercase;"
            f"font-weight:700;align-self:center'>OS</span>"
            f"<span style='background:{badge_color};color:white;padding:0.25rem 0.8rem;"
            f"border-radius:12px;font-weight:600;font-size:0.85rem;align-self:center'>"
            f"{user_name}{role_html}"
            f"</span></div>"
        )
        with top_search:
            sq = st.text_input(
                "Global search", value=st.session_state.get('search_query', ''),
                placeholder="🔍 Search leads, inbox, drafts…",
                label_visibility="collapsed", key="search_input",
            )
            if sq and sq.strip() and sq.strip() != st.session_state.get('search_query', ''):
                st.session_state.search_query = sq.strip()
                st.session_state.page = "search"
                st.rerun()
        if top_right.button("🚪 Sign out", key="signout_btn",
                             use_container_width=True):
            st.session_state.pop('logged_in_user_email', None)
            st.session_state.pop('team_password_ok', None)
            st.rerun()

    st.markdown("<div style='border-bottom:1px solid rgba(148,163,184,0.10);"
                 "margin:0 0 0.6rem 0'></div>", unsafe_allow_html=True)

    nav_items = [
        ("🚀 Operations", "operations"),
        ("📬 Inbox", "inbox"),
        ("👥 Customers", "customers"),
        ("✉️ Compose", "send_message"),
        ("📋 Audit", "audit"),
        ("⚙️ Setup", "setup"),
    ]
    if is_admin():
        nav_items.append(("🛡 Admin", "admin"))
    # Same container pattern — mobile CSS :has() selects this row for its own
    # 2-col grid layout instead of the global force-stack rule.
    with st.container():
        st.markdown('<div class="aqp-navrow-marker"></div>',
                     unsafe_allow_html=True)
        cols = st.columns(len(nav_items))
        for col, (label, page_id) in zip(cols, nav_items):
            with col:
                is_active = st.session_state.page == page_id or (
                    page_id == "customers" and st.session_state.page == "customer_detail"
                )
                if st.button(label, key=f"nav_{page_id}",
                             use_container_width=True,
                             type="primary" if is_active else "secondary"):
                    st.session_state.page = page_id
                    if page_id != "customer_detail":
                        st.session_state.pop('viewing_lead_id', None)
                    if page_id != "send_message":
                        st.session_state.pop('message_lead_id', None)
                        st.session_state.pop('draft', None)
                    st.rerun()
    st.markdown("---")


# ===========================================================================
# ONBOARDING WIZARD (5 forced steps)
# ===========================================================================
def show_onboarding():
    step = st.session_state.onboarding_step
    total_steps = 5

    st.title("👋 Welcome to AqueLyst Hunter")
    st.progress(min(step / total_steps, 1.0),
                text=f"Setup: Step {min(step + 1, total_steps)} of {total_steps}")
    st.markdown("")

    if step == 0:
        st.markdown("### Let's get you set up to start selling Duo Equine.")
        st.markdown("""
        This takes about **5 minutes**. We'll walk you through:

        1. ✉️  Connect your email *(so you can send messages)*
        2. 🧠  Connect AI *(so messages are written for you)*
        3. 🌐  Get your website form ready *(so customers can reach you)*
        4. 🐎  Add some sample customers *(to play around)*
        5. 🎉  You're done!

        You can skip any step and finish later in **Setup**.
        """)
        col1, col2 = st.columns([2, 1])
        if col1.button("Let's start →", type="primary", use_container_width=True):
            st.session_state.onboarding_step = 1
            st.rerun()
        if col2.button("Skip all setup", use_container_width=True):
            st.session_state.onboarding_done = True
            st.session_state.page = "home"
            st.rerun()

    elif step == 1:
        onboard_email()
    elif step == 2:
        onboard_ai()
    elif step == 3:
        onboard_website()
    elif step == 4:
        onboard_samples()
    else:
        onboard_done()


def onboard_email():
    st.markdown("### Step 1 — Connect Your Email")
    st.markdown("This is the email address your customers will see when you reach out.")
    st.markdown("")

    if smtp_sender.is_configured():
        cfg = smtp_sender.load_smtp_config()
        st.success(f"✅ Already connected: **{cfg['email']}**")
        if st.button("Continue to Step 2 →", type="primary", use_container_width=True):
            st.session_state.onboarding_step = 2
            st.rerun()
        return

    email = st.text_input(
        "What email do you want to send from?",
        value="joseph@aquelyst.com",
        placeholder="joseph@aquelyst.com",
        help="This will appear in the 'From' field of every email"
    )

    if email and email_helpers.is_valid_email(email):
        provider = email_helpers.detect_provider(email)
        instructions = email_helpers.get_setup_instructions(provider)

        st.info(f"📍 Detected: **{instructions['title']}** · Setup time: {instructions['time_estimate']}")

        st.markdown("##### How to get your App Password:")
        st.markdown("""
        Email providers don't let apps use your real password.
        Instead, you create an **App Password** — a special 16-character code just for this app.
        """)

        for line in instructions['steps']:
            st.markdown(line)

        st.markdown(f"### 👉 [Click here to create your App Password]({instructions['app_password_url']})")
        st.caption("This opens in a new tab. Sign in, create the password, then come back here.")

        st.markdown("---")
        st.markdown("##### Paste your App Password below:")

        app_pw = st.text_input(
            "App Password (16 characters)",
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
            help="Paste the password Google/Outlook gave you. It's NOT your regular password."
        )

        col1, col2 = st.columns(2)
        if col1.button("Connect My Email", type="primary", use_container_width=True):
            if not app_pw:
                st.error("Paste the App Password first")
            else:
                with st.spinner("Connecting..."):
                    success, msg = smtp_sender.test_smtp_connection(provider, email, app_pw.replace(' ', ''))
                    if success:
                        smtp_sender.save_smtp_config(
                            provider, email, app_pw.replace(' ', ''),
                            "Joseph at AqueLyst"
                        )
                        st.balloons()
                        st.success("✅ Email connected!")
                        st.session_state.onboarding_step = 2
                        st.rerun()
                    else:
                        st.error(translate_smtp_error(msg))

        if col2.button("Skip for now", use_container_width=True):
            st.session_state.onboarding_step = 2
            st.rerun()


def onboard_ai():
    st.markdown("### Step 2 — Connect AI (Recommended)")
    st.markdown("AI writes personalized messages for each customer. **Cerebras is free and fast.**")
    st.markdown("")

    if api_keys.has_key('cerebras') or api_keys.has_key('claude'):
        st.success("✅ AI already connected")
        if st.button("Continue to Step 3 →", type="primary", use_container_width=True):
            st.session_state.onboarding_step = 3
            st.rerun()
        return

    st.markdown("##### Get a free Cerebras API Key:")
    st.markdown("""
    1. Click the link below
    2. Sign up (free, no credit card required)
    3. Click **API Keys** → **Create Key**
    4. Copy the key (starts with `csk-`)
    5. Paste it below
    """)

    st.markdown("### 👉 [Get your free Cerebras API Key](https://cloud.cerebras.ai)")

    st.markdown("---")
    key = st.text_input(
        "Paste your Cerebras key below:",
        type="password",
        placeholder="csk-..."
    )

    col1, col2 = st.columns(2)
    if col1.button("Connect AI", type="primary", use_container_width=True):
        if key:
            api_keys.set_key('cerebras', key.strip())
            with st.spinner("Testing your key..."):
                success, msg = ai_providers.test_provider('cerebras')
                if success:
                    st.balloons()
                    st.success("✅ Cerebras AI connected!")
                    st.session_state.onboarding_step = 3
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
        else:
            st.warning("Paste your key first")

    if col2.button("Skip — use templates", use_container_width=True):
        st.session_state.onboarding_step = 3
        st.rerun()


def onboard_website():
    st.markdown("### Step 3 — Your Website Contact Form")
    st.markdown("When customers visit AqueLyst.com and fill out a form, they'll show up here automatically.")
    st.markdown("")

    st.success("✅ Your website form is already built and configured!")

    st.markdown("##### What to do next:")
    st.markdown("""
    1. The form file is ready: `web3forms_template.html`
    2. Upload it to AqueLyst.com (or copy the HTML into your contact page)
    3. When someone fills it out, you'll get an email
    4. Paste that email into the **Customers** tab → leads are created automatically

    **Don't worry about this now — you can do it later from the Setup tab.**
    """)

    if st.button("Continue to Step 4 →", type="primary", use_container_width=True):
        st.session_state.onboarding_step = 4
        st.rerun()


def onboard_samples():
    st.markdown("### Step 4 — Try It With Sample Customers")
    st.markdown("Want us to load 10 fake horse barn customers so you can play around?")
    st.markdown("")

    has_leads = len(database.get_all_leads()) > 0
    if has_leads:
        st.info(f"You already have {len(database.get_all_leads())} customers in the system")
        if st.button("Continue →", type="primary", use_container_width=True):
            st.session_state.onboarding_step = 5
            st.rerun()
        return

    col1, col2 = st.columns(2)
    if col1.button("✅ Yes, load 10 samples", type="primary", use_container_width=True):
        with st.spinner("Adding sample customers..."):
            seed_sample_data()
            st.balloons()
            st.success("✅ Loaded! 10 sample horse barn customers ready.")
        st.session_state.onboarding_step = 5
        st.rerun()

    if col2.button("Skip — start empty", use_container_width=True):
        st.session_state.onboarding_step = 5
        st.rerun()


def onboard_done():
    st.balloons()
    st.markdown("# 🎉 You're All Set!")
    st.markdown("")

    # Show what got connected
    smtp_ok = smtp_sender.is_configured()
    ai_ok = api_keys.has_key('cerebras') or api_keys.has_key('claude')
    has_leads = len(database.get_all_leads()) > 0

    st.markdown("##### What's connected:")
    st.markdown(f"- {'✅' if smtp_ok else '⚠️'} Email " + ("(ready to send)" if smtp_ok else "(skipped — set up in Setup tab)"))
    st.markdown(f"- {'✅' if ai_ok else '⚠️'} AI " + ("(ready to write)" if ai_ok else "(skipped — using templates)"))
    st.markdown(f"- ✅ Website form (ready to receive customers)")
    st.markdown(f"- {'✅' if has_leads else '⚠️'} Sample customers " + ("(loaded)" if has_leads else "(skipped)"))

    st.markdown("---")
    st.markdown("##### What you can do next:")
    st.markdown("""
    - 🏠  **Today** — See what needs your attention
    - 👥  **Customers** — Browse all your customers
    - ✉️  **Send Message** — Write to a customer
    - 🔍  **Find New** — Discover horse barns to reach out to
    - ⚙️  **Setup** — Change settings anytime
    """)

    if st.button("Take me to my dashboard →", type="primary", use_container_width=True):
        st.session_state.onboarding_done = True
        st.session_state.page = "home"
        st.rerun()


# ===========================================================================
# HOME (Today)
# ===========================================================================
def show_home():
    _et_now = ui_kit.now_et()
    hour = _et_now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    today_short = _et_now.strftime("%a · %d %b %Y").upper()
    now_time = _et_now.strftime("%H:%M ET")

    stats = database.get_dashboard_stats()
    ap_state = autopilot.get_state()
    ap_running = ap_state.get('running', False)

    # Personalize greeting with the logged-in user's first name
    user_first = "team"
    try:
        u = team.get_current_user()
        if u and u.get('name'):
            user_first = u['name'].split()[0]
    except Exception:
        pass

    # ========== FUTURISTIC HERO (dark glass, cyan accents) ==========
    if stats['hot_leads'] > 0:
        pulse_color = '#ef4444'
        pipeline_text = (
            f"<strong style='color:#fb923c'>{stats['hot_leads']} hot</strong> "
            f"need{'s' if stats['hot_leads']==1 else ''} outreach"
        )
    elif stats['follow_ups_due'] > 0:
        pulse_color = '#f59e0b'
        s = '' if stats['follow_ups_due'] == 1 else 's'
        pipeline_text = (
            f"<strong style='color:#f59e0b'>{stats['follow_ups_due']} "
            f"follow-up{s}</strong> due"
        )
    else:
        pulse_color = '#10b981'
        pipeline_text = "pipeline caught up · time to hunt"

    ap_status = (
        '<span style="color:#10b981">● live</span>' if ap_running
        else '<span style="color:#64748b">○ idle</span>'
    )

    st.markdown(f"""
    <style>
        @keyframes aqp-pulse {{
            0%,100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.45; transform: scale(0.92); }}
        }}
    </style>
    <div style='position:relative;
                background:linear-gradient(135deg,#0a0f1c 0%,#0f172a 55%,#0a1f24 100%);
                border-radius:18px;padding:1.7rem 2.1rem;margin-bottom:1.5rem;
                border:1px solid rgba(6,182,212,0.20);
                box-shadow:0 10px 30px rgba(6,182,212,0.07),
                            inset 0 1px 0 rgba(255,255,255,0.04);
                overflow:hidden'>
        <div style='position:absolute;inset:0;pointer-events:none;
                    background-image:
                        radial-gradient(circle at 12% 0%, rgba(6,182,212,0.10) 0%, transparent 38%),
                        radial-gradient(circle at 100% 100%, rgba(26,95,63,0.10) 0%, transparent 42%),
                        linear-gradient(rgba(6,182,212,0.04) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(6,182,212,0.04) 1px, transparent 1px);
                    background-size: auto, auto, 32px 32px, 32px 32px'></div>
        <div style='position:relative;display:flex;justify-content:space-between;
                    align-items:center;font-family:JetBrains Mono,monospace;
                    font-size:0.66rem;letter-spacing:0.22em;color:#64748b;
                    text-transform:uppercase;margin-bottom:1.4rem;font-weight:700'>
            <span>◢ AQUELYST OS · TODAY</span>
            <span>{today_short} · {now_time}</span>
        </div>
        <div style='position:relative;display:flex;justify-content:space-between;
                    align-items:flex-end;flex-wrap:wrap;gap:1.6rem'>
            <div>
                <div style='font-size:2.4rem;font-weight:700;color:#e2e8f0;
                            letter-spacing:-0.02em;line-height:1.05'>
                    {greeting}, <span style='background:linear-gradient(135deg,#06b6d4,#a3e635);
                                              -webkit-background-clip:text;
                                              -webkit-text-fill-color:transparent;
                                              background-clip:text'>{user_first}</span>.
                </div>
                <div style='color:#94a3b8;margin-top:0.55rem;font-size:0.95rem;
                            display:flex;align-items:center;gap:0.55rem'>
                    <span style='display:inline-block;width:9px;height:9px;border-radius:50%;
                                 background:{pulse_color};
                                 box-shadow:0 0 14px {pulse_color};
                                 animation:aqp-pulse 2s infinite'></span>
                    {pipeline_text}
                </div>
                <div style='color:#475569;margin-top:0.45rem;font-size:0.74rem;
                            font-family:JetBrains Mono,monospace;letter-spacing:0.06em'>
                    autopilot {ap_status}
                </div>
            </div>
            <div style='display:flex;gap:1.1rem;align-items:center'>
                <div style='text-align:right;padding:0 0.3rem'>
                    <div style='font-family:JetBrains Mono,monospace;font-size:1.7rem;
                                font-weight:700;color:#e2e8f0;line-height:1'>
                        {stats['total_leads']}
                    </div>
                    <div style='font-size:0.62rem;color:#64748b;text-transform:uppercase;
                                letter-spacing:0.10em;font-weight:600;margin-top:0.3rem'>
                        Total leads
                    </div>
                </div>
                <div style='width:1px;height:38px;background:linear-gradient(180deg,
                            transparent,#06b6d4,transparent)'></div>
                <div style='text-align:right;padding:0 0.3rem'>
                    <div style='font-family:JetBrains Mono,monospace;font-size:1.7rem;
                                font-weight:700;color:#10b981;line-height:1'>
                        {stats['closed_won']}
                    </div>
                    <div style='font-size:0.62rem;color:#64748b;text-transform:uppercase;
                                letter-spacing:0.10em;font-weight:600;margin-top:0.3rem'>
                        Closed
                    </div>
                </div>
                <div style='width:1px;height:38px;background:linear-gradient(180deg,
                            transparent,#06b6d4,transparent)'></div>
                <div style='text-align:right;padding:0 0.3rem'>
                    <div style='font-family:JetBrains Mono,monospace;font-size:1.7rem;
                                font-weight:700;color:#06b6d4;line-height:1'>
                        {stats['conversion_rate']}%
                    </div>
                    <div style='font-size:0.62rem;color:#64748b;text-transform:uppercase;
                                letter-spacing:0.10em;font-weight:600;margin-top:0.3rem'>
                        Win rate
                    </div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ========== AUTOPILOT MINI LIVE WIDGET (always visible) ==========
    _home_autopilot_widget()

    if stats['total_leads'] == 0:
        # ========== EMPTY STATE — push autopilot hard ==========
        st.markdown("""
        <div style='background:#fff;border:2px dashed #4d7c0f;border-radius:14px;
                    padding:2.5rem 2rem;text-align:center;margin-bottom:1rem'>
            <div style='font-size:3.5rem'>🤖</div>
            <h2 style='color:#4d7c0f !important;margin:0.5rem 0'>
                Your CRM is empty. Let's fix that in 2 minutes.
            </h2>
            <p style='color:#6c757d;font-size:1.05rem;max-width:500px;margin:0.5rem auto 1.5rem'>
                Autopilot scrapes the open web for horse barns, has Cerebras AI read each website,
                qualifies each lead, and writes personalized cold emails — automatically.
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Launch Autopilot", type="primary", use_container_width=True):
            st.session_state.page = "autopilot"
            st.rerun()

        st.markdown("##### Or add leads manually:")
        col1, col2 = st.columns(2)
        if col1.button("➕ Add One Customer", use_container_width=True):
            st.session_state.page = "add_customer"
            st.rerun()
        if col2.button("🔍 Browse Google Maps", use_container_width=True):
            st.session_state.page = "find_customers"
            st.rerun()
        return

    # 3 simple metrics
    col1, col2, col3 = st.columns(3)
    # ========== KPI CARDS (auto-refresh every 30s) ==========
    _home_kpi_fragment()
    st.markdown("")

    # ========== "DO THIS NOW" CARD ==========
    next_action_lead = None
    next_action_label = None
    next_action_button = None

    if stats['follow_ups_due'] > 0:
        due = database.get_follow_ups_due()
        if due:
            next_action_lead = due[0]
            next_action_label = "📅 Follow up today"
            next_action_button = ("Open customer →", "customer_detail")
    elif stats['hot_leads'] > 0:
        hot = database.get_hot_leads()
        if hot:
            next_action_lead = hot[0]
            next_action_label = "🔥 Your hottest lead"
            next_action_button = ("Send them a message →", "send_message")

    if next_action_lead:
        lead = next_action_lead
        score = lead['lead_score'] or 0
        location = (
            f"{lead['city']}, {lead['state']}"
            if lead['city'] and lead['state']
            else lead['city'] or lead['state'] or 'Location unknown'
        )
        st.markdown(f"""
        <div style='position:relative;
                    background:linear-gradient(135deg,
                        rgba(6,182,212,0.07) 0%,
                        rgba(15,23,42,0.02) 100%);
                    border:1px solid rgba(6,182,212,0.30);
                    border-radius:14px;padding:1.4rem 1.8rem;
                    margin-bottom:1.2rem;
                    box-shadow:0 4px 24px rgba(6,182,212,0.08)'>
            <div style='font-size:0.68rem;color:#06b6d4;text-transform:uppercase;
                        letter-spacing:0.18em;font-weight:700;
                        font-family:JetBrains Mono,monospace;
                        display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem'>
                <span style='display:inline-block;width:6px;height:6px;border-radius:50%;
                             background:#06b6d4;box-shadow:0 0 10px #06b6d4;
                             animation:aqp-pulse 2s infinite'></span>
                ◢ {next_action_label}
            </div>
            <h2 style='margin:0 0 0.3rem;color:#0f172a !important;
                       font-size:1.55rem;font-weight:700;letter-spacing:-0.01em'>
                {lead['business_name']}
            </h2>
            <div style='color:#475569;font-size:0.92rem'>
                {lead['contact_name'] or 'No contact name'} · {location} ·
                Match score
                <strong style='color:#0f172a;font-family:JetBrains Mono,monospace'>{score}/100</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])
        action_label, action_page = next_action_button
        if col1.button(action_label, type="primary", use_container_width=True):
            if action_page == "customer_detail":
                st.session_state.viewing_lead_id = lead['id']
            elif action_page == "send_message":
                st.session_state.message_lead_id = lead['id']
            st.session_state.page = action_page
            st.rerun()
        if col2.button("Browse all", use_container_width=True):
            st.session_state.page = "customers"
            st.rerun()
    else:
        st.markdown(f"""
        <div style='position:relative;
                    background:linear-gradient(135deg,
                        rgba(16,185,129,0.07) 0%,
                        rgba(15,23,42,0.02) 100%);
                    border:1px solid rgba(16,185,129,0.32);
                    border-radius:14px;padding:1.4rem 1.8rem;
                    text-align:center;margin-bottom:1.2rem'>
            <div style='font-size:0.68rem;color:#10b981;text-transform:uppercase;
                        letter-spacing:0.18em;font-weight:700;
                        font-family:JetBrains Mono,monospace;margin-bottom:0.5rem'>
                ◢ ALL CLEAR
            </div>
            <h3 style='color:#0f172a !important;margin:0.2rem 0;
                       font-weight:700;letter-spacing:-0.01em'>You're caught up.</h3>
            <div style='color:#475569;font-size:0.92rem'>
                No urgent tasks — find more leads or work the pipeline.
            </div>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        if col1.button("🤖 Hunt new leads with Autopilot", type="primary", use_container_width=True):
            st.session_state.page = "autopilot"
            st.rerun()
        if col2.button("👥 Browse customers", use_container_width=True):
            st.session_state.page = "customers"
            st.rerun()

    # Section divider — futuristic cyan accent
    st.markdown("""
    <div style='display:flex;align-items:center;gap:0.8rem;margin:1.6rem 0 0.6rem'>
        <div style='font-family:JetBrains Mono,monospace;font-size:0.68rem;
                    letter-spacing:0.20em;color:#475569;text-transform:uppercase;
                    font-weight:700'>◢ Pipeline Telemetry</div>
        <div style='flex:1;height:1px;background:linear-gradient(90deg,
                    rgba(6,182,212,0.35) 0%,rgba(6,182,212,0) 100%)'></div>
    </div>
    """, unsafe_allow_html=True)

    # ========== DASHBOARD VISUALIZATIONS ==========
    _today_dashboard_charts()

    # Section divider
    st.markdown("""
    <div style='display:flex;align-items:center;gap:0.8rem;margin:1.6rem 0 0.6rem'>
        <div style='font-family:JetBrains Mono,monospace;font-size:0.68rem;
                    letter-spacing:0.20em;color:#475569;text-transform:uppercase;
                    font-weight:700'>◢ Live Intelligence</div>
        <div style='flex:1;height:1px;background:linear-gradient(90deg,
                    rgba(6,182,212,0.35) 0%,rgba(6,182,212,0) 100%)'></div>
    </div>
    """, unsafe_allow_html=True)

    # ========== TOP LEADS GALLERY + ACTIVITY ==========
    col_left, col_right = st.columns([3, 2])

    with col_left:
        ui_kit.section_header('TOP HOT LEADS', accent='#a3e635')
        hot_leads = database.get_hot_leads()[:5]
        if hot_leads:
            for l in hot_leads:
                score = l['lead_score'] or 0
                # Brand-aligned score band: lime (90+), amber (80-89), orange (70-79)
                ring = ('#a3e635' if score >= 90
                        else '#f59e0b' if score >= 80
                        else '#fb923c')
                contact = l['contact_name'] or 'No contact'
                loc_parts = [p for p in (l['city'], l['state']) if p]
                location = ', '.join(loc_parts) or 'Location unknown'

                hook = ''
                if l['notes'] and '💡 Hook:' in l['notes']:
                    hook = l['notes'].split('💡 Hook:')[1].split('\n')[0].strip()[:140]
                hook_block = (
                    f"<div style='margin-top:0.55rem;font-size:0.85rem;"
                    f"color:#cbd5e1;border-left:2px solid {ring}99;"
                    f"padding:0.1rem 0 0.1rem 0.65rem;font-style:italic;"
                    f"line-height:1.45'>💡 {hook}…</div>"
                    if hook else ""
                )

                st.markdown(f"""
                <div style='position:relative;
                            background:rgba(15,23,42,0.55);
                            border:1px solid {ring}40;
                            border-radius:14px;padding:1.0rem 1.2rem;
                            margin-bottom:0.6rem;
                            backdrop-filter:blur(12px);
                            -webkit-backdrop-filter:blur(12px);
                            box-shadow:0 4px 14px rgba(15,23,42,0.20)'>
                    <div style='display:flex;justify-content:space-between;
                                align-items:flex-start;gap:1rem'>
                        <div style='flex:1;min-width:0'>
                            <div style='font-weight:700;color:#e2e8f0;
                                        font-size:1.05rem;letter-spacing:-0.01em;
                                        white-space:nowrap;overflow:hidden;
                                        text-overflow:ellipsis'>
                                {l['business_name']}
                            </div>
                            <div style='color:#94a3b8;font-size:0.85rem;
                                        margin-top:0.22rem'>
                                {contact} · {location}
                            </div>
                            {hook_block}
                        </div>
                        <!-- Score ring (matches the KPI rings + provider rings) -->
                        <div style='flex-shrink:0;width:56px;height:56px;
                                    border-radius:50%;
                                    background:conic-gradient({ring} 0% {score}%,
                                                              rgba(148,163,184,0.10) {score}% 100%);
                                    display:flex;align-items:center;
                                    justify-content:center;
                                    box-shadow:0 0 14px {ring}55'>
                            <div style='width:40px;height:40px;border-radius:50%;
                                        background:#0a0f1c;display:flex;
                                        align-items:center;justify-content:center'>
                                <div style='font-family:JetBrains Mono,monospace;
                                            font-weight:800;font-size:0.95rem;
                                            color:{ring};line-height:1'>{score}</div>
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Small right-aligned Open button (no more giant full-width button)
                _spacer, _btn = st.columns([3, 1])
                if _btn.button("Open →", key=f"home_lead_{l['id']}",
                                use_container_width=True):
                    st.session_state.viewing_lead_id = l['id']
                    st.session_state.page = "customer_detail"
                    st.rerun()
        else:
            st.markdown("""
            <div style='background:rgba(15,23,42,0.40);
                        border:1px dashed rgba(163,230,53,0.32);
                        border-radius:14px;padding:2.2rem 2rem;text-align:center;
                        color:#94a3b8;backdrop-filter:blur(8px);
                        -webkit-backdrop-filter:blur(8px)'>
                <div style='font-size:1.9rem;opacity:0.55'>🎯</div>
                <div style='margin-top:0.55rem;color:#e2e8f0;font-weight:700;
                            letter-spacing:-0.01em'>No hot leads yet</div>
                <div style='font-size:0.85rem;margin-top:0.3rem;color:#64748b'>
                    Run Autopilot to find some.
                </div>
            </div>
            """, unsafe_allow_html=True)

    with col_right:
        ui_kit.section_header('ACTIVITY · 30s', accent='#06b6d4')
        _home_activity_fragment()


@st.fragment(run_every=30)
def _inbox_status_fragment():
    """4 INTERACTIVE status cards — counts navigate, toggle cards toggle bots."""
    sent = database.get_sent_drafts(limit=500)
    pending = database.get_pending_drafts(limit=500)
    watcher_running = email_responder.is_running()
    engagement_running = auto_engagement.is_running()

    cols = st.columns(4)

    # SENT BY BOT — clickable to navigate to Sent
    with cols[0]:
        st.html(
            "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px 12px 0 0;padding:0.85rem 1rem 0.4rem;text-align:center'>"
            f"<div style='font-size:1.8rem;font-weight:800;color:#0ea5e9;line-height:1'>{len(sent)}</div>"
            "<div style='font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-top:0.3rem'>"
            "📤 Sent by Bot</div></div>"
        )
        if st.button("View sent →", key="inbox_card_sent", use_container_width=True):
            st.session_state.page = "send_message"
            st.session_state.compose_subtab = "sent"
            st.rerun()

    # DRAFTS PENDING — clickable card jumps straight to drafts tab
    with cols[1]:
        st.html(
            "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px 12px 0 0;padding:0.85rem 1rem 0.4rem;text-align:center'>"
            f"<div style='font-size:1.8rem;font-weight:800;color:#f59e0b;line-height:1'>{len(pending)}</div>"
            "<div style='font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-top:0.3rem'>"
            "📝 Drafts Pending</div></div>"
        )
        if st.button(f"Review {len(pending)} draft{'s' if len(pending) != 1 else ''} →",
                     key="inbox_card_drafts", use_container_width=True,
                     type="primary" if len(pending) > 0 else "secondary"):
            st.session_state.page = "send_message"
            st.session_state.compose_subtab = "drafts"
            st.rerun()

    # INBOX WATCHER — clickable TOGGLE
    with cols[2]:
        watcher_color = '#16a34a' if watcher_running else '#dc2626'
        watcher_bg = '#dcfce7' if watcher_running else '#fef2f2'
        watcher_label = '🟢 WATCHING' if watcher_running else '🔴 OFF'
        watcher_icon = '👁️‍🗨️' if watcher_running else '👁'

        # Surface last-checked + next-check so user can SEE the watcher polling
        sub_line = ""
        if watcher_running:
            try:
                wstate = email_responder.get_state() or {}
                last_run = wstate.get('last_run')
                next_check = wstate.get('next_check')
                if last_run:
                    sub_line = f"last {format_date_friendly(last_run)}"
                if next_check:
                    sub_line += f" · next {format_date_friendly(next_check)}"
            except Exception:
                pass

        st.html(
            f"<div style='background:{watcher_bg};border:2px solid {watcher_color};border-radius:12px 12px 0 0;padding:0.85rem 1rem 0.4rem;text-align:center'>"
            f"<div style='font-size:1.5rem'>{watcher_icon}</div>"
            f"<div style='font-size:0.95rem;font-weight:800;color:{watcher_color};margin-top:0.2rem'>{watcher_label}</div>"
            f"<div style='font-size:0.65rem;color:#64748b;font-weight:500;margin-top:0.2rem;height:0.85rem'>{sub_line}</div>"
            f"<div style='font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-top:0.2rem'>"
            f"Inbox Watcher (every 5min)</div></div>"
        )
        toggle_label = "Click to STOP" if watcher_running else "Click to START"
        if st.button(toggle_label, key="inbox_card_watcher_toggle", use_container_width=True):
            if watcher_running:
                email_responder.stop_responder()
            else:
                email_responder.start_responder(check_interval_minutes=5, auto_reply_mode='draft')
            st.rerun()

    # AUTO-ENGAGEMENT — clickable TOGGLE
    with cols[3]:
        # Read user's preferred mode (auto-send vs draft) from session
        eng_auto_send = st.session_state.get('engagement_auto_send', True)
        cfg = (auto_engagement.get_state() or {}).get('config', {})
        running_auto_send = cfg.get('auto_send', False) if engagement_running else None

        eng_color = '#16a34a' if engagement_running else '#dc2626'
        eng_bg = '#dcfce7' if engagement_running else '#fef2f2'
        if engagement_running:
            mode_text = '🚀 AUTO-SEND' if running_auto_send else '✍️ DRAFTING'
        else:
            mode_text = '🔴 OFF'
        st.html(
            f"<div style='background:{eng_bg};border:2px solid {eng_color};border-radius:12px 12px 0 0;padding:0.85rem 1rem 0.4rem;text-align:center'>"
            f"<div style='font-size:1.5rem'>🚀</div>"
            f"<div style='font-size:0.85rem;font-weight:800;color:{eng_color};margin-top:0.2rem'>{mode_text}</div>"
            f"<div style='font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-top:0.2rem'>"
            f"Auto-Engagement</div></div>"
        )
        if not engagement_running:
            # Mode picker shown BEFORE start so user picks intent explicitly
            new_auto_send = st.checkbox(
                "Auto-send (no approval)",
                value=eng_auto_send,
                key="engagement_auto_send_inline",
                help="If checked, Aqua actually sends emails. If unchecked, "
                     "she only drafts and waits for your approval.",
            )
            st.session_state['engagement_auto_send'] = new_auto_send
            if st.button("▶️ START", key="inbox_card_engagement_toggle",
                          use_container_width=True, type="primary"):
                auto_engagement.start_engagement(
                    min_score=70,
                    auto_send=new_auto_send,
                    check_interval_minutes=15,
                    max_per_run=5,
                    follow_up_enabled=True,
                )
                st.rerun()
        else:
            if st.button("⏸ STOP", key="inbox_card_engagement_toggle",
                          use_container_width=True):
                auto_engagement.stop_engagement()
                auto_engagement.update_state(running=False, config={})
                st.rerun()


def _glass_chart(title, body_html, stat_html='', accent='#06b6d4'):
    """Glass-card wrapper for a chart panel. Mono ◢ title left, optional stat right."""
    stat_block = (
        f"<div style='font-family:JetBrains Mono,monospace;font-size:0.85rem;"
        f"color:#e2e8f0;font-weight:700'>{stat_html}</div>"
        if stat_html else ""
    )
    return (
        f"<div style='background:rgba(15,23,42,0.55);"
        f"border:1px solid rgba(148,163,184,0.12);border-radius:14px;"
        f"padding:1.1rem 1.3rem 1.0rem;backdrop-filter:blur(12px);"
        f"-webkit-backdrop-filter:blur(12px);margin-bottom:1.0rem;"
        f"box-shadow:0 4px 18px rgba(15,23,42,0.20)'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:center;margin-bottom:0.85rem'>"
        f"<div style='font-family:JetBrains Mono,monospace;font-size:0.68rem;"
        f"color:{accent};letter-spacing:0.18em;text-transform:uppercase;"
        f"font-weight:700'>◢ {title}</div>"
        f"{stat_block}</div>{body_html}</div>"
    )


def _sparkline_svg(values, color='#06b6d4', width=320, height=48):
    """Single-line sparkline with a gradient fill underneath."""
    if not values:
        return (
            f"<div style='height:{height}px;display:flex;align-items:center;"
            f"justify-content:center;color:#64748b;font-size:0.82rem'>"
            f"no data yet</div>"
        )
    max_v = max(values) or 1
    n = len(values)
    pts = []
    fill_pts = [f"0,{height}"]
    for i, v in enumerate(values):
        x = round(i * width / max(1, n - 1), 1)
        y = round(height - (v / max_v) * (height - 6) - 3, 1)
        pts.append(f"{x},{y}")
        fill_pts.append(f"{x},{y}")
    fill_pts.append(f"{width},{height}")
    line = ' '.join(pts)
    fill = ' '.join(fill_pts)
    grad_id = f"sg_{color.lstrip('#')}"
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" style="display:block;overflow:visible">'
        f'<defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.45"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{fill}" fill="url(#{grad_id})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _dual_sparkline_svg(values_a, values_b, color_a='#06b6d4', color_b='#a3e635',
                          width=320, height=48):
    """Two overlaid sparklines (same Y-scale for honest comparison)."""
    if not values_a and not values_b:
        return _sparkline_svg([])
    max_v = max(max(values_a or [0]), max(values_b or [0])) or 1
    n = max(len(values_a or []), len(values_b or []))

    def _polyline(values, color):
        if not values:
            return ''
        pts = []
        for i, v in enumerate(values):
            x = round(i * width / max(1, n - 1), 1)
            y = round(height - (v / max_v) * (height - 6) - 3, 1)
            pts.append(f"{x},{y}")
        return (f'<polyline points="{" ".join(pts)}" fill="none" '
                f'stroke="{color}" stroke-width="2" stroke-linejoin="round" '
                f'stroke-linecap="round"/>')

    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" style="display:block;overflow:visible">'
        f'{_polyline(values_a, color_a)}'
        f'{_polyline(values_b, color_b)}'
        f'</svg>'
    )


def _today_dashboard_charts():
    """Pipeline telemetry — futuristic dark cards with custom SVG/HTML
    visualizations. All queries are dual-backend safe (no SQLite-only date math)."""
    from collections import Counter
    from datetime import date, timedelta

    # ===== Pipeline funnel — full-width horizontal bars =====
    all_leads = database.get_all_leads()
    status_counts = Counter(l['status'] for l in all_leads if l['status'])
    funnel_order = [
        ('new',           '🆕 New',           '#67e8f9'),
        ('researched',    '📚 Researched',    '#22d3ee'),
        ('drafted',       '✏️ Draft ready',   '#06b6d4'),
        ('contacted',     '📞 Contacted',     '#bef264'),
        ('interested',    '⭐ Interested',    '#a3e635'),
        ('trial_offered', '🎁 Trial offered', '#84cc16'),
        ('sample_sent',   '📦 Sample sent',   '#65a30d'),
        ('closed_won',    '✅ Won',           '#10b981'),
    ]
    funnel_active = [(l, status_counts.get(s, 0), c)
                      for s, l, c in funnel_order
                      if status_counts.get(s, 0) > 0]
    total_in_flight = sum(c for _, c, _ in funnel_active)
    max_in_funnel = max((c for _, c, _ in funnel_active), default=1)

    if funnel_active:
        bars_html = ""
        for label, count, color in funnel_active:
            pct = round(100 * count / max_in_funnel)
            bars_html += (
                f"<div style='display:flex;align-items:center;gap:0.8rem;"
                f"margin-bottom:0.5rem'>"
                f"<div style='flex:0 0 140px;font-size:0.82rem;color:#cbd5e1;"
                f"font-weight:600'>{label}</div>"
                f"<div style='flex:1;height:9px;"
                f"background:rgba(148,163,184,0.10);border-radius:999px;"
                f"overflow:hidden;position:relative'>"
                f"<div style='height:100%;width:{pct}%;"
                f"background:linear-gradient(90deg,{color}aa,{color});"
                f"border-radius:999px;box-shadow:0 0 10px {color}66'></div>"
                f"</div>"
                f"<div style='flex:0 0 32px;text-align:right;"
                f"font-family:JetBrains Mono,monospace;color:#e2e8f0;"
                f"font-weight:700;font-size:0.92rem'>{count}</div>"
                f"</div>"
            )
        funnel_stat = (f"{total_in_flight} <span style='color:#64748b;"
                        f"font-size:0.7rem;letter-spacing:0.10em;"
                        f"text-transform:uppercase;font-weight:600'>in flight</span>")
    else:
        bars_html = (
            "<div style='color:#64748b;font-size:0.88rem;padding:0.5rem 0'>"
            "No pipeline data yet — start adding customers.</div>"
        )
        funnel_stat = ""

    st.markdown(_glass_chart(
        title='PIPELINE FUNNEL',
        stat_html=funnel_stat,
        body_html=bars_html,
    ), unsafe_allow_html=True)

    # ===== 14-day activity sparkline + Email volume — dual sparkline =====
    cutoff = (datetime.utcnow() - timedelta(days=14)).strftime('%Y-%m-%d %H:%M:%S')
    days = [(date.today() - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]

    activity_values, activity_total = [0] * 14, 0
    try:
        conn = database.get_connection()
        cur = conn.cursor()
        cur.execute('''SELECT DATE(created_at) as day, COUNT(*) as count
                       FROM activities WHERE created_at >= ?
                       GROUP BY DATE(created_at) ORDER BY day''', (cutoff,))
        counts = {str(r['day'])[:10]: r['count'] for r in cur.fetchall()}
        conn.close()
        activity_values = [counts.get(d, 0) for d in days]
        activity_total = sum(activity_values)
    except Exception:
        pass

    sent_values, recv_values, sent_total, recv_total = [0]*14, [0]*14, 0, 0
    try:
        conn = database.get_connection()
        cur = conn.cursor()
        cur.execute('''SELECT DATE(created_at) as day, COUNT(*) as count
                       FROM outreach_drafts
                       WHERE sent = 1 AND created_at >= ?
                       GROUP BY DATE(created_at) ORDER BY day''', (cutoff,))
        sent_counts = {str(r['day'])[:10]: r['count'] for r in cur.fetchall()}
        cur.execute('''SELECT DATE(received_at) as day, COUNT(*) as count
                       FROM inbound_messages WHERE received_at >= ?
                       GROUP BY DATE(received_at) ORDER BY day''', (cutoff,))
        recv_counts = {str(r['day'])[:10]: r['count'] for r in cur.fetchall()}
        conn.close()
        sent_values = [sent_counts.get(d, 0) for d in days]
        recv_values = [recv_counts.get(d, 0) for d in days]
        sent_total = sum(sent_values)
        recv_total = sum(recv_values)
    except Exception:
        pass

    col_act, col_email = st.columns(2)
    with col_act:
        st.markdown(_glass_chart(
            title='ACTIVITY · 14d',
            stat_html=(f"<span style='color:#06b6d4'>{activity_total}</span> "
                        f"<span style='color:#64748b;font-size:0.7rem;"
                        f"letter-spacing:0.10em;text-transform:uppercase;"
                        f"font-weight:600'>events</span>"),
            body_html=_sparkline_svg(activity_values, color='#06b6d4'),
        ), unsafe_allow_html=True)
    with col_email:
        legend = (
            f"<div style='display:flex;gap:0.8rem;margin-top:0.5rem;"
            f"font-size:0.68rem;color:#94a3b8;font-family:JetBrains Mono,monospace;"
            f"letter-spacing:0.08em;text-transform:uppercase;font-weight:600'>"
            f"<span><span style='color:#06b6d4'>━</span> sent</span>"
            f"<span><span style='color:#a3e635'>━</span> received</span>"
            f"</div>"
        )
        st.markdown(_glass_chart(
            title='EMAILS · 14d',
            stat_html=(f"<span style='color:#06b6d4'>↑ {sent_total}</span>  "
                        f"<span style='color:#a3e635'>↓ {recv_total}</span>"),
            body_html=_dual_sparkline_svg(sent_values, recv_values) + legend,
        ), unsafe_allow_html=True)

    # ===== Bid Intelligence + Lead sources =====
    bid_stats = database.bid_opportunities_stats()
    top_bids = []
    try:
        top_bids = database.get_bid_opportunities(min_score=60, limit=3)
    except Exception:
        pass

    src_data = []
    try:
        conn = database.get_connection()
        cur = conn.cursor()
        cur.execute('''SELECT COALESCE(lead_source, 'unknown') as source,
                              COUNT(*) as count FROM leads
                       WHERE lead_source != 'team_internal' OR lead_source IS NULL
                       GROUP BY lead_source ORDER BY count DESC LIMIT 6''')
        rows = cur.fetchall()
        conn.close()
        friendly = {
            'autopilot': '🤖 Autopilot',
            'autopilot_osm': '🌍 OpenStreetMap',
            'web3forms_webhook': '🌐 Web form',
            'compose': '✉️ Manual',
            'manual': '✏️ Manual',
            'csv_import': '📥 CSV',
            'sample': '🐎 Sample',
            'inbound_email': '📨 Email reply',
            'bid_intelligence': '💰 Bid Intelligence',
            'unsolicited_inbound': '📥 Unsolicited',
            'unknown': '❓ Unknown',
        }
        src_data = [(friendly.get(r['source'], r['source']), r['count'])
                    for r in rows]
    except Exception:
        pass

    col_bids, col_src = st.columns(2)

    with col_bids:
        if bid_stats['total'] == 0:
            bid_body = (
                "<div style='color:#64748b;font-size:0.88rem;padding:0.6rem 0;"
                "text-align:center'>"
                "<div style='font-size:1.6rem;opacity:0.5;margin-bottom:0.3rem'>💰</div>"
                "<div>No bids loaded yet.</div>"
                "<div style='font-size:0.78rem;margin-top:0.4rem;opacity:0.8'>"
                "Operations → Bids → Refresh from SAM.gov</div></div>"
            )
        else:
            bid_body = (
                f"<div style='display:flex;justify-content:space-between;"
                f"gap:0.8rem;margin-bottom:0.9rem'>"
                f"<div style='text-align:center;flex:1'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.4rem;"
                f"font-weight:700;color:#e2e8f0;line-height:1'>{bid_stats['total']}</div>"
                f"<div style='font-size:0.6rem;color:#64748b;text-transform:uppercase;"
                f"letter-spacing:0.10em;font-weight:600;margin-top:0.25rem'>Total</div></div>"
                f"<div style='text-align:center;flex:1'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.4rem;"
                f"font-weight:700;color:#06b6d4;line-height:1'>{bid_stats['new']}</div>"
                f"<div style='font-size:0.6rem;color:#64748b;text-transform:uppercase;"
                f"letter-spacing:0.10em;font-weight:600;margin-top:0.25rem'>New</div></div>"
                f"<div style='text-align:center;flex:1'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.4rem;"
                f"font-weight:700;color:#a3e635;line-height:1'>{bid_stats['hot']}</div>"
                f"<div style='font-size:0.6rem;color:#64748b;text-transform:uppercase;"
                f"letter-spacing:0.10em;font-weight:600;margin-top:0.25rem'>Hot ≥60</div></div>"
                f"</div>"
            )
            if top_bids:
                t = top_bids[0]
                title = (t.get('title') or 'Untitled')[:80]
                score = t.get('match_score') or 0
                deadline = (t.get('deadline') or '')[:10] or 'no deadline'
                product = t.get('product_fit') or ''
                bid_body += (
                    f"<div style='border-top:1px solid rgba(148,163,184,0.15);"
                    f"padding-top:0.8rem;margin-top:0.4rem'>"
                    f"<div style='font-size:0.62rem;color:#a3e635;"
                    f"text-transform:uppercase;letter-spacing:0.16em;"
                    f"font-weight:700;font-family:JetBrains Mono,monospace;"
                    f"margin-bottom:0.4rem'>◢ TOP HOT BID"
                    f"{f' · {product}' if product else ''}</div>"
                    f"<div style='font-weight:700;color:#e2e8f0;"
                    f"font-size:0.92rem;line-height:1.35'>{title}</div>"
                    f"<div style='font-size:0.78rem;color:#94a3b8;"
                    f"margin-top:0.35rem;display:flex;gap:0.7rem'>"
                    f"<span><strong style='color:#a3e635;"
                    f"font-family:JetBrains Mono,monospace'>{score}</strong>/100</span>"
                    f"<span style='color:#475569'>·</span>"
                    f"<span>deadline {deadline}</span></div></div>"
                )

        st.markdown(_glass_chart(
            title='BID INTELLIGENCE',
            body_html=bid_body,
            accent='#a3e635',
        ), unsafe_allow_html=True)
        if bid_stats['total'] > 0:
            if st.button("Open Bid panel →", key="today_open_bids",
                          use_container_width=True):
                st.session_state.page = "operations"
                st.session_state.ops_subpage = "bids"
                st.rerun()

    with col_src:
        if not src_data:
            src_body = ("<div style='color:#64748b;font-size:0.88rem;"
                        "padding:0.5rem 0'>No leads yet.</div>")
        else:
            max_src = max(c for _, c in src_data) or 1
            src_body = ""
            for label, count in src_data:
                pct = round(100 * count / max_src)
                src_body += (
                    f"<div style='display:flex;align-items:center;gap:0.7rem;"
                    f"margin-bottom:0.45rem'>"
                    f"<div style='flex:1;font-size:0.8rem;color:#cbd5e1;"
                    f"font-weight:600;white-space:nowrap;overflow:hidden;"
                    f"text-overflow:ellipsis'>{label}</div>"
                    f"<div style='flex:0 0 70px;height:7px;"
                    f"background:rgba(148,163,184,0.10);border-radius:999px;"
                    f"overflow:hidden'>"
                    f"<div style='height:100%;width:{pct}%;"
                    f"background:linear-gradient(90deg,#06b6d4,#a3e635);"
                    f"border-radius:999px'></div></div>"
                    f"<div style='flex:0 0 26px;text-align:right;"
                    f"font-family:JetBrains Mono,monospace;color:#e2e8f0;"
                    f"font-weight:700;font-size:0.85rem'>{count}</div>"
                    f"</div>"
                )

        st.markdown(_glass_chart(
            title='LEAD SOURCES',
            body_html=src_body,
        ), unsafe_allow_html=True)


@st.fragment(run_every=30)
def _home_kpi_fragment():
    """Auto-refreshing KPI rings on the Home page — clickable to drill into records.
    Ring arc length = value / max-across-row, color identifies the metric, glow
    matches the ring color so the eye instantly knows where the volume is."""
    stats = database.get_dashboard_stats()
    # (label, value, color, click_action)
    kpi_data = [
        ('HOT', stats['hot_leads'], '#ef4444', 'hot'),
        ('DUE', stats['follow_ups_due'], '#fb923c', 'due'),
        ('INTERESTED', stats['interested'], '#f59e0b', 'interested'),
        ('TRIAL', stats['trial_offered'], '#06b6d4', 'trial_offered'),
        ('WON', stats['closed_won'], '#10b981', 'closed_won'),
    ]
    max_val = max((v for _, v, _, _ in kpi_data), default=0) or 1

    cols = st.columns(5)
    for col, (label, value, color, click_action) in zip(cols, kpi_data):
        pct = round(100 * value / max_val) if max_val else 0
        with col:
            st.html(
                f"<div style='text-align:center;padding:0.45rem 0.2rem 0.2rem'>"
                f"<div style='width:96px;height:96px;border-radius:50%;"
                f"background:conic-gradient({color} 0% {pct}%, "
                f"rgba(15,23,42,0.08) {pct}% 100%);"
                f"display:flex;align-items:center;justify-content:center;"
                f"margin:0 auto 0.7rem;"
                f"box-shadow:0 0 0 1px rgba(15,23,42,0.06), 0 0 24px {color}33,"
                f" inset 0 0 0 2px rgba(255,255,255,0.6)'>"
                f"<div style='width:70px;height:70px;border-radius:50%;"
                f"background:#ffffff;display:flex;flex-direction:column;"
                f"align-items:center;justify-content:center;"
                f"box-shadow:inset 0 1px 2px rgba(15,23,42,0.06)'>"
                f"<div style='font-family:JetBrains Mono,monospace;font-size:1.7rem;"
                f"font-weight:800;color:{color};line-height:1'>{value}</div>"
                f"</div></div>"
                f"<div style='font-size:0.7rem;color:#475569;text-transform:uppercase;"
                f"letter-spacing:0.12em;font-weight:700'>{label}</div>"
                f"</div>"
            )
            if st.button("View →", key=f"kpi_{click_action}_{value}",
                          use_container_width=True):
                st.session_state.customers_filter = click_action
                st.session_state.page = "customers"
                st.rerun()


@st.fragment(run_every=30)
def _home_activity_fragment():
    """Auto-refreshing activity feed for the Home page — dark glass entries
    with semantic left-bar accent + monospace timestamp on the right."""
    activities = database.get_recent_activities(8)
    if not activities:
        st.markdown("""
        <div style='color:#64748b;font-size:0.86rem;padding:1rem 0.5rem;
                    text-align:center;font-style:italic'>
            Activity will appear as you work.
        </div>
        """, unsafe_allow_html=True)
        return

    # Brand-aligned activity colors: cyan family for outbound/system,
    # lime family for AI/research, warm for status/follow-up.
    type_color = {
        'autopilot_added':   '#10b981',
        'autopilot_drafted': '#a3e635',
        'email_sent':        '#06b6d4',
        'compose_send':      '#06b6d4',
        'created':           '#06b6d4',
        'status_change':     '#f59e0b',
        'enrichment':        '#a3e635',
        'follow_up':         '#fb923c',
        'inbound_reply':     '#22d3ee',
        'auto_reply_sent':   '#10b981',
    }
    for a in activities:
        biz = a['business_name'] or 'System'
        desc = a['description'] or ''
        time_str = format_date_friendly(a['created_at'])
        act_type = a['activity_type'] if 'activity_type' in a.keys() else 'system'
        color = type_color.get(act_type, '#64748b')

        st.html(
            f"<div style='position:relative;"
            f"background:rgba(15,23,42,0.55);"
            f"border:1px solid rgba(148,163,184,0.10);"
            f"border-left:3px solid {color};"
            f"border-radius:0 10px 10px 0;"
            f"padding:0.65rem 0.95rem;margin-bottom:0.45rem;"
            f"backdrop-filter:blur(8px);"
            f"-webkit-backdrop-filter:blur(8px)'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:flex-start;gap:0.6rem'>"
            f"<div style='font-weight:700;color:#e2e8f0;font-size:0.88rem;"
            f"line-height:1.3;min-width:0;flex:1;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{biz}</div>"
            f"<div style='color:{color};opacity:0.75;font-size:0.66rem;"
            f"font-family:JetBrains Mono,monospace;letter-spacing:0.06em;"
            f"text-transform:uppercase;font-weight:700;flex-shrink:0;"
            f"white-space:nowrap'>{time_str}</div>"
            f"</div>"
            f"<div style='color:#94a3b8;font-size:0.8rem;margin-top:0.2rem;"
            f"line-height:1.4'>{desc}</div>"
            f"</div>"
        )


# ===========================================================================
# CUSTOMERS
# ===========================================================================
def show_autopilot():
    """The headline feature — autonomous AI lead generation. Beautiful UI."""

    state = autopilot.get_state()
    running = state.get('running', False)

    # Check prerequisites
    has_ai = api_keys.has_key('cerebras') or api_keys.has_key('claude')

    if not has_ai:
        _render_autopilot_locked()
        return

    if running:
        _render_autopilot_running(state)
    else:
        _render_autopilot_idle(state)


def _render_autopilot_locked():
    """When AI isn't configured — show the value prop and CTA to set it up."""
    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Autopilot</span> needs an AI brain",
        subtitle="Connect Cerebras (free, 2 minutes) and Autopilot will scrape the open "
                  "web for horse barns, qualify each lead with AI, and fill your CRM "
                  "while you sleep.",
        eyebrow="🤖 AUTOPILOT · LOCKED",
        chips=[
            ("Free tier available", "#10b981"),
            ("Runs while you sleep", "#06b6d4"),
        ],
    )

    st.error("⚠️ Autopilot needs AI to work. It uses Cerebras (free tier) to read websites and qualify leads.")
    st.markdown("")
    if st.button("→ Connect Cerebras (free, 2 minutes)",
                  type="primary", use_container_width=True):
        st.session_state.page = "setup"
        st.rerun()


def _render_autopilot_running(state):
    """Live-running dashboard. Uses st.fragment for partial reruns
    so the rest of the page stays still and tab state is preserved."""
    _autopilot_live_fragment()


@st.fragment(run_every=5)
def _home_autopilot_widget():
    """Mini live-view widget for the Home page.
    Shows autopilot status + quick start/stop. Auto-refreshes every 5s."""
    state = autopilot.get_state()
    running = state.get('running', False)
    stats = state.get('stats', {})
    has_ai = api_keys.has_key('cerebras') or api_keys.has_key('claude')

    if running:
        action = state.get('current_action', 'working')
        target = state.get('current_target', '')
        recent = state.get('recent_leads', [])

        st.markdown(f"""
        <div style='background:linear-gradient(135deg,#fef3c7 0%,#fde68a 100%);
                    border:2px solid #f59e0b;border-radius:14px;padding:1.2rem 1.5rem;
                    margin-bottom:1.5rem;box-shadow:0 4px 16px rgba(245,158,11,0.18)'>
            <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.5rem'>
                <div style='display:flex;align-items:center;gap:0.8rem'>
                    <div style='font-size:0.7rem;color:#92400e;text-transform:uppercase;
                                letter-spacing:0.08em;font-weight:700;display:flex;
                                align-items:center;gap:0.4rem'>
                        <span style='display:inline-block;width:8px;height:8px;background:#dc2626;
                                     border-radius:50%;animation:pulse 1.5s infinite'></span>
                        Autopilot Live
                    </div>
                </div>
                <div style='display:flex;gap:1.5rem;align-items:center'>
                    <div style='text-align:center'>
                        <div style='font-size:1.4rem;font-weight:800;color:#92400e'>
                            {stats.get('added_to_crm', 0)}
                        </div>
                        <div style='font-size:0.65rem;color:#92400e;text-transform:uppercase;
                                    letter-spacing:0.05em;font-weight:600'>Added</div>
                    </div>
                    <div style='text-align:center'>
                        <div style='font-size:1.4rem;font-weight:800;color:#92400e'>
                            {stats.get('researched', 0)}
                        </div>
                        <div style='font-size:0.65rem;color:#92400e;text-transform:uppercase;
                                    letter-spacing:0.05em;font-weight:600'>Researched</div>
                    </div>
                </div>
            </div>
            <div style='margin-top:0.6rem;color:#78350f;font-size:0.85rem'>
                <strong>{action.title()}:</strong> {target or '...'}
            </div>
        </div>
        <style>
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.4; }}
            }}
        </style>
        """, unsafe_allow_html=True)

        # Show last few leads if any
        if recent:
            cols = st.columns(min(len(recent[:3]), 3))
            for i, lead in enumerate(recent[:3]):
                with cols[i]:
                    score = lead.get('score', 0)
                    st.markdown(f"""
                    <div style='background:#fff;border:1px solid #e2e8f0;border-radius:8px;
                                padding:0.6rem 0.8rem;font-size:0.8rem'>
                        <div style='font-weight:600;color:#0f172a;
                                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>
                            {lead['business_name']}
                        </div>
                        <div style='color:#64748b;font-size:0.75rem'>
                            Score {score} · {lead.get('source', '?')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])
        if col1.button("👀 Open full live view →", use_container_width=True):
            st.session_state.page = "autopilot"
            st.rerun()
        if col2.button("🛑 Stop", use_container_width=True):
            autopilot.stop_autopilot()

    else:
        # Idle state — quick launch button
        if has_ai:
            st.markdown(f"""
            <div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;
                        padding:1rem 1.3rem;margin-bottom:1.5rem;display:flex;
                        align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap'>
                <div style='display:flex;align-items:center;gap:0.8rem'>
                    <div style='font-size:1.6rem'>🤖</div>
                    <div>
                        <div style='font-weight:700;color:#0f172a;font-size:0.95rem'>
                            Autopilot is idle
                        </div>
                        <div style='color:#64748b;font-size:0.82rem;margin-top:0.1rem'>
                            Last run: {stats.get('added_to_crm', 0)} added · {stats.get('skipped', 0)} skipped
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns([3, 1])
            if col1.button("🚀 Quick-launch Autopilot (25 leads, default settings)",
                            type="primary", use_container_width=True, key="home_quick_ap"):
                config = {
                    'state': None,
                    'city': None,
                    'business_types': ['horse boarding facility', 'equestrian center',
                                       'horse stable', 'horse rescue'],
                    'target_leads': 25,
                    'min_score': 85,
                    'auto_draft_outreach': True,
                }
                autopilot.clear_log()
                success, msg = autopilot.start_autopilot(config)
                if success:
                    st.balloons()
                    st.success("🚀 Autopilot launched!")
                    st.rerun()
                else:
                    st.error(msg)
            if col2.button("⚙️ Configure", use_container_width=True, key="home_ap_config"):
                st.session_state.page = "autopilot"
                st.rerun()


@st.fragment(run_every=4)
def _autopilot_live_fragment():
    """The live-updating fragment of the Autopilot page.
    This section refreshes every 4 seconds — the rest of the page stays still."""
    state = autopilot.get_state()

    if not state.get('running', False):
        # Autopilot stopped while we were viewing — trigger full rerun
        st.info("✅ Autopilot finished. Refresh the page to see the idle view.")
        if st.button("Reload page →", type="primary"):
            st.rerun()
        return

    stats = state.get('stats', {})
    target = state.get('config', {}).get('target_leads', 25)
    added = stats.get('added_to_crm', 0)
    progress_pct = min(added / max(target, 1), 1.0)

    # ================== HERO (clean live status) ==================
    st.markdown(f"""
    <div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;
                padding:1.5rem 1.8rem;margin-bottom:1.5rem;
                box-shadow:0 1px 3px rgba(0,0,0,0.04)'>
        <div style='display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:1rem'>
            <div>
                <div style='display:flex;align-items:center;gap:0.5rem;
                            font-size:0.8rem;color:#16a34a;text-transform:uppercase;
                            letter-spacing:0.08em;font-weight:700'>
                    <span style='display:inline-block;width:8px;height:8px;
                                 background:#16a34a;border-radius:50%;
                                 animation:pulse 1.5s infinite'></span>
                    Autopilot Live
                </div>
                <div style='font-size:1.6rem;font-weight:700;color:#0f172a;
                            margin-top:0.3rem;letter-spacing:-0.02em'>
                    Hunting leads · {added} of {target}
                </div>
                <div style='color:#64748b;font-size:0.9rem;margin-top:0.2rem'>
                    Auto-refreshes every 4 seconds
                </div>
            </div>
            <div style='text-align:right'>
                <div style='font-size:2.5rem;font-weight:800;color:#0f172a;line-height:1'>
                    {int(progress_pct * 100)}%
                </div>
                <div style='color:#64748b;font-size:0.75rem;text-transform:uppercase;
                            letter-spacing:0.05em;font-weight:600;margin-top:0.2rem'>
                    Complete
                </div>
            </div>
        </div>
        <div style='background:#f1f5f9;height:6px;border-radius:3px;
                    margin-top:1.2rem;overflow:hidden'>
            <div style='background:linear-gradient(90deg,#16a34a 0%,#22c55e 100%);
                        height:100%;width:{progress_pct * 100}%;
                        border-radius:3px;transition:width 0.5s'></div>
        </div>
    </div>
    <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
    </style>
    """, unsafe_allow_html=True)

    # ================== CURRENT ACTIVITY ==================
    action = state.get('current_action', '')
    target_str = state.get('current_target', '')
    action_label = {
        'discovering': '🔎 Discovering businesses',
        'researching': '🔬 Deep-researching',
        'analyzing': '🧠 AI analyzing website',
        'finding_email': '📧 Finding email address',
        'saving': '💾 Saving to CRM',
        'drafting': '✍️ Drafting personalized outreach',
        'starting': '🚀 Starting up',
        'stopping': '🛑 Stopping...',
    }.get(action, f'⚙️ {action}')

    if any(k in action.lower() for k in ('scraping', 'discovering', 'searching')):
        action_label = f"📡 {action.title()}"

    st.markdown(f"""
    <div style='background:#fff;border:1px solid #e9ecef;border-left:4px solid #4d7c0f;
                padding:1rem 1.5rem;border-radius:8px;margin-bottom:1.5rem;
                box-shadow:0 2px 8px rgba(0,0,0,0.04)'>
        <div style='font-size:0.85rem;color:#6c757d;margin-bottom:0.25rem;
                    text-transform:uppercase;letter-spacing:0.05em'>
            Right now
        </div>
        <div style='font-size:1.1rem;font-weight:600;color:#4d7c0f'>
            {action_label}
        </div>
        <div style='color:#495057;margin-top:0.25rem'>
            {target_str or '...'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ================== STATS PIPELINE (CLICKABLE) ==================
    pipeline_stats = [
        ("🔎", "Discovered", stats.get('discovered', 0), "#007bff", "discovered"),
        ("🧠", "Researched", stats.get('researched', 0), "#6610f2", "researched"),
        ("✅", "Qualified", stats.get('qualified', 0), "#28a745", "qualified"),
        ("⏭", "Skipped", stats.get('skipped', 0), "#6c757d", "skipped"),
        ("⚠️", "Errors", stats.get('errors', 0), "#dc3545", "errors"),
    ]
    cols = st.columns(5)
    for col, (icon, label, val, color, drill) in zip(cols, pipeline_stats):
        with col:
            st.html(
                f"<div style='background:#fff;border:1px solid #e9ecef;border-radius:8px 8px 0 0;"
                f"padding:0.85rem 1rem 0.4rem;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.05)'>"
                f"<div style='font-size:1.4rem'>{icon}</div>"
                f"<div style='font-size:1.8rem;font-weight:700;color:{color};line-height:1.1;margin:0.25rem 0'>{val}</div>"
                f"<div style='font-size:0.75rem;color:#6c757d;text-transform:uppercase;letter-spacing:0.05em;font-weight:600'>"
                f"{label}</div></div>"
            )
            if st.button("Show records →", key=f"ap_drill_{drill}", use_container_width=True):
                st.session_state.autopilot_drill = drill
                st.rerun()

    # Drill-down view
    drill = st.session_state.get('autopilot_drill')
    if drill:
        _render_autopilot_drill(drill)


def _render_autopilot_drill(drill):
    """Show the records behind an autopilot stat card."""
    state = autopilot.get_state()
    log = autopilot.read_log()
    recent = state.get('recent_leads', [])

    drill_filters = {
        'discovered': lambda e: e.get('type') == 'discovery',
        'researched': lambda e: e.get('type') == 'research',
        'qualified': lambda e: e.get('type') == 'added',
        'skipped': lambda e: e.get('type') == 'skipped',
        'errors': lambda e: e.get('type') == 'error',
    }
    fltr = drill_filters.get(drill, lambda e: True)
    filtered = [e for e in log if fltr(e)]

    st.html(
        f"<div style='background:#eff6ff;border-left:4px solid #3b82f6;padding:0.6rem 1rem;border-radius:0 6px 6px 0;margin:0.8rem 0'>"
        f"<strong style='color:#1e40af'>📋 Records: {drill.title()}</strong> &nbsp;·&nbsp; "
        f"<span style='color:#1e40af'>{len(filtered)} entries</span>"
        f"</div>"
    )

    if drill == 'qualified' and recent:
        st.markdown("**Recently added leads (full details):**")
        for lead in recent[:20]:
            st.html(
                f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:0.7rem 1rem;margin-bottom:0.4rem'>"
                f"<div style='font-weight:600;color:#0f172a'>{lead['business_name']}</div>"
                f"<div style='color:#64748b;font-size:0.82rem;margin-top:0.15rem'>"
                f"Score: {lead.get('score', '?')} · {lead.get('city', '')} {lead.get('state', '')} · via {lead.get('source', '?')}"
                f"</div></div>"
            )

    if filtered:
        st.markdown("**Activity log entries:**")
        for entry in filtered[:50]:
            t = entry.get('time', '')[11:19]
            msg = entry.get('message', '')
            st.markdown(f"`{t}` — {msg}")
    else:
        st.caption("_No entries yet._")

    if st.button("← Close drill-down", key=f"ap_close_drill"):
        st.session_state.pop('autopilot_drill', None)
        st.rerun()

    st.markdown("")

    # Stop button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🛑 Stop", type="primary", use_container_width=True):
            autopilot.stop_autopilot()
            st.warning("Stopping after current task...")
            st.rerun()

    st.markdown("---")

    # ================== TWO COLUMNS: SOURCES + RECENT LEADS ==================
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.markdown("### 📡 Data Sources")
        st.caption("Where we're scraping from")
        sources = state.get('sources_used', {})
        if sources:
            total_from_sources = sum(sources.values())
            for source, count in sorted(sources.items(), key=lambda x: -x[1]):
                pct = int((count / total_from_sources) * 100)
                st.markdown(f"""
                <div style='background:#f8f9fa;border-radius:6px;padding:0.6rem 0.8rem;
                            margin-bottom:0.4rem'>
                    <div style='display:flex;justify-content:space-between;
                                font-size:0.9rem;font-weight:600'>
                        <span>{source}</span><span>{count}</span>
                    </div>
                    <div style='background:#e9ecef;height:4px;border-radius:2px;
                                margin-top:0.4rem;overflow:hidden'>
                        <div style='background:#4d7c0f;height:100%;width:{pct}%'></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("_Sources will appear as leads are added..._")

        # All possible sources we use
        st.markdown("---")
        st.caption("**Active scrapers:**")
        st.markdown("""
        - 🦆 DuckDuckGo HTML
        - 🔵 Bing HTML
        - 📒 YellowPages
        - 🐴 Equine industry directories
        - 🌐 Direct website scraping
        """)

    with col_right:
        st.markdown("### 🎯 Recently Added Leads")
        recent = state.get('recent_leads', [])
        if recent:
            for lead in recent[:6]:
                score = lead.get('score', 0)
                score_color = "#dc3545" if score >= 75 else "#ffc107" if score >= 55 else "#6c757d"
                hook = (lead.get('hook') or '').replace('"', '&quot;')
                location = lead.get('city') or ''
                if lead.get('state'):
                    location = f"{location}, {lead['state']}".strip(', ')
                contact = lead.get('contact_name') or 'Contact unknown'
                source = lead.get('source', 'web')

                st.markdown(f"""
                <div style='background:#fff;border:1px solid #e9ecef;border-radius:10px;
                            padding:1rem 1.2rem;margin-bottom:0.75rem;
                            box-shadow:0 2px 4px rgba(0,0,0,0.04)'>
                    <div style='display:flex;justify-content:space-between;align-items:start'>
                        <div style='flex:1'>
                            <div style='font-weight:700;color:#4d7c0f;font-size:1.05rem'>
                                {lead['business_name']}
                            </div>
                            <div style='color:#6c757d;font-size:0.88rem;margin-top:0.15rem'>
                                {contact} · {location or 'Location unknown'} · via {source}
                            </div>
                        </div>
                        <div style='background:{score_color};color:white;padding:0.3rem 0.7rem;
                                    border-radius:14px;font-weight:700;font-size:0.85rem'>
                            {score}
                        </div>
                    </div>
                    <div style='margin-top:0.7rem;padding:0.6rem 0.8rem;background:#f8f9fa;
                                border-left:3px solid #4d7c0f;border-radius:4px;
                                font-size:0.88rem;color:#495057;font-style:italic'>
                        💡 {hook[:160]}{'...' if len(hook) > 160 else ''}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style='background:#f8f9fa;border:2px dashed #dee2e6;border-radius:10px;
                        padding:3rem;text-align:center;color:#6c757d'>
                <div style='font-size:2rem'>🔍</div>
                <div style='margin-top:0.5rem'>Hunting for leads...</div>
                <div style='font-size:0.85rem;margin-top:0.25rem'>
                    First leads usually appear within 30-60 seconds
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ================== ACTIVITY FEED ==================
    st.markdown("---")
    st.markdown("### 📜 Live Activity Feed")

    log = autopilot.read_log()
    if log:
        with st.container():
            for entry in log[:25]:
                event_type = entry.get('type', 'system')
                msg = entry.get('message', '')
                time_str = entry.get('time', '')[11:19]  # just HH:MM:SS

                color = {
                    'added': '#28a745',
                    'discovery': '#007bff',
                    'research': '#6610f2',
                    'skipped': '#6c757d',
                    'error': '#dc3545',
                    'system': '#fd7e14',
                }.get(event_type, '#666')

                bg_color = {
                    'added': '#f0f9f4',
                    'error': '#fef2f2',
                }.get(event_type, '#fff')

                st.markdown(
                    f"<div style='border-left:3px solid {color};background:{bg_color};"
                    f"padding:0.5rem 0.9rem;margin-bottom:0.35rem;border-radius:0 4px 4px 0;"
                    f"font-size:0.9rem;font-family:monospace'>"
                    f"<span style='color:#999;margin-right:0.6rem'>{time_str}</span>"
                    f"{msg}</div>",
                    unsafe_allow_html=True
                )
    else:
        st.caption("_Waiting for first activity..._")


def _render_autopilot_idle(state):
    """Idle state — clean hero + config form + previous run results."""

    last_stats = state.get('stats', {})
    has_previous_run = last_stats and any(last_stats.values())

    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Autonomous</span> lead generation",
        subtitle="AI scrapes horse businesses across the open web, qualifies each lead, "
                  "and writes personalized cold emails. Free. Cerebras-powered.",
        eyebrow="🤖 AUTOPILOT",
        chips=[
            ("5 scrapers", "#06b6d4"),
            ("Cerebras AI", "#10b981"),
            ("$0 / month", "#f59e0b"),
        ],
    )

    # ================== HOW IT WORKS ==================
    st.markdown("### How it works")
    pipeline_steps = [
        ("🔎", "Discover", "Scrapes DuckDuckGo, Bing, YellowPages, and equine directories"),
        ("🌐", "Crawl Sites", "Fetches each business website (homepage + about + contact)"),
        ("🧠", "AI Analyze", "Cerebras reads the site, extracts owner names, services, pain points"),
        ("🎯", "Qualify", "AI scores 0-100 with reasoning. Junk businesses get skipped."),
        ("📧", "Find Email", "Scrapes contact info or generates pattern guesses"),
        ("✍️", "Draft Outreach", "AI writes a cold email referencing real facts from their site"),
    ]

    for i, (icon, title, desc) in enumerate(pipeline_steps):
        st.markdown(f"""
        <div style='background:#fff;border:1px solid #e9ecef;border-radius:10px;
                    padding:1rem 1.3rem;margin-bottom:0.6rem;display:flex;
                    align-items:center;gap:1rem'>
            <div style='font-size:1.6rem'>{icon}</div>
            <div style='flex:1'>
                <div style='font-weight:700;color:#4d7c0f'>{i+1}. {title}</div>
                <div style='color:#6c757d;font-size:0.92rem;margin-top:0.1rem'>{desc}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ================== PREVIOUS RUN RESULTS ==================
    if has_previous_run:
        st.markdown("### 📊 Last Run Results")
        cols = st.columns(4)
        cols[0].metric("✅ Added to CRM", last_stats.get('added_to_crm', 0))
        cols[1].metric("🧠 Researched", last_stats.get('researched', 0))
        cols[2].metric("⏭ Skipped", last_stats.get('skipped', 0))
        cols[3].metric("⚠️ Errors", last_stats.get('errors', 0))

        if state.get('stopped_at'):
            st.caption(f"Last run: {state.get('stopped_at', '')[:19].replace('T', ' ')}")

        # Show recently added leads from last run
        recent = state.get('recent_leads', [])
        if recent:
            with st.expander(f"🎯 View last {len(recent)} leads added"):
                for lead in recent:
                    st.markdown(f"**{lead['business_name']}** "
                                f"(score {lead.get('score', '?')}) · "
                                f"_{(lead.get('hook') or '')[:120]}_")

        st.markdown("---")

    # ================== CONFIG ==================
    st.markdown("### ⚙️ Configure this hunt")

    # ========== Explainer for sliders ==========
    with st.expander("📚 How does AI scoring & lead targeting work?"):
        st.markdown("""
        ### The AI Quality Score (0-100)

        After scraping a candidate business, **Cerebras AI reads their entire website** and grades them on:

        | Signal | Weight | What it looks for |
        |--------|--------|---------------------|
        | **Business type fit** | 30 pts | Is this a horse boarding facility, stable, equestrian center, breeder, rescue, trainer, tack shop, or feed store? |
        | **Pain signals** | 25 pts | Mentions of ammonia, flies, manure, odor, stalls, trailers, bedding, fly control, barn air |
        | **Contact completeness** | 20 pts | Has email + phone + website + social media? |
        | **Engagement signals** | 15 pts | Named contact person, professional website, activity |
        | **Commercial scale** | 10 pts | Number of stalls (10+ = bigger ammonia problem = better fit) |

        **AI also makes a judgment call:** is this a real business worth pursuing? It returns `should_pursue: true/false` with reasoning. Junk listings, directories, or unrelated businesses get auto-skipped regardless of score.

        ### Score brackets
        - **80-100** 🔥 Hot lead — drop everything, contact today
        - **60-79** ⭐ Qualified — schedule outreach this week
        - **40-59** 👍 Potential — research more or send a soft touch
        - **20-39** ❓ Early stage — needs more info before outreach
        - **0-19** 📋 New — not yet scored

        ### How to dial it in
        - **Lower minimum score** (e.g., 30) = more leads pass through, less picky
        - **Higher minimum score** (e.g., 70) = only top-tier matches make it in
        - **Default is 40** which gives you a healthy mix to work with

        ### Lead count = stop condition
        Autopilot keeps hunting until it adds N leads to your CRM that pass the threshold,
        OR runs out of candidates to evaluate. Either way it stops cleanly.
        """)

    col1, col2 = st.columns(2)
    with col1:
        target_count = st.slider("How many qualified leads to add?", 5, 200, 50, 5,
                                  help="Autopilot stops once this many leads pass the score threshold and land in your CRM.")
        min_score = st.slider(
            "Minimum AI quality score",
            10, 95, 85, 5,
            help="Higher = pickier. Leads scoring below this are skipped (not added to CRM)."
        )

    with col2:
        state_options = [""] + [f"{s[0]} - {s[1]}" for s in prospecting.TOP_EQUINE_STATES]
        state_choice = st.selectbox(
            "Target state (or leave blank for nationwide)",
            state_options
        )
        city_choice = st.text_input("Target city (optional)", placeholder="Lexington")

    target_state = state_choice.split(" - ")[0] if state_choice else None

    # Pull editable categories — supports all product lines, not just equine
    import hunt_categories
    all_categories = hunt_categories.load_categories()
    business_types_all = [c['type'] for c in all_categories]
    default_types = [c['type'] for c in all_categories if c.get('active')]

    if not business_types_all:
        # Fall back to discovery targets
        business_types_all = [t['type'] for t in lead_discovery.get_discovery_targets()]
        default_types = business_types_all[:4]

    selected_types = st.multiselect(
        "Business types to hunt for",
        business_types_all,
        default=default_types,
        help="Edit/add categories below. Defaults are pre-checked based on which are 'active' in your category list.",
    )

    # Inline category editor
    with st.expander(f"⚙️ Manage hunt categories ({len(all_categories)} types across products)"):
        st.caption("Add new types for any product line — bot will hunt for them in future runs.")

        # Add new
        with st.form("add_category", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            new_type = c1.text_input("Business type", placeholder="e.g. dog daycare, marina, country club")
            new_product = c2.selectbox("For product", ['', 'Duo Equine', 'Pets', 'SpillMaster', 'AMR', 'HouseHold', 'Inversion Misting'])
            new_priority = c3.selectbox("Priority", [1, 2, 3, 4], index=2,
                                         help="1 = best fit, 4 = lowest")
            if st.form_submit_button("➕ Add category", type="primary", use_container_width=True):
                if new_type:
                    if hunt_categories.add_category(new_type, new_product, new_priority):
                        st.success(f"Added {new_type}")
                        st.rerun()
                    else:
                        st.warning(f"{new_type} already in list")

        # Reset-to-defaults safety net
        rc1, rc2 = st.columns([5, 1])
        rc1.caption("Reset reloads the latest built-in defaults (loses your custom additions).")
        if rc2.button("↻ Reset", key="reset_categories",
                      help="Reload the latest default categories"):
            hunt_categories.reset()
            st.success("Reloaded default categories")
            st.rerun()

        # Product picker — avoids nested-expander API violation
        product_order = ['Duo Equine', 'Pets', 'SpillMaster', 'AMR', 'HouseHold',
                         'Inversion Misting']
        cats_by_product = {p: [] for p in product_order}
        cats_by_product['Other'] = []
        for orig_idx, cat in enumerate(all_categories):
            prod = cat.get('product') or 'Other'
            cats_by_product.setdefault(prod, []).append((orig_idx, cat))

        # Build label with counts so user can see at a glance
        all_products = product_order + (['Other'] if cats_by_product.get('Other') else [])
        labels = []
        for p in all_products:
            n = len(cats_by_product.get(p, []))
            a = sum(1 for _, c in cats_by_product.get(p, []) if c.get('active'))
            labels.append(f"{p} · {n} types ({a} active)")

        st.markdown("")
        st.markdown("##### Filter by product")
        chosen_label = st.radio(
            "Filter", labels, horizontal=True,
            key="cat_product_filter", label_visibility="collapsed"
        )
        chosen_idx = labels.index(chosen_label)
        chosen_product = all_products[chosen_idx]

        st.markdown("")

        for orig_idx, cat in cats_by_product[chosen_product]:
            c1, c2, c3, c4 = st.columns([3, 1, 1, 0.5])
            c1.markdown(f"**{cat['type']}**")
            c2.caption(f"Priority {cat.get('priority', 3)}")
            new_active = c3.checkbox("Active", value=cat.get('active', False),
                                      key=f"cat_active_{orig_idx}")
            if new_active != cat.get('active', False):
                hunt_categories.update_category(orig_idx, active=new_active)
                st.rerun()
            if c4.button("🗑️", key=f"cat_del_{orig_idx}"):
                hunt_categories.delete_category(orig_idx)
                st.rerun()

    auto_draft = st.checkbox(
        "✍️ Auto-write a personalized cold email for each lead (recommended)",
        value=True
    )

    st.markdown("")

    # Big start button
    if st.button(
        f"🚀 Launch Autopilot — Hunt {target_count} Qualified Leads",
        type="primary", use_container_width=True,
        disabled=not selected_types
    ):
        config = {
            'state': target_state,
            'city': city_choice or None,
            'business_types': selected_types,
            'target_leads': target_count,
            'min_score': min_score,
            'auto_draft_outreach': auto_draft,
        }

        autopilot.clear_log()
        success, msg = autopilot.start_autopilot(config)
        if success:
            st.balloons()
            # Force immediate state log so live view has something to show right away
            autopilot.log_event('system', '🚀 Autopilot launched — initializing...')
            autopilot.update_state(
                current_action='starting',
                current_target=f'Hunting {target_count} leads',
            )
            st.success(f"🚀 Autopilot launched! Live status loading...")
            # Brief pause so the thread can write its first stats
            import time as _time
            _time.sleep(1)
            st.rerun()
        else:
            st.error(msg)

    if not selected_types:
        st.warning("Pick at least one business type above to hunt for.")


def show_sales_bot():
    """Sales Bot page — control center for autonomous engagement + training chat."""

    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Autonomous</span> NEPQ sales agent",
        subtitle="When a lead crosses your hot threshold, Aqua writes a Jeremy Miner-style "
                  "NEPQ cold email and (optionally) sends it. When prospects reply, she "
                  "auto-classifies intent and drafts the perfect next move. Train her in "
                  "the chat below.",
        eyebrow="🎯 SALES BOT",
        chips=[
            ("NEPQ methodology", "#06b6d4"),
            ("Inbox monitoring", "#f59e0b"),
            ("Auto-engagement", "#ec4899"),
        ],
    )

    # legacy chip block kept (now hidden) — preserves any downstream layout
    st.markdown("""
    <div style='display:none'>
        <div style='display:flex;gap:0.5rem;margin-top:1rem;flex-wrap:wrap'>
            <span style='background:#f0f9ff;color:#0369a1;padding:0.3rem 0.7rem;
                         border-radius:14px;font-size:0.8rem;font-weight:600'>
                NEPQ methodology
            </span>
            <span style='background:#fef3c7;color:#92400e;padding:0.3rem 0.7rem;
                         border-radius:14px;font-size:0.8rem;font-weight:600'>
                Inbox monitoring
            </span>
            <span style='background:#fce7f3;color:#9d174d;padding:0.3rem 0.7rem;
                         border-radius:14px;font-size:0.8rem;font-weight:600'>
                Multi-touch sequences
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Prereq check
    has_ai = api_keys.has_key('cerebras') or api_keys.has_key('claude')
    has_email = smtp_sender.is_configured()

    if not has_ai:
        st.error("⚠️ The Sales Bot needs AI. Connect Cerebras or Claude in **Setup → AI Providers** first.")
        if st.button("→ Go to AI Setup", type="primary"):
            st.session_state.page = "setup"
            st.rerun()
        return

    if not has_email:
        st.warning("⚠️ Email not connected. The bot can draft messages but can't send or check inbox until you connect SMTP/IMAP in **Setup**.")

    tab_chat, tab_engagement, tab_responder, tab_train, tab_knowledge, tab_logs = st.tabs([
        "💬 Chat with Aqua",
        "🚀 Auto-Engagement",
        "📨 Inbox Watcher",
        "🎓 Train / Roleplay",
        "📚 Knowledge Base",
        "📜 Activity",
    ])

    with tab_chat:
        _show_freeform_chat()
    with tab_engagement:
        _show_engagement_panel()
    with tab_responder:
        _show_responder_panel()
    with tab_train:
        _show_training_chat()
    with tab_knowledge:
        _show_knowledge_base()
    with tab_logs:
        _show_bot_logs()


def _show_freeform_chat():
    """Live chat with Aqua. Per-user persistent memory survives across sessions.
    Hit Enter to send. Shift+Enter for newline.
    """
    import team as _team
    current = _team.get_current_user()
    user_email = (current.get('email') or '').lower()
    user_first = (current.get('name') or 'there').split()[0]

    if not user_email:
        st.warning("Connect your email in Setup → 📧 Email so Aqua can remember your conversations.")

    st.markdown(f"### Chat with Aqua — _hey {user_first}_")
    facts = database.aqua_get_user_facts(user_email, limit=5) if user_email else []
    if facts:
        with st.expander(f"🧠 What Aqua remembers about you ({len(facts)} notes)"):
            for f in facts:
                st.caption(f"• {f['fact']}")
            st.caption("Aqua persists corrections + intel across sessions.")
    st.caption("Aqua is your teammate, not your assistant. She runs deals, drafts outreach, "
                "handles inbound. Coach her here — she remembers per-person.")

    # Pull persistent history (DB-backed, oldest-first)
    history = database.aqua_get_chat_history(user_email, limit=40) if user_email else []

    # Quick prompts
    suggestions = [
        ("📈 What's working in pipeline?", "Look at our live CRM snapshot and tell me: which lead source is converting best, what intents we're seeing this week, and one concrete thing we should do MORE of."),
        ("🎯 Roleplay 'too expensive'", "Roleplay: You're a horse barn owner objecting to the price of Duo Equine. Hit me with it like a real owner would."),
        ("💡 5 lead sources I haven't tried", "Give me 5 creative places to find prospects across our different verticals (horse, pet, commercial, fleet, residential) that aren't obvious."),
        ("📝 Critique my last 3 emails", "Pull our 3 most recent sent emails and critique them — what's working, what's salesy, what to fix."),
        ("🐴 Equine playbook", "Brief me like an insider on the equine industry: who decides, top pains, lingo, common objections."),
        ("🚗 AMR playbook", "Brief me on auto/marine/RV/transit prospects: who decides, top pains, common objections, how to position the AMR product."),
        ("🧪 SpillMaster playbook", "Brief me on commercial cleanup / food / healthcare prospects for SpillMaster."),
        ("🏠 HouseHold playbook", "Brief me on residential & cleaning-service prospects — who decides, top pains, how to position HouseHold."),
        ("💨 Inversion Misting", "Brief me on large-facility / livestock / ag prospects — what to say to win the Inversion Misting capital sale."),
        ("⚖️ Top 5 objections", "Walk me through the top 5 objections we hit and the NEPQ-style response for each."),
        ("🔁 Re-engagement sequence", "Design a 3-touch re-engagement sequence for prospects who went quiet after one reply. Use a different framework each touch."),
        ("🧠 Remember this:", "I want you to remember this fact going forward: "),
    ]
    with st.expander("⚡ Quick prompts (click to send)", expanded=(len(history) == 0)):
        cols = st.columns(4)
        for i, (label, prompt) in enumerate(suggestions):
            with cols[i % 4]:
                if st.button(label, key=f"qp_{i}", use_container_width=True):
                    if user_email:
                        database.aqua_save_message(user_email, 'user', prompt)
                    _aqua_respond(user_email, prompt)
                    st.rerun()

    st.markdown("---")

    # Render history as chat bubbles
    if not history:
        st.caption(f"_Empty chat. Aqua's ready. Try a quick prompt above or just type below._")
    for msg in history:
        if msg['role'] == 'user':
            st.html(
                f"<div style='background:linear-gradient(135deg,#06b6d4,#4d7c0f);"
                f"color:white;padding:0.8rem 1.1rem;"
                f"border-radius:14px 14px 4px 14px;margin-bottom:0.5rem;"
                f"margin-left:18%;font-size:0.95rem;white-space:pre-wrap;"
                f"box-shadow:0 2px 8px rgba(6,182,212,0.2)'>{msg['content']}</div>"
            )
        else:
            src_badge = ''
            if msg.get('source') and msg['source'] != 'cerebras':
                src_badge = f"<span style='font-size:0.7rem;color:#94a3b8'> · {msg['source']}</span>"
            st.html(
                f"<div style='background:rgba(255,255,255,0.7);"
                f"backdrop-filter:blur(12px);"
                f"border:1px solid rgba(15,23,42,0.08);color:#0a0f1c;"
                f"padding:0.8rem 1.1rem;"
                f"border-radius:14px 14px 14px 4px;margin-bottom:0.5rem;"
                f"margin-right:18%;font-size:0.95rem;white-space:pre-wrap'>"
                f"<div style='font-size:0.72rem;color:#06b6d4;font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.3rem'>"
                f"AQUA{src_badge}</div>"
                f"{msg['content']}</div>"
            )

    # Clear button (separate from input)
    cc1, cc2 = st.columns([5, 1])
    if user_email and history and cc2.button("🗑️ Clear chat", key="aqua_clear",
                                                use_container_width=True):
        database.aqua_clear_chat(user_email)
        st.rerun()

    # Native chat input — Enter sends, Shift+Enter newline
    user_input = st.chat_input("Talk to Aqua… (Enter to send, Shift+Enter for newline)")
    if user_input and user_input.strip():
        if user_email:
            database.aqua_save_message(user_email, 'user', user_input.strip())
            # Detect "remember" instructions and persist as long-term facts
            lower = user_input.strip().lower()
            if any(k in lower for k in ['remember this', 'remember that',
                                          'going forward', 'from now on']):
                database.aqua_remember_fact(user_email, user_input.strip(),
                                              category='user_directive')
        _aqua_respond(user_email, user_input.strip())
        st.rerun()


def _aqua_respond(user_email, user_message):
    """Build the system context, call the LLM, persist Aqua's reply."""
    history = database.aqua_get_chat_history(user_email, limit=20) if user_email else []
    facts = database.aqua_get_user_facts(user_email, limit=20) if user_email else []

    # Inject persistent memory as extra context
    extra_lines = []
    if facts:
        extra_lines.append("## WHAT YOU'VE LEARNED ABOUT THIS PERSON (persistent memory across sessions)")
        for f in facts:
            extra_lines.append(f"- {f['fact']}")
    extra_context = "\n".join(extra_lines) if extra_lines else ""

    # Convert DB history to LLM message format (exclude the just-saved user msg
    # so we don't duplicate it — training_chat appends it itself)
    llm_history = [{'role': m['role'], 'content': m['content']} for m in history[:-1]]

    with st.spinner("Aqua thinking..."):
        result = nepq_engine.training_chat(
            llm_history,
            user_message,
            training_mode='qa',
            extra_context=extra_context,
        )

    if user_email:
        database.aqua_save_message(user_email, 'assistant', result['text'],
                                     source=result.get('source'))


def _show_knowledge_base():
    """Upload documents Aqua learns from. Persists across sessions."""
    import knowledge_base as kb

    st.markdown("### Knowledge Base — feed Aqua docs to learn from")
    st.caption("Upload sales scripts, product manuals, FAQs, customer success stories, "
                "internal docs. Aqua reads them when crafting messages.")

    # Show existing docs
    docs = kb.list_documents()

    if docs:
        st.markdown(f"**Loaded documents ({len(docs)}):**")
        for d in docs:
            with st.expander(f"📄 {d['title']} · {d.get('size', 0)} chars · added {format_date_friendly(d.get('added_at', ''))}"):
                st.markdown(f"**Source:** {d.get('source', 'Unknown')}")
                st.text(d['content'][:2000] + ('...' if len(d.get('content', '')) > 2000 else ''))
                if st.button(f"🗑️ Remove this document", key=f"kb_del_{d['id']}"):
                    kb.delete_document(d['id'])
                    st.rerun()
    else:
        st.info("No documents yet. Upload the first one below.")

    st.markdown("---")
    st.markdown("### ➕ Add knowledge")

    upload_method = st.radio(
        "How do you want to add it?",
        ["📝 Paste text", "📎 Upload file (.txt, .md)", "🔗 URL (we'll scrape)"],
        horizontal=True,
    )

    if "Paste text" in upload_method:
        with st.form("kb_paste_form", clear_on_submit=True):
            title = st.text_input("Title", placeholder="e.g. 'Sales script — handling Texas barn owners'")
            content = st.text_area("Content", height=200,
                                      placeholder="Paste anything — script, FAQ, product doc, customer story...")
            if st.form_submit_button("📚 Save to knowledge base", type="primary"):
                if title and content:
                    kb.add_document(title=title, content=content, source='manual_paste')
                    st.success(f"✅ Added {title}")
                    st.rerun()

    elif "Upload file" in upload_method:
        uploaded = st.file_uploader("Drop a file", type=['txt', 'md'])
        if uploaded:
            try:
                content = uploaded.read().decode('utf-8', errors='replace')
                title = st.text_input("Title", value=uploaded.name)
                if st.button("📚 Save to knowledge base", type="primary"):
                    kb.add_document(title=title, content=content, source=f'file:{uploaded.name}')
                    st.success(f"✅ Added {title}")
                    st.rerun()
            except Exception as e:
                st.error(f"Couldn't read file: {e}")

    elif "URL" in upload_method:
        url = st.text_input("URL to scrape", placeholder="https://aquelyst.com/about")
        if url and st.button("🌐 Scrape and add", type="primary"):
            with st.spinner("Fetching..."):
                try:
                    import enrichment
                    content_data = enrichment.gather_site_intelligence(url) if hasattr(enrichment, 'gather_site_intelligence') else None
                    if not content_data:
                        # Simple fallback fetch
                        import requests, re
                        r = requests.get(url, timeout=10, headers={'User-Agent': 'AqueLyst-Hunter'})
                        if r.status_code == 200:
                            text = re.sub(r'<[^>]+>', ' ', r.text)
                            text = re.sub(r'\s+', ' ', text).strip()[:30000]
                            kb.add_document(title=url, content=text, source=f'url:{url}')
                            st.success(f"✅ Scraped {len(text)} chars from {url}")
                            st.rerun()
                except Exception as e:
                    st.error(f"Couldn't scrape: {e}")


def _show_engagement_panel():
    """Auto-engagement controls — sends initial NEPQ outreach when leads go hot."""
    state = auto_engagement.get_state()
    running = state.get('running', False)
    config = state.get('config', {})
    stats = state.get('stats', {})

    st.markdown("### How auto-engagement works")
    st.markdown("""
    1. Bot scans your CRM every N minutes
    2. Finds leads with **AI score ≥ threshold** that haven't been contacted
    3. Generates a personalized NEPQ-style cold email
    4. **Drafts mode:** Saves to your draft queue for review
    5. **Send mode:** Sends immediately, schedules Day 3 / 7 / 14 / 21 follow-ups
    6. Stops when prospect replies (Inbox Watcher takes over)
    """)

    if running:
        st.success(f"🟢 **Auto-engagement is RUNNING** · "
                    f"Mode: **{config.get('auto_send', False) and 'AUTO-SEND' or 'DRAFT-ONLY'}** · "
                    f"Min score: **{config.get('min_score', 70)}**")

        cols = st.columns(4)
        cols[0].metric("Initial drafts", stats.get('initial_emails_drafted', 0))
        cols[1].metric("Initial sent", stats.get('initial_emails_sent', 0))
        cols[2].metric("Followups drafted", stats.get('followups_drafted', 0))
        cols[3].metric("Followups sent", stats.get('followups_sent', 0))

        if state.get('last_run'):
            st.caption(f"Last cycle: {state['last_run'][:19].replace('T', ' ')}")

        if st.button("🛑 Stop Auto-Engagement", type="primary", use_container_width=True):
            auto_engagement.stop_engagement()
            st.rerun()

    else:
        # Config form
        st.markdown("### Configure")

        col1, col2 = st.columns(2)
        with col1:
            min_score = st.slider("Hot lead threshold (AI score)", 30, 100, 70, 5,
                                   help="Only leads at or above this score get auto-engaged.")
            interval = st.slider("Check interval (minutes)", 5, 120, 15, 5,
                                  help="How often to scan the CRM for new hot leads.")
        with col2:
            max_per_run = st.slider("Max emails per cycle", 1, 25, 5, 1,
                                     help="Stay polite — limits how many emails fire per check.")
            mode = st.radio("Mode",
                             ["📝 Draft only (you approve before sending)",
                              "📤 Auto-send (no human approval)"],
                             help="Start in DRAFT mode until you trust the bot's writing.")

        auto_send = "Auto-send" in mode
        followup_enabled = st.checkbox("Also send NEPQ follow-ups on Day 3 / 7 / 14 / 21",
                                         value=True)

        # Show how many leads would be eligible RIGHT NOW
        candidates = auto_engagement.find_engagement_candidates(min_score)
        st.info(f"📊 **{len(candidates)} leads** in your CRM currently meet this threshold.")

        if candidates:
            with st.expander(f"Preview the {min(len(candidates), 10)} leads that would be engaged first"):
                for c in candidates[:10]:
                    st.markdown(f"- **{c['business_name']}** · score {c['lead_score']} · "
                                f"{c['email']}")

        if st.button("🚀 Start Auto-Engagement Bot",
                      type="primary", use_container_width=True,
                      disabled=not has_email_safe()):
            success, msg = auto_engagement.start_engagement(
                min_score=min_score,
                auto_send=auto_send,
                check_interval_minutes=interval,
                max_per_run=max_per_run,
                follow_up_enabled=followup_enabled,
            )
            if success:
                st.balloons()
                st.success("Bot started!")
                st.rerun()
            else:
                st.error(msg)

        if not has_email_safe() and not auto_send:
            st.caption("✓ Draft-only mode works without email setup")
        elif not has_email_safe():
            st.warning("Email setup required for auto-send mode")


def _show_responder_panel():
    """IMAP inbox watcher controls."""
    state = email_responder.get_state()
    running = state.get('running', False)
    stats = state.get('stats', {})

    st.markdown("### How inbox watching works")
    st.markdown("""
    1. Bot connects to your email inbox via IMAP every N minutes
    2. Reads unread messages, finds the matching lead in your CRM (by sender)
    3. Cerebras AI **classifies** what they said: interested / question / objection / unsubscribe / etc.
    4. Updates the lead's status automatically
    5. Generates an NEPQ-aligned reply
    6. **Draft mode:** Saves for your review · **Send mode:** Auto-replies in your name
    7. Skips auto-senders (no-reply addresses) and unsubscribes go straight to suppression list
    """)

    if not has_email_safe():
        st.error("⚠️ Email not configured — inbox watcher can't connect. Set up SMTP in **Setup → Email** first (same credentials work for IMAP).")
        return

    if running:
        st.success(f"🟢 **Inbox Watcher is RUNNING** · "
                    f"Mode: **{state.get('auto_reply_mode', 'draft').upper()}** · "
                    f"Every {state.get('check_interval_minutes', 30)} min")

        cols = st.columns(4)
        cols[0].metric("Checks done", stats.get('checks_completed', 0))
        cols[1].metric("Emails processed", stats.get('emails_processed', 0))
        cols[2].metric("Replies drafted", stats.get('replies_drafted', 0))
        cols[3].metric("Auto-sent", stats.get('replies_auto_sent', 0))

        if state.get('last_check'):
            st.caption(f"Last check: {state['last_check'][:19].replace('T', ' ')}")
        if state.get('next_check'):
            st.caption(f"Next check: {state['next_check'][:19].replace('T', ' ')}")

        col1, col2 = st.columns(2)
        if col1.button("🔍 Check Inbox Now", use_container_width=True):
            with st.spinner("Checking..."):
                email_responder.run_one_check()
                st.success("Done — see Activity tab for details")

        if col2.button("🛑 Stop Watcher", type="primary", use_container_width=True):
            email_responder.stop_responder()
            st.rerun()

    else:
        st.markdown("### Configure")

        col1, col2 = st.columns(2)
        with col1:
            interval = st.slider("Check inbox every N minutes", 5, 120, 30, 5)
        with col2:
            mode = st.radio("Reply mode",
                             ["📝 Draft only", "📤 Auto-reply"],
                             help="Auto-reply lets the bot answer prospects in real-time. Use carefully.")

        auto_reply_mode = 'send' if 'Auto-reply' in mode else 'draft'

        if st.button("🚀 Start Inbox Watcher",
                      type="primary", use_container_width=True):
            success, msg = email_responder.start_responder(
                check_interval_minutes=interval,
                auto_reply_mode=auto_reply_mode,
            )
            if success:
                st.balloons()
                st.success("Inbox watcher started!")
                st.rerun()
            else:
                st.error(msg)


def _show_training_chat():
    """Practice + train the NEPQ sales bot through conversation."""
    st.markdown("### Practice & Train")
    st.caption("Roleplay scenarios with the bot, get feedback on emails you wrote, "
                "or ask NEPQ methodology questions.")

    # Initialize conversation history
    if 'bot_chat_history' not in st.session_state:
        st.session_state.bot_chat_history = []

    # Mode selector
    col1, col2 = st.columns([3, 1])
    with col1:
        mode = st.radio(
            "What do you want to do?",
            [("practice", "🎭 Practice — I'll play a horse barn owner, you respond as the bot"),
             ("review", "🔍 Review — Critique an email I wrote"),
             ("rewrite", "✏️ Rewrite — Make my draft more NEPQ"),
             ("qa", "❓ Q&A — Ask me anything about NEPQ / sales psychology")],
            format_func=lambda x: x[1],
            horizontal=False,
        )
        chat_mode = mode[0]

    with col2:
        st.markdown("")
        st.markdown("")
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.bot_chat_history = []
            st.rerun()

    st.markdown("---")

    # Display chat history
    for msg in st.session_state.bot_chat_history:
        if msg['role'] == 'user':
            st.markdown(f"""
            <div style='background:#0f172a;color:white;padding:0.8rem 1.1rem;
                        border-radius:14px 14px 4px 14px;margin-bottom:0.5rem;
                        margin-left:15%;font-size:0.95rem'>
                {msg['content']}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style='background:#f1f5f9;color:#0f172a;padding:0.8rem 1.1rem;
                        border-radius:14px 14px 14px 4px;margin-bottom:0.5rem;
                        margin-right:15%;font-size:0.95rem;white-space:pre-wrap'>
                {msg['content']}
            </div>
            """, unsafe_allow_html=True)

    # Input
    with st.form('bot_chat_form', clear_on_submit=True):
        user_input = st.text_area(
            "Your message:",
            placeholder={
                'practice': "Try: 'We've tried fly traps but they don't really work...'",
                'review': "Paste an email you wrote here for critique...",
                'rewrite': "Paste your draft here and I'll NEPQ-ify it...",
                'qa': "Ask: 'How do I handle the price objection in email?'",
            }.get(chat_mode, "Type a message..."),
            height=100,
        )
        send = st.form_submit_button("Send →", type="primary", use_container_width=True)

    if send and user_input.strip():
        # Add user message to history
        st.session_state.bot_chat_history.append({
            'role': 'user', 'content': user_input.strip()
        })

        # Get bot response
        with st.spinner("Bot thinking..."):
            result = nepq_engine.training_chat(
                st.session_state.bot_chat_history[:-1],
                user_input.strip(),
                training_mode=chat_mode
            )

        st.session_state.bot_chat_history.append({
            'role': 'assistant', 'content': result['text']
        })

        # Cap history at 30 messages
        st.session_state.bot_chat_history = st.session_state.bot_chat_history[-30:]
        st.rerun()


def _show_bot_logs():
    """Combined activity log from engagement + responder."""
    st.markdown("### Activity Feed")
    st.caption("Auto-refreshes every 30s · Combined log from auto-engagement + inbox watcher")
    _bot_logs_fragment()


@st.fragment(run_every=30)
def _bot_logs_fragment():
    """Auto-refreshing combined log from engagement + responder."""
    eng_log = auto_engagement.read_log()
    resp_log = email_responder.read_log()

    combined = []
    for e in eng_log[:30]:
        combined.append({**e, 'source': 'engagement'})
    for e in resp_log[:30]:
        combined.append({**e, 'source': 'responder'})

    combined.sort(key=lambda x: x.get('time', ''), reverse=True)

    if not combined:
        st.info("No activity yet. Start auto-engagement or inbox watcher to see entries here.")
        return

    for entry in combined[:50]:
        ttype = entry.get('type', '')
        msg = entry.get('message', '')
        time_str = entry.get('time', '')[11:19]
        source = entry.get('source', '')

        color = {
            'sent': '#28a745',
            'drafted': '#0ea5e9',
            'classified': '#8b5cf6',
            'engaging': '#f59e0b',
            'cycle_start': '#fd7e14',
            'cycle_done': '#fd7e14',
            'check_start': '#06b6d4',
            'check_done': '#06b6d4',
            'system': '#6366f1',
            'error': '#dc3545',
            'skipped': '#6b7280',
        }.get(ttype, '#666')

        source_emoji = '📨' if source == 'responder' else '🚀'

        st.markdown(f"""
        <div style='border-left:3px solid {color};background:#fafafa;
                    padding:0.5rem 0.9rem;margin-bottom:0.35rem;
                    border-radius:0 4px 4px 0;font-size:0.88rem'>
            <span style='color:#999;margin-right:0.5rem'>{time_str}</span>
            <span style='margin-right:0.5rem'>{source_emoji}</span>
            {msg}
        </div>
        """, unsafe_allow_html=True)


def has_email_safe():
    """Safe wrapper for email config check."""
    try:
        return smtp_sender.is_configured()
    except Exception:
        return False


def show_inbox():
    """Unified Inbox — see everything the bot is sending and receiving."""

    ui_kit.page_hero(
        title="Everything the bot is <span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>sending &amp; receiving</span>",
        subtitle="Sent emails, drafts waiting for your approval, customer replies, "
                  "and live activity from the watcher.",
        eyebrow="📬 INBOX",
    )

    # Quick stats row (auto-refreshes every 30s)
    _inbox_status_fragment()

    # Capture data for buttons + tabs (these need fresh-on-each-render values)
    sent = database.get_sent_drafts(limit=500)
    pending = database.get_pending_drafts(limit=500)
    smtp_ok = smtp_sender.is_configured()
    watcher_running = email_responder.is_running()

    st.markdown("")

    # (Auto-engagement toggle is now built into the status card above — no redundant control)

    # Quick actions row
    if smtp_ok:
        col1, col2 = st.columns(2)
        if col1.button("🔍 Check Inbox Now",
                        type="primary" if not watcher_running else "secondary",
                        use_container_width=True):
            with st.spinner("Connecting to your inbox..."):
                try:
                    email_responder.run_one_check()
                    st.success("✅ Done — new replies appear below")
                    st.rerun()
                except Exception as e:
                    st.error(f"Check failed: {str(e)[:120]}")

        if col2.button("🧪 Test the Bot (send myself a test)", use_container_width=True):
            st.session_state.show_bot_test = True
    else:
        st.warning("⚠️ Email not connected. Set up email in **Setup → 📧 Email** first to see sent items and check inbox.")

    # Bot test panel
    if st.session_state.get('show_bot_test'):
        _show_bot_test_panel()

    # ===== ESCALATION BANNER (clickable, jumps to attention) =====
    escalation_count = sum(1 for d in pending if (d['message_type'] or '').startswith('ESCALATED'))
    if escalation_count:
        if st.button(
            f"⚠️  {escalation_count} email{'s' if escalation_count != 1 else ''} need{'s' if escalation_count == 1 else ''} your attention — click to review",
            type="primary", use_container_width=True, key="esc_banner_btn"
        ):
            st.session_state.show_escalations = True

        if st.session_state.get('show_escalations'):
            st.markdown("### ⚠️ Items needing your attention")
            _show_escalations(pending)
            if st.button("✅ Done reviewing — hide", key="hide_esc"):
                st.session_state.show_escalations = False
                st.rerun()

    st.markdown("---")

    # ===== REPLIES RECEIVED — split into Team and External, both open =====
    _show_split_received_replies()

    # Helpful hint to find the moved tabs
    st.markdown("---")
    st.caption("💡 Looking for **Sent by Bot** or **Drafts Pending**? They're on the **✉️ Compose** tab.")


def _inbox_engagement_toggle():
    """Toggle for auto-engagement bot at the top of the Inbox page."""
    state = auto_engagement.get_state()
    is_running = state.get('running', False)
    config = state.get('config', {})

    bg_color = '#dcfce7' if is_running else '#f1f5f9'
    border = '#86efac' if is_running else '#cbd5e1'
    status_label = "🟢 ON — actively engaging hot leads" if is_running else "⚫ OFF — bot idle"
    status_color = '#166534' if is_running else '#475569'

    # Pre-compute the subtitle (avoids the operator-precedence bug)
    if is_running:
        mode_label = 'AUTO-SEND' if config.get('auto_send', False) else 'DRAFT'
        subtitle = f"Min score: {config.get('min_score', 70)} · Mode: {mode_label}"
    else:
        subtitle = "Auto-engages leads above threshold with NEPQ outreach"

    st.html(
        f"<div style='background:{bg_color};border:2px solid {border};border-radius:12px;"
        f"padding:0.9rem 1.2rem;margin-bottom:0.5rem'>"
        f"<div style='font-weight:700;color:{status_color};font-size:1rem'>"
        f"🚀 Auto-Engagement Bot — {status_label}"
        f"</div>"
        f"<div style='color:#64748b;font-size:0.82rem;margin-top:0.15rem'>"
        f"{subtitle}"
        f"</div></div>"
    )

    # Toggle buttons — always show BOTH so user can force toggle if state is weird
    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "▶️ Start" if not is_running else "▶️ Restart",
            type="primary" if not is_running else "secondary",
            use_container_width=True,
            key="inbox_start_engagement",
            disabled=is_running,
        ):
            success, _ = auto_engagement.start_engagement(
                min_score=70, auto_send=False,
                check_interval_minutes=15, max_per_run=5,
                follow_up_enabled=True
            )
            if success:
                st.rerun()
    with col2:
        if st.button(
            "🛑 Stop",
            type="primary" if is_running else "secondary",
            use_container_width=True,
            key="inbox_stop_engagement",
            disabled=not is_running,
        ):
            auto_engagement.stop_engagement()
            # Force-clear the running state in case background thread is hung
            try:
                auto_engagement.update_state(running=False, config={})
            except Exception:
                pass
            st.rerun()

    st.markdown("")


def _show_split_received_replies():
    """Show all received replies split into Team and External boxes — both open."""
    inbound = database.get_all_inbound(limit=200)

    if not inbound:
        st.html(
            "<div style='background:#f9fafb;border:1px dashed #d1d5db;border-radius:12px;padding:2rem;text-align:center'>"
            "<div style='font-size:2rem'>📭</div>"
            "<div style='font-weight:600;color:#374151;margin-top:0.5rem'>No replies received yet</div>"
            "<div style='color:#6b7280;font-size:0.9rem;margin-top:0.3rem'>"
            "When prospects (or teammates) reply to your emails, they'll appear here.</div>"
            "</div>"
        )
        return

    # Split team vs external
    import team as _team
    team_msgs = []
    external_msgs = []
    for m in inbound:
        from_email = (m['from_email'] or '').lower().strip()
        if _team.get_member_by_email(from_email):
            team_msgs.append(m)
        else:
            external_msgs.append(m)

    # ===== EXTERNAL REPLIES (top — most important) =====
    # Filters
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    intent_filter = f1.selectbox(
        "Intent", ["All", "interested", "ready_to_buy", "pricing_request",
                    "question", "objection", "not_interested", "unsubscribe",
                    "auto_reply", "other"],
        key="inbox_intent_filter")
    sentiment_filter = f2.selectbox(
        "Sentiment", ["All", "positive", "neutral", "negative", "hostile"],
        key="inbox_sentiment_filter")
    age_filter = f3.selectbox(
        "Age", ["All", "Last 24h", "Last 7d", "Last 30d"],
        key="inbox_age_filter")
    f4.write("")  # spacer

    # Apply filters
    from datetime import datetime as _dt, timedelta as _td
    filtered = list(external_msgs)
    if intent_filter != "All":
        filtered = [m for m in filtered if (m['intent'] or '') == intent_filter]
    if sentiment_filter != "All":
        filtered = [m for m in filtered if (m['sentiment'] or 'neutral') == sentiment_filter]
    if age_filter != "All":
        cutoff = _dt.now() - {
            "Last 24h": _td(hours=24),
            "Last 7d": _td(days=7),
            "Last 30d": _td(days=30),
        }[age_filter]
        def _msg_dt(m):
            try:
                return _dt.fromisoformat((m['received_at'] or '').replace('Z', ''))
            except Exception:
                return _dt.min
        filtered = [m for m in filtered if _msg_dt(m) >= cutoff]

    label_suffix = ""
    if len(filtered) != len(external_msgs):
        label_suffix = f" — showing {len(filtered)} of {len(external_msgs)}"

    st.markdown(f"### 📨 From customers & prospects ({len(external_msgs)}){label_suffix}")
    if not filtered:
        st.caption(f"_No matches with these filters._")
    else:
        for m in filtered[:30]:
            _render_inbound_card(m, is_team=False)

    # Dismissed messages (junk) — undo if needed
    junk_inbound = [m for m in database.get_all_inbound(limit=100, include_junk=True)
                    if m['is_junk']]
    if junk_inbound:
        with st.expander(f"🗑 Dismissed as junk ({len(junk_inbound)}) — undo if you change your mind"):
            for m in junk_inbound[:30]:
                jc1, jc2, jc3 = st.columns([4, 2, 1])
                jc1.markdown(
                    f"**{m['business_name'] or m['from_name'] or m['from_email']}**  \n"
                    f"_{(m['subject'] or '')[:80]}_"
                )
                jc2.caption(f"Reason: {m['junk_reason'] or 'manual dismiss'}")
                if jc3.button("Restore", key=f"unjunk_{m['id']}"):
                    database.unmark_inbound_junk(m['id'])
                    st.rerun()

    st.markdown("---")

    # ===== TEAM REPLIES (separate box) =====
    st.markdown(f"### 🤝 From your AqueLyst team ({len(team_msgs)})")
    if not team_msgs:
        st.caption("_No team replies yet_")
    else:
        for m in team_msgs[:30]:
            _render_inbound_card(m, is_team=True)


def _render_inbound_card(msg, is_team=False):
    """Render a single inbound message card. Click to expand the full conversation thread."""
    biz = msg['business_name'] or msg['from_name'] or 'Unknown'
    from_email = msg['from_email'] or ''
    subject = msg['subject'] or '(no subject)'
    received = format_date_friendly(msg['received_at'])
    timestamp_full = format_timestamp_full(msg['received_at'])
    body_preview = (msg['body'] or '').strip().replace('\n', ' ')[:140]
    intent = msg['intent'] or ''
    sentiment = msg['sentiment'] or 'neutral'
    summary = msg['summary'] or ''

    intent_color = {
        'interested': '#16a34a', 'question': '#0ea5e9', 'objection': '#f59e0b',
        'not_interested': '#dc2626', 'unsubscribe': '#dc2626', 'pricing_request': '#7c3aed',
        'ready_to_buy': '#16a34a', 'auto_reply': '#9ca3af', 'other': '#6b7280',
    }.get(intent, '#6b7280')

    sentiment_emoji = {
        'positive': '😊', 'neutral': '😐', 'negative': '😟', 'hostile': '😡',
    }.get(sentiment, '😐')

    border_color = '#3b82f6' if is_team else '#4d7c0f'

    with st.container():
        # Inline header row with quick "Not real" dismiss button so junk can be
        # killed without expanding (only for external messages — team is always real)
        if not is_team:
            head = st.columns([5, 1])
            head[0].markdown(f"📨  **{biz}** · _{from_email}_  ·  {received}")
            if head[1].button("🗑 Not real", key=f"junk_{msg['id']}",
                                help="Dismiss as spam/non-prospect. Aqua learns "
                                     "from this and auto-flags similar future messages.",
                                use_container_width=True):
                database.mark_inbound_junk(msg['id'], reason="Manual dismiss from inbox")
                st.toast("✅ Dismissed. Aqua learned the pattern.", icon="🧠")
                st.rerun()

        # Click to expand the full conversation
        with st.expander(f"📨  **{biz}** · {received}  ·  _{subject[:60]}_"):
            st.html(
                f"<div style='display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;margin-bottom:0.6rem'>"
                f"<span style='background:{intent_color};color:white;padding:0.2rem 0.6rem;border-radius:10px;font-size:0.7rem;font-weight:700'>{intent.upper()}</span>"
                f"<span style='font-size:0.95rem'>{sentiment_emoji} {sentiment}</span>"
                f"<span style='color:#64748b;font-size:0.78rem'>from {from_email}</span>"
                f"<span style='color:#94a3b8;font-size:0.78rem;margin-left:auto'>{timestamp_full}</span>"
                f"</div>"
            )

            if summary:
                st.html(
                    f"<div style='background:#fef9e7;border-left:3px solid #f59e0b;padding:0.5rem 0.8rem;border-radius:0 4px 4px 0;font-size:0.85rem;color:#78350f;font-style:italic;margin-bottom:0.5rem'>"
                    f"💡 AI summary: {summary}"
                    f"</div>"
                )

            # Full body
            st.markdown("**Their message:**")
            st.code(msg['body'] or '(empty body)', language=None)

            # Full thread + action buttons
            st.markdown("---")
            col1, col2 = st.columns(2)
            if col1.button("💬 View full conversation thread", key=f"thread_{msg['id']}",
                            use_container_width=True):
                st.session_state.viewing_lead_id = msg['lead_id']
                st.session_state.page = "customer_detail"
                st.rerun()
            if col2.button("✏️ See AI's drafted reply", key=f"draftview_{msg['id']}",
                            use_container_width=True):
                st.session_state.page = "send_message"
                st.rerun()

            # Show the conversation thread inline
            if msg['lead_id']:
                thread = database.get_conversation_thread(msg['lead_id'])
                if len(thread) > 1:
                    st.markdown("---")
                    st.markdown(f"### 💬 Full thread ({len(thread)} messages)")
                    lead_for_thread = database.get_lead(msg['lead_id'])
                    if lead_for_thread:
                        _render_conversation_thread(thread, lead_for_thread,
                                                     key_ns=f"inbox_{msg['id']}")


def _show_escalations(all_pending):
    """Show escalated items the bot couldn't handle alone."""
    escalations = [d for d in all_pending if (d['message_type'] or '').startswith('ESCALATED')]

    if not escalations:
        st.html(
            "<div style='background:#f0fdf4;border:1px dashed #86efac;border-radius:12px;padding:2rem;text-align:center'>"
            "<div style='font-size:2rem'>✅</div>"
            "<div style='font-weight:600;color:#166534;margin-top:0.5rem'>No escalations — bot is handling everything</div>"
            "<div style='color:#15803d;font-size:0.9rem;margin-top:0.3rem'>"
            "When a prospect asks for pricing, mentions legal, gets angry, or wants to buy — "
            "they'll show up here for you to handle personally.</div>"
            "</div>"
        )
        return

    st.html(
        "<div style='background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;padding:1rem 1.2rem;margin-bottom:1rem'>"
        f"<strong style='color:#991b1b'>⚠️ {len(escalations)} email(s) need your personal attention</strong>"
        "<div style='color:#991b1b;font-size:0.88rem;margin-top:0.3rem'>"
        "These are situations the bot decided are too important / sensitive to auto-reply to. "
        "Each comes with a draft reply you can edit, send, or discard."
        "</div></div>"
    )

    for d in escalations:
        biz = d['business_name'] or 'Unknown'
        to_email = d['lead_email'] or ''
        subject = d['subject'] or '(no subject)'
        date = format_date_friendly(d['created_at'])
        msg_type = (d['message_type'] or '').replace('ESCALATED_', '')

        # Pull escalation reason from the lead's notes (NEW: stored separately,
        # not embedded in the email body so it can't accidentally get sent).
        # Fall back to content parsing for old escalations.
        reason = ''
        try:
            lead_row = database.get_lead(d['lead_id'])
            if lead_row and lead_row['notes']:
                # Look for the most recent escalation note
                notes = lead_row['notes']
                if '⚠️ ESCALATION' in notes:
                    last_escalation = notes.rsplit('⚠️ ESCALATION', 1)[1]
                    if ': ' in last_escalation:
                        reason = last_escalation.split(': ', 1)[1].strip()
        except Exception:
            pass

        # Legacy: also try parsing from body (for old drafts created before fix)
        content = d['content'] or ''
        if not reason and '⚠️ AI ESCALATED THIS — ' in content:
            try:
                reason = content.split('⚠️ AI ESCALATED THIS — ')[1].split('\n')[0]
            except IndexError:
                pass

        # Use the suggested-reply portion if it's an old draft with the warning in body
        suggested_reply = content
        if 'Suggested NEPQ reply (REVIEW BEFORE SENDING):' in content:
            suggested_reply = content.split('Suggested NEPQ reply (REVIEW BEFORE SENDING):')[1].strip()

        with st.expander(f"⚠️  **{biz}**  · {msg_type.upper()} · {date}", expanded=True):
            st.html(
                "<div style='background:#fef3c7;border-left:3px solid #f59e0b;padding:0.6rem 0.9rem;border-radius:6px;margin-bottom:0.8rem'>"
                f"<strong style='color:#92400e'>Why escalated:</strong> "
                f"<span style='color:#78350f'>{reason or 'Sensitive content (review the message before sending)'}</span>"
                "</div>"
            )

            st.markdown(f"**To:** {to_email}")
            st.markdown(f"**Original subject:** {subject.replace('[ESCALATED] ', '')}")

            st.markdown("**Suggested reply (review carefully — bot escalated this for a reason):**")
            edited = st.text_area("Reply", value=suggested_reply, height=250,
                                     key=f"esc_body_{d['id']}",
                                     label_visibility="collapsed")

            edited_subj = st.text_input("Subject", value=subject.replace('[ESCALATED] ', ''),
                                           key=f"esc_subj_{d['id']}")

            col1, col2, col3 = st.columns(3)
            if col1.button("📤 Send Reply", type="primary",
                            key=f"esc_send_{d['id']}", use_container_width=True):
                if not smtp_sender.is_configured():
                    st.error("Email not configured")
                elif not to_email:
                    st.error("No email on file")
                else:
                    with st.spinner("Sending..."):
                        success, m = smtp_sender.send_email(to_email, edited_subj, edited)
                        if success:
                            database.approve_draft(d['id'])
                            database.mark_draft_sent(d['id'])
                            database.update_lead(d['lead_id'], status='contacted',
                                                  last_contacted=datetime.now().isoformat())
                            database.log_activity(d['lead_id'], 'escalation_handled',
                                                   f"Escalation resolved: {edited_subj[:40]}")
                            st.balloons()
                            st.success("✅ Sent!")
                            st.rerun()
                        else:
                            st.error(translate_smtp_error(m))

            if col2.button("👁️ View Customer", key=f"esc_view_{d['id']}",
                            use_container_width=True):
                st.session_state.viewing_lead_id = d['lead_id']
                st.session_state.page = "customer_detail"
                st.rerun()

            if col3.button("🗑️ Discard", key=f"esc_discard_{d['id']}",
                            use_container_width=True):
                conn = database.get_connection()
                cur = conn.cursor()
                cur.execute('DELETE FROM outreach_drafts WHERE id = ?', (d['id'],))
                conn.commit()
                conn.close()
                st.rerun()


def _show_bot_test_panel():
    """Send a test email to yourself, optionally as a fake prospect."""
    st.html(
        "<div style='background:#eff6ff;border:1px solid #93c5fd;border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:1rem'>"
        "<strong style='color:#1e40af;font-size:1.05rem'>🧪 Test the Sales Bot</strong>"
        "<div style='color:#1e40af;font-size:0.9rem;margin-top:0.3rem'>"
        "We'll add a fake test customer using your email, then have the bot send YOU an NEPQ-style cold email "
        "as if you were a prospect. Reply to it (you can write any horse-barn-owner-style response), "
        "then click 'Check Inbox Now' to watch the bot reply back."
        "</div></div>"
    )

    col1, col2 = st.columns([3, 1])
    cfg = smtp_sender.load_smtp_config()

    test_business = col1.text_input("Test customer name",
                                      value="My Test Stable",
                                      placeholder="e.g. My Test Stable")

    if st.button("🚀 Create test lead + send NEPQ email to myself",
                  type="primary", use_container_width=True):
        if not cfg:
            st.error("Email not configured")
            return

        # Check if this email already exists
        existing = None
        for l in database.get_all_leads():
            if l['email'] and l['email'].lower() == cfg['email'].lower():
                existing = l
                break

        if existing:
            st.info(f"Test lead already exists (ID #{existing['id']}). Sending another email...")
            test_lead_id = existing['id']
            test_lead_dict = dict(existing)
        else:
            # Add as a fake hot lead
            test_lead_id = database.add_lead(
                business_name=test_business,
                contact_name=cfg.get('sender_name', 'Test User').split()[0],
                email=cfg['email'],
                phone='555-TEST',
                business_type='horse boarding facility',
                pain_hypothesis='ammonia smell in stalls + summer fly issues',
                product_fit='Duo Equine',
                lead_source='bot_test',
                notes='⚠️ This is a test lead pointing to your own email so you can test the bot end-to-end.',
            )
            if not test_lead_id:
                st.error("Couldn't create test lead (email might already exist as a real lead)")
                return

            database.update_lead(test_lead_id, lead_score=85, status='researched')
            test_lead_dict = dict(database.get_lead(test_lead_id))

        # Generate NEPQ initial email
        with st.spinner("Bot is writing the email..."):
            try:
                result = nepq_engine.generate_initial_outreach(test_lead_dict)
            except Exception as e:
                st.error(f"AI generation failed: {str(e)[:120]}")
                return

        # Send it
        with st.spinner("Sending..."):
            success, msg = smtp_sender.send_email(
                cfg['email'], result['subject'], result['body']
            )
            if success:
                draft_id = database.add_outreach_draft(
                    test_lead_id, 'bot_test_initial',
                    result['subject'], result['body']
                )
                database.approve_draft(draft_id)
                database.mark_draft_sent(draft_id)
                database.update_lead(test_lead_id, status='contacted',
                                      last_contacted=datetime.now().isoformat())
                database.log_activity(test_lead_id, 'bot_test_sent',
                                       f"Test NEPQ email sent ({result['source']})")

                st.balloons()
                st.success(f"✅ Sent to {cfg['email']}!")
                st.info("**Now do this:**  \n"
                        "1. Open your inbox  \n"
                        "2. Reply to the email pretending to be a horse barn owner "
                        "(e.g. 'We've tried fly traps but they don't work — what do you do differently?')  \n"
                        "3. Make sure **Inbox Watcher is running** in Sales Bot tab  \n"
                        "4. Click **🔍 Check Inbox Now** here to trigger the bot to read + reply")

                st.markdown(f"**Subject:** {result['subject']}")
                with st.expander("See what the bot wrote"):
                    st.code(result['body'])

                st.session_state.show_bot_test = False
            else:
                st.error(f"Send failed: {msg}")


def _show_received_replies():
    """Show recent replies the inbox watcher processed."""
    log = email_responder.read_log()
    classified = [e for e in log if e.get('type') in ('classified', 'sent', 'drafted', 'skipped')]

    if not classified:
        st.html(
            "<div style='background:#f9fafb;border:1px dashed #d1d5db;border-radius:12px;padding:2rem;text-align:center'>"
            "<div style='font-size:2rem'>📭</div>"
            "<div style='font-weight:600;color:#374151;margin-top:0.5rem'>No replies processed yet</div>"
            "<div style='color:#6b7280;font-size:0.9rem;margin-top:0.3rem'>"
            "Start the Inbox Watcher in Sales Bot, or click 'Check Inbox Now' above.</div>"
            "</div>"
        )

        st.markdown("---")
        st.markdown("##### Want to test it end-to-end?")
        st.markdown("Click **🧪 Test the Bot** above to add yourself as a fake prospect, "
                    "have the bot email you, reply to it, then watch the bot reply back.")
        return

    for entry in classified[:30]:
        ttype = entry.get('type', '')
        msg = entry.get('message', '')
        time_str = entry.get('time', '')[11:19]
        details = entry.get('details', {})
        intent = details.get('intent', '')

        color = {
            'classified': '#8b5cf6',
            'sent': '#16a34a',
            'drafted': '#0ea5e9',
            'skipped': '#9ca3af',
        }.get(ttype, '#666')

        intent_badge = ''
        if intent:
            intent_color = {
                'interested': '#16a34a',
                'question': '#0ea5e9',
                'objection': '#f59e0b',
                'not_interested': '#dc2626',
                'unsubscribe': '#dc2626',
            }.get(intent, '#6b7280')
            intent_badge = (
                f"<span style='background:{intent_color};color:white;padding:0.2rem 0.6rem;"
                f"border-radius:12px;font-size:0.7rem;font-weight:700;margin-left:0.5rem'>"
                f"{intent.upper()}</span>"
            )

        st.html(
            f"<div style='border-left:3px solid {color};background:#fff;border:1px solid #e2e8f0;"
            f"padding:0.8rem 1.1rem;margin-bottom:0.5rem;border-radius:0 8px 8px 0'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div style='color:#374151;font-size:0.92rem;font-weight:500'>{msg}{intent_badge}</div>"
            f"<div style='color:#9ca3af;font-size:0.78rem'>{time_str}</div>"
            f"</div></div>"
        )


def _show_sent_emails(sent):
    """Show emails the bot has actually sent."""
    if not sent:
        st.html(
            "<div style='background:#f9fafb;border:1px dashed #d1d5db;border-radius:12px;padding:2rem;text-align:center'>"
            "<div style='font-size:2rem'>📤</div>"
            "<div style='font-weight:600;color:#374151;margin-top:0.5rem'>No emails sent yet</div>"
            "<div style='color:#6b7280;font-size:0.9rem;margin-top:0.3rem'>"
            "Use Compose tab, run Auto-Engagement, or test the bot to start sending.</div>"
            "</div>"
        )
        return

    for d in sent[:50]:
        biz = d['business_name'] or 'Unknown'
        contact = d['contact_name'] or ''
        to_email = d['lead_email'] or ''
        subject = d['subject'] or '(no subject)'
        date = format_date_friendly(d['created_at'])
        msg_type = d['message_type'] or ''

        type_label = msg_type.replace('_', ' ').title()
        if msg_type.startswith('nepq'):
            type_color = '#7c3aed'
        elif msg_type.startswith('auto_reply'):
            type_color = '#0ea5e9'
        elif msg_type.startswith('bot_test'):
            type_color = '#f59e0b'
        else:
            type_color = '#64748b'

        with st.expander(f"📧  **{subject}**  →  {biz} · {date}"):
            st.html(
                f"<div style='display:flex;gap:0.5rem;margin-bottom:0.8rem;flex-wrap:wrap'>"
                f"<span style='background:{type_color};color:white;padding:0.2rem 0.6rem;border-radius:12px;font-size:0.75rem;font-weight:600'>"
                f"{type_label}</span>"
                f"<span style='background:#f1f5f9;color:#475569;padding:0.2rem 0.6rem;border-radius:12px;font-size:0.75rem'>"
                f"To: {to_email}</span>"
                f"<span style='background:#f1f5f9;color:#475569;padding:0.2rem 0.6rem;border-radius:12px;font-size:0.75rem'>"
                f"Contact: {contact or 'unknown'}</span>"
                f"</div>"
            )
            st.markdown(f"**Subject:** {subject}")
            st.markdown("**Body:**")
            st.code(d['content'] or '', language=None)

            if st.button(f"View customer", key=f"view_lead_from_sent_{d['id']}"):
                st.session_state.viewing_lead_id = d['lead_id']
                st.session_state.page = "customer_detail"
                st.rerun()


def _show_pending_drafts(pending):
    """Show drafts waiting for review/approval — with the original incoming message
    that they're responding to (so user can SEE what the prospect said)."""
    if not pending:
        st.html(
            "<div style='background:#f9fafb;border:1px dashed #d1d5db;border-radius:12px;padding:2rem;text-align:center'>"
            "<div style='font-size:2rem'>📝</div>"
            "<div style='font-weight:600;color:#374151;margin-top:0.5rem'>No drafts pending review</div>"
            "<div style='color:#6b7280;font-size:0.9rem;margin-top:0.3rem'>"
            "When the bot drafts emails (instead of auto-sending), they'll show here for your approval.</div>"
            "</div>"
        )
        return

    for d in pending[:50]:
        biz = d['business_name'] or 'Unknown'
        to_email = d['lead_email'] or ''
        subject = d['subject'] or '(no subject)'
        date = format_date_friendly(d['created_at'])
        msg_type = d['message_type'] or ''

        # Look up the original incoming message this draft is responding to
        inbound = database.get_inbound_by_draft(d['id'])

        with st.expander(f"📝  **{subject}**  →  {biz} · {date}"):
            st.markdown(f"**To:** {to_email}")
            st.markdown(f"**Type:** {msg_type.replace('_', ' ').title()}")

            # ===== Show the prospect's original message FIRST =====
            if inbound:
                intent = inbound['intent'] or 'unknown'
                sentiment = inbound['sentiment'] or 'neutral'
                summary = inbound['summary'] or ''
                received = format_date_friendly(inbound['received_at'])

                intent_color = {
                    'interested': '#16a34a',
                    'question': '#0ea5e9',
                    'objection': '#f59e0b',
                    'not_interested': '#dc2626',
                    'unsubscribe': '#dc2626',
                    'pricing_request': '#7c3aed',
                    'ready_to_buy': '#16a34a',
                    'auto_reply': '#9ca3af',
                }.get(intent, '#6b7280')

                sentiment_emoji = {
                    'positive': '😊',
                    'neutral': '😐',
                    'negative': '😟',
                    'hostile': '😡',
                }.get(sentiment, '😐')

                st.html(
                    f"<div style='background:#fef9e7;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;padding:0.9rem 1.1rem;margin:0.8rem 0'>"
                    f"<div style='display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.5rem'>"
                    f"<strong style='color:#92400e'>📨 What they said</strong>"
                    f"<span style='background:{intent_color};color:white;padding:0.15rem 0.55rem;border-radius:10px;font-size:0.7rem;font-weight:700'>{intent.upper()}</span>"
                    f"<span style='font-size:1rem'>{sentiment_emoji} {sentiment}</span>"
                    f"<span style='color:#92400e;font-size:0.78rem;margin-left:auto'>received {received}</span>"
                    f"</div>"
                    f"<div style='color:#78350f;font-size:0.85rem;font-style:italic;margin-bottom:0.5rem'>"
                    f"<strong>AI summary:</strong> {summary}"
                    f"</div></div>"
                )

                # The actual body of what they wrote
                inbound_body = inbound['body'] or '(no body)'
                with st.container():
                    st.markdown("**Their full message:**")
                    st.code(inbound_body, language=None)

                st.markdown("---")
                st.markdown("**✍️ Your AI-drafted reply (edit before sending):**")
            else:
                # No linked inbound — this is an outbound the bot initiated (cold email, etc)
                st.caption("ℹ️ This draft is a new outreach (not a reply). No prospect message to show.")

            # Editable
            edited_subject = st.text_input("Subject", value=subject,
                                              key=f"draft_subj_{d['id']}")
            edited_body = st.text_area("Message", value=d['content'] or '',
                                          height=250, key=f"draft_body_{d['id']}")

            col1, col2, col3 = st.columns(3)
            if col1.button("📤 Send Now", type="primary",
                            key=f"send_draft_{d['id']}", use_container_width=True):
                if not smtp_sender.is_configured():
                    st.error("Email not configured")
                elif not to_email:
                    st.error("No email on file for this lead")
                else:
                    with st.spinner("Sending..."):
                        success, msg = smtp_sender.send_email(
                            to_email, edited_subject, edited_body
                        )
                        if success:
                            database.approve_draft(d['id'])
                            database.mark_draft_sent(d['id'])
                            database.update_lead(d['lead_id'], status='contacted',
                                                  last_contacted=datetime.now().isoformat())
                            database.log_activity(d['lead_id'], 'manual_send',
                                                   f"Approved draft sent: {edited_subject[:40]}")
                            st.balloons()
                            st.success("✅ Sent!")
                            st.rerun()
                        else:
                            st.error(translate_smtp_error(msg))

            if col2.button("👁️ View Customer", key=f"view_pend_{d['id']}",
                            use_container_width=True):
                st.session_state.viewing_lead_id = d['lead_id']
                st.session_state.page = "customer_detail"
                st.rerun()

            if col3.button("🗑️ Discard", key=f"discard_{d['id']}",
                            use_container_width=True):
                # Just delete the draft
                conn = database.get_connection()
                cur = conn.cursor()
                cur.execute('DELETE FROM outreach_drafts WHERE id = ?', (d['id'],))
                conn.commit()
                conn.close()
                st.rerun()


def show_customers():
    """Customer hub — 6 tabs organized by how a sales team actually navigates leads."""

    ui_kit.page_hero(
        title="Your team's <span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>CRM</span>",
        subtitle="Action queue, pipeline, by product, federal bids, full search, "
                  "and the don't-contact list — all under one roof.",
        eyebrow="👥 CUSTOMERS",
    )
    add_l, add_r = st.columns([4, 1])
    if add_r.button("➕ Add customer", type="primary", use_container_width=True):
        st.session_state.page = "add_customer"
        st.rerun()

    # ── Persistent filter bar ─────────────────────────────────────────────
    # These filters apply across every tab below.
    PRODUCT_OPTIONS = ['All', 'Duo Equine', 'Pets', 'SpillMaster', 'AMR',
                       'HouseHold', 'Inversion Misting']
    SOURCE_OPTIONS = ['All', 'autopilot', 'web_form', 'manual',
                       'bid_intelligence', 'inbound', 'team_internal']

    fc1, fc2, fc3, fc4 = st.columns([3, 2, 2, 2])
    search = fc1.text_input(
        "Search", placeholder="🔍 business, contact, email, notes…",
        label_visibility="collapsed", key="customers_search",
    )
    product_filter = fc2.selectbox("Product", PRODUCT_OPTIONS,
                                    key="customers_product_filter")
    source_filter = fc3.selectbox("Source", SOURCE_OPTIONS,
                                   key="customers_source_filter")
    min_score = fc4.slider("Min score", 0, 100, 0, 5,
                            key="customers_min_score")

    # Pre-filter from clicked-KPI flow (Today page deep-link)
    pre_filter = st.session_state.pop('customers_filter', None)

    def _apply_filters(leads):
        out = leads
        if search and search.strip():
            q = search.lower().strip()
            out = [l for l in out if
                   q in (l['business_name'] or '').lower() or
                   q in (l['contact_name'] or '').lower() or
                   q in (l['email'] or '').lower() or
                   q in (l.get('notes') or '').lower()]
        if product_filter != 'All':
            out = [l for l in out if (l.get('product_fit') or '') == product_filter]
        if source_filter != 'All':
            out = [l for l in out if (l.get('lead_source') or '') == source_filter]
        if min_score > 0:
            out = [l for l in out if (l.get('lead_score') or 0) >= min_score]
        return out

    # Counts (after global filters applied)
    all_leads = _apply_filters(database.get_all_leads())
    hot = [l for l in all_leads if (l.get('lead_score') or 0) >= 70]
    due = _apply_filters(database.get_follow_ups_due())
    bids = [l for l in all_leads if (l.get('lead_source') or '') == 'bid_intelligence']

    # Action queue = hot + due, deduped, sorted by score desc
    seen = set()
    action_queue = []
    for batch in (hot, due):
        for l in batch:
            if l['id'] not in seen:
                seen.add(l['id'])
                action_queue.append(l)
    action_queue.sort(key=lambda l: -(l.get('lead_score') or 0))

    suppression = database.get_suppression_list()

    # ── Tabs ────────────────────────────────────────────────────────────────
    tab_action, tab_pipe, tab_prod, tab_bids, tab_all, tab_supp = st.tabs([
        f"🔥 Action queue ({len(action_queue)})",
        f"📊 Pipeline ({len(all_leads)})",
        "🛒 By Product",
        f"💰 Bids ({len(bids)})",
        f"📋 All & Search ({len(all_leads)})",
        f"🚫 Don't Contact ({len(suppression)})",
    ])

    with tab_action:
        st.caption(
            "Highest-priority leads to work right now — hot leads (score ≥ 70) "
            "plus follow-ups that are due today, sorted by score."
        )
        if not action_queue:
            st.info("🎉 Nothing urgent in the queue. Run Autopilot or check Pipeline.")
        else:
            show_customer_cards(action_queue,
                                 "Nothing urgent.", key_prefix="action_q")

    with tab_pipe:
        _render_pipeline_view(all_leads)

    with tab_prod:
        _render_by_product_view(all_leads)

    with tab_bids:
        st.caption(
            "Federal procurement leads — auto-imported from the Bids tab in Operations. "
            "These have hard deadlines and a different sales motion (proposal-based, B2G)."
        )
        if not bids:
            st.info(
                "_No bid leads yet. Go to **🚀 Operations → 💰 Bids** → click "
                "**📥 Add to CRM as lead** on opportunities you want to pursue._"
            )
        else:
            show_customer_cards(bids, "_No bid leads._", key_prefix="bids")

    with tab_all:
        if pre_filter:
            filter_labels = {
                'hot': '🔥 Hot leads (score ≥70)',
                'due': '📅 Follow-ups due today',
                'interested': '⭐ Interested',
                'trial_offered': '🎁 Trial offered',
                'closed_won': '✅ Closed/won',
            }
            st.info(f"Pre-filter applied: **{filter_labels.get(pre_filter, pre_filter)}** "
                     "(uncheck filters above to clear).")

        st.markdown(f"### 📋 {len(all_leads)} customers match current filters")
        show_customer_cards(all_leads, "No customers match these filters.",
                             key_prefix="all_filtered")

    with tab_supp:
        st.caption("Emails on the Don't-Contact list. Aqua never reaches out to these.")
        if not suppression:
            st.info("_Empty — nobody has been suppressed._")
        else:
            for entry in suppression:
                cc1, cc2, cc3 = st.columns([3, 2, 1])
                cc1.markdown(f"`{entry['email']}`")
                cc2.caption(f"Reason: {entry.get('reason') or '?'} · added {entry.get('added_at', '')[:10]}")
                if cc3.button("Restore", key=f"unsupp_{entry['id']}"):
                    database.remove_from_suppression(entry['email'])
                    st.rerun()


def _render_pipeline_view(leads):
    """Stage-by-stage breakdown — like a kanban but vertical/expandable."""
    STAGES = [
        ('new', '🆕 New', '#94a3b8'),
        ('researched', '🔍 Researched', '#06b6d4'),
        ('drafted', '✍️ Drafted', '#0ea5e9'),
        ('contacted', '📤 Contacted', '#4d7c0f'),
        ('follow_up_due', '🔁 Follow-up due', '#f59e0b'),
        ('interested', '⭐ Interested', '#16a34a'),
        ('trial_offered', '🎁 Trial offered', '#a855f7'),
        ('sample_sent', '📦 Sample sent', '#a855f7'),
        ('closed_won', '✅ Closed won', '#16a34a'),
        ('closed_lost', '❌ Closed lost', '#94a3b8'),
        ('opted_out', '🚫 Opted out', '#94a3b8'),
    ]

    # Group leads by status
    by_stage = {s[0]: [] for s in STAGES}
    for l in leads:
        s = l.get('status') or 'new'
        if s in by_stage:
            by_stage[s].append(l)

    # Visual summary row
    st.markdown("##### Pipeline at a glance")
    pipe_cols = st.columns(len(STAGES))
    for col, (stage_id, label, color) in zip(pipe_cols, STAGES):
        n = len(by_stage[stage_id])
        col.html(
            f"<div style='background:{color};color:white;border-radius:8px;"
            f"padding:0.5rem 0.4rem;text-align:center;height:64px;"
            f"display:flex;flex-direction:column;justify-content:center'>"
            f"<div style='font-size:1.2rem;font-weight:800'>{n}</div>"
            f"<div style='font-size:0.65rem;opacity:0.95;line-height:1.1'>{label}</div>"
            f"</div>"
        )

    st.markdown("---")
    st.markdown("##### Drill into any stage")
    for stage_id, label, _ in STAGES:
        items = by_stage[stage_id]
        if not items:
            continue
        with st.expander(f"{label} — {len(items)}", expanded=(len(items) <= 5)):
            show_customer_cards(items, "_No leads in this stage._",
                                 key_prefix=f"pipe_{stage_id}")


def _render_by_product_view(leads):
    """Group every lead under its product_fit, with sub-sections."""
    PRODUCTS = [
        ('Duo Equine', '🐴'),
        ('Pets', '🐾'),
        ('SpillMaster', '🧪'),
        ('AMR', '🚗'),
        ('HouseHold', '🏠'),
        ('Inversion Misting', '💨'),
    ]

    by_product = {p[0]: [] for p in PRODUCTS}
    unmatched = []
    for l in leads:
        p = (l.get('product_fit') or '').strip()
        if p in by_product:
            by_product[p].append(l)
        else:
            unmatched.append(l)

    # Visual summary cards
    st.markdown("##### Coverage by product")
    cols = st.columns(len(PRODUCTS))
    for col, (prod, emoji) in zip(cols, PRODUCTS):
        n = len(by_product[prod])
        hot_n = sum(1 for l in by_product[prod] if (l.get('lead_score') or 0) >= 70)
        col.html(
            f"<div style='background:rgba(255,255,255,0.7);"
            f"backdrop-filter:blur(12px);border:1px solid rgba(15,23,42,0.08);"
            f"border-radius:12px;padding:0.85rem 0.5rem;text-align:center'>"
            f"<div style='font-size:1.6rem'>{emoji}</div>"
            f"<div style='font-size:0.72rem;color:#64748b;text-transform:uppercase;"
            f"letter-spacing:0.05em;font-weight:700'>{prod}</div>"
            f"<div style='font-family:JetBrains Mono,monospace;font-size:1.4rem;"
            f"font-weight:700;color:#0a0f1c;margin-top:0.2rem'>{n}</div>"
            f"<div style='font-size:0.7rem;color:#dc2626;font-weight:600'>"
            f"🔥 {hot_n} hot</div></div>"
        )

    st.markdown("---")
    st.markdown("##### Drill into any product line")

    for prod, emoji in PRODUCTS:
        items = by_product[prod]
        if not items:
            continue
        items_sorted = sorted(items, key=lambda l: -(l.get('lead_score') or 0))
        hot_n = sum(1 for l in items_sorted if (l.get('lead_score') or 0) >= 70)
        with st.expander(f"{emoji} **{prod}** — {len(items_sorted)} leads "
                          f"({hot_n} hot)",
                          expanded=False):
            show_customer_cards(items_sorted, "_No leads for this product._",
                                 key_prefix=f"prod_{prod.replace(' ', '_')}")

    if unmatched:
        with st.expander(f"❓ Unmatched / no product set — {len(unmatched)}"):
            show_customer_cards(unmatched, "_None._", key_prefix="prod_unmatched")


def show_customer_cards(leads, empty_msg, key_prefix="default"):
    if not leads:
        st.info(empty_msg)
        return

    # Sales-stage order for progress visualization
    stage_order = [
        ('new', '🆕 New'),
        ('researched', '📚 Researched'),
        ('contacted', '📞 Contacted'),
        ('interested', '⭐ Interested'),
        ('trial_offered', '🎁 Trial offered'),
        ('sample_sent', '📦 Sample sent'),
        ('closed_won', '✅ Won'),
    ]

    for lead in leads[:50]:
        score = lead['lead_score'] or 0
        score_color = "#dc3545" if score >= 70 else "#ffc107" if score >= 40 else "#6c757d"

        # Compute stage progress (0-100%)
        current_status = lead['status'] or 'new'
        stage_keys = [s[0] for s in stage_order]
        try:
            current_stage_idx = stage_keys.index(current_status)
            stage_pct = int((current_stage_idx + 1) / len(stage_order) * 100)
        except ValueError:
            current_stage_idx = -1
            stage_pct = 0

        # Build mini progress bar HTML
        progress_dots = ''.join([
            f"<span style='display:inline-block;width:14px;height:14px;border-radius:50%;"
            f"background:{'#16a34a' if i <= current_stage_idx else '#e2e8f0'};"
            f"margin-right:3px' title='{label}'></span>"
            for i, (st_key, label) in enumerate(stage_order)
        ])

        status_label = STATUS_FRIENDLY.get(current_status, current_status)
        contact = lead['contact_name'] or 'No contact name'
        location = f"{lead['city']}, {lead['state']}" if lead['city'] else 'No location'

        st.html(
            f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:1rem 1.2rem;margin-bottom:0.6rem'>"
            f"<div style='display:flex;justify-content:space-between;align-items:start;gap:0.5rem;margin-bottom:0.5rem'>"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-weight:700;color:#0f172a;font-size:1.05rem'>{lead['business_name']}</div>"
            f"<div style='color:#64748b;font-size:0.85rem;margin-top:0.15rem'>{contact} · {location}</div>"
            f"</div>"
            f"<div style='display:flex;gap:0.4rem;align-items:center'>"
            f"<span style='background:#f1f5f9;color:#0f172a;padding:0.2rem 0.6rem;border-radius:10px;font-size:0.75rem;font-weight:600'>{status_label}</span>"
            f"<span style='background:{score_color};color:white;padding:0.3rem 0.7rem;border-radius:14px;font-weight:700;font-size:0.85rem'>{score}</span>"
            f"</div></div>"
            f"<div style='display:flex;align-items:center;gap:0.5rem;margin-top:0.5rem'>"
            f"<div style='font-size:0.7rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;min-width:70px'>Stage</div>"
            f"<div>{progress_dots}</div>"
            f"<div style='font-size:0.78rem;color:#475569;margin-left:auto'>{stage_pct}% through funnel</div>"
            f"</div></div>"
        )

        # Open button below the card
        if st.button(f"Open {lead['business_name'][:50]} →",
                      key=f"view_{key_prefix}_{lead['id']}",
                      use_container_width=True):
            st.session_state.viewing_lead_id = lead['id']
            st.session_state.page = "customer_detail"
            st.rerun()


# ===========================================================================
# CUSTOMER DETAIL
# ===========================================================================
def show_customer_detail():
    lead_id = st.session_state.get('viewing_lead_id')
    if not lead_id:
        st.session_state.page = "customers"
        st.rerun()
        return

    lead = database.get_lead(lead_id)
    if not lead:
        st.error("Customer not found")
        if st.button("← Back to Customers"):
            st.session_state.page = "customers"
            st.rerun()
        return

    if st.button("← Back to Customers"):
        st.session_state.page = "customers"
        st.rerun()

    # Header
    score = lead['lead_score'] or 0
    score_color = "#dc3545" if score >= 70 else "#ffc107" if score >= 40 else "#6c757d"
    status_label = STATUS_FRIENDLY.get(lead['status'], lead['status'])

    st.title(lead['business_name'])
    st.markdown(
        f"<div style='margin-bottom:1.5rem'>"
        f"<span style='background:{score_color};color:white;padding:0.4rem 0.9rem;"
        f"border-radius:20px;font-weight:bold'>Match Score: {score}/100</span>"
        f" &nbsp;&nbsp; "
        f"<span style='background:#e9ecef;padding:0.4rem 0.9rem;border-radius:20px'>{status_label}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    # Two big primary actions
    col1, col2 = st.columns(2)

    with col1:
        if st.button("✉️ Send Message", type="primary", use_container_width=True):
            st.session_state.message_lead_id = lead_id
            st.session_state.page = "send_message"
            st.rerun()

    with col2:
        if lead['phone']:
            phone_url = gmail_integration.build_call_url(lead['phone'])
            st.markdown(
                f"<a href='{phone_url}' style='text-decoration:none'>"
                f"<button style='background:#28a745;color:white;border:none;"
                f"padding:0.75rem;border-radius:8px;width:100%;font-size:1rem;"
                f"font-weight:600;cursor:pointer'>📞 Call {lead['phone']}</button></a>",
                unsafe_allow_html=True
            )
        else:
            st.button("📞 No phone on file", disabled=True, use_container_width=True)

    st.markdown("")

    # Contact info
    with st.expander("📞 Contact Info", expanded=True):
        col1, col2 = st.columns(2)
        col1.markdown(f"**Contact:** {lead['contact_name'] or '_Not set_'}")
        col1.markdown(f"**Email:** {lead['email'] or '_Not set_'}")
        col1.markdown(f"**Phone:** {lead['phone'] or '_Not set_'}")
        col2.markdown(f"**Website:** {lead['website'] or '_Not set_'}")
        col2.markdown(f"**Location:** {(lead['city'] or '') + ', ' + (lead['state'] or '') if lead['city'] else '_Not set_'}")
        col2.markdown(f"**Type:** {lead['business_type'] or '_Not set_'}")

        # Auto-find info button
        if lead['website']:
            if st.button("✨ Auto-find email & phone from their website", key=f"enrich_{lead_id}"):
                with st.spinner(f"Looking up {lead['website']}..."):
                    result = enrichment.enrich_from_website(lead['website'])
                    updates = {}
                    if result['emails'] and not lead['email']:
                        updates['email'] = enrichment.get_best_email(result['emails'])
                    if result['phones'] and not lead['phone']:
                        updates['phone'] = enrichment.get_best_phone(result['phones'])
                    if result['socials'] and not lead['social_url']:
                        updates['social_url'] = next(iter(result['socials'].values()))
                    if updates:
                        database.update_lead(lead_id, **updates)
                        database.log_activity(lead_id, "enrichment", f"Auto-found {len(updates)} fields")
                        st.success(f"✅ Found {len(updates)} new pieces of info!")
                        st.rerun()
                    else:
                        st.info("Nothing new found")

    # About this customer
    with st.expander("📋 About This Customer"):
        st.markdown(f"**Their problem:**  \n{lead['pain_hypothesis'] or '_Not documented yet_'}")
        if lead['notes']:
            st.markdown(f"**Notes:**  \n{lead['notes']}")
        st.markdown(f"**How we found them:** {lead['lead_source'] or '_Unknown_'}")
        st.markdown(f"**Match score:** {score}/100 — {lead_scoring.get_lead_score_explanation(score)}")
        st.markdown(f"**Best product fit:** {lead['product_fit'] or '_Not determined_'}")

    # ===== TABS — clean navigation instead of stacked expanders =====
    thread = database.get_conversation_thread(lead_id)
    thread_count = len(thread)
    history = [a for a in database.get_recent_activities(50) if a['lead_id'] == lead_id]

    cd_tab_conv, cd_tab_act, cd_tab_status, cd_tab_actions = st.tabs([
        f"💬 Conversation ({thread_count})",
        f"📜 Activity ({len(history)})",
        "✏️ Status",
        "⚙️ Actions",
    ])

    with cd_tab_conv:
        if not thread:
            st.caption("No emails exchanged yet. When you send or receive a message, it'll show here.")
        else:
            _render_conversation_thread(thread, lead, key_ns=f"detail_{lead_id}")

    with cd_tab_act:
        if history:
            for a in history[:20]:
                st.markdown(f"- {a['description']} — *{format_date_friendly(a['created_at'])}*")
        else:
            st.caption("No activity yet")

    with cd_tab_status:
        statuses_list = list(STATUS_FRIENDLY.items())
        current_idx = next((i for i, (s, _) in enumerate(statuses_list) if s == lead['status']), 0)
        selected = st.selectbox(
            "Where is this customer in your sales process?",
            statuses_list,
            format_func=lambda x: x[1],
            index=current_idx
        )

        if st.button("💾 Save Status Change", key=f"save_status_{lead_id}"):
            old_status = lead['status']
            database.update_lead(lead_id, status=selected[0])
            if old_status != selected[0]:
                database.log_activity(lead_id, "status_change",
                                       f"Status: {STATUS_FRIENDLY.get(old_status, old_status)} → {selected[1]}")
            st.success("✅ Updated!")
            st.rerun()

    with cd_tab_actions:
        col1, col2 = st.columns(2)

        if col1.button("📅 Schedule follow-up in 7 days", use_container_width=True, key=f"fu_{lead_id}"):
            database.schedule_follow_up(lead_id, "manual", 7)
            database.log_activity(lead_id, "follow_up", "Scheduled in 7 days")
            st.success("✅ Will follow up in 7 days")
            st.rerun()

        if col2.button("🚫 Add to Don't-Contact list", use_container_width=True, key=f"sup_{lead_id}"):
            if lead['email']:
                database.add_to_suppression(lead['email'], "manual")
                database.log_activity(lead_id, "suppression", "Added to don't-contact list")
                st.success("✅ Won't contact again")
                st.rerun()

        st.markdown("---")
        if st.button("🗑️ Delete this customer", key=f"del_{lead_id}"):
            database.delete_lead(lead_id)
            st.success("Deleted")
            st.session_state.page = "customers"
            st.rerun()


# ===========================================================================
# SEND MESSAGE
# ===========================================================================
def _render_conversation_thread(thread, lead, key_ns=""):
    """Render the conversation as chat bubbles — outgoing right, incoming left.

    key_ns: optional namespace appended to widget keys so the same thread
    rendered from multiple parent contexts (e.g., separate inbox cards) doesn't
    collide on Streamlit element IDs.
    """

    contact_name = (lead['contact_name'] or 'them').split()[0] if lead['contact_name'] else 'them'

    # Top summary line
    out_count = sum(1 for m in thread if m['direction'] == 'out')
    in_count = sum(1 for m in thread if m['direction'] == 'in')
    sent_count = sum(1 for m in thread if m['direction'] == 'out' and m.get('sent'))
    pending_count = sum(1 for m in thread if m['direction'] == 'out' and not m.get('sent'))

    st.html(
        f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;"
        f"padding:0.6rem 1rem;margin-bottom:1rem;font-size:0.85rem;color:#475569'>"
        f"<strong>{out_count}</strong> from us "
        f"({sent_count} sent · {pending_count} draft) &nbsp;·&nbsp; "
        f"<strong>{in_count}</strong> from {contact_name}"
        f"</div>"
    )

    for msg in thread:
        timestamp = format_timestamp_full(msg['timestamp'])
        relative = format_date_friendly(msg['timestamp'])

        if msg['direction'] == 'out':
            # Outgoing message — right side, green
            is_draft = not msg.get('sent')
            sent_badge = (
                "<span style='background:#16a34a;color:white;padding:0.1rem 0.5rem;"
                "border-radius:8px;font-size:0.7rem;font-weight:700;margin-left:0.5rem'>SENT</span>"
                if msg.get('sent')
                else "<span style='background:#f59e0b;color:white;padding:0.1rem 0.5rem;"
                     "border-radius:8px;font-size:0.7rem;font-weight:700;margin-left:0.5rem'>DRAFT</span>"
            )

            mtype = (msg.get('message_type') or 'email').replace('_', ' ').title()

            st.html(
                f"<div style='display:flex;justify-content:flex-end;margin:0.6rem 0'>"
                f"<div style='max-width:85%;background:linear-gradient(135deg,#4d7c0f 0%,#65a30d 100%);"
                f"color:white;padding:0.9rem 1.2rem;border-radius:14px 14px 4px 14px;"
                f"box-shadow:0 2px 6px rgba(26,95,63,0.18)'>"
                f"<div style='font-size:0.7rem;opacity:0.85;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-bottom:0.25rem'>"
                f"📤 You · {mtype}{sent_badge}"
                f"</div>"
                f"<div style='font-weight:700;font-size:0.95rem;margin-bottom:0.4rem'>"
                f"{msg['subject']}"
                f"</div>"
                f"<div style='font-size:0.88rem;line-height:1.5;white-space:pre-wrap;opacity:0.95'>"
                f"{(msg['body'] or '')[:1500]}"
                f"{'...' if len(msg['body'] or '') > 1500 else ''}"
                f"</div>"
                f"<div style='font-size:0.7rem;opacity:0.75;margin-top:0.5rem;text-align:right'>"
                f"{timestamp} · {relative}"
                f"</div>"
                f"</div></div>"
            )

            # If this is a DRAFT, show inline Send / Edit / Discard so user doesn't navigate away
            # NOTE: lead may be a sqlite3.Row OR a dict — use bracket access with safe fallback
            try:
                lead_email = lead['email']
            except (KeyError, TypeError, IndexError):
                lead_email = None
            if is_draft and lead_email:
                _spc, b1, b2, b3 = st.columns([1, 1, 1, 1])
                if b1.button("📤 Send Now", type="primary", key=f"thread_send_{key_ns}_{msg['id']}",
                              use_container_width=True):
                    if smtp_sender.is_configured():
                        if database.is_suppressed(lead['email']):
                            st.error("Email is on suppression list.")
                        else:
                            with st.spinner("Sending..."):
                                ok, send_msg = smtp_sender.send_email(
                                    lead['email'], msg['subject'], msg['body']
                                )
                                if ok:
                                    database.approve_draft(msg['id'])
                                    database.mark_draft_sent(msg['id'])
                                    database.update_lead(lead['id'], status='contacted',
                                                          last_contacted=datetime.now().isoformat())
                                    database.log_activity(lead['id'], 'manual_send_thread',
                                                          f"Sent from thread: {msg['subject'][:40]}")
                                    st.balloons()
                                    st.success("✅ Sent!")
                                    st.rerun()
                                else:
                                    st.error(translate_smtp_error(send_msg))
                    else:
                        st.error("Email not configured.")
                if b2.button("✏️ Edit in Compose", key=f"thread_edit_{key_ns}_{msg['id']}",
                              use_container_width=True):
                    st.session_state.page = "send_message"
                    st.rerun()
                if b3.button("🗑️ Discard", key=f"thread_discard_{key_ns}_{msg['id']}",
                              use_container_width=True):
                    conn = database.get_connection()
                    cur = conn.cursor()
                    cur.execute('DELETE FROM outreach_drafts WHERE id = ?', (msg['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()

        else:
            # Incoming message — left side, white with intent badge
            intent = msg.get('intent', '') or 'unknown'
            sentiment = msg.get('sentiment', '') or 'neutral'
            summary = msg.get('summary', '')

            intent_color = {
                'interested': '#16a34a',
                'question': '#0ea5e9',
                'objection': '#f59e0b',
                'not_interested': '#dc2626',
                'unsubscribe': '#dc2626',
                'pricing_request': '#7c3aed',
                'ready_to_buy': '#16a34a',
                'auto_reply': '#9ca3af',
                'other': '#6b7280',
            }.get(intent, '#6b7280')

            sentiment_emoji = {
                'positive': '😊',
                'neutral': '😐',
                'negative': '😟',
                'hostile': '😡',
            }.get(sentiment, '😐')

            from_name = msg.get('from_name', '') or contact_name
            from_email = msg.get('from_email', '')

            summary_block = (
                f"<div style='background:#fef9e7;border-left:3px solid #f59e0b;"
                f"padding:0.4rem 0.7rem;border-radius:0 4px 4px 0;margin-bottom:0.5rem;"
                f"font-size:0.78rem;color:#78350f;font-style:italic'>"
                f"💡 AI summary: {summary}"
                f"</div>"
                if summary else ""
            )

            st.html(
                f"<div style='display:flex;justify-content:flex-start;margin:0.6rem 0'>"
                f"<div style='max-width:85%;background:#fff;border:1px solid #e2e8f0;"
                f"padding:0.9rem 1.2rem;border-radius:14px 14px 14px 4px;"
                f"box-shadow:0 1px 3px rgba(0,0,0,0.05)'>"
                f"<div style='display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;margin-bottom:0.4rem'>"
                f"<span style='font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600'>"
                f"📨 {from_name}"
                f"</span>"
                f"<span style='background:{intent_color};color:white;padding:0.1rem 0.5rem;"
                f"border-radius:8px;font-size:0.7rem;font-weight:700'>{intent.upper()}</span>"
                f"<span style='font-size:0.85rem'>{sentiment_emoji}</span>"
                f"</div>"
                f"<div style='font-weight:700;color:#0f172a;font-size:0.95rem;margin-bottom:0.4rem'>"
                f"{msg['subject']}"
                f"</div>"
                f"{summary_block}"
                f"<div style='font-size:0.88rem;line-height:1.5;white-space:pre-wrap;color:#334155'>"
                f"{(msg['body'] or '')[:1500]}"
                f"{'...' if len(msg['body'] or '') > 1500 else ''}"
                f"</div>"
                f"<div style='font-size:0.7rem;color:#94a3b8;margin-top:0.5rem'>"
                f"{from_email} · {timestamp} · {relative}"
                f"</div>"
                f"</div></div>"
            )


def show_send_message():
    """Compose page — write to anyone + see all sent emails + drafts pending."""

    ui_kit.page_hero(
        title="Write to anyone · "
               "<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>see sent</span> · review drafts",
        subtitle="Email any address. AI drafts it. Every send is logged. "
                  "Bot drafts wait for your approval before going out.",
        eyebrow="✉️ COMPOSE",
    )

    sent = database.get_sent_drafts(limit=500)
    pending = database.get_pending_drafts(limit=500)

    # Sub-tab state — controllable from outside (e.g., inbox "Review drafts" button)
    active = st.session_state.setdefault('compose_subtab', 'compose')

    sub_options = [
        ('compose', "✏️ Compose new"),
        ('sent', f"📤 Sent by Bot ({len(sent)})"),
        ('drafts', f"📝 Drafts Pending ({len(pending)})"),
    ]
    sub_cols = st.columns(len(sub_options))
    for i, (key, label) in enumerate(sub_options):
        with sub_cols[i]:
            is_active = active == key
            if st.button(label, key=f"compose_subtab_{key}", use_container_width=True,
                         type="primary" if is_active else "secondary"):
                st.session_state.compose_subtab = key
                st.rerun()
    st.markdown("")

    if active == 'sent':
        _show_sent_emails(sent)
    elif active == 'drafts':
        _show_pending_drafts(pending)
    else:
        _show_compose_main()


def _show_compose_main():
    """The actual compose form (was the body of show_send_message)."""

    # If a lead was pre-selected (e.g. user clicked 'Send Message' on a customer detail page),
    # default to CRM mode so they see that customer immediately.
    pre_selected_lead = st.session_state.get('message_lead_id')
    default_mode_index = 1 if pre_selected_lead else 0

    mode = st.radio(
        "Who are you writing to?",
        ["📧 Anyone (type any email address)", "👥 Pick from my customers"],
        horizontal=True,
        key="compose_mode_picker",
        index=default_mode_index,
    )

    if "Pick from my customers" in mode:
        _compose_from_crm()
    else:
        _compose_free_form()

    # ===== Recent-sends panel (always visible, bottom of Compose) =====
    st.markdown("---")
    st.markdown("### 📤 Recently sent (everything that left this OS)")
    st.caption("Auto-refreshes every 30s · Every email — customers, prospects, teammates — logged here. "
                "Click 'Open in Inbox' for the full archive.")

    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("📬 Open Inbox →", use_container_width=True):
            st.session_state.page = "inbox"
            st.rerun()

    _compose_recent_sends_fragment()


@st.fragment(run_every=30)
def _compose_recent_sends_fragment():
    """Auto-refreshing recent-sends panel on Compose page."""
    recent_sent = database.get_sent_drafts(limit=10)

    if not recent_sent:
        st.info("Nothing sent yet — write your first message above.")
        return

    for d in recent_sent[:10]:
        biz = d['business_name'] or 'Unknown'
        to_email = d['lead_email'] or '?'
        subject = d['subject'] or '(no subject)'
        date = format_date_friendly(d['created_at'])
        msg_type = d['message_type'] or ''

        # Color/icon based on type
        if 'team' in msg_type.lower() or '[Team]' in biz:
            type_icon = '🤝'
            type_label = 'Team'
        elif msg_type.startswith('nepq') or msg_type.startswith('compose'):
            type_icon = '✉️'
            type_label = 'Compose'
        elif msg_type.startswith('auto_reply'):
            type_icon = '🤖'
            type_label = 'Auto-reply'
        elif msg_type.startswith('bot_test'):
            type_icon = '🧪'
            type_label = 'Test'
        else:
            type_icon = '📧'
            type_label = msg_type[:15]

        st.html(
            f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:8px;"
            f"padding:0.65rem 1rem;margin-bottom:0.4rem;display:flex;"
            f"align-items:center;justify-content:space-between'>"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-weight:600;color:#0f172a;font-size:0.92rem;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>"
            f"{type_icon} {subject}</div>"
            f"<div style='color:#64748b;font-size:0.78rem;margin-top:0.15rem'>"
            f"to <strong>{biz}</strong> · {to_email} · {type_label}"
            f"</div>"
            f"</div>"
            f"<div style='color:#94a3b8;font-size:0.78rem;flex-shrink:0;margin-left:0.6rem'>"
            f"{date}</div>"
            f"</div>"
        )


def _compose_from_crm():
    """Original flow — pick from existing CRM leads."""
    lead_id = st.session_state.get('message_lead_id')

    if not lead_id:
        all_leads = database.get_all_leads()
        if not all_leads:
            st.info("You don't have any customers yet.")
            if st.button("➕ Add Your First Customer", type="primary"):
                st.session_state.page = "add_customer"
                st.rerun()
            return

        all_leads_sorted = sorted(all_leads, key=lambda x: -(x['lead_score'] or 0))
        options = [(l['id'], f"{l['business_name']} (score {l['lead_score'] or 0})") for l in all_leads_sorted]
        selected = st.selectbox("Pick a customer:", options, format_func=lambda x: x[1])

        if st.button("Continue →", type="primary"):
            st.session_state.message_lead_id = selected[0]
            st.rerun()
        return

    lead = database.get_lead(lead_id)
    if not lead:
        st.session_state.pop('message_lead_id', None)
        st.rerun()
        return

    st.markdown(f"### To: **{lead['business_name']}**")
    st.caption(f"{lead['contact_name'] or 'No contact'} · {lead['email'] or '⚠️ NO EMAIL'} · "
               f"Score: {lead['lead_score'] or 0}")

    if st.button("← Pick a different customer"):
        st.session_state.pop('message_lead_id', None)
        st.session_state.pop('draft', None)
        st.rerun()

    if not lead['email']:
        st.warning("⚠️ This customer has no email. Add one in Customers tab.")
        return
    if database.is_suppressed(lead['email']):
        st.error("⚠️ This email is on your Don't-Contact list.")
        return

    _render_compose_form(
        recipient_email=lead['email'],
        recipient_name=lead['contact_name'] or '',
        lead_data=dict(lead),
        existing_lead_id=lead_id,
    )


def _compose_free_form():
    """New flow — write to anyone, even non-leads."""
    col1, col2 = st.columns([2, 1])
    with col1:
        recipient_email = st.text_input(
            "📧 Their email address",
            placeholder="example@horsefarm.com",
            key="compose_freeform_email",
        )
    with col2:
        recipient_name = st.text_input(
            "Their name (optional)",
            placeholder="Sarah",
            key="compose_freeform_name",
        )

    if not recipient_email:
        st.info("Type an email address above to start composing.")
        return

    if not email_helpers.is_valid_email(recipient_email):
        st.warning("That doesn't look like a valid email.")
        return

    # Check if email already exists in CRM
    existing_lead = None
    for l in database.get_all_leads():
        if l['email'] and l['email'].lower() == recipient_email.lower():
            existing_lead = l
            break

    # ===== Detect if recipient is on the AqueLyst team =====
    import team as _team
    team_member = _team.get_member_by_email(recipient_email)

    if team_member:
        st.html(
            "<div style='background:#eff6ff;border-left:3px solid #2563eb;padding:0.7rem 1rem;"
            "border-radius:6px;margin-bottom:0.6rem;font-size:0.9rem'>"
            f"🤝 <strong>{team_member['name']}</strong> is on your AqueLyst team "
            f"({team_member.get('short_role', team_member.get('role', ''))}). "
            f"Aqua will use a casual peer tone — no sales pitch."
            "</div>"
        )
        lead_data = {
            'business_name': team_member.get('company', 'AqueLyst'),
            'contact_name': team_member['name'],
            'email': recipient_email,
            'business_type': team_member.get('role', ''),
            'pain_hypothesis': '',
        }
        existing_lead_id = None
    elif existing_lead:
        st.success(f"✓ This email is already in your CRM as **{existing_lead['business_name']}**")
        st.caption("AI will use their existing context (score, problem, prior emails) when writing.")
        lead_data = dict(existing_lead)
        existing_lead_id = existing_lead['id']
    else:
        st.html(
            "<div style='background:#fef3c7;border-left:3px solid #f59e0b;padding:0.6rem 0.9rem;"
            "border-radius:6px;margin-bottom:0.5rem;font-size:0.88rem'>"
            "💡 New contact — after you send, we'll ask if you want to add them as a customer."
            "</div>"
        )
        # Title-case the name pulled from the email prefix
        derived_name = (recipient_name or recipient_email.split('@')[0]).strip()
        if derived_name and derived_name == derived_name.lower():
            derived_name = derived_name.title()
        lead_data = {
            'business_name': derived_name,
            'contact_name': derived_name,
            'email': recipient_email,
            'business_type': '',
            'pain_hypothesis': '',
        }
        existing_lead_id = None

    if database.is_suppressed(recipient_email):
        st.error("⚠️ This email is on your Don't-Contact list. Remove it from suppression first.")
        return

    _render_compose_form(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        lead_data=lead_data,
        existing_lead_id=existing_lead_id,
    )


def _render_compose_form(recipient_email, recipient_name, lead_data, existing_lead_id=None):
    """Shared compose form: pick goal → AI draft → review → send → maybe-add-to-CRM."""

    st.markdown("---")
    st.markdown("### What's the goal of this message?")
    goal = st.radio(
        "Pick one:",
        list(GOAL_TO_TYPE.keys()),
        label_visibility="collapsed",
        key=f"goal_{recipient_email}",
    )
    message_type = GOAL_TO_TYPE[goal]

    best_provider = ai_providers.get_best_provider()
    provider_label = {
        'claude': '⚡⚡⚡⚡ Claude',
        'cerebras': '⚡⚡⚡ Cerebras',
        'openai': '⚡⚡⚡ OpenAI',
        'ollama': '⚡⚡ Ollama',
        'templates': '⚡ Templates',
    }.get(best_provider, '⚡ Templates')

    # Custom message gets a special input box
    custom_instruction = ''
    if message_type == 'custom':
        st.html(
            "<div style='background:#fef3c7;border-left:3px solid #f59e0b;padding:0.6rem 0.9rem;border-radius:6px;margin-bottom:0.5rem;font-size:0.88rem'>"
            "💬 Describe what you want Aqua to say — be as specific or vague as you want."
            "</div>"
        )
        custom_instruction = st.text_area(
            "What should the email say?",
            placeholder="e.g. Tell them I noticed they just opened a new boarding facility and "
                          "ask if they've thought about ammonia control before they move horses in.",
            height=100,
            key=f"custom_instr_{recipient_email}",
        )

    button_disabled = (message_type == 'custom' and not custom_instruction.strip())

    if st.button(f"✨ Write the message (using {provider_label})",
                  type="primary", use_container_width=True,
                  key=f"gen_{recipient_email}",
                  disabled=button_disabled):
        with st.spinner("Aqua is writing..."):
            try:
                if message_type == 'cold_email':
                    result = nepq_engine.generate_initial_outreach(lead_data)
                    st.session_state.compose_draft = {
                        'subject': result['subject'],
                        'content': result['body'],
                        'tier_label': f"NEPQ via {result['source']}",
                        'source': result['source'],
                    }
                elif message_type == 'aqua_intro':
                    result = nepq_engine.generate_aqua_intro(lead_data)
                    st.session_state.compose_draft = {
                        'subject': result['subject'],
                        'content': result['body'],
                        'tier_label': f"Aqua intro via {result['source']}",
                        'source': result['source'],
                    }
                elif message_type == 'custom':
                    result = nepq_engine.generate_custom_message(lead_data, custom_instruction)
                    st.session_state.compose_draft = {
                        'subject': result['subject'],
                        'content': result['body'],
                        'tier_label': f"Custom via {result['source']}",
                        'source': result['source'],
                    }
                else:
                    result = outreach.generate_smart(message_type, lead_data, provider=best_provider)
                    st.session_state.compose_draft = result
            except Exception as e:
                st.error(f"AI failed: {str(e)[:120]}")

    # Show draft
    if 'compose_draft' in st.session_state:
        draft = st.session_state.compose_draft
        st.markdown("---")
        st.markdown("### Your message")
        st.caption(f"Written by {draft.get('tier_label', '⚡ Templates')} · You can edit anything below")

        subject = st.text_input("Subject", value=draft.get('subject', ''),
                                  key=f"subj_{recipient_email}")
        content = st.text_area("Message", value=draft.get('content', ''), height=320,
                                  key=f"body_{recipient_email}")

        st.markdown("")
        st.markdown("### Send it")

        col1, col2 = st.columns(2)

        # Open in Gmail (always works)
        gmail_url = gmail_integration.build_gmail_compose_url(recipient_email, subject, content)
        col1.link_button("📧 Open in Gmail (new tab)", url=gmail_url, use_container_width=True)

        # SMTP send → ALWAYS log first, then trigger customer-gate flow
        if smtp_sender.is_configured():
            if col2.button("📨 Send via SMTP", type="primary", use_container_width=True,
                            key=f"send_{recipient_email}"):
                with st.spinner("Sending..."):
                    success, msg = smtp_sender.send_email(recipient_email, subject, content)
                    if success:
                        # === ALWAYS log this send (even for team members, even before "is customer?" gate) ===
                        log_lead_id = _log_compose_send(
                            recipient_email=recipient_email,
                            recipient_name=recipient_name,
                            subject=subject,
                            content=content,
                            existing_lead_id=existing_lead_id,
                        )

                        # Stash for the (now optional) customer-promote gate
                        st.session_state.just_sent = {
                            'recipient_email': recipient_email,
                            'recipient_name': recipient_name,
                            'subject': subject,
                            'content': content,
                            'message_type': 'compose',
                            'existing_lead_id': existing_lead_id,
                            'log_lead_id': log_lead_id,
                            'lead_data': lead_data,
                        }
                        st.balloons()
                        st.success(f"✅ Sent to {recipient_email} · logged to Inbox → Sent")
                        st.session_state.pop('compose_draft', None)
                        st.rerun()
                    else:
                        st.error(translate_smtp_error(msg))
        else:
            with col2:
                st.caption("💡 Set up email in Setup tab to send from app")

    # ===== "Is this a customer?" GATE (after send) =====
    if 'just_sent' in st.session_state:
        _render_customer_gate(st.session_state.just_sent)


def _is_invalid_email(email):
    """Reject obviously-fake emails so we don't create junk leads."""
    if not email or '@' not in email:
        return True
    local, _, domain = email.lower().partition('@')
    bad_locals = {'null', 'none', 'unknown', 'no-email', 'noemail', 'placeholder',
                  'example', 'test', 'fake', 'na', 'n/a'}
    if local in bad_locals:
        return True
    if not domain or '.' not in domain:
        return True
    if domain.endswith('.example') or domain == 'example.com' or domain == 'test.com':
        return True
    return False


def _log_compose_send(recipient_email, recipient_name, subject, content, existing_lead_id=None):
    """Log every Compose send to the database immediately, BEFORE the customer gate.

    - If recipient is already a CRM lead → use that lead_id
    - If recipient is on the AqueLyst team → use existing team-internal lead, DON'T create new
    - If recipient is a brand new email → auto-create a 'pending' lead
      (the customer-gate's 'No' button will DELETE this auto-lead)

    Returns the lead_id used for the draft, or None if email is invalid.
    """
    import team as _team

    # Reject obviously-bad emails before doing anything
    if _is_invalid_email(recipient_email):
        return None

    lead_id = existing_lead_id
    team_member = _team.get_member_by_email(recipient_email)

    if not lead_id:
        # Try to find an existing lead by email (any status, including team_internal)
        for l in database.get_all_leads(include_team_internal=True):
            if l['email'] and l['email'].lower() == recipient_email.lower():
                lead_id = l['id']
                break

        if not lead_id:
            if team_member:
                # Hidden internal lead for the teammate
                biz_name = f"[Team] {team_member['name']}"
                lead_source = 'team_internal'
                status = 'team_internal'
                score = 0
                contact = team_member['name']
                notes_text = f"Auto-created for tracking team email. {team_member['role']} on the team."
            else:
                # Pending external lead — user will be asked to promote OR discard via gate
                biz_name = (recipient_name or recipient_email.split('@')[0].title())
                lead_source = 'compose_pending'
                status = 'new'
                score = 20
                contact = recipient_name or ''
                notes_text = ("Auto-created from Compose. Awaiting user decision: "
                              "promote to full CRM lead OR discard via gate.")

            lead_id = database.add_lead(
                business_name=biz_name,
                contact_name=contact,
                email=recipient_email,
                lead_source=lead_source,
                pain_hypothesis='',
                notes=notes_text,
            )
            if lead_id:
                database.update_lead(lead_id, status=status, lead_score=score)

    if not lead_id:
        return None

    # Save the draft as sent
    msg_type = 'compose_team' if team_member else 'compose'
    draft_id = database.add_outreach_draft(lead_id, msg_type, subject, content)
    database.approve_draft(draft_id)
    database.mark_draft_sent(draft_id)

    # Log activity
    database.log_activity(lead_id, 'compose_send',
                          f"Compose: {subject[:50]}")

    return lead_id


def _discard_pending_compose_lead(lead_id):
    """When user clicks 'No don't track' in the customer gate, delete the auto-created lead
    (only if it's still in 'pending' state — was auto-created and hasn't been promoted)."""
    if not lead_id:
        return
    lead = database.get_lead(lead_id)
    if not lead:
        return
    # Only delete if it's a pending compose lead (preserve real customer leads)
    if lead['lead_source'] == 'compose_pending':
        database.delete_lead(lead_id)


def _render_customer_gate(sent_context):
    """After sending, if recipient was a NEW email (not in CRM), offer to promote
    them from a pending auto-lead to a full customer with rich info.

    The send itself is already logged in the database via _log_compose_send.
    This gate is purely about CRM promotion + follow-up scheduling for prospects.
    """
    recipient = sent_context['recipient_email']
    existing_id = sent_context.get('existing_lead_id')
    log_lead_id = sent_context.get('log_lead_id')

    # Skip the gate entirely for team members (already logged + tagged team_internal)
    import team as _team
    if _team.get_member_by_email(recipient):
        st.session_state.pop('just_sent', None)
        st.session_state.pop('show_customer_gate_form', None)
        return

    # If already in CRM (real customer), update status + schedule follow-up
    if existing_id:
        database.update_lead(existing_id, status='contacted',
                              last_contacted=datetime.now().isoformat())
        database.schedule_follow_up(existing_id, "auto_after_send", 3)
        st.info("📅 Follow-up scheduled in 3 days. Status: Contacted.")
        st.session_state.pop('just_sent', None)
        return

    # === New email — ask the question ===
    st.markdown("---")
    st.html(
        "<div style='background:linear-gradient(135deg,#eff6ff 0%,#dbeafe 100%);"
        "border:2px solid #93c5fd;border-radius:14px;padding:1.5rem 2rem;margin:1rem 0'>"
        "<div style='font-size:0.8rem;color:#1e40af;text-transform:uppercase;letter-spacing:0.08em;font-weight:700'>"
        "Quick question"
        "</div>"
        f"<div style='font-size:1.4rem;font-weight:700;color:#1e3a8a;margin-top:0.3rem'>"
        f"Is <code style='background:#dbeafe;padding:0.1rem 0.5rem;border-radius:4px'>{recipient}</code> a customer?"
        "</div>"
        "<div style='color:#1e40af;font-size:0.95rem;margin-top:0.4rem'>"
        "If yes, we'll add them to your CRM with all the info you have, "
        "score them, and the bot will track replies + handle follow-ups automatically."
        "</div></div>"
    )

    col1, col2, col3 = st.columns(3)

    if col1.button("✅ Yes — add them to CRM",
                    type="primary", use_container_width=True,
                    key="cust_gate_yes"):
        st.session_state.show_customer_gate_form = True
        st.rerun()

    if col2.button("❌ No — just send (don't track)",
                    use_container_width=True,
                    key="cust_gate_no"):
        # Actually delete the auto-created pending lead so it doesn't pollute CRM
        _discard_pending_compose_lead(sent_context.get('log_lead_id'))
        st.success("Email sent. Not in CRM (auto-lead removed).")
        st.session_state.pop('just_sent', None)
        st.session_state.pop('show_customer_gate_form', None)
        st.rerun()

    if col3.button("🤔 Maybe later — remind me",
                    use_container_width=True,
                    key="cust_gate_later"):
        # Also discard for now — user can add manually later if they change their mind
        _discard_pending_compose_lead(sent_context.get('log_lead_id'))
        st.info("OK — removed from CRM for now. You can add them anytime via Customers → ➕ Add.")
        st.session_state.pop('just_sent', None)
        st.session_state.pop('show_customer_gate_form', None)
        st.rerun()

    # ===== EXPANDED FORM (if they clicked Yes) =====
    if st.session_state.get('show_customer_gate_form'):
        st.markdown("---")
        st.markdown("### Add to CRM")
        st.caption("We've pre-filled what we know. Add details so the bot can personalize follow-ups.")

        with st.form('add_to_crm_form'):
            c1, c2 = st.columns(2)
            bn = c1.text_input("Business / Company name *",
                                  value=sent_context.get('lead_data', {}).get('business_name', ''),
                                  placeholder="Smith Equestrian Center")
            cn = c2.text_input("Contact's first/full name",
                                  value=sent_context.get('recipient_name', ''),
                                  placeholder="Sarah Smith")

            c1, c2 = st.columns(2)
            phone = c1.text_input("Phone (if you know it)", placeholder="555-0100")
            website = c2.text_input("Website (we'll auto-find their info)",
                                       placeholder="smithequestrian.com")

            c1, c2 = st.columns(2)
            city = c1.text_input("City", placeholder="Austin")
            state = c2.text_input("State", placeholder="TX")

            bt = st.selectbox(
                "What kind of business?",
                ["", "horse boarding facility", "horse stable", "equestrian center",
                 "trainer", "breeder", "rescue", "tack shop", "feed store",
                 "other equine business"],
                format_func=lambda x: x if x else "— Pick one —",
            )

            pain = st.text_area(
                "What problem do they have? (helps the bot personalize)",
                placeholder="e.g. Ammonia smell in 20 stalls, fly problem in summer",
                height=80,
            )

            c1, c2 = st.columns(2)
            submit = c1.form_submit_button("✅ Save to CRM", type="primary", use_container_width=True)
            cancel = c2.form_submit_button("Cancel", use_container_width=True)

            if cancel:
                st.session_state.pop('show_customer_gate_form', None)
                st.rerun()

            if submit:
                if not bn:
                    st.error("Business name is required.")
                else:
                    # The lead may already exist (auto-created by _log_compose_send).
                    # PROMOTE it from pending to a real customer with rich info.
                    new_lead_data = {
                        'business_name': bn,
                        'contact_name': cn,
                        'email': recipient,
                        'phone': phone,
                        'website': website,
                        'city': city,
                        'state': state,
                        'business_type': bt,
                        'pain_hypothesis': pain,
                        'lead_source': 'compose',
                    }

                    # Find the existing auto-lead (by email) — created when send happened
                    existing = None
                    for l in database.get_all_leads():
                        if l['email'] and l['email'].lower() == recipient.lower():
                            existing = l
                            break

                    if existing:
                        # Promote: update with rich info from form
                        lead_id = existing['id']
                        update_fields = {k: v for k, v in new_lead_data.items() if v}
                        update_fields['status'] = 'contacted'
                        update_fields['last_contacted'] = datetime.now().isoformat()
                        database.update_lead(lead_id, **update_fields)
                    else:
                        # Edge case — wasn't auto-created somehow. Create now.
                        lead_id = database.add_lead(**new_lead_data)

                    if not lead_id:
                        st.error("Couldn't save lead.")
                    else:
                        # Auto-enrich from website if provided
                        if website:
                            with st.spinner("Looking up their info from website..."):
                                try:
                                    result = enrichment.enrich_from_website(website)
                                    updates = {}
                                    if result['phones'] and not phone:
                                        updates['phone'] = enrichment.get_best_phone(result['phones'])
                                    if updates:
                                        database.update_lead(lead_id, **updates)
                                except Exception:
                                    pass

                        # Re-score with the new richer info
                        score = lead_scoring.calculate_lead_score(new_lead_data)
                        product, _ = lead_scoring.match_product(new_lead_data)
                        database.update_lead(lead_id, lead_score=score, product_fit=product)

                        database.schedule_follow_up(lead_id, "auto_after_send", 3)
                        database.log_activity(lead_id, "compose_promoted",
                                               f"Promoted to full customer · Score: {score}")

                        st.balloons()
                        st.success(f"🎉 **{bn}** is now in your CRM with score **{score}/100**! "
                                    f"Follow-up scheduled in 3 days.")

                        # Cleanup
                        st.session_state.pop('just_sent', None)
                        st.session_state.pop('show_customer_gate_form', None)

                        # Offer to view
                        if st.button("👁️ View this customer →"):
                            st.session_state.viewing_lead_id = lead_id
                            st.session_state.page = "customer_detail"
                            st.rerun()


# ===========================================================================
# ADD CUSTOMER
# ===========================================================================
def show_add_customer():
    st.title("➕ Add a Customer")
    st.caption("Just fill in what you know — we'll find the rest.")

    if st.button("← Back to Customers"):
        st.session_state.page = "customers"
        st.rerun()

    with st.form("add_customer"):
        bn = st.text_input("Business Name *", placeholder="Smith Equestrian Center")

        col1, col2 = st.columns(2)
        cn = col1.text_input("Contact Name", placeholder="John Smith")
        ph = col2.text_input("Phone", placeholder="555-0100")

        col1, col2 = st.columns(2)
        em = col1.text_input("Email", placeholder="john@smithequestrian.com")
        web = col2.text_input("Website (we'll auto-find their info)",
                               placeholder="smithequestrian.com")

        col1, col2 = st.columns(2)
        city = col1.text_input("City", placeholder="Austin")
        state = col2.text_input("State", placeholder="TX")

        bt = st.selectbox(
            "What kind of business?",
            ["", "horse boarding facility", "horse stable", "equestrian center",
             "trainer", "breeder", "rescue", "tack shop", "feed store",
             "other equine business"],
            format_func=lambda x: x if x else "— Pick one —"
        )

        pain = st.text_area(
            "What problem are they having?",
            placeholder="e.g. Ammonia smell in 20 stalls, fly problem in summer, "
                        "trailer odor after long hauls...",
            help="Helps the AI write a better message"
        )

        col1, col2 = st.columns(2)
        submit = col1.form_submit_button("Save Customer", type="primary", use_container_width=True)
        cancel = col2.form_submit_button("Cancel", use_container_width=True)

        if cancel:
            st.session_state.page = "customers"
            st.rerun()

        if submit:
            if not bn:
                st.error("Business name is required")
            else:
                lead_data = {
                    'business_name': bn, 'contact_name': cn, 'email': em,
                    'phone': ph, 'website': web, 'city': city, 'state': state,
                    'business_type': bt, 'pain_hypothesis': pain,
                    'lead_source': 'manual'
                }
                lead_id = database.add_lead(**lead_data)
                if lead_id:
                    # Auto-enrich
                    if web:
                        with st.spinner("Looking up their info..."):
                            result = enrichment.enrich_from_website(web)
                            updates = {}
                            if result['emails'] and not em:
                                updates['email'] = enrichment.get_best_email(result['emails'])
                            if result['phones'] and not ph:
                                updates['phone'] = enrichment.get_best_phone(result['phones'])
                            if updates:
                                database.update_lead(lead_id, **updates)

                    score = lead_scoring.calculate_lead_score(lead_data)
                    product, _ = lead_scoring.match_product(lead_data)
                    database.update_lead(lead_id, lead_score=score, product_fit=product)
                    database.log_activity(lead_id, "created", f"Manually added (score: {score})")

                    st.balloons()
                    st.success(f"✅ Added **{bn}** with match score **{score}/100**!")
                    st.session_state.viewing_lead_id = lead_id
                    st.session_state.page = "customer_detail"
                    st.rerun()
                else:
                    st.error("This email already exists in your customers, or there was an error.")


# ===========================================================================
# FIND NEW CUSTOMERS
# ===========================================================================
def show_find_customers():
    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Find</span> new customers",
        subtitle="Search Google Maps for horse barns and AqueLyst-fit businesses in "
                  "your target area, then add them to the CRM with one click.",
        eyebrow="🔍 LEAD DISCOVERY",
    )

    col1, col2 = st.columns(2)
    state_options = [""] + [f"{s[0]} - {s[1]}" for s in prospecting.TOP_EQUINE_STATES]
    state = col1.selectbox("Which state? (optional)", state_options)
    city = col2.text_input("Which city? (optional)", placeholder="Lexington")

    state_code = state.split(" - ")[0] if state else None

    st.markdown("---")
    st.markdown("### Click any link to search Google Maps:")

    business_searches = [
        ("🐴 Horse Boarding Facilities", "horse boarding facility",
         "Best targets — they have ongoing odor & manure issues"),
        ("🏇 Equestrian Centers", "equestrian center",
         "Premium facilities, often have multiple stalls"),
        ("🐎 Stables", "horse stable",
         "Smaller operations, often need affordable solutions"),
        ("👨‍🏫 Horse Trainers", "horse trainer",
         "Often have a few stalls + trailers"),
        ("🌱 Horse Breeders", "horse breeder",
         "High-end operations, quality-focused"),
        ("❤️ Horse Rescues", "horse rescue",
         "Many horses, often non-profit, need bulk solutions"),
        ("🛍️ Tack Shops", "tack shop",
         "Could resell Duo Equine to customers"),
        ("🌾 Feed Stores", "feed store",
         "Could resell Duo Equine to customers"),
    ]

    for label, btype, why in business_searches:
        url = prospecting.build_google_maps_search_url(btype, city, state_code)
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"#### {label}")
            st.caption(why)
        with col2:
            st.markdown(
                f"<a href='{url}' target='_blank' style='text-decoration:none'>"
                f"<button style='background:#4d7c0f;color:white;border:none;padding:0.5rem;"
                f"border-radius:8px;width:100%;font-weight:600;cursor:pointer;margin-top:0.5rem'>"
                f"Search Maps →</button></a>",
                unsafe_allow_html=True
            )
        st.markdown("---")

    st.markdown("### When you find one, add them:")
    if st.button("➕ Add a Customer Now", type="primary", use_container_width=True):
        st.session_state.page = "add_customer"
        st.rerun()


# ===========================================================================
# IMPORT FROM EMAIL
# ===========================================================================
def show_import_email():
    st.markdown("### 📧 Paste Web3Forms Email")
    st.caption("Got a contact form email? Paste it below and we'll create the customer automatically.")

    email_body = st.text_area(
        "Paste the email body here:",
        height=250,
        placeholder="Paste the entire email from Web3Forms..."
    )

    if email_body and st.button("Create Customer from Email", type="primary"):
        lead_id, msg = import_export.manual_import_web3forms(email_body)
        if lead_id:
            lead = database.get_lead(lead_id)
            score = lead_scoring.calculate_lead_score(dict(lead))
            product, _ = lead_scoring.match_product(dict(lead))
            database.update_lead(lead_id, lead_score=score, product_fit=product)
            database.log_activity(lead_id, "imported", "From Web3Forms email paste")

            st.balloons()
            st.success(f"✅ Customer added with score {score}/100!")
            st.session_state.viewing_lead_id = lead_id
            st.session_state.page = "customer_detail"
            st.rerun()
        else:
            st.error(f"Couldn't import: {msg}")


# ===========================================================================
# SETUP
# ===========================================================================
def show_audit_log():
    """Comprehensive audit log — every transaction, second-level timestamps, timezone-aware.
    For legal + records-keeping compliance."""

    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Complete</span> transaction history",
        subtitle="Every email, lead change, login, bot action — recorded down to the second "
                  "with timezone. Hash-chained for tamper-evidence. Exportable for legal review.",
        eyebrow="📋 AUDIT LOG",
    )

    # Status row (auto-refresh)
    _audit_status_fragment()

    st.markdown("---")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        event_filter = st.selectbox(
            "Event type",
            ['all', 'email_sent', 'email_received', 'email_send_failed',
             'lead_change', 'bot_action', 'auth', 'settings_change', 'system'],
            key='audit_event_filter',
        )
    with col2:
        # Actor filter from team list
        import team as _team
        team_emails = [m['email'] for m in _team.load_team()]
        actor_filter = st.selectbox(
            "Actor (logged-in user)",
            ['all'] + team_emails,
            key='audit_actor_filter',
        )
    with col3:
        search = st.text_input("Search", placeholder="email, name, action...",
                                  key='audit_search')
    with col4:
        limit = st.slider("Show entries", 50, 1000, 200, 50, key='audit_limit')

    # Verify chain integrity
    valid, broken_at = audit_log.verify_chain()
    if valid:
        st.html(
            "<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:8px;"
            "padding:0.6rem 1rem;margin:1rem 0;font-size:0.88rem;color:#166534'>"
            "🔒 <strong>Hash chain verified</strong> — audit log is intact and untampered."
            "</div>"
        )
    else:
        st.html(
            f"<div style='background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;"
            f"padding:0.6rem 1rem;margin:1rem 0;font-size:0.88rem;color:#991b1b'>"
            f"⚠️ <strong>Hash chain broken at entry #{broken_at}</strong> — log may have been tampered with."
            f"</div>"
        )

    # Action buttons
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("📥 Export to CSV", use_container_width=True):
            from datetime import datetime as _dt
            filename = f"audit_log_{_dt.now().strftime('%Y%m%d_%H%M%S')}.csv"
            ok, msg = audit_log.export_csv(
                filename,
                event_type=event_filter if event_filter != 'all' else None,
                actor_email=actor_filter if actor_filter != 'all' else None,
                search=search or None,
                limit=10000,
            )
            if ok:
                with open(filename, 'rb') as f:
                    st.download_button("⬇️ Download CSV", f.read(),
                                          file_name=filename, mime='text/csv')
                st.success(msg)
            else:
                st.error(msg)

    st.markdown("---")
    st.markdown("### Activity (newest first)")
    st.caption("Auto-refreshes every 30s · Times shown in your local timezone with seconds")

    _audit_table_fragment(event_filter, actor_filter, search, limit)


@st.fragment(run_every=30)
def _audit_status_fragment():
    """Auto-refreshing audit log status cards."""
    total = audit_log.count()
    sent_count = audit_log.count(event_type='email_sent')
    received_count = audit_log.count(event_type='email_received')
    bot_count = audit_log.count(event_type='bot_action')
    lead_count = audit_log.count(event_type='lead_change')

    cols = st.columns(5)
    metrics = [
        ('📋', 'Total Events', total, '#4d7c0f'),
        ('📤', 'Emails Sent', sent_count, '#0ea5e9'),
        ('📨', 'Emails Received', received_count, '#8b5cf6'),
        ('🤖', 'Bot Actions', bot_count, '#7c3aed'),
        ('👥', 'Lead Changes', lead_count, '#f59e0b'),
    ]
    for col, (icon, label, value, color) in zip(cols, metrics):
        with col:
            st.html(
                f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:1rem;text-align:center'>"
                f"<div style='font-size:1.4rem'>{icon}</div>"
                f"<div style='font-size:1.8rem;font-weight:800;color:{color};line-height:1'>{value:,}</div>"
                f"<div style='font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:600;margin-top:0.3rem'>{label}</div>"
                f"</div>"
            )


@st.fragment(run_every=30)
def _audit_table_fragment(event_filter, actor_filter, search, limit):
    """Auto-refreshing audit log table."""
    rows = audit_log.query(
        limit=limit,
        event_type=event_filter if event_filter != 'all' else None,
        actor_email=actor_filter if actor_filter != 'all' else None,
        search=search or None,
    )

    if not rows:
        st.info("No audit entries match these filters yet.")
        return

    st.caption(f"Showing {len(rows)} entries")

    for r in rows:
        ttype = r['event_type'] or 'system'
        action = r['action'] or ''
        actor = r['actor_name'] or 'System'
        actor_email = r['actor_email'] or ''
        local_ts = (r['timestamp_local'] or '')[:19].replace('T', ' ')
        tz = r['timezone_offset'] or ''
        target = r['target_label'] or (f"#{r['target_id']}" if r['target_id'] else '')

        color = {
            'email_sent': '#0ea5e9',
            'email_received': '#8b5cf6',
            'email_send_failed': '#dc2626',
            'lead_change': '#f59e0b',
            'bot_action': '#7c3aed',
            'auth': '#16a34a',
            'settings_change': '#fb923c',
            'system': '#6366f1',
        }.get(ttype, '#6b7280')

        type_label = ttype.replace('_', ' ').title()

        st.html(
            f"<div style='background:#fff;border:1px solid #e2e8f0;border-left:3px solid {color};"
            f"border-radius:0 8px 8px 0;padding:0.7rem 1rem;margin-bottom:0.4rem'>"
            f"<div style='display:flex;justify-content:space-between;gap:0.5rem;flex-wrap:wrap'>"
            f"<div style='flex:1;min-width:0'>"
            f"<div style='font-weight:600;color:#0f172a;font-size:0.92rem'>{action}</div>"
            f"<div style='color:#64748b;font-size:0.78rem;margin-top:0.2rem'>"
            f"<span style='background:{color};color:white;padding:0.1rem 0.5rem;border-radius:8px;font-weight:600;font-size:0.7rem'>"
            f"{type_label}</span>"
            f" · {actor} ({actor_email}) · {target}"
            f"</div></div>"
            f"<div style='text-align:right;font-size:0.78rem;color:#94a3b8;font-family:monospace;flex-shrink:0'>"
            f"{local_ts}<br><span style='font-size:0.7rem'>{tz}</span>"
            f"</div></div></div>"
        )


def show_setup():
    smtp_ok = smtp_sender.is_configured()
    ai_ok = api_keys.has_key('cerebras') or api_keys.has_key('claude')

    chips = []
    chips.append(("Email connected", "#10b981") if smtp_ok else ("Email pending", "#f59e0b"))
    chips.append(("AI connected", "#10b981") if ai_ok else ("AI pending", "#f59e0b"))
    chips.append(("Web form ready", "#06b6d4"))

    ui_kit.page_hero(
        title="<span style='background:linear-gradient(135deg,#06b6d4,#a3e635);"
               "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
               "background-clip:text'>Configure</span> your operating system",
        subtitle="Connect email + AI providers, manage the team, edit the product catalog, "
                  "and customize the website intake form.",
        eyebrow="⚙️ SETUP",
        chips=chips,
    )

    # Status overview
    st.markdown("### What's connected:")
    col1, col2, col3 = st.columns(3)
    with col1:
        if smtp_ok:
            cfg = smtp_sender.load_smtp_config()
            st.success(f"✅ Email\n\n{cfg['email']}")
        else:
            st.error("⚠️ Email not connected")
    with col2:
        if ai_ok:
            best = ai_providers.get_best_provider()
            st.success(f"✅ AI ({best.title()})")
        else:
            st.warning("⚠️ AI not connected\n(using templates)")
    with col3:
        st.success("✅ Website form ready")

    st.markdown("---")

    tabs = st.tabs(["📧 Email", "🧠 AI", "👥 Team", "🛒 Products", "🌐 Website Form", "💾 Backup & Data"])

    with tabs[0]:
        setup_email_tab()
    with tabs[1]:
        setup_ai_tab()
    with tabs[2]:
        setup_team_tab()
    with tabs[3]:
        setup_products_tab()
    with tabs[4]:
        setup_website_tab()
    with tabs[5]:
        setup_data_tab()


def setup_team_tab():
    """Manage AqueLyst team members."""
    import team

    st.markdown("### AqueLyst Team")
    st.caption("The bot uses this list to know WHO is logged in (based on connected email) "
                "and to recognize team members when prospects mention them.")

    # Show current user
    current = team.get_current_user()
    if current.get('_unknown'):
        st.warning(f"⚠️ Currently connected email **{current.get('email', 'none')}** "
                    f"isn't matched to any team member. Add yourself below.")
    else:
        st.success(f"✅ **You're logged in as:** {current['name']} — {current['role']}")
        st.caption(f"All emails will be signed as you. Bot recognizes the rest of the team in the list below.")

    st.markdown("---")
    st.markdown("### Team members")

    members = team.load_team()
    for i, m in enumerate(members):
        is_current = (current.get('email', '').lower() == m.get('email', '').lower())
        badge = "🟢 YOU" if is_current else ""

        with st.expander(f"**{m['name']}** · {m.get('short_role', m.get('role', ''))} · {m.get('email', '')}  {badge}"):
            with st.form(f'edit_member_{i}'):
                c1, c2 = st.columns(2)
                name = c1.text_input("Full name", value=m.get('name', ''))
                email = c2.text_input("Email", value=m.get('email', ''))

                role = st.text_input("Role / Title", value=m.get('role', ''),
                                        placeholder="e.g. CEO, COO, Co-Founder")

                bio = st.text_area("Bio (helps the bot describe them to prospects)",
                                      value=m.get('bio', ''), height=80)

                aliases = st.text_input("Aliases / nicknames (comma-separated)",
                                           value=', '.join(m.get('aliases', [])),
                                           placeholder="e.g. joe, joseph, dimartino",
                                           help="When prospects mention these names, bot recognizes this person.")

                company = st.text_input("Company", value=m.get('company', 'AqueLyst'))

                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 Save", type="primary", use_container_width=True):
                    team.update_member(i,
                                          name=name, email=email, role=role,
                                          short_role=role, bio=bio,
                                          aliases=[a.strip() for a in aliases.split(',') if a.strip()],
                                          company=company)
                    st.success("Saved!")
                    st.rerun()

                if c2.form_submit_button("🗑️ Remove from team", use_container_width=True):
                    team.delete_member(i)
                    st.rerun()

    st.markdown("---")
    st.markdown("### ➕ Add team member")

    with st.form('add_member_form', clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Full name", placeholder="Jane Doe")
        new_email = c2.text_input("Email", placeholder="jane@aquelyst.com")

        new_role = st.text_input("Role", placeholder="e.g. VP Sales, Marketing Director")
        new_bio = st.text_area("Bio (one or two sentences)", height=70,
                                  placeholder="What they do and how prospects might interact with them.")
        new_aliases = st.text_input("Aliases / nicknames (comma-separated)",
                                       placeholder="jane, doe")
        new_company = st.text_input("Company", value="AqueLyst")

        if st.form_submit_button("➕ Add team member", type="primary", use_container_width=True):
            if new_name and new_email:
                team.add_member(
                    name=new_name, email=new_email, role=new_role,
                    bio=new_bio,
                    aliases=[a.strip() for a in new_aliases.split(',') if a.strip()],
                    company=new_company,
                )
                st.success(f"✅ Added {new_name}")
                st.rerun()
            else:
                st.error("Name and email are required")

    st.markdown("---")
    if st.button("🔄 Reset to default team (5 founders + Wyatt)"):
        team.reset_team()
        st.success("Team reset")
        st.rerun()


def setup_products_tab():
    """Manage the product catalog the sales bot can reference."""
    import product_catalog

    st.markdown("### Products the Sales Bot can recommend")
    st.caption("The bot will naturally link to these in emails. The starred (⭐) product is "
                "the main call-to-action — usually a free trial.")

    catalog = product_catalog.load_catalog()

    # Show existing products
    if catalog:
        for i, prod in enumerate(catalog):
            magnet_badge = (
                "<span style='background:#fef3c7;color:#92400e;padding:0.2rem 0.6rem;"
                "border-radius:12px;font-size:0.75rem;font-weight:700;margin-left:0.5rem'>"
                "⭐ MAIN CTA</span>"
                if prod.get('is_lead_magnet') else ""
            )

            with st.expander(f"📦 **{prod['name']}** {'⭐' if prod.get('is_lead_magnet') else ''}"):
                st.markdown(magnet_badge, unsafe_allow_html=True)

                with st.form(f'edit_product_{i}'):
                    c1, c2 = st.columns(2)
                    name = c1.text_input("Product name", value=prod.get('name', ''))
                    price = c2.text_input("Price", value=prod.get('price', ''))

                    short = st.text_input("Short description (1 sentence)",
                                            value=prod.get('short_description', ''))
                    long_desc = st.text_area("Long description (for the bot's context)",
                                               value=prod.get('long_description', ''),
                                               height=80)

                    c1, c2 = st.columns(2)
                    url = c1.text_input("Product page URL",
                                          value=prod.get('url', ''),
                                          placeholder="https://aquelyst.com/products/...")
                    best_for = c2.text_input("Best for",
                                                value=prod.get('best_for', ''),
                                                placeholder="e.g. small barns, large facilities")

                    is_magnet = st.checkbox("⭐ This is the main lead-magnet (offer it first)",
                                              value=prod.get('is_lead_magnet', False))

                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 Save", type="primary", use_container_width=True):
                        product_catalog.update_product(i,
                                                          name=name, price=price,
                                                          short_description=short,
                                                          long_description=long_desc,
                                                          url=url, best_for=best_for,
                                                          is_lead_magnet=is_magnet)
                        st.success("Saved!")
                        st.rerun()

                    if c2.form_submit_button("🗑️ Delete this product", use_container_width=True):
                        product_catalog.delete_product(i)
                        st.success("Deleted")
                        st.rerun()
    else:
        st.info("No products in catalog. Add one below.")

    st.markdown("---")
    st.markdown("### ➕ Add a new product")

    with st.form('add_product_form', clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_name = c1.text_input("Product name", placeholder="Duo Equine — Trailer Kit")
        new_price = c2.text_input("Price", placeholder="$49 / month or 'Free'")

        new_short = st.text_input("Short description (1 sentence)",
                                     placeholder="A compact kit for horse trailer odor control")
        new_url = st.text_input("Product page URL",
                                  placeholder="https://aquelyst.com/products/trailer-kit")
        new_long = st.text_area("Long description (gives the bot context)",
                                  placeholder="Used by trainers and competitors for long hauls...",
                                  height=80)
        new_best_for = st.text_input("Best for (audience)",
                                        placeholder="e.g. trainers, competitors, transporters")
        new_is_magnet = st.checkbox("⭐ Set as main lead-magnet (CTA)")

        if st.form_submit_button("➕ Add Product", type="primary", use_container_width=True):
            if new_name and new_short:
                product_catalog.add_product(
                    name=new_name,
                    short_description=new_short,
                    url=new_url,
                    price=new_price,
                    long_description=new_long,
                    best_for=new_best_for,
                    is_lead_magnet=new_is_magnet,
                )
                st.success(f"✅ Added {new_name}")
                st.rerun()
            else:
                st.error("Name and short description are required")

    st.markdown("---")
    if st.button("🔄 Reset to default AqueLyst products"):
        product_catalog.reset_catalog()
        st.success("Reset")
        st.rerun()

    st.markdown("---")
    st.caption("💡 The bot weaves product links naturally into emails when relevant. "
               "It won't dump links — it uses them like a real salesperson would.")


def setup_email_tab():
    """Email setup — visual step-by-step wizard. Designed for non-technical users."""

    # ===== Already connected =====
    if smtp_sender.is_configured():
        cfg = smtp_sender.load_smtp_config()
        st.html(
            "<div style='background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);border:2px solid #86efac;border-radius:14px;padding:1.5rem 2rem;text-align:center;margin-bottom:1.5rem'>"
            "<div style='font-size:2.5rem'>✅</div>"
            "<h2 style='color:#166534 !important;margin:0.5rem 0;font-size:1.5rem'>Email is connected!</h2>"
            f"<div style='color:#15803d;font-size:1.05rem'><strong>{cfg['email']}</strong> · {cfg['provider'].title()}</div>"
            "</div>"
        )

        col1, col2 = st.columns(2)
        if col1.button("✉️ Send a test email to myself", type="primary", use_container_width=True):
            with st.spinner("Sending..."):
                success, msg = smtp_sender.send_email(
                    cfg['email'], "Aqua test — email connection check",
                    f"Hi {(cfg.get('sender_name') or 'there').split()[0]},\n\n"
                    "Quick test from Aqua (your AI sales assistant).\n\n"
                    "If you got this, your email setup is working perfectly!\n\n"
                    "— Aqua"
                )
                if success:
                    st.balloons()
                    st.success("✅ Sent! Check your inbox.")
                else:
                    st.error(translate_smtp_error(msg))

        if col2.button("🔄 Disconnect & use a different email", use_container_width=True):
            import os as _os
            if _os.path.exists(smtp_sender.CONFIG_FILE):
                _os.remove(smtp_sender.CONFIG_FILE)
                if 'email_wizard_step' in st.session_state:
                    del st.session_state.email_wizard_step
                st.rerun()
        return

    # ===== Wizard state =====
    if 'email_wizard_step' not in st.session_state:
        st.session_state.email_wizard_step = 0
    if 'email_wizard_email' not in st.session_state:
        st.session_state.email_wizard_email = ''
    if 'email_wizard_provider' not in st.session_state:
        st.session_state.email_wizard_provider = ''

    step = st.session_state.email_wizard_step
    total_steps = 4

    # Visual progress bar
    bars_html = ''.join([
        f"<div style='flex:1;height:6px;border-radius:3px;background:{'#4d7c0f' if i < step + 1 else '#e2e8f0'}'></div>"
        for i in range(total_steps)
    ])
    st.html(
        "<div style='margin-bottom:1.5rem'>"
        f"<div style='font-size:0.8rem;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;font-weight:600;margin-bottom:0.5rem'>"
        f"Email Setup Wizard · Step {min(step + 1, total_steps)} of {total_steps}"
        "</div>"
        f"<div style='display:flex;gap:0.5rem;align-items:center'>{bars_html}</div>"
        "</div>"
    )

    # ===== STEP 1 =====
    if step == 0:
        st.html(
            "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:1.5rem 2rem;margin-bottom:1rem'>"
            "<div style='display:flex;align-items:center;gap:1rem'>"
            "<div style='width:44px;height:44px;background:#4d7c0f;color:white;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.2rem;flex-shrink:0'>1</div>"
            "<div>"
            "<div style='font-size:1.3rem;font-weight:700;color:#0f172a'>What email do you want to send from?</div>"
            "<div style='color:#64748b;font-size:0.92rem;margin-top:0.2rem'>This is the email your customers will see in their inbox.</div>"
            "</div>"
            "</div>"
            "</div>"
        )

        email_input = st.text_input(
            "Email address",
            value=st.session_state.email_wizard_email or "",
            placeholder="yourname@gmail.com",
            label_visibility="collapsed",
        )

        if email_input and email_helpers.is_valid_email(email_input):
            provider = email_helpers.detect_provider(email_input)
            instructions = email_helpers.get_setup_instructions(provider)

            st.success(f"📍 Detected: **{instructions['title']}** · "
                        f"Setup time: about {instructions['time_estimate']}")

            if st.button("Next: Get your App Password →", type="primary", use_container_width=True):
                st.session_state.email_wizard_email = email_input
                st.session_state.email_wizard_provider = provider
                st.session_state.email_wizard_step = 1
                st.rerun()
        elif email_input:
            st.warning("That doesn't look like a valid email address.")

    # ===== STEP 2 =====
    elif step == 1:
        provider = st.session_state.email_wizard_provider
        instructions = email_helpers.get_setup_instructions(provider)
        email_addr = st.session_state.email_wizard_email

        # Header card — single line of HTML, no blank lines (st.html is bullet-proof)
        st.html(
            f"<div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:1.5rem 2rem;margin-bottom:1rem'>"
            f"<div style='display:flex;align-items:center;gap:1rem'>"
            f"<div style='width:44px;height:44px;background:#4d7c0f;color:white;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.2rem;flex-shrink:0'>2</div>"
            f"<div>"
            f"<div style='font-size:1.3rem;font-weight:700;color:#0f172a'>Get your App Password</div>"
            f"<div style='color:#64748b;font-size:0.92rem;margin-top:0.2rem'>"
            f"Apps can't use your real password — {provider.title()} makes a special 16-character code instead."
            f"</div>"
            f"</div>"
            f"</div>"
            f"</div>"
        )

        # If Gmail/Workspace, show the 2-step process explicitly
        if provider == 'gmail':
            st.html(
                "<div style='background:#fef3c7;border-left:4px solid #f59e0b;padding:1rem 1.2rem;border-radius:6px;margin-bottom:1rem'>"
                "<strong style='color:#92400e'>⚠️ IMPORTANT — Do this in order or it won't work:</strong>"
                "</div>"
            )

            st.markdown("##### 🔐 First — Turn on 2-Step Verification")
            st.markdown("App Passwords don't exist until 2-Step Verification is ON. This is the #1 cause of the error message *'the setting you are looking for is not available for your account'*.")

            st.link_button(
                "🔗 Open Google 2-Step Verification",
                url="https://myaccount.google.com/signinoptions/twosv",
                type="secondary",
                use_container_width=True,
            )

            st.markdown(f"""
On the page that opens:
1. Sign in with `{email_addr}`
2. Click **Turn on 2-Step Verification**
3. Add your phone number for codes (or use Google Prompts)
4. Finish the wizard — it takes 2 minutes
""")

            st.markdown("---")
            st.markdown("##### 🔑 Then — Create the App Password")
            st.markdown("Now that 2-Step is on, you can create App Passwords. Click below:")

            st.link_button(
                "🔗 Open App Passwords page",
                url="https://myaccount.google.com/apppasswords",
                type="primary",
                use_container_width=True,
            )

            st.markdown(f"""
On that page:
1. **Make sure you're signed in as** `{email_addr}` (top-right shows the account)
2. Look for a text box labeled **"App name"** — type: `AqueLyst Hunter`
3. Click **Create**
4. Google shows you a **16-character password** in a yellow box (like `abcd efgh ijkl mnop`)
5. **Copy it** — you only see it once
""")

            with st.expander("❓ Still seeing 'this setting is not available' error?"):
                st.markdown(f"""
This usually means one of these:

**1. You're on a Google Workspace account (custom domain like aquelyst.com)**
   - Your **Workspace admin** must enable App Passwords for your account
   - Admin needs to go to [admin.google.com](https://admin.google.com) → Security → Authentication → 2-Step Verification → set "Allow users to turn on 2-Step Verification" to ON
   - OR admin can enable: Apps → Google Workspace → Gmail → User settings → Less secure apps → Allow users to manage their access

**2. Your account is too new** — Google sometimes requires accounts to be 24+ hours old before allowing App Passwords

**3. You haven't fully completed 2-Step Verification setup**
   - Make sure you finished the entire wizard (added phone number, verified it)
   - Sign out and back in, then try again

**4. Workaround — use a personal Gmail instead**
   - If aquelyst.com email won't work, create a free Gmail like `aquelyst.sales@gmail.com`
   - Personal Gmail accounts always allow App Passwords once 2FA is on
   - You can still send AS joseph@aquelyst.com using Gmail's "Send mail as" feature later
""")
        else:
            # Non-Gmail providers — simpler flow
            st.markdown("##### 👉 Click here to open the App Password page")
            st.link_button(
                f"🔗 Open {instructions['title']}",
                url=instructions['app_password_url'],
                type="primary",
                use_container_width=True,
            )

            st.markdown(f"""
On that page:
1. **Sign in** with `{email_addr}`
2. **If asked, turn on 2-Step Verification first**
3. **Look for "Create" or "Generate" App Password**
4. **Name it:** `AqueLyst Hunter`
5. **Copy the 16-character password**
""")

        # Helpful note
        st.info("⚠️ The password is shown ONCE — copy it before closing the window. "
                "If you lose it, just generate a new one.")

        st.markdown("---")

        col1, col2 = st.columns([1, 3])
        if col1.button("← Back"):
            st.session_state.email_wizard_step = 0
            st.rerun()
        if col2.button("✅ I copied my App Password — Next →",
                        type="primary", use_container_width=True):
            st.session_state.email_wizard_step = 2
            st.rerun()

    # ===== STEP 3 =====
    elif step == 2:
        provider_name = st.session_state.email_wizard_provider.title()
        st.html(
            "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:1.5rem 2rem;margin-bottom:1rem'>"
            "<div style='display:flex;align-items:center;gap:1rem'>"
            "<div style='width:44px;height:44px;background:#4d7c0f;color:white;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.2rem;flex-shrink:0'>3</div>"
            "<div>"
            "<div style='font-size:1.3rem;font-weight:700;color:#0f172a'>Paste your App Password</div>"
            f"<div style='color:#64748b;font-size:0.92rem;margin-top:0.2rem'>"
            f"16-character code from {provider_name}. Spaces are fine — we'll clean them up."
            "</div>"
            "</div>"
            "</div>"
            "</div>"
        )

        app_pw = st.text_input(
            "Paste your 16-character App Password:",
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
            help="Paste the password from the page above. NOT your regular password.",
        )

        default_name = st.session_state.email_wizard_email.split('@')[0].title()
        sender_name = st.text_input(
            "How should this email show in recipients' inbox? (optional)",
            value=f"{default_name} at AqueLyst",
            help="This name appears in 'From'. Example: 'Joseph at AqueLyst'"
        )

        col1, col2 = st.columns([1, 3])
        if col1.button("← Back"):
            st.session_state.email_wizard_step = 1
            st.rerun()
        if col2.button("Connect Email →", type="primary", use_container_width=True):
            if not app_pw:
                st.error("Paste the password first")
            else:
                with st.spinner("Connecting and testing..."):
                    cleaned_pw = app_pw.replace(' ', '').strip()
                    provider = st.session_state.email_wizard_provider
                    email_addr = st.session_state.email_wizard_email

                    success, msg = smtp_sender.test_smtp_connection(provider, email_addr, cleaned_pw)
                    if success:
                        smtp_sender.save_smtp_config(provider, email_addr, cleaned_pw, sender_name)
                        st.session_state.email_wizard_step = 3
                        st.rerun()
                    else:
                        st.error(translate_smtp_error(msg))
                        st.markdown("**Most common fixes:**")
                        st.markdown("""
- Make sure you used the **App Password** (16 chars), not your real password
- Confirm 2-Step Verification is **ON** for your account
- Try generating a brand-new App Password
""")

    # ===== STEP 4 (DONE) =====
    elif step >= 3:
        st.balloons()
        connected_email = st.session_state.email_wizard_email
        st.html(
            "<div style='background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);border:2px solid #86efac;border-radius:14px;padding:2rem;text-align:center;margin-bottom:1.5rem'>"
            "<div style='font-size:3rem'>🎉</div>"
            "<h1 style='color:#166534 !important;margin:0.5rem 0;font-size:1.8rem'>You're connected!</h1>"
            f"<div style='color:#15803d;font-size:1.05rem'>Email <strong>{connected_email}</strong> is ready to send.</div>"
            "</div>"
        )

        if st.button("✉️ Send myself a test email", type="primary", use_container_width=True):
            with st.spinner("Sending..."):
                success, msg = smtp_sender.send_email(
                    st.session_state.email_wizard_email,
                    "🎉 Aqua is connected and ready",
                    "Your email is connected. Aqua (your AI sales assistant) is ready to send.\n\n"
                    "Now you can:\n"
                    "- Run Autopilot to find leads\n"
                    "- Have Aqua auto-engage hot leads\n"
                    "- Let Aqua reply to prospects automatically\n\n"
                    "Time to make some sales!\n\n"
                    "— Aqua"
                )
                if success:
                    st.success("✅ Sent! Check your inbox.")
                else:
                    st.error(msg)

        # Reset wizard for next time
        st.session_state.email_wizard_step = 0
        st.session_state.email_wizard_email = ''
        st.session_state.email_wizard_provider = ''


def setup_ai_tab():
    import team as _team
    st.markdown("### AI — Aqua's brain")
    st.caption("More keys connected = Aqua never hits rate limits. Add YOUR personal keys too — "
                "the team pools all keys and rotates between them.")

    current = _team.get_current_user()
    me_email = (current.get('email') or '').lower()
    me_first = (current.get('name') or 'You').split()[0]

    # ============================================================
    # SECTION A — Your Personal Cerebras Key (the new guided flow)
    # ============================================================
    st.markdown("---")
    st.html(
        "<div style='background:linear-gradient(135deg,rgba(6,182,212,0.10),rgba(26,95,63,0.10));"
        "border:1px solid rgba(6,182,212,0.25);border-radius:14px;padding:1rem 1.3rem;"
        "margin-bottom:1rem'>"
        f"<div style='font-size:0.8rem;color:#06b6d4;text-transform:uppercase;letter-spacing:0.08em;"
        f"font-weight:700;margin-bottom:0.3rem'>🚀 POWER-UP FOR {me_first.upper()}</div>"
        f"<div style='font-size:1.4rem;font-weight:700;color:#0a0f1c;line-height:1.2'>"
        f"Add your personal Cerebras key</div>"
        "<div style='color:#475569;margin-top:0.5rem;font-size:0.95rem'>"
        "When the team's shared brain gets busy, Aqua falls back to YOURS. "
        "Takes ~3 minutes. Free forever. Your key stays yours."
        "</div></div>"
    )

    if not me_email:
        st.warning("⚠️ Connect your email first (📧 Email tab) so Aqua knows whose key this is.")
    else:
        existing_personal = database.team_keys_get_for_user(me_email, 'cerebras')

        if existing_personal:
            masked = existing_personal[:8] + "..." + existing_personal[-4:]
            st.success(f"✅ {me_first}'s personal Cerebras key is connected — `{masked}`")
            cc1, cc2 = st.columns(2)
            if cc1.button("Test it works", key="test_personal_cerebras"):
                with st.spinner("Testing..."):
                    import requests as _r
                    try:
                        rr = _r.post(
                            "https://api.cerebras.ai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {existing_personal}",
                                      "Content-Type": "application/json"},
                            json={"model": "llama3.1-8b",
                                   "messages": [{"role": "user", "content": "Say hi in 1 word."}],
                                   "max_tokens": 10},
                            timeout=15,
                        )
                        if rr.status_code == 200:
                            st.success("✅ Working — Aqua can use your key.")
                        else:
                            st.error(f"❌ Cerebras returned {rr.status_code}: {rr.text[:160]}")
                    except Exception as e:
                        st.error(f"❌ {e}")
            if cc2.button("🗑 Remove my key", key="del_personal_cerebras"):
                database.team_keys_delete(me_email, 'cerebras')
                st.rerun()
        else:
            with st.container(border=True):
                st.markdown("##### Step 1 of 4 · Sign up free at Cerebras")
                st.markdown(
                    "[**👉 Click here to open cloud.cerebras.ai**](https://cloud.cerebras.ai/?utm_source=aquelyst)  \n"
                    "Use any email (your work email is fine). **No credit card needed.** "
                    "Verify your email when they send the link."
                )

                st.markdown("##### Step 2 of 4 · Open the API Keys page")
                st.markdown(
                    "After you're signed in:  \n"
                    "[**👉 Click here to open the API Keys page**](https://cloud.cerebras.ai/platform/keys)"
                )

                st.markdown("##### Step 3 of 4 · Create a key")
                st.markdown(
                    "1. Click the big **\"Create API Key\"** button  \n"
                    "2. Name it `AqueLyst OS`  \n"
                    "3. **Copy the key** — it starts with `csk-` and you only see it once  \n"
                )

                st.markdown("##### Step 4 of 4 · Paste it here")
                st.caption("It's stored encrypted, never visible in chat or email. Only Aqua reads it.")

                with st.form("personal_cerebras_form", clear_on_submit=False):
                    new_key = st.text_input(
                        "Paste your Cerebras key (starts with csk-)",
                        type="password",
                        placeholder="csk-...",
                    )
                    submitted = st.form_submit_button("✅ Save & Test",
                                                       type="primary",
                                                       use_container_width=True)
                if submitted:
                    if not new_key or not new_key.strip().startswith('csk-'):
                        st.error("That doesn't look like a Cerebras key (should start with `csk-`).")
                    else:
                        with st.spinner("Testing..."):
                            import requests as _r
                            try:
                                rr = _r.post(
                                    "https://api.cerebras.ai/v1/chat/completions",
                                    headers={"Authorization": f"Bearer {new_key.strip()}",
                                              "Content-Type": "application/json"},
                                    json={"model": "llama3.1-8b",
                                           "messages": [{"role": "user", "content": "Say ok"}],
                                           "max_tokens": 5},
                                    timeout=15,
                                )
                                if rr.status_code == 200:
                                    database.team_keys_save(me_email, 'cerebras',
                                                              new_key.strip(),
                                                              label=f"{me_first}'s personal")
                                    st.balloons()
                                    st.success("✅ Connected and saved!")
                                    st.rerun()
                                else:
                                    st.error(
                                        f"❌ Cerebras rejected the key ({rr.status_code}). "
                                        f"Make sure you copied the whole key. "
                                        f"Detail: {rr.text[:160]}"
                                    )
                            except Exception as e:
                                st.error(f"❌ Couldn't reach Cerebras: {e}")

    # ============================================================
    # SECTION B — Team key pool status (who's connected)
    # ============================================================
    st.markdown("---")
    st.markdown("#### 👥 Team Cerebras key pool")
    pool = database.team_keys_get_pool('cerebras')
    if not pool:
        st.caption("_Nobody has added a personal key yet. The team is on the shared baseline only._")
    else:
        st.caption(f"{len(pool)} team member{'s' if len(pool) != 1 else ''} contributing keys. "
                    "Aqua rotates through them when the shared key is busy.")
        for row in pool:
            owner = row['user_email']
            label_bits = [f"`{row['user_email']}`"]
            if row.get('last_ok_at'):
                label_bits.append(f"✅ last ok {row['last_ok_at'][:16].replace('T', ' ')}")
            if row.get('last_err_at'):
                label_bits.append(f"⚠️ last err {row['last_err_at'][:16].replace('T', ' ')}")
            st.markdown(" · ".join(label_bits))

    # ============================================================
    # SECTION C — Shared baseline (team-wide) keys
    # ============================================================
    st.markdown("---")
    st.markdown("#### 🌐 Shared baseline keys (team-wide)")
    st.caption("Used as a fallback when no personal keys are available.")

    # Cerebras baseline
    cerebras_key = api_keys.get_key('cerebras')
    if cerebras_key:
        masked = cerebras_key[:8] + "..." + cerebras_key[-4:]
        st.markdown(f"**Cerebras (shared)** — `{masked}` ✅")
    else:
        with st.expander("Add a shared Cerebras key (admin only)"):
            new_key = st.text_input("Cerebras shared key", type="password",
                                    key="setup_cerebras_shared", placeholder="csk-...")
            if st.button("Save shared key", key="conn_cerebras_shared"):
                if new_key:
                    api_keys.set_key('cerebras', new_key.strip())
                    st.rerun()

    # Claude baseline
    claude_key = api_keys.get_key('claude')
    if claude_key:
        masked = claude_key[:10] + "..."
        st.markdown(f"**Claude (shared)** — `{masked}` ✅")
        if st.button("Remove Claude key", key="del_claude"):
            api_keys.delete_key('claude')
            st.rerun()
    else:
        with st.expander("Add Claude (Anthropic) — backup brain, $5 of credits goes far"):
            st.markdown(
                "Claude is more capable than Cerebras for nuanced sales chat. "
                "Adding it as a backup means Aqua never falls back to templates.  \n"
                "[**👉 Get a Claude API key**](https://console.anthropic.com/settings/keys)"
            )
            new_key = st.text_input("Paste Claude API key", type="password",
                                    key="setup_claude", placeholder="sk-ant-...")
            if st.button("Connect Claude", type="primary", key="conn_claude"):
                if new_key:
                    api_keys.set_key('claude', new_key.strip())
                    st.rerun()


def setup_website_tab():
    st.markdown("### Your Website Contact Form")

    st.success("✅ Web3Forms is wired up (key: `993ac019...`)")
    st.success("✅ Webhook server is running on port 8502")

    st.markdown("---")
    st.markdown("##### To put the form on AqueLyst.com:")
    st.markdown("""
    1. Find the file `web3forms_template.html` in this folder
    2. Open it in your browser to test it (it should look like a contact form)
    3. Upload it to your website as `contact.html`
    4. Link to it from your website menu

    **When customers fill it out:**
    - You'll get an email
    - Paste that email into **Customers → Import from Email** tab
    - The customer is added automatically with a match score
    """)

    st.markdown("📁 File location:")
    st.code("/Users/debraleblang/Desktop/AqueLyst-Hunter/web3forms_template.html")


def setup_data_tab():
    st.markdown("### Backup & Data")

    stats = database.get_dashboard_stats()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total customers", stats['total_leads'])
    col2.metric("Hot customers", stats['hot_leads'])
    col3.metric("Closed sales", stats['closed_won'])

    st.markdown("---")
    st.markdown("#### Backup your customer data")
    st.caption("Run this in Terminal to make a copy of your customer database:")
    st.code("cp aquelyst_hunter.db aquelyst_hunter.db.backup")

    st.markdown("---")
    st.markdown("#### Restart onboarding")
    if st.button("Take me through setup again"):
        st.session_state.onboarding_step = 0
        st.session_state.onboarding_done = False
        st.session_state.page = "onboarding"
        st.rerun()

    st.markdown("---")
    st.markdown("#### 🚪 Save & Logout")
    st.caption("Disconnects email, stops bots, and returns to the welcome screen. Your data stays.")
    if st.button("💾 Save & Logout", type="primary", use_container_width=True):
        # Stop background bots
        try:
            email_responder.stop_responder()
        except Exception:
            pass
        try:
            auto_engagement.stop_engagement()
            auto_engagement.update_state(running=False, config={})
        except Exception:
            pass
        # Disconnect email
        import os as _os
        if _os.path.exists(smtp_sender.CONFIG_FILE):
            _os.remove(smtp_sender.CONFIG_FILE)
        # Reset onboarding so next user goes through setup
        st.session_state.onboarding_step = 0
        st.session_state.onboarding_done = False
        # Clear all session state
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.session_state.page = "onboarding"
        try:
            import audit_log
            audit_log.log('logout', 'User logged out via Save & Logout button')
        except Exception:
            pass
        st.success("👋 Logged out. Bots stopped. Email disconnected.")
        st.rerun()


# ===========================================================================
# HELPERS
# ===========================================================================
def format_date_friendly(date_str):
    """Convert ISO/SQLite UTC date to friendly relative format in user's local TZ.

    SQLite's CURRENT_TIMESTAMP returns naive UTC strings like '2026-04-26 20:20:14'.
    We must treat those as UTC and convert to local for accurate 'X min ago' display.
    """
    if not date_str:
        return "—"
    try:
        from datetime import timezone as _tz
        # Strip Z if present
        clean = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean)

        # If naive, treat as UTC (matches SQLite's CURRENT_TIMESTAMP behavior)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)

        # Use timezone-aware "now" so the math is correct regardless of user's TZ
        now = datetime.now(_tz.utc)
        delta = now - dt
        total_seconds = delta.total_seconds()

        # Negative or near-zero → just now
        if total_seconds < 60:
            return "just now"
        if total_seconds < 3600:
            mins = int(total_seconds / 60)
            return f"{mins}m ago"
        if total_seconds < 86400:
            hours = int(total_seconds / 3600)
            return f"{hours}h ago"
        if total_seconds < 86400 * 2:
            return "yesterday"
        if total_seconds < 86400 * 7:
            days = int(total_seconds / 86400)
            return f"{days}d ago"

        # Older than a week — show the date in user's local TZ
        local_dt = dt.astimezone()
        return local_dt.strftime("%b %d")
    except Exception:
        return date_str


def format_timestamp_full(date_str):
    """Convert UTC timestamp to full local-time display with seconds: 'Apr 26, 4:23:14 PM EDT'"""
    if not date_str:
        return "—"
    try:
        from datetime import timezone as _tz
        clean = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        local = dt.astimezone()
        return local.strftime("%b %d, %-I:%M:%S %p %Z")
    except Exception:
        return date_str


def translate_smtp_error(msg):
    """Convert technical SMTP errors to plain English."""
    msg_lower = (msg or '').lower()
    if 'authentication' in msg_lower or 'auth' in msg_lower:
        return ("❌ Wrong password. Most common fix: make sure you used your **App Password** "
                "(16 characters), not your regular email password. "
                "If you don't have one yet, click the App Password link above.")
    if 'timeout' in msg_lower or 'timed out' in msg_lower:
        return "❌ Took too long to connect. Check your internet connection and try again."
    if 'recipient' in msg_lower:
        return "❌ The recipient email address looks invalid."
    if 'connection' in msg_lower:
        return "❌ Couldn't reach the email server. Check your internet connection."
    return f"❌ Email error: {msg}"


def seed_sample_data():
    """Load 10 sample equine leads."""
    samples = [
        {'business_name': 'Golden Oaks Equestrian Center', 'contact_name': 'Margaret Thompson',
         'email': 'margaret@goldenoaks.example', 'phone': '555-0101', 'city': 'Austin', 'state': 'TX',
         'business_type': 'horse boarding facility',
         'pain_hypothesis': 'Severe ammonia odor in 25 stalls, especially in summer',
         'lead_source': 'sample'},
        {'business_name': 'Ridgemont Stables', 'contact_name': 'David Lee',
         'email': 'david@ridgemont.example', 'phone': '555-0102', 'city': 'Boulder', 'state': 'CO',
         'business_type': 'horse stable',
         'pain_hypothesis': 'Manure odor affecting visitors and boarders',
         'lead_source': 'sample'},
        {'business_name': 'Prairie Horse Rescue', 'contact_name': 'Jennifer White',
         'email': 'jen@prairie.example', 'phone': '555-0103', 'city': 'Kansas City', 'state': 'KS',
         'business_type': 'rescue',
         'pain_hypothesis': 'Fly control critical for horse health, limited budget',
         'lead_source': 'sample'},
        {'business_name': 'Twin Creek Trainers', 'contact_name': 'Michael Chen',
         'email': 'michael@twincreek.example', 'phone': '555-0104', 'city': 'San Diego', 'state': 'CA',
         'business_type': 'trainer',
         'pain_hypothesis': 'Ammonia in trailers and stalls during long competition season',
         'lead_source': 'sample'},
        {'business_name': 'Elite Equine Genetics', 'contact_name': 'Patricia Garcia',
         'email': 'patricia@elite.example', 'phone': '555-0105', 'city': 'Lexington', 'state': 'KY',
         'business_type': 'breeder',
         'pain_hypothesis': 'Premium facility, need top-tier odor elimination for client visits',
         'lead_source': 'sample'},
        {'business_name': 'Valley Feed & Tack', 'contact_name': 'Robert Johnson',
         'email': 'robert@valleyfeed.example', 'phone': '555-0106', 'city': 'Salem', 'state': 'OR',
         'business_type': 'feed store',
         'pain_hypothesis': 'Customers keep asking for fly and odor solutions',
         'lead_source': 'sample'},
        {'business_name': 'Sunshine Tack Shop', 'contact_name': 'Lisa Martinez',
         'email': 'lisa@sunshinetack.example', 'phone': '555-0107', 'city': 'Phoenix', 'state': 'AZ',
         'business_type': 'tack shop',
         'pain_hypothesis': 'Want to add barn odor products to retail lineup',
         'lead_source': 'sample'},
        {'business_name': 'Highland Equestrian Academy', 'contact_name': 'Amanda Scott',
         'email': 'amanda@highland.example', 'phone': '555-0108', 'city': 'Nashville', 'state': 'TN',
         'business_type': 'equestrian center',
         'pain_hypothesis': '30+ horses, severe fly problem affecting student lessons',
         'lead_source': 'sample'},
        {'business_name': 'Mystic Meadows Boarding', 'contact_name': 'Thomas Brown',
         'email': 'thomas@mystic.example', 'phone': '555-0109', 'city': 'Portland', 'state': 'ME',
         'business_type': 'horse boarding facility',
         'pain_hypothesis': 'Premium boarding clients expect odor-free environment',
         'lead_source': 'sample'},
        {'business_name': 'Desert Horse Trailers', 'contact_name': 'Kevin Wilson',
         'email': 'kevin@deserttrailers.example', 'phone': '555-0110', 'city': 'Las Vegas', 'state': 'NV',
         'business_type': 'other equine business',
         'pain_hypothesis': 'Trailers develop ammonia smell on long hauls — need solution',
         'lead_source': 'sample'},
    ]

    for s in samples:
        lead_id = database.add_lead(**s)
        if lead_id:
            score = lead_scoring.calculate_lead_score(s)
            product, _ = lead_scoring.match_product(s)
            database.update_lead(lead_id, lead_score=score, product_fit=product, status='researched')
            database.log_activity(lead_id, "created", f"Sample customer (score: {score})")


if __name__ == "__main__":
    main()
