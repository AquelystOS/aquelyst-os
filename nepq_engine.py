"""NEPQ Sales Engine — Neuro-Emotional Persuasion Questioning (Jeremy Miner method).

The bot uses NEPQ framework to:
- Open conversations with curiosity, not pitch
- Use connecting questions to lower resistance
- Ask situation/problem awareness questions
- Surface emotional consequences
- Lead the prospect to their own conclusion (not push)
- Handle objections by re-questioning

This module powers:
- Autonomous initial outreach (when lead becomes hot)
- Reply handling (when prospect responds)
- Multi-touch sequence (Day 1, 3, 7, 14, 21)
- Training chat where Joseph practices with the bot
"""

import json
import re
import requests
from datetime import datetime

import api_keys
import product_catalog
import team


CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"


# ============================================================================
# NEPQ SYSTEM PROMPT — the bot's brain
# ============================================================================
NEPQ_SYSTEM_PROMPT = """You are Aqua, the AqueLyst TEAM's elite AI sales assistant. The whole team uses you — Erika, Dani, Joseph, Debra, and Wyatt all share you. You don't belong to any one person. Whichever team member is currently logged in (see the YOU ARE WRITING AS block), you write FROM that person's email and sign off as them. But your loyalty is to AqueLyst as a whole, not to any individual.

AqueLyst makes a family of patented molecular converters that eliminate odor at the source — not by masking with fragrance. The technology comes from Remedia International, a parent company trusted by the EPA. The products work in 5 distinct verticals, and you should match the right product to the right prospect:

- **Duo Equine** ($62.50/gal) — Equine biosecurity. Horse barns, stalls, equestrian centers, trailers, breeders, rescues, tack shops, feed stores. PRIMARY product for any horse-industry prospect.
- **SpillMaster** ($75.00/gal) — Commercial spill response, food service/processing, healthcare, transit hubs, waste management, industrial cleanup.
- **Pets** ($46.50/gal) — Kennels, shelters, vet clinics, grooming salons, pet daycares, multi-pet households.
- **HouseHold** ($38.50/gal) — Residential odor control. Homeowners, apartments, families, fragrance-sensitive households.
- **AMR (Auto/Marine/RV)** ($36.99/gal) — Fleet/rideshare, RVs, marine/boats, aviation, transit/buses/trains, cruise lines.
- **Inversion Misting System** — Large-area automatic application for any facility, works with all products. Custom quote.

All products available in 1, 5, and 55 gallon sizes.

KEY SELLING POINTS (use sparingly, only when relevant):
- PATENTED technology (from Remedia International)
- EPA-trusted parent company / serious environmental applications
- MOLECULAR CONVERTER — works at the molecular level, not surface masking
- Non-toxic, biodegradable, safe for animals/people when used as directed
- Eliminates odor SOURCES (urine, manure, ammonia, organic compounds), which also reduces flies

You operate using the NEPQ (Neuro-Emotional Persuasion Questioning) methodology by Jeremy Miner. This is NOT old-school pushy sales. You sound like a curious peer who genuinely cares about helping, not a salesperson.

You operate using the NEPQ (Neuro-Emotional Persuasion Questioning) methodology by Jeremy Miner. This is NOT old-school pushy sales. You sound like a curious peer who genuinely cares about helping, not a salesperson.

## CORE NEPQ PRINCIPLES (always apply)

1. **Lower resistance first** — Prospects automatically resist anyone who sounds salesy. Open with curiosity, not a pitch. Ask before telling.

2. **Connection over conversion** — First message goal is conversation, not commitment. Get them talking about THEIR situation.

3. **Tonality matters even in writing** — Use a calm, low-stakes, curious tone. Never use exclamation points (rare exceptions). No bro-energy. Sound like a thoughtful peer.

4. **Skilled questions, not statements** — Lead with questions that make them think. The prospect should be doing 70% of the talking. In email: short, end with one focused question.

5. **Future pacing & consequence** — Once they share a problem, ask what happens if it stays unsolved (NEPQ "consequence questions"). Let them feel the cost of inaction in their own words.

6. **Never argue with objections** — Reflect them back as a question. "What makes you say that?" or "How do you mean?" — get them to elaborate so the objection often dissolves.

7. **Tie commitment to their own words** — When they say "I want to fix the fly problem before summer," you respond by quoting that back to them in the close.

## NEPQ QUESTION TYPES (use them in order)

1. **Connecting questions** (first contact)
   - "How are you currently handling [pain point] over there?"
   - "What's your current setup for [thing related to product]?"

2. **Situation questions** (gather facts)
   - "About how many stalls are you running?"
   - "Who handles the day-to-day at the barn?"

3. **Problem awareness** (surface pain they may not have named)
   - "What kind of issues come up with ammonia in summer for you?"
   - "How are clients reacting to it?"

4. **Solution awareness** (test what they've tried)
   - "What have you tried so far for the fly issue?"
   - "How well has [their current solution] been working?"

5. **Consequence questions** (raise the cost of inaction)
   - "If nothing changes, what does next summer look like?"
   - "How does that affect boarding clients staying with you?"

6. **Qualifying** (do they actually have authority/budget?)
   - "If you found something that actually worked, what would the decision look like for you?"
   - "Who else would be involved in deciding to try something new?"

7. **Transition** (gentle move toward solution)
   - "Would it be helpful if I showed you what's worked for facilities your size?"
   - "Worth a quick conversation to see if it'd fit your operation?"

8. **Commitment** (close, soft and confident)
   - "Based on what you shared, want me to ship out a 7-day trial so you can see it for yourself?"
   - "Sound like a fit?"

## EMAIL VOICE RULES

- 4-7 sentences for cold emails (never longer)
- 2-3 sentences for follow-up emails
- One question per email — focused, easy to reply to
- No multi-paragraph product explanations
- No bullet lists in cold emails (looks like marketing)
- Sign off as the LOGGED-IN team member's name (see "YOU ARE WRITING AS" block below)
- Subject lines: short, sound personal, no emojis except sparingly
- Include the prospect's first name once, naturally
- Reference something REAL about their business if you have it (from research)

## PRODUCT MATCHING LOGIC

Pick the right product for the prospect. NEVER recommend Duo Equine to a non-equine business.

| Prospect type | Lead with |
|---|---|
| Horse barn / stable / breeder / equine | Duo Equine |
| Pet shelter / kennel / vet / grooming | Pets |
| Commercial cleanup / spills / waste mgmt | SpillMaster |
| Auto fleet / RV / marine / aviation / transit | AMR |
| Homeowner / apartment / family | HouseHold |
| Large facility (any vertical, big space) | Cross-sell the Inversion Misting System |

When pricing comes up: mention the 1-gallon entry price for their product, then mention 5/55 gallon options exist for bigger operations. Don't try to close the sale on price alone — bring it back to the molecular-converter benefit.

## OUTREACH FACTS

- Joseph at AqueLyst (joseph@aquelyst.com) is the human contact
- For high-stakes inquiries (pricing, contracts, technical depth), the bot ESCALATES to Joseph
- Customers typically see results in days, not weeks
- Patented Remedia International technology, EPA-trusted parent

## NEVER DO

- Open with "I hope this email finds you well"
- Use words like "revolutionary", "amazing", "exclusive", "limited time"
- Pitch in the first message
- Send multi-paragraph product overviews
- Use marketing-speak ("solutions provider", "world-class")
- Send "just checking in" emails (write a real reason to follow up)
- Send the same template twice — vary phrasing
- Sound desperate or apologetic
- Mention price unless they ask

You have access to context about the prospect (business name, contact, score, pain hypothesis, prior emails). Use that context to make every message feel one-to-one."""


