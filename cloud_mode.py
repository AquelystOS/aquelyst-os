"""Detect whether we're running on Streamlit Cloud vs locally.

When deployed to Streamlit Cloud:
- Container sleeps after inactivity → background threads die
- File system is ephemeral → SQLite resets on restart
- Need to either:
   a) Move to Postgres for persistence (Phase B of rollout)
   b) Run bots on a separate always-on machine (Phase C)
   c) Only run bots when someone is manually using the app

This module gives the rest of the codebase a way to check the environment
and warn appropriately.
"""

import os


def is_cloud():
    """True when running on Streamlit Cloud (or any hosted environment)."""
    # Streamlit Cloud sets this env var
    if os.environ.get('STREAMLIT_RUNTIME', '').lower() in ('cloud', 'community'):
        return True
    # Fallback heuristics
    if os.environ.get('STREAMLIT_SERVER_HEADLESS', '').lower() == 'true' \
       and os.environ.get('HOSTNAME', '').startswith('streamlit'):
        return True
    # Check if there's a streamlit secrets file with our deployment marker
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            try:
                if st.secrets.get('CLOUD_DEPLOYMENT', False):
                    return True
            except Exception:
                pass
    except ImportError:
        pass
    return False


def background_workers_supported():
    """True if background threads/workers can run reliably (i.e. local install).
    On Streamlit Cloud the container sleeps so threads die — return False."""
    return not is_cloud()


def get_environment_warning():
    """Short text explaining the current environment's limitations, or empty if local."""
    if is_cloud():
        return (
            "☁️ **Running on Streamlit Cloud (free tier)** — the app sleeps when nobody's "
            "using it. Background bots (Autopilot, Inbox Watcher, Auto-Engagement) only run "
            "while the page is open. For 24/7 bots, deploy a worker on a Mac/VPS that "
            "connects to the same database."
        )
    return ""
