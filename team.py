"""AqueLyst team / staff registry.

Stores info about each team member so the bot:
1. Knows WHO is logged in (auto-detected from connected SMTP email)
2. Personalizes outreach as that specific person (CEO vs COO vs Co-Founder)
3. Knows who's who when prospects mention names or ask to talk to specific people
4. Routes escalations to the right person

Joseph (CEO) installs the OS, connects his email → bot acts as Joseph.
Debra (COO) installs the OS on her machine, connects her email → bot acts as Debra.
Same codebase, different identity per machine based on who's connected.
"""

import json
from pathlib import Path

TEAM_FILE = "team_members.json"


# Default AqueLyst team — Joseph can edit/add/remove via Setup → Team
DEFAULT_TEAM = [
    {
        'name': 'Erika Goff',
        'email': 'erika@aquelyst.com',
        'role': 'Co-Founder, Chairwoman',
        'short_role': 'Co-Founder · Chairwoman',
        'bio': (
            'Co-founder of AqueLyst and Chairwoman of the Board. '
            'Strategic vision, partnerships, and high-level relationships.'
        ),
        'aliases': ['erika'],
        'company': 'AqueLyst',
    },
    {
        'name': 'Danielle Oberholtzer',
        'email': 'danielle@aquelyst.com',
        'role': 'Co-Founder, Chief of Staff',
        'short_role': 'Co-Founder · Chief of Staff',
        'bio': (
            'Co-founder and Chief of Staff. Operations, internal coordination, '
            'and execution across the company. Goes by Dani.'
        ),
        'aliases': ['dani', 'danielle', 'oberholtzer', 'dani@aquelyst.com'],
        'company': 'AqueLyst',
    },
    {
        'name': 'Joseph Dimartino',
        'email': 'joseph@aquelyst.com',
        'role': 'CEO',
        'short_role': 'CEO',
        'bio': (
            'Chief Executive Officer. Sales leadership, partnerships, '
            'and external relationships.'
        ),
        'aliases': ['joseph', 'joe', 'dimartino', 'joseph dimartino'],
        'company': 'AqueLyst',
    },
    {
        'name': 'Debra Leblang',
        'email': 'debra@aquelyst.com',
        'role': 'COO',
        'short_role': 'COO',
        'bio': (
            'Chief Operating Officer. Day-to-day operations, fulfillment, '
            'logistics, and customer success.'
        ),
        'aliases': ['debra', 'leblang', 'deb'],
        'company': 'AqueLyst',
    },
    {
        'name': 'Wyatt Schwab',
        'email': 'w.schwab@remedia.global',
        'role': 'President of AqueLyst, VP of Remedia International',
        'short_role': 'President of AqueLyst · VP Remedia International',
        'bio': (
            'President of AqueLyst and Vice President of Remedia International '
            '(the parent company that owns the patented molecular converter '
            'technology trusted by the EPA).'
        ),
        'aliases': ['wyatt', 'schwab', 'w. schwab'],
        'company': 'AqueLyst / Remedia International',
    },
]


def load_team(include_self_registered=True):
    """Load team from disk, falls back to defaults.

    If `include_self_registered` is True (default), also merges in users
    who signed in via the "Other email" path on the login screen and
    aren't yet on the official roster. Each gets a synthesized profile
    flagged with `_self_registered=True` so the UI can offer a "Promote
    to roster" action. This is what surfaces them in the login dropdown
    + Admin → Team panel after sign-up.
    """
    # Official roster
    if not Path(TEAM_FILE).exists():
        save_team(DEFAULT_TEAM)
        roster = list(DEFAULT_TEAM)
    else:
        try:
            with open(TEAM_FILE) as f:
                data = json.load(f)
            roster = data if isinstance(data, list) and data else list(DEFAULT_TEAM)
        except Exception:
            roster = list(DEFAULT_TEAM)

    if not include_self_registered:
        return roster

    # Merge self-registered users (live in user_accounts, not the JSON file)
    try:
        import database as _db
        accounts = _db.user_account_list()
    except Exception:
        accounts = []

    roster_emails = {(m.get('email') or '').lower().strip() for m in roster}
    for acc in accounts:
        email = (acc.get('email') or '').lower().strip()
        if not email or email in roster_emails:
            continue
        local = email.split('@')[0]
        # "joe.smith" / "joe-smith" / "joe_smith" → "Joe Smith"
        cleaned = local.replace('.', ' ').replace('_', ' ').replace('-', ' ')
        name = ' '.join(part.capitalize() for part in cleaned.split() if part)
        roster.append({
            'name': name or email,
            'email': email,
            'role': 'Team member',
            'short_role': 'AqueLyst',
            'bio': '',
            'aliases': [local.lower()],
            'company': 'AqueLyst',
            '_self_registered': True,
            'last_login': acc.get('last_login'),
            'created_at': acc.get('created_at'),
        })

    return roster


def save_team(team):
    try:
        with open(TEAM_FILE, 'w') as f:
            json.dump(team, f, indent=2)
        return True
    except Exception:
        return False


def reset_team():
    return save_team(list(DEFAULT_TEAM))