# ============================================================================
# Provider helpers
# ============================================================================
def _cerebras_chat(messages, max_tokens=1024, temperature=0.7):
    """Call Cerebras with a message list. Returns (text, error)."""
    api_key = api_keys.get_key('cerebras')
    if not api_key:
        return None, "No Cerebras key"

    # Pick best model
    try:
        mr = requests.get(f"{CEREBRAS_BASE_URL}/models",
                          headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        if mr.status_code == 200:
            available = [m['id'] for m in mr.json().get('data', [])]
            preferences = ['qwen-3-235b-a22b-instruct-2507', 'gpt-oss-120b',
                            'zai-glm-4.7', 'llama-3.3-70b', 'llama3.1-8b']
            model = next((m for m in preferences if m in available), available[0])
        else:
            model = 'llama3.1-8b'
    except Exception:
        model = 'llama3.1-8b'

    try:
        r = requests.post(
            f"{CEREBRAS_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=45
        )
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content'], None
        return None, f"Cerebras {r.status_code}: {r.text[:150]}"
    except Exception as e:
        return None, f"Cerebras error: {str(e)[:100]}"


def _claude_chat(messages, max_tokens=1024, system_prompt=None):
    """Call Claude with a message list. Returns (text, error)."""
    api_key = api_keys.get_key('claude')
    if not api_key:
        return None, "No Claude key"

    try:
        # Find available model
        mr = requests.get(f"{CLAUDE_BASE_URL}/models",
                          headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                          timeout=10)
        if mr.status_code == 200:
            available = [m['id'] for m in mr.json().get('data', [])]
            preferences = ['claude-sonnet-4-6', 'claude-haiku-4-5', 'claude-opus-4-7']
            model = next((m for m in preferences if m in available), available[0])
        else:
            model = 'claude-haiku-4-5'

        r = requests.post(
            f"{CLAUDE_BASE_URL}/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt or NEPQ_SYSTEM_PROMPT,
                "messages": messages,
            },
            timeout=45
        )
        if r.status_code == 200:
            return r.json()['content'][0]['text'], None
        return None, f"Claude {r.status_code}: {r.text[:150]}"
    except Exception as e:
        return None, f"Claude error: {str(e)[:100]}"


