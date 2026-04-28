"""AI provider router — Claude → Cerebras → Ollama → Templates fallback chain.

Power Tiers:
  Tier 1 ⚡⚡⚡⚡  Claude (cloud, paid, smartest)
  Tier 2 ⚡⚡⚡   Cerebras (cloud, free tier, fast + smart)
  Tier 3 ⚡⚡    Ollama (local, free, slower)
  Tier 4 ⚡     Templates (always works, deterministic)
"""

import requests
import api_keys


CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
OLLAMA_BASE_URL = "http://localhost:11434"


def _system_prompt():
    """System prompt for sales outreach generation."""
    return """You are an expert B2B sales copywriter for AqueLyst, a company selling Duo Equine — a barn odor and fly elimination product.

Duo Equine eliminates ammonia at the source (not masks it), reduces fly-attracting compounds, and improves barn air quality. It's used in horse stalls, trailers, and bedding.

Your messages must:
- Be concise (5-7 sentences for emails, 2-3 for DMs)
- Sound human, never AI-generated
- Reference the prospect's specific business and pain
- Lead with the problem, not the product
- End with ONE focused, low-pressure discovery question — no offer, no close, no sample/trial language unless the user explicitly asks for it
- Avoid spammy words ("revolutionary", "amazing", "exclusive", excessive exclamation)
- Avoid all-caps, emojis (unless casual DM), or salesy language
- Do NOT pitch a free trial, sample, demo, or any offer unless explicitly instructed for THIS message

Output ONLY the message body. No preamble, no explanations, no markdown formatting unless requested."""