def get_member_by_email(email):
    """Find team member by their email address."""
    if not email:
        return None
    email = email.lower().strip()
    for m in load_team():
        if m.get('email', '').lower().strip() == email:
            return m
    return None


def get_member_by_name_or_alias(query):
    """Find team member by name fragment, alias, or partial match."""
    if not query:
        return None
    q = query.lower().strip()
    for m in load_team():
        if q == m.get('name', '').lower():
            return m
        if q in [a.lower() for a in m.get('aliases', [])]:
            return m
        # Partial substring match
        if q in m.get('name', '').lower():
            return m
    return None


def add_member(name, email, role, bio='', aliases=None, company='AqueLyst'):
    """Add a person to the official roster (team_members.json).

    Reads the persisted roster ONLY (not the synthesized self-registered
    merge layer) so promoting a self-registered user doesn't accidentally
    write the synthesized entry back to disk alongside the new one.

    If the email already exists on the official roster, updates that
    member's name/role/bio in place instead of appending a duplicate."""
    email = (email or '').lower().strip()
    if not email:
        return False
    team = load_team(include_self_registered=False)
    for m in team:
        if (m.get('email') or '').lower().strip() == email:
            m['name'] = name or m.get('name')
            m['role'] = role or m.get('role')
            m['short_role'] = role or m.get('short_role')
            m['bio'] = bio or m.get('bio')
            m.pop('_self_registered', None)
            m.pop('last_login', None)
            m.pop('created_at', None)
            return save_team(team)
    team.append({
        'name': name,
        'email': email,
        'role': role,
        'short_role': role,
        'bio': bio,
        'aliases': aliases or [name.split()[0].lower()],
        'company': company,
    })
    return save_team(team)


def update_member(index, **fields):
    team = load_team()
    if 0 <= index < len(team):
        team[index].update(fields)
        return save_team(team)
    return False


def delete_member(index):
    team = load_team()
    if 0 <= index < len(team):
        team.pop(index)
        return save_team(team)
    return False


def get_current_user():
    """Determine the currently-logged-in user.

    Source of truth is the per-user login flow (st.session_state). NEVER
    fall back to whoever's SMTP config happens to exist on disk — that
    bug caused emails generated when Danielle was logged in to be signed
    as Joseph (whose SMTP config was the global fallback). The session-
    state user is the only authoritative answer.

    Returns a member dict from team_members.json if known, otherwise a
    placeholder built from the email. Never returns a different person.
    """
    try:
        import streamlit as _st
        email = (_st.session_state.get('logged_in_user_email') or '').lower()
    except Exception:
        email = ''

    if email:
        member = get_member_by_email(email)
        if member:
            return member
        # Logged in but not on the official roster — build a self-only profile
        return {
            'name': email.split('@')[0].title(),
            'email': email,
            'role': 'Team member',
            'short_role': 'AqueLyst',
            'bio': '',
            'aliases': [],
            'company': 'AqueLyst',
            '_unknown': True,
        }

    # Nobody logged in (background thread before session_state, dev mode,
    # or the login gate itself). Return a generic placeholder — DO NOT read
    # any SMTP config or fall back to a real team member.
    return {
        'name': 'AqueLyst Team',
        'email': '',
        'role': 'AqueLyst',
        'short_role': 'AqueLyst',
        'bio': '',
        'aliases': [],
        'company': 'AqueLyst',
        '_unknown': True,
    }


def format_for_bot_prompt():
    """Render the team list as system-prompt context for the bot.
    Tells the bot WHO is on the team and what they do."""
    team = load_team()
    if not team:
        return ""

    lines = ["## ALQUELYST TEAM (you know everyone — match prospects to the right person)"]
    for m in team:
        lines.append(f"\n**{m['name']}** ({m.get('email', '')})")
        lines.append(f"- Role: {m.get('role', '')}")
        if m.get('bio'):
            lines.append(f"- Bio: {m['bio']}")

    lines.append("""
## TEAM-AWARENESS RULES
- If a prospect says "I want to talk to your CEO" → it's Joseph Dimartino
- If they ask for the COO → Debra Leblang
- If they want a co-founder or strategic conversation → Erika or Dani
- If they ask about the parent company / Remedia → Wyatt Schwab is the bridge
- If a prospect references someone by name from the team, recognize them
- For partnership / distribution / large-bulk inquiries (>$5K), ESCALATE so the right human takes over
""")

    return "\n".join(lines)


def format_current_user_block():
    """Tells the bot WHO IT IS RIGHT NOW (which team member's email is connected)."""
    user = get_current_user()
    if user.get('_unknown'):
        return (
            f"\n## YOU ARE WRITING AS\n"
            f"Name: {user['name']}\n"
            f"Email: {user['email']}\n"
            f"Sign emails as: {user['name']}\n"
        )

    return (
        f"\n## YOU ARE WRITING AS (this is who's logged in right now)\n"
        f"Name: {user['name']}\n"
        f"Role: {user['role']}\n"
        f"Email: {user['email']}\n"
        f"Sign emails as: {user['name']} (or just first name in casual replies)\n"
        f"\nWhen mentioning yourself, use this exact name and role. "
        f"You ARE this person speaking — never mention 'on behalf of' for THEM, "
        f"only for OTHER team members.\n"
    )