def chat(messages, prefer='auto', extra_context=''):
    """
    Main chat entry point. Routes to Claude → Cerebras → templates.
    messages: list of {role: user/assistant, content: str}

    Returns: (text, source) where source is 'claude' | 'cerebras' | 'template'
    """
    system = NEPQ_SYSTEM_PROMPT

    # Inject team identity (who the bot is RIGHT NOW + everyone else on the team)
    try:
        system = system + team.format_current_user_block()
        team_text = team.format_for_bot_prompt()
        if team_text:
            system = system + "\n\n" + team_text
    except Exception:
        pass

    # Inject the live product catalog so the bot can link to real products
    try:
        catalog_text = product_catalog.format_for_bot_prompt()
        if catalog_text:
            system = system + "\n\n" + catalog_text
    except Exception:
        pass

    # Inject the team's knowledge base (docs, scripts, FAQs the team has uploaded)
    try:
        import knowledge_base
        kb_text = knowledge_base.format_for_bot_prompt()
        if kb_text:
            system = system + "\n\n" + kb_text
    except Exception:
        pass

    # Inject LIVE CRM snapshot so the bot can answer "what's working" without being told
    try:
        crm_text = _build_crm_snapshot()
        if crm_text:
            system = system + "\n\n" + crm_text
    except Exception:
        pass

    if extra_context:
        system = system + "\n\n## ADDITIONAL CONTEXT\n" + extra_context

    if prefer == 'auto':
        # Prefer Claude for nuanced sales conversations
        if api_keys.has_key('claude'):
            text, err = _claude_chat(messages, system_prompt=system)
            if text:
                return text, 'claude'
        if api_keys.has_key('cerebras'):
            cerebras_msgs = [{"role": "system", "content": system}] + messages
            text, err = _cerebras_chat(cerebras_msgs)
            if text:
                return text, 'cerebras'
        return _template_fallback(messages), 'template'

    if prefer == 'claude':
        text, err = _claude_chat(messages, system_prompt=system)
        return (text or _template_fallback(messages)), ('claude' if text else 'template')

    if prefer == 'cerebras':
        cerebras_msgs = [{"role": "system", "content": system}] + messages
        text, err = _cerebras_chat(cerebras_msgs)
        return (text or _template_fallback(messages)), ('cerebras' if text else 'template')

    return _template_fallback(messages), 'template'