def _build_user_prompt(message_type, lead_data):
    """Build context-rich prompt for AI. Forces AI to engage with the SPECIFIC
    prospect's research data — not write generic templates."""
    contact = lead_data.get('contact_name') or 'there'
    first_name = contact.split()[0] if contact and contact != 'there' else 'there'
    business = lead_data.get('business_name', '')
    business_type = lead_data.get('business_type', 'unknown')
    pain = lead_data.get('pain_hypothesis') or lead_data.get('message') or ''
    state = lead_data.get('state', '')
    city = lead_data.get('city', '')
    website = lead_data.get('website', '')
    notes = lead_data.get('notes', '')
    product_fit = lead_data.get('product_fit') or 'unknown'

    location = f"{city}, {state}".strip(', ') if city or state else 'unknown'

    # Pull the AI-research personalized_hook (a specific fact about THIS prospect)
    hook = (lead_data.get('_personalized_hook') or
             lead_data.get('personalized_hook') or '')

    # Surface burden tags + need-probability so the email can engage with REAL pain
    intel_lines = []
    try:
        import intelligence_layer as _il
        burden = _il.get_burden_tags(business_type)
        if burden:
            intel_lines.append(f"Operational burden indicators: {', '.join(burden[:6])}")
    except Exception:
        pass

    context = f"""PROSPECT DATA (use these specifics — don't write a generic email):
- Business: {business or '(unknown — flag in subject)'}
- Type: {business_type}
- Product fit (per research): {product_fit}
- Contact first name: {first_name}
- Location: {location}
- Website: {website or 'none'}
- Specific fact / hook from website research: {hook or '(none — must reference business type + location)'}
- Pain hypothesis: {pain or '(infer from operational burden indicators below)'}"""
    if intel_lines:
        context += "\n- " + "\n- ".join(intel_lines)
    if notes:
        context += f"\n\nADDITIONAL RESEARCH NOTES:\n{notes[:600]}"

    context += "\n\nSENDER: write FROM the logged-in team member (see YOU ARE WRITING AS block in system prompt)."

    type_instructions = {
        "cold_email": (
            "Write a cold email (5-7 sentences). Subject line first as 'Subject: ...', blank line, body.\n"
            "RULES (STRICT — VIOLATING ANY OF THESE IS A FAILED EMAIL):\n"
            "1. You MUST reference at least ONE specific fact from the prospect's research above "
            "(their hook, their location, their business type, or a burden indicator). NO generic openers.\n"
            "2. PRODUCT LOCK: The 'Product fit' field above tells you exactly which AqueLyst "
            "product belongs in this email. STAY ON THAT PRODUCT. If it's 'Pets' you talk "
            "kennel/shelter/vet pain. If 'AMR' you talk fleet/marine/RV. If 'SpillMaster' you "
            "talk commercial/food/healthcare. Do NOT pivot to horses unless product_fit is 'Duo Equine'.\n"
            "3. ABSOLUTELY NO OFFERS in cold outreach: no trial, no sample, no demo, no "
            "free week, no '7 days', no money-back, no testing offer. The whole point is "
            "discovery — get them TALKING. Offers come ONLY in reply mode after they've "
            "expressed interest. Mentioning ANY offer in a cold email is a failed email.\n"
            "4. End with ONE focused, low-pressure discovery question. Make them think.\n"
            "5. If the prospect data is too thin to write something specific (no hook, no "
            "burden indicators, generic business name), output EXACTLY: "
            "'ESCALATE: insufficient research data' and nothing else."
        ),
        "reply_to_inbound": (
            "They reached out. Read what they said and RESPOND TO IT — don't pivot. Acknowledge their actual words first, then engage. Subject 'Re: ...' first."
        ),
        "instagram_dm": "Casual Instagram DM (2-3 sentences). Lowercase, no subject. Reference one specific thing from their profile/business. End with a question.",
        "facebook_message": "Facebook message (3-4 sentences). Professional but friendly. Reference one specific thing about them. No subject line.",
        "phone_opener": "20-30 second phone opener. Mention their {business_type} specifically and the burden YOU INFERRED (not generic). Ask for 30 seconds.",
        "follow_up_education": (
            "Educational follow-up. Briefly explain HOW their specific operational pain works at the molecular level — match it to their vertical's burden indicators. No pitch. End with a curiosity question."
        ),
        "trial_offer": "Formal trial offer (only when explicitly requested by user — never a default). Subject first. Easy to say yes.",
        "social_proof": "Reference a comparable facility (describe one realistically for THEIR vertical, not generic). Subject first.",
        "objection_budget": "They said budget is tight. Reframe with math relevant to their vertical. Subject first.",
        "objection_timing": "They said timing's bad. Reframe with the seasonal/operational pressure SPECIFIC to their vertical. Subject first.",
    }

    instruction = type_instructions.get(message_type, "Write an outreach message.")

    return f"{context}\n\nMESSAGE TYPE: {message_type}\nINSTRUCTION: {instruction}"