def _build_crm_snapshot():
    """Build a live snapshot of CRM + email stats so Aqua can answer questions about
    'what's working' / 'how are we doing' without the user having to paste data."""
    import sqlite3
    try:
        conn = sqlite3.connect('aquelyst_hunter.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Pipeline counts
        c.execute('''SELECT status, COUNT(*) as n FROM leads
                     WHERE (lead_source IS NULL OR lead_source != 'team_internal')
                     GROUP BY status''')
        statuses = {r['status']: r['n'] for r in c.fetchall()}

        c.execute('SELECT COUNT(*) FROM leads WHERE lead_score >= 70 AND status != "team_internal"')
        hot_count = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM leads WHERE lead_source != "team_internal" OR lead_source IS NULL')
        total = c.fetchone()[0]

        # Sent + received last 7 days
        c.execute('''SELECT COUNT(*) FROM outreach_drafts
                     WHERE sent = 1 AND created_at >= datetime('now', '-7 days')''')
        sent_7d = c.fetchone()[0]

        c.execute('''SELECT COUNT(*) FROM inbound_messages
                     WHERE received_at >= datetime('now', '-7 days')''')
        recv_7d = c.fetchone()[0]

        # Top intents in last 7 days
        c.execute('''SELECT intent, COUNT(*) as n FROM inbound_messages
                     WHERE received_at >= datetime('now', '-7 days')
                     GROUP BY intent ORDER BY n DESC LIMIT 5''')
        intents = [(r['intent'], r['n']) for r in c.fetchall() if r['intent']]

        # Lead sources
        c.execute('''SELECT COALESCE(lead_source, 'unknown') as src, COUNT(*) as n
                     FROM leads
                     WHERE (lead_source IS NULL OR lead_source != 'team_internal')
                     GROUP BY src ORDER BY n DESC LIMIT 5''')
        sources = [(r['src'], r['n']) for r in c.fetchall()]

        # Recent sent subject lines for "what's working" analysis
        c.execute('''SELECT subject, message_type FROM outreach_drafts
                     WHERE sent = 1 AND created_at >= datetime('now', '-7 days')
                     ORDER BY id DESC LIMIT 10''')
        recent_sent = [(r['subject'], r['message_type']) for r in c.fetchall()]

        conn.close()

        lines = [
            "## LIVE CRM SNAPSHOT (use this to answer questions about pipeline, performance, or 'what's working' — DO NOT ask the user to paste data, you have it)",
            f"- Total leads: {total} (hot: {hot_count})",
            f"- Pipeline by status: {statuses}",
            f"- Last 7 days: {sent_7d} sent, {recv_7d} received",
        ]

        if intents:
            lines.append(f"- Reply intents (last 7d): {dict(intents)}")
        if sources:
            lines.append(f"- Top lead sources: {dict(sources)}")
        if recent_sent:
            lines.append("- Recent sent subjects (newest first):")
            for subj, mt in recent_sent:
                lines.append(f"  · [{mt}] {subj}")

        return "\n".join(lines)
    except Exception:
        return ""


def _template_fallback(messages):
    """Smart fallback when AI is unavailable. Context-aware based on the conversation."""
    # Look at the last user message to detect if this is for a teammate or prospect
    last_msg = ''
    is_teammate = False
    for m in messages:
        if m.get('role') == 'user':
            last_msg = m.get('content', '')
    lower = last_msg.lower()
    if any(k in lower for k in ['teammate', 'team member', 'peer mode', 'co-founder', 'internal note']):
        is_teammate = True

    # Try to use the logged-in user's name for sign-off
    try:
        current = team.get_current_user()
        sign = current['name'].split()[0] if current.get('name') else ''
    except Exception:
        sign = ''

    if is_teammate:
        return f"Got it — thanks for sending this over. I'll process and follow up if I have specific questions.\n\n— {sign or 'Aqua'}"

    return (f"Got your note. Let me think on this and circle back with a more thoughtful reply.\n\n— {sign or 'Joseph'}")


# ============================================================================
# Specific NEPQ-aligned email generators
# ============================================================================
def generate_initial_outreach(lead_data):
    """Generate the FIRST cold email using NEPQ opening framework.

    Returns: dict with subject, body, source
    """
    business = lead_data.get('business_name', 'their barn')
    contact = lead_data.get('contact_name') or 'there'
    first_name = contact.split()[0] if contact != 'there' else 'there'
    pain = lead_data.get('pain_hypothesis') or lead_data.get('message') or ''
    notes = lead_data.get('notes') or ''
    location = ''
    if lead_data.get('city'):
        location = lead_data['city']
        if lead_data.get('state'):
            location += f", {lead_data['state']}"

    # Extract personalized hook from notes (autopilot puts AI hooks there)
    hook = ''
    if '💡 Hook:' in notes:
        hook = notes.split('💡 Hook:')[1].split('\n')[0].strip()

    current_user = team.get_current_user()
    sender_first = current_user['name'].split()[0] if current_user.get('name') else 'there'

    user_msg = f"""Generate the FIRST cold email to this prospect.

PROSPECT:
- Business: {business}
- Contact (first name): {first_name}
- Location: {location or 'unknown'}
- Known pain/problem: {pain or 'unknown — you may need to use a generic curiosity opener'}
- Personalized hook from research: {hook or 'none'}

YOU ARE: {current_user['name']} ({current_user['role']}) — sign off as "{sender_first}"

EMAIL REQUIREMENTS:
- 4-6 sentences max
- Open with NEPQ-style connecting question (not pitch)
- If you have a specific personalized hook, work it in naturally as the opener
- ONE focused question at the end (their answer is the next move)
- Subject line: short, conversational, sounds personal
- Sign off as "{sender_first}" (the logged-in user's first name)

OUTPUT FORMAT (exactly):
Subject: <subject line here>

<email body here, no preamble>"""

    text, source = chat([{"role": "user", "content": user_msg}])

    # Parse subject + body
    subject, body = _parse_subject_body(text)
    return {
        'subject': subject or f"Quick question about {business}",
        'body': body or text,
        'source': source,
    }


def generate_aqua_intro(lead_data):
    """Aqua introduces himself — branches on whether recipient is a team member.

    If recipient is on the AqueLyst team → casual internal peer message, no pitch.
    Otherwise → external prospect intro with AI-disclosure and gentle offer.
    """
    contact = lead_data.get('contact_name') or ''
    first_name = (contact.split()[0] if contact else '').strip().title() or 'there'
    recipient_email = (lead_data.get('email') or '').lower().strip()

    current_user = team.get_current_user()
    user_first = current_user['name'].split()[0] if current_user.get('name') else 'them'
    user_full = current_user['name']
    user_role = current_user.get('role', 'team member')
    user_email = current_user.get('email', '')

    # ===== Detect if recipient is a team member =====
    recipient_member = team.get_member_by_email(recipient_email)

    if recipient_member:
        # PEER MODE — casual internal note between two AqueLyst people, no pitch
        recipient_name = recipient_member['name']
        recipient_first = recipient_name.split()[0]
        recipient_role = recipient_member.get('role', '')

        user_msg = f"""You're Aqua, the AqueLyst TEAM's shared AI assistant. Every team member uses you — you're not just one person's tool. {user_first} happens to be the one logged in right now and is running a test.

You're writing a short, casual INTERNAL note to a TEAMMATE on the AqueLyst team. This is NOT a sales prospect.

TEAMMATE (the recipient):
- Name: {recipient_name}
- Role: {recipient_role}
- Email: {recipient_email}

CURRENTLY LOGGED IN (the sender):
- Name: {user_full}
- Role: {user_role}

CONTEXT:
{recipient_first} is a co-founder/exec at AqueLyst — they founded/run the company. Do NOT pitch products. Do NOT explain what AqueLyst does. Do NOT use "businesses like yours" language.

Write a short casual peer message:
- Greet {recipient_first} by name (properly capitalized)
- Note that {user_first} is testing the AqueLyst OS / Aqua bot
- Briefly say what you (Aqua) are: the team's shared AI assistant inside the OS
- 3-4 sentences MAX
- Casual, friendly — like coworkers
- Light closer: "want to ping back so we can see how it handles teammate replies?" or similar
- Sign off as "— Aqua · AqueLyst" (the whole team's assistant, not personal to {user_first})

OUTPUT FORMAT:
Subject: <subject>

<body>"""

    else:
        # EXTERNAL PROSPECT MODE
        business = lead_data.get('business_name', 'their business')
        business_type = lead_data.get('business_type', '') or ''
        location = ''
        if lead_data.get('city'):
            location = lead_data['city']
            if lead_data.get('state'):
                location += f", {lead_data['state']}"

        biz_phrase = (f"businesses like {business}" if business and business != 'their business'
                      else (f"{business_type}s" if business_type else "businesses in your space"))

        user_msg = f"""You're Aqua, the AqueLyst team's shared AI assistant. Right now {user_full} ({user_role}) is the one logged in, so emails go FROM their address — but you represent the whole AqueLyst team, not just them.

Write a short INTRODUCTION email to a prospect. NOT a pitch — just an honest, friendly intro that opens the door for conversation.

PROSPECT:
- Business: {business}
- Type: {business_type or 'unknown'}
- Contact name: {first_name}
- Location: {location or 'unknown'}

CURRENTLY LOGGED IN (sender):
- {user_full}, {user_role} at AqueLyst ({user_email})

REQUIREMENTS:
- 3-5 sentences MAX, conversational
- Disclose you're AI — phrase it as "AqueLyst's AI assistant" or "the AqueLyst team's AI assistant" (NOT "{user_first}'s personal AI"). Aqua is shared by the whole team.
- ONE sentence on why the team is reaching out to {biz_phrase}
- Do NOT explain product features, do NOT pitch, do NOT mention pricing
- End with a low-stakes question or "want to chat?" — give them an easy yes
- Sign off: "— Aqua · AqueLyst" then on next line "On behalf of {user_first} ({user_role}) — {user_email}"
- Subject: 4-7 words, warm, no exclamation marks

Be VARIED. Don't follow a template. Sound like a real person introducing themselves at a conference.

OUTPUT FORMAT:
Subject: <subject>

<body>"""

    text, source = chat([{"role": "user", "content": user_msg}])
    subject, body = _parse_subject_body(text)

    fallback_subject = (f"Hello from Aqua at AqueLyst" if recipient_member
                        else f"Quick intro — {lead_data.get('business_name', 'AqueLyst')}")

    return {
        'subject': subject or fallback_subject,
        'body': body or text,
        'source': source,
        'is_team_recipient': bool(recipient_member),
    }


def generate_custom_message(lead_data, user_instruction):
    """User describes what they want to say in plain English; Aqua writes the email.

    user_instruction: free-form text from Joseph like:
        "Tell them I noticed they have a new boarding facility opening and ask if
         they've thought about ammonia control before they move horses in."
    """
    business = lead_data.get('business_name', 'their business')
    contact = lead_data.get('contact_name') or 'there'
    first_name = contact.split()[0] if contact and contact != 'there' else 'there'
    business_type = lead_data.get('business_type', '') or ''
    location = ''
    if lead_data.get('city'):
        location = lead_data['city']
        if lead_data.get('state'):
            location += f", {lead_data['state']}"
    pain = lead_data.get('pain_hypothesis') or ''
    current_user = team.get_current_user()
    user_first = current_user['name'].split()[0] if current_user.get('name') else 'I'
    user_full = current_user['name']

    user_msg = f"""{user_full} (the {current_user.get('role', 'team member')} at AqueLyst) wants you to write a custom email to a prospect. They've described what they want to say below — your job is to turn it into a polished NEPQ-style email.

PROSPECT:
- Business: {business}
- Contact (first name): {first_name}
- Type: {business_type or 'unknown'}
- Location: {location or 'unknown'}
- Known pain: {pain or 'unknown'}

WHAT {user_first.upper()} WANTS TO SAY:
\"\"\"
{user_instruction}
\"\"\"

YOUR JOB:
- Take {user_first}'s intent and craft an email that achieves it
- Apply NEPQ principles (curious, low-stakes, one focused question)
- Use {user_first}'s key points but improve the phrasing
- Keep it 4-7 sentences
- Make it personal to {first_name} and {business}
- Sign off as "{user_first}" (or "Aqua · AqueLyst" if {user_first} mentioned wanting AI to send it)
- Subject line: short, conversational
- Don't add things {user_first} didn't ask for — stay close to their intent

OUTPUT FORMAT (exactly):
Subject: <subject>

<body>"""

    text, source = chat([{"role": "user", "content": user_msg}])
    subject, body = _parse_subject_body(text)
    return {
        'subject': subject or f"Re: {business}",
        'body': body or text,
        'source': source,
    }


def generate_followup(lead_data, prior_messages, touch_number):
    """Generate a follow-up email when no reply has come in.

    touch_number: 2 (day 3 education), 3 (day 7 trial offer), 4 (day 14 social proof), etc.
    """
    business = lead_data.get('business_name', '')
    first_name = (lead_data.get('contact_name') or 'there').split()[0]
    pain = lead_data.get('pain_hypothesis') or ''

    touch_focus = {
        2: ("EDUCATIONAL: Briefly explain HOW barn odor actually works (ammonia → flies). "
            "No pitch. Just useful insight. End with a curiosity question."),
        3: ("TRIAL OFFER: Make a low-friction soft offer of the 7-day free barn trial. "
            "Frame it as a 'no-obligation way to see for themselves.' One question."),
        4: ("SOCIAL PROOF: Reference a similar facility (you can describe one realistically). "
            "Their results in their own words. Then ask if their situation sounds similar."),
        5: ("SEASONAL: Acknowledge fly/ammonia season is coming or here. "
            "Ask if it's still on their radar."),
        6: ("FINAL: Honest, low-pressure 'closing the loop' — give them an out. "
            "'Should I assume this isn't a fit right now?' style. Polite, no guilt."),
    }

    focus = touch_focus.get(touch_number, "Friendly check-in with one specific question.")

    prior_summary = "\n".join([
        f"- {m['role']}: {m['content'][:200]}..." for m in prior_messages[-3:]
    ]) if prior_messages else "(no prior conversation)"

    user_msg = f"""Generate FOLLOW-UP email #{touch_number} (no reply received yet from prospect).

PROSPECT:
- Business: {business}
- First name: {first_name}
- Pain: {pain}

PRIOR EMAILS (most recent last):
{prior_summary}

THIS EMAIL'S FOCUS:
{focus}

REQUIREMENTS:
- 2-4 sentences (shorter than initial outreach)
- Don't repeat what prior emails said
- One focused question
- Subject line: can use "Re: ..." or fresh — your choice
- Sign off as the LOGGED-IN team member's first name (per the YOU ARE WRITING AS block above — could be Joseph, Debra, Erika, Dani, or Wyatt)

OUTPUT FORMAT:
Subject: <subject>

<body>"""

    text, source = chat([{"role": "user", "content": user_msg}])
    subject, body = _parse_subject_body(text)
    return {
        'subject': subject or f"Re: {business}",
        'body': body or text,
        'source': source,
    }


def generate_reply_to_inbound(lead_data, conversation_history, their_latest_message):
    """Generate a reply to an incoming message — RESPOND TO WHAT THEY ACTUALLY SAID.

    conversation_history: list of {role, content} dicts of prior emails
    their_latest_message: str of what they just sent
    """
    business = lead_data.get('business_name', '')
    first_name = (lead_data.get('contact_name') or 'there').split()[0]

    # Detect if this is a teammate (different reply mode)
    recipient_email = (lead_data.get('email') or '').lower().strip()
    teammate = team.get_member_by_email(recipient_email)

    if teammate:
        # PEER MODE — casual reply to a teammate
        user_msg = f"""A TEAMMATE just replied to you. They are NOT a sales prospect.

WHO REPLIED: {teammate['name']} ({teammate.get('role', 'team member')}) — on the AqueLyst team

WHAT THEY LITERALLY SAID:
\"\"\"
{their_latest_message}
\"\"\"

YOUR JOB:
- Read their message carefully and RESPOND TO WHAT THEY ACTUALLY SAID
- If they said "It works!" → just acknowledge it briefly ("Glad it landed clean!" etc.) — don't pivot to a sales pitch
- If they greeted you casually ("Hi", "Ello poppet" etc.) → reply casually back
- If they asked a question → answer it directly
- If they shared an observation → engage with it as a peer would
- DO NOT pitch products, do NOT ask NEPQ sales questions, do NOT mention the trial
- DO NOT explain what AqueLyst does or list product features
- Keep it 1-3 sentences, casual, friendly
- Sign off as Aqua (the team's AI assistant)

OUTPUT FORMAT:
Subject: Re: <previous subject>

<body>"""
    else:
        # PROSPECT MODE — NEPQ but RESPOND TO WHAT THEY SAID FIRST
        user_msg = f"""The prospect just replied. Read what they LITERALLY said and respond to THAT — don't pivot to what you want to discuss.

PROSPECT: {first_name} at {business}
Pain context: {lead_data.get('pain_hypothesis', 'unknown')}

WHAT THEY LITERALLY SAID:
\"\"\"
{their_latest_message}
\"\"\"

CRITICAL RULES:
1. **RESPOND TO WHAT THEY SAID** — quote or paraphrase their actual words, don't ignore them
2. If they answered a question, ACKNOWLEDGE the answer before asking the next thing
3. If they asked a question, ANSWER IT directly first (don't deflect with another question)
4. If they made a statement, engage with the SUBSTANCE of what they said
5. If they're being brief or casual, match that energy — don't write a paragraph back
6. Don't repeat the same NEPQ angle they already deflected
7. Only ask a follow-up question if it's natural and relevant to what they JUST said

NEPQ STYLE GUIDELINES:
- Use NEPQ framework (curious, low-stakes) but don't force it if they're being casual
- Match their tone and length
- Keep it 2-5 sentences MAX
- Subject: "Re: <previous subject>" (preserve thread)
- Sign off as the logged-in user's first name

EXAMPLES OF GOOD vs BAD:

❌ BAD (ignores what they said, pivots to NEPQ):
   They said: "I use PDZ and Lyme"
   You said: "What are biggest frustrations going into show season?" ← totally ignores their answer

✅ GOOD (responds to what they said):
   They said: "I use PDZ and Lyme"
   You said: "Got it — PDZ and lime are common go-tos. How well are they keeping up with ammonia in summer for you?"

OUTPUT FORMAT:
Subject: Re: <previous subject>

<body>"""

    # Include conversation context (last 6 turns for memory)
    messages = []
    for msg in conversation_history[-6:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_msg})

    text, source = chat(messages)
    subject, body = _parse_subject_body(text)
    return {
        'subject': subject or f"Re: {business}",
        'body': body or text,
        'source': source,
    }


def classify_inbound_intent(message_body):
    """Classify what kind of reply this is so we know how to handle it.

    Returns dict with intent, escalation flag, and reasoning.
    Escalation = "this needs the human (Joseph) — don't auto-reply."
    """
    user_msg = f"""Classify this email reply from a sales prospect.

EMAIL:
{message_body[:2000]}

You're a sales operations AI deciding what should happen next.

Return JSON only (no markdown fences):
{{
  "intent": "one of: interested, question, objection, ready_to_buy, pricing_request, not_interested, unsubscribe, auto_reply, complaint, legal_concern, escalate_human, other",
  "summary": "one-sentence summary of what they said",
  "suggested_lead_status": "one of: interested, trial_offered, closed_won, closed_lost, opted_out, researched",
  "should_auto_reply": true/false,
  "escalate_to_human": true/false,
  "escalation_reason": "if escalate_to_human=true, one sentence why. Otherwise null.",
  "urgency": "high | medium | low",
  "sentiment": "positive | neutral | negative | hostile"
}}

ESCALATE TO HUMAN when:
- They have a complaint, are angry, or hostile
- They mention legal, lawyer, refund, or compliance
- They want a BULK quote that would total OVER $5,000 (e.g. multiple 55-gal drums for facility-wide misting, large fleet order, multi-site contract)
- They ask a complex technical question the bot can't answer reliably (e.g. specific chemistry, EPA registration numbers, MSDS/SDS docs)
- They want to talk to a real person specifically
- They reference a previous conversation/relationship the bot doesn't have context for
- They mention partnership, distribution, reseller, or wholesale agreements

DO NOT escalate (bot handles autonomously):
- ANY standard pricing question — the bot KNOWS the prices ($62.50 Duo Equine 1gal, $75 SpillMaster, $46.50 Pets, $38.50 HouseHold, $36.99 AMR)
- "How much does it cost?" → bot quotes the 1-gal price for their product, mentions 5/55 gallon variants
- Routine objections (too expensive, not now, I'll think about it)
- Standard product/trial/how-it-works questions
- Asking for more info, brochure, or details
- Polite no's
- Buying intent at standard volume (single gallon up to a few 5-gallon containers)

The bot is GOOD at:
- NEPQ-style sales conversations
- Quoting standard prices for all 5 products
- Recommending size variants (1/5/55 gallon)
- Recommending the right product for the prospect's vertical
- Mentioning the inversion misting system for large facilities

The bot is BAD at (escalate these):
- Bulk quotes >$5,000 / multi-site contracts
- Custom misting system installations
- Distribution / reseller / partnership deals
- Angry customers, legal threats
- Technical depth (chemistry, regulatory docs)
- Existing-customer support issues"""

    text, source = chat([{"role": "user", "content": user_msg}])

    cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    array_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if array_match:
        cleaned = array_match.group(0)

    try:
        result = json.loads(cleaned)
        # Backwards compat: ensure expected fields exist
        result.setdefault('should_auto_reply', result.get('should_reply', True))
        result.setdefault('escalate_to_human', False)
        result.setdefault('sentiment', 'neutral')
        # If escalating, override should_auto_reply to False
        if result.get('escalate_to_human'):
            result['should_auto_reply'] = False
        # Backwards compat for old code paths
        result['should_reply'] = result['should_auto_reply']
        return result
    except json.JSONDecodeError:
        # Fallback heuristic
        lower = message_body.lower()
        if 'unsubscribe' in lower or 'remove me' in lower:
            return {'intent': 'unsubscribe', 'should_auto_reply': False, 'should_reply': False,
                    'escalate_to_human': False, 'suggested_lead_status': 'opted_out',
                    'urgency': 'high', 'sentiment': 'neutral',
                    'summary': 'Unsubscribe request'}
        if any(w in lower for w in ['lawyer', 'legal', 'refund', 'angry', 'complaint']):
            return {'intent': 'escalate_human', 'should_auto_reply': False, 'should_reply': False,
                    'escalate_to_human': True,
                    'escalation_reason': 'Detected legal/complaint keywords',
                    'suggested_lead_status': 'researched', 'urgency': 'high',
                    'sentiment': 'negative', 'summary': 'Sensitive topic — needs human'}
        if any(w in lower for w in ['buy', 'purchase', 'price', 'cost', 'how much']):
            return {'intent': 'pricing_request', 'should_auto_reply': False, 'should_reply': False,
                    'escalate_to_human': True,
                    'escalation_reason': 'Buying/pricing inquiry — close-the-deal moment',
                    'suggested_lead_status': 'interested', 'urgency': 'high',
                    'sentiment': 'positive', 'summary': 'Asking about pricing/buying'}
        if any(w in lower for w in ['not interested', 'no thanks', 'pass']):
            return {'intent': 'not_interested', 'should_auto_reply': False, 'should_reply': False,
                    'escalate_to_human': False, 'suggested_lead_status': 'closed_lost',
                    'urgency': 'low', 'sentiment': 'neutral', 'summary': 'Declined'}
        if '?' in message_body:
            return {'intent': 'question', 'should_auto_reply': True, 'should_reply': True,
                    'escalate_to_human': False, 'suggested_lead_status': 'interested',
                    'urgency': 'high', 'sentiment': 'neutral', 'summary': 'Asked a question'}
        return {'intent': 'other', 'should_auto_reply': True, 'should_reply': True,
                'escalate_to_human': False, 'suggested_lead_status': 'interested',
                'urgency': 'medium', 'sentiment': 'neutral', 'summary': 'General reply'}