def generate_with_claude(prompt, model='claude-sonnet-4-6', max_tokens=1024):
    """Generate via Claude API. Returns (text, error)."""
    api_key = api_keys.get_key('claude')
    if not api_key:
        return None, "Claude API key not configured"

    try:
        response = requests.post(
            f"{CLAUDE_BASE_URL}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": _system_prompt(),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            text = data['content'][0]['text']
            return text, None
        else:
            return None, f"Claude API error {response.status_code}: {response.text[:200]}"

    except requests.Timeout:
        return None, "Claude API timeout"
    except Exception as e:
        return None, f"Claude error: {str(e)}"


def generate_with_cerebras(prompt, model='llama-3.3-70b', max_tokens=1024):
    """Generate via Cerebras API. Returns (text, error)."""
    api_key = api_keys.get_key('cerebras')
    if not api_key:
        return None, "Cerebras API key not configured"

    try:
        response = requests.post(
            f"{CEREBRAS_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            text = data['choices'][0]['message']['content']
            return text, None
        else:
            return None, f"Cerebras API error {response.status_code}: {response.text[:200]}"

    except requests.Timeout:
        return None, "Cerebras API timeout"
    except Exception as e:
        return None, f"Cerebras error: {str(e)}"


def generate_with_openai(prompt, model='gpt-4o-mini', max_tokens=1024):
    """Generate via OpenAI API. Returns (text, error)."""
    api_key = api_keys.get_key('openai')
    if not api_key:
        return None, "OpenAI API key not configured"

    try:
        response = requests.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content'], None
        else:
            return None, f"OpenAI API error {response.status_code}"

    except Exception as e:
        return None, f"OpenAI error: {str(e)}"


def generate_with_ollama(prompt, model='mistral'):
    """Generate via local Ollama. Returns (text, error)."""
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": f"{_system_prompt()}\n\n{prompt}",
                "stream": False,
            },
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('response', '').strip(), None
        return None, f"Ollama HTTP {response.status_code}"
    except (requests.RequestException, requests.ConnectionError) as e:
        return None, f"Ollama not available: {str(e)}"


def check_ollama_available():
    """Check if Ollama is running."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def get_ollama_models():
    """List Ollama models."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return [m['name'] for m in response.json().get('models', [])]
    except Exception:
        pass
    return []


def get_cerebras_models():
    """Fetch live list of Cerebras models from their API."""
    api_key = api_keys.get_key('cerebras')
    if not api_key:
        return []
    try:
        response = requests.get(
            f"{CEREBRAS_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return [m['id'] for m in data.get('data', [])]
    except Exception:
        pass
    return []


def get_claude_models():
    """Fetch live list of Claude models from Anthropic API."""
    api_key = api_keys.get_key('claude')
    if not api_key:
        return []
    try:
        response = requests.get(
            f"{CLAUDE_BASE_URL}/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return [m['id'] for m in data.get('data', [])]
    except Exception:
        pass
    return []


def get_available_tiers():
    """Return list of available AI tiers, ranked by power."""
    tiers = []

    if api_keys.has_key('claude'):
        tiers.append({
            'tier': 1,
            'provider': 'claude',
            'label': '⚡⚡⚡⚡ Claude (Maximum Intelligence)',
            'badge_color': '#7c3aed',
        })

    if api_keys.has_key('cerebras'):
        tiers.append({
            'tier': 2,
            'provider': 'cerebras',
            'label': '⚡⚡⚡ Cerebras (Smart + Fast)',
            'badge_color': '#dc2626',
        })

    if api_keys.has_key('openai'):
        tiers.append({
            'tier': 2,
            'provider': 'openai',
            'label': '⚡⚡⚡ OpenAI (Smart)',
            'badge_color': '#10a37f',
        })

    if check_ollama_available():
        tiers.append({
            'tier': 3,
            'provider': 'ollama',
            'label': '⚡⚡ Ollama (Local, Free)',
            'badge_color': '#3b82f6',
        })

    tiers.append({
        'tier': 4,
        'provider': 'templates',
        'label': '⚡ Templates (Reliable Baseline)',
        'badge_color': '#6b7280',
    })

    return tiers


def get_best_provider():
    """Return the most powerful available provider."""
    tiers = get_available_tiers()
    return tiers[0]['provider'] if tiers else 'templates'


def generate(message_type, lead_data, provider='auto', model=None):
    """
    Top-level generation router. Returns dict with text, source, tier, error.

    provider: 'auto' (best available), 'claude', 'cerebras', 'openai', 'ollama', 'templates'
    """
    if provider == 'auto':
        provider = get_best_provider()

    prompt = _build_user_prompt(message_type, lead_data)

    if provider == 'claude':
        info = api_keys.get_provider_info('claude')
        chosen_model = model or info.get('default_model', 'claude-sonnet-4-6')
        text, error = generate_with_claude(prompt, model=chosen_model)
        if text:
            return {'text': text, 'source': 'claude', 'model': chosen_model,
                    'tier': 1, 'tier_label': '⚡⚡⚡⚡ Claude'}
        # Fallback chain
        return generate(message_type, lead_data, provider='cerebras', model=None)

    if provider == 'cerebras':
        info = api_keys.get_provider_info('cerebras')
        chosen_model = model or info.get('default_model', 'llama-3.3-70b')
        text, error = generate_with_cerebras(prompt, model=chosen_model)
        if text:
            return {'text': text, 'source': 'cerebras', 'model': chosen_model,
                    'tier': 2, 'tier_label': '⚡⚡⚡ Cerebras'}
        return generate(message_type, lead_data, provider='openai', model=None)

    if provider == 'openai':
        info = api_keys.get_provider_info('openai')
        chosen_model = model or info.get('default_model', 'gpt-4o-mini')
        text, error = generate_with_openai(prompt, model=chosen_model)
        if text:
            return {'text': text, 'source': 'openai', 'model': chosen_model,
                    'tier': 2, 'tier_label': '⚡⚡⚡ OpenAI'}
        return generate(message_type, lead_data, provider='ollama', model=None)

    if provider == 'ollama':
        chosen_model = model or 'mistral'
        text, error = generate_with_ollama(prompt, model=chosen_model)
        if text:
            return {'text': text, 'source': 'ollama', 'model': chosen_model,
                    'tier': 3, 'tier_label': '⚡⚡ Ollama'}
        return generate(message_type, lead_data, provider='templates', model=None)

    # Final fallback: templates
    import outreach
    template_result = outreach.generate_outreach(message_type, lead_data, use_ollama=False)
    return {
        'text': template_result['content'],
        'subject': template_result.get('subject'),
        'source': 'templates',
        'model': 'fallback',
        'tier': 4,
        'tier_label': '⚡ Templates'
    }


def parse_subject_from_text(text):
    """Extract 'Subject: ...' from first line of generated text if present."""
    if not text:
        return None, text

    lines = text.strip().split('\n')
    first = lines[0].strip()
    if first.lower().startswith('subject:'):
        subject = first[8:].strip().strip('*').strip('"').strip()
        body = '\n'.join(lines[1:]).strip()
        return subject, body
    return None, text


def test_provider(provider, model=None):
    """Quick test of an AI provider. Returns (success, message)."""
    if provider == 'claude':
        # Try with a minimal call
        live_models = get_claude_models()
        test_model = model
        if not test_model:
            test_model = live_models[0] if live_models else 'claude-haiku-4-5'

        text, error = generate_with_claude("Say 'hello' in one word.", model=test_model, max_tokens=20)
        if text:
            return True, f"✅ Claude works! Model: {test_model}. Available models: {len(live_models)}"
        return False, f"❌ Claude API error: {error}"

    if provider == 'cerebras':
        live_models = get_cerebras_models()
        test_model = model

        if live_models and not test_model:
            test_model = live_models[0]
        elif not test_model:
            test_model = 'llama3.1-8b'

        text, error = generate_with_cerebras("Say 'hello' in one word.", model=test_model, max_tokens=20)
        if text:
            available = ', '.join(live_models[:5]) if live_models else 'unknown'
            return True, f"✅ Cerebras works! Model: {test_model}. Available: {available}"

        # Try with a smaller fallback model if current failed
        if test_model != 'llama3.1-8b':
            text2, error2 = generate_with_cerebras("Say hello.", model='llama3.1-8b', max_tokens=20)
            if text2:
                return True, f"✅ Cerebras works with llama3.1-8b (your default '{test_model}' failed: {error})"

        return False, f"❌ Cerebras API error: {error}"

    if provider == 'openai':
        test_model = model or 'gpt-4o-mini'
        text, error = generate_with_openai("Say 'hello' in one word.", model=test_model, max_tokens=20)
        if text:
            return True, f"✅ OpenAI works! Model: {test_model}"
        return False, f"❌ OpenAI API error: {error}"

    if provider == 'ollama':
        models = get_ollama_models()
        test_model = model or (models[0] if models else 'mistral')
        text, error = generate_with_ollama("Say 'hello' in one word.", model=test_model)
        if text:
            return True, f"✅ Ollama works! Model: {test_model}"
        return False, f"❌ Ollama error: {error}"

    return False, f"❌ Unknown provider: {provider}"