def _parse_subject_body(text):
    """Parse 'Subject: ...\n\n<body>' format. Returns (subject, body)."""
    if not text:
        return None, text

    lines = text.strip().split('\n', 1)
    first = lines[0].strip()

    if first.lower().startswith('subject:'):
        subject = first[8:].strip().strip('*').strip('"').strip()
        body = lines[1].strip() if len(lines) > 1 else ''
        return subject, body

    return None, text


# ============================================================================
# Training/practice chat — Joseph teaches the bot
# ============================================================================
def training_chat(conversation_history, user_message, training_mode='practice'):
    """Joseph chats with the bot to practice scenarios or train it.

    training_mode:
      - 'practice': Joseph plays a prospect, bot responds as the salesperson
      - 'review': Bot critiques an email Joseph wrote
      - 'rewrite': Bot rewrites Joseph's email in NEPQ style
      - 'qa': Joseph asks the bot questions about NEPQ methodology
    """
    mode_instructions = {
        'practice': (
            "You are the salesperson. The user is roleplaying as a prospect — "
            "could be horse barn owner, fleet manager, kennel operator, or any vertical the AqueLyst products serve. "
            "Ask clarifying questions about WHO they're playing if unclear, then engage them with NEPQ. "
            "After your response, in italics on a new line, briefly note which NEPQ technique you used "
            "and why you picked it."
        ),
        'review': (
            "The user will paste an email or response they wrote. "
            "Critique it through an NEPQ lens. What's strong? What sounds salesy? "
            "What questions could they have asked? Be specific and actionable. "
            "Give a rewritten version at the end."
        ),
        'rewrite': (
            "The user will give you an email or message draft. "
            "Rewrite it in NEPQ style — curious, low-stakes, one focused question. "
            "Show ORIGINAL and NEPQ VERSION side by side."
        ),
        'qa': (
            "You are Aqua, the AqueLyst team's AI sales assistant and ALWAYS-LEARNING sales coach. "
            "The team is talking to you in open chat — could be questions, ideas, brainstorms, deal strategy, "
            "general business musings, or roleplays beyond just horses. "
            "Engage as a thoughtful peer who happens to be deeply versed in B2B sales psychology. "
            "Pull from your knowledge of NEPQ, Sandler, Challenger, SPIN, MEDDIC, and modern sales frameworks. "
            "When a team member shares an insight, ACKNOWLEDGE it and build on it. "
            "Treat every conversation as an opportunity to LEARN about the company's needs, the market, "
            "what's working in the field. Ask the team good follow-up questions sometimes. "
            "If they want to roleplay any sales scenario (B2B, B2C, any industry), play along — "
            "you're a master sales pro who can adapt to ANY product, not just AqueLyst. "
            "If they paste an email exchange and ask for advice, give specific tactical guidance. "
            "Remember: Joseph Dimartino (CEO) is the lead sales trainer here — when he gives you guidance "
            "or correction, internalize it and apply it going forward."
        ),
    }

    extra = mode_instructions.get(training_mode, mode_instructions['practice'])

    messages = []
    for msg in conversation_history[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": user_message})

    text, source = chat(messages, extra_context=extra)
    return {'text': text, 'source': source}
