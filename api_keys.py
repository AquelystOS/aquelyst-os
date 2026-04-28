"""Secure local API key storage for AqueLyst Hunter.

Keys are base64-encoded and stored locally with restricted permissions.
Not encryption — but adequate for single-user local app.
For multi-user/cloud deployment, use OS keychain or env vars instead.
"""

import json
import os
import base64
from pathlib import Path

KEYS_FILE = "api_keys.json"

# Sentinel user_email row in the team_api_keys table that holds the team's
# shared baseline keys (the ones the Admin UI saves). Survives Streamlit Cloud
# reboots when DATABASE_URL is configured to Postgres — unlike api_keys.json,
# which is on the ephemeral container filesystem.
_SHARED_USER = '__shared_baseline__'

# Hardcoded fallbacks — only used if st.secrets / env var / local file all fail.
# These keep the cloud deploy working even if Streamlit secrets aren't set.
# REPO MUST BE PRIVATE — these leak via GitHub if public.
_HARDCODED_FALLBACKS = {
    'cerebras': 'csk-yx4v98d5kpprjvdcdc9x82j2ddmdmwcfvemvfpt36m35942k',
}


def _save_to_team_table(provider, api_key):
    """Persist to team_api_keys (Postgres on cloud, SQLite locally) so saves
    survive container reboots. Best-effort — failures don't break the save."""
    try:
        import database
        database.team_keys_save(_SHARED_USER, provider, api_key, label='shared baseline')
    except Exception:
        pass


def _get_from_team_table(provider):
    try:
        import database
        return database.team_keys_get_for_user(_SHARED_USER, provider)
    except Exception:
        return None


def _delete_from_team_table(provider):
    try:
        import database
        database.team_keys_delete(_SHARED_USER, provider)
    except Exception:
        pass


def _load_raw():
    if not Path(KEYS_FILE).exists():
        return {}
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_raw(data):
    with open(KEYS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(KEYS_FILE, 0o600)
    except Exception:
        pass


def set_key(provider, api_key):
    """Save an API key for a provider. Writes to BOTH the local encoded file
    (so local dev keeps working without a DB) AND the team_api_keys table
    (so cloud deploys survive container reboots when Postgres is configured)."""
    data = _load_raw()
    data[provider] = base64.b64encode(api_key.encode()).decode()
    _save_raw(data)
    _save_to_team_table(provider, api_key.strip())


def get_key(provider):
    """Retrieve an API key for a provider.

    Priority order:
    1. Streamlit secrets — `st.secrets["CEREBRAS_API_KEY"]` etc.
    2. Environment variables — `CEREBRAS_API_KEY`
    3. team_api_keys table (shared baseline row) — Postgres on cloud (persistent)
       or SQLite locally. This is what the Admin UI's "save key" button writes to.
    4. Local encoded file (api_keys.json) — legacy / dev mode.
    5. Hardcoded fallback (last resort, only Cerebras).
    """
    # 1. Try Streamlit secrets first (works in cloud + when user has set them locally)
    try:
        import streamlit as st
        secret_key = f"{provider.upper()}_API_KEY"
        if hasattr(st, 'secrets'):
            try:
                val = st.secrets.get(secret_key, "")
                if val:
                    return val
            except Exception:
                pass
    except ImportError:
        pass

    # 2. Env var
    env_var = f"{provider.upper()}_API_KEY"
    env_value = os.environ.get(env_var)
    if env_value:
        return env_value

    # 3. Shared-baseline row in team_api_keys (persistent across Cloud reboots
    # when DATABASE_URL points to Postgres)
    table_val = _get_from_team_table(provider)
    if table_val:
        return table_val

    # 4. Local file (legacy / dev mode)
    data = _load_raw()
    encoded = data.get(provider)
    if encoded:
        try:
            return base64.b64decode(encoded).decode()
        except Exception:
            pass

    # 5. Hardcoded fallback (cloud-deploy safety net — keep repo private!)
    return _HARDCODED_FALLBACKS.get(provider)


def delete_key(provider):
    """Remove an API key from BOTH the local file and the team table."""
    data = _load_raw()
    existed_locally = provider in data
    if existed_locally:
        del data[provider]
        _save_raw(data)
    _delete_from_team_table(provider)
    return existed_locally or _get_from_team_table(provider) is None


def has_key(provider):
    """Check if a provider has a configured key."""
    return get_key(provider) is not None


def list_configured_providers():
    """List all providers with configured keys."""
    return [p for p in ['claude', 'cerebras', 'openai'] if has_key(p)]


# Provider metadata: where to get keys, pricing notes, model options
PROVIDER_INFO = {
    'claude': {
        'name': 'Claude (Anthropic)',
        'tier': 1,
        'tier_label': '⚡⚡⚡⚡ Maximum Intelligence',
        'description': 'Most powerful — best personalization, nuance, and reasoning. Costs ~$0.001-0.015 per email.',
        'signup_url': 'https://console.anthropic.com/settings/keys',
        'help_url': 'https://docs.claude.com/en/api/getting-started',
        'pricing_url': 'https://www.anthropic.com/pricing',
        'free_tier': 'No (paid only — but cheap, ~$5 lasts hundreds of emails)',
        'how_to_get': '1. Sign up at console.anthropic.com\n2. Add $5 credit\n3. Go to API Keys → Create Key\n4. Copy the sk-ant-... key',
        'models': [
            {'id': 'claude-haiku-4-5', 'name': 'Haiku 4.5 (fast, cheap)', 'recommended_for': 'bulk outreach'},
            {'id': 'claude-sonnet-4-6', 'name': 'Sonnet 4.6 (balanced)', 'recommended_for': 'most outreach'},
            {'id': 'claude-opus-4-7', 'name': 'Opus 4.7 (most powerful)', 'recommended_for': 'high-stakes prospects'},
        ],
        'default_model': 'claude-sonnet-4-6',
    },
    'cerebras': {
        'name': 'Cerebras Inference',
        'tier': 2,
        'tier_label': '⚡⚡⚡ Smart + Blazing Fast',
        'description': 'Llama 3.3 / Qwen / GPT-OSS at 2000+ tokens/sec. Free tier available. No local install needed.',
        'signup_url': 'https://cloud.cerebras.ai/?utm_source=aquelyst-hunter',
        'help_url': 'https://inference-docs.cerebras.ai/quickstart',
        'pricing_url': 'https://cloud.cerebras.ai/pricing',
        'free_tier': 'YES — Free tier with generous limits. Perfect for daily use.',
        'how_to_get': '1. Sign up free at cloud.cerebras.ai\n2. Go to API Keys → Create Key\n3. Copy the csk-... key',
        'models': [
            {'id': 'llama-3.3-70b', 'name': 'Llama 3.3 70B (most capable)', 'recommended_for': 'best quality'},
            {'id': 'llama3.1-8b', 'name': 'Llama 3.1 8B (fastest)', 'recommended_for': 'bulk speed'},
            {'id': 'qwen-3-32b', 'name': 'Qwen 3 32B', 'recommended_for': 'balanced'},
            {'id': 'gpt-oss-120b', 'name': 'GPT-OSS 120B', 'recommended_for': 'reasoning'},
        ],
        'default_model': 'llama-3.3-70b',
    },
    'openai': {
        'name': 'OpenAI (optional)',
        'tier': 2,
        'tier_label': '⚡⚡⚡ Smart',
        'description': 'GPT-4o / GPT-4o-mini. Optional alternative.',
        'signup_url': 'https://platform.openai.com/api-keys',
        'help_url': 'https://platform.openai.com/docs/quickstart',
        'pricing_url': 'https://openai.com/pricing',
        'free_tier': 'No (paid)',
        'how_to_get': '1. Sign up at platform.openai.com\n2. Add credit\n3. Create API key (sk-...)',
        'models': [
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini (cheap)', 'recommended_for': 'bulk'},
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'recommended_for': 'quality'},
        ],
        'default_model': 'gpt-4o-mini',
    }
}


def get_provider_info(provider):
    return PROVIDER_INFO.get(provider, {})


# ============================================================================
# Full provider catalog — used by Admin + Setup UIs to show all options,
# their tier (free/freemium/paid), where to sign up, and how the key looks.
# Order = priority Aqua should try them in (free first, premium last).
# ============================================================================
PROVIDER_CATALOG = [
    {
        'id': 'cerebras',
        'name': 'Cerebras',
        'tier': 'FREE',
        'tier_color': '#16a34a',
        'note': 'Llama / Qwen / GPT-OSS at 2000+ tok/sec. Generous free tier.',
        'signup_url': 'https://cloud.cerebras.ai',
        'keys_url': 'https://cloud.cerebras.ai/platform/keys',
        'key_prefix': 'csk-',
        'api_base': 'https://api.cerebras.ai/v1',
        'compat': 'openai',
    },
    {
        'id': 'groq',
        'name': 'Groq',
        'tier': 'FREE',
        'tier_color': '#16a34a',
        'note': 'Fastest inference on Earth. Free tier with daily rate limits.',
        'signup_url': 'https://console.groq.com',
        'keys_url': 'https://console.groq.com/keys',
        'key_prefix': 'gsk_',
        'api_base': 'https://api.groq.com/openai/v1',
        'compat': 'openai',
    },
    {
        'id': 'together',
        'name': 'Together AI',
        'tier': 'FREE',
        'tier_color': '#16a34a',
        'note': '$25 free credit on signup. Many open models.',
        'signup_url': 'https://api.together.xyz',
        'keys_url': 'https://api.together.xyz/settings/api-keys',
        'key_prefix': '',
        'api_base': 'https://api.together.xyz/v1',
        'compat': 'openai',
    },
    {
        'id': 'mistral',
        'name': 'Mistral',
        'tier': 'FREEMIUM',
        'tier_color': '#06b6d4',
        'note': 'European AI. Free tier with rate limits, paid scales up.',
        'signup_url': 'https://console.mistral.ai',
        'keys_url': 'https://console.mistral.ai/api-keys',
        'key_prefix': '',
        'api_base': 'https://api.mistral.ai/v1',
        'compat': 'openai',
    },
    {
        'id': 'cohere',
        'name': 'Cohere',
        'tier': 'FREE',
        'tier_color': '#16a34a',
        'note': 'Free tier with generous limits. Chat + reasoning.',
        'signup_url': 'https://cohere.com',
        'keys_url': 'https://dashboard.cohere.com/api-keys',
        'key_prefix': '',
        'api_base': 'https://api.cohere.ai/compatibility/v1',
        'compat': 'openai',
    },
    {
        'id': 'openrouter',
        'name': 'OpenRouter',
        'tier': 'PAID',
        'tier_color': '#f59e0b',
        'note': 'One key → access to every model. Cheap pay-as-you-go.',
        'signup_url': 'https://openrouter.ai',
        'keys_url': 'https://openrouter.ai/keys',
        'key_prefix': 'sk-or-',
        'api_base': 'https://openrouter.ai/api/v1',
        'compat': 'openai',
    },
    {
        'id': 'deepseek',
        'name': 'DeepSeek',
        'tier': 'PAID',
        'tier_color': '#f59e0b',
        'note': 'Powerful + extremely cheap. Strong reasoning model.',
        'signup_url': 'https://platform.deepseek.com',
        'keys_url': 'https://platform.deepseek.com/api_keys',
        'key_prefix': 'sk-',
        'api_base': 'https://api.deepseek.com/v1',
        'compat': 'openai',
    },
    {
        'id': 'openai',
        'name': 'OpenAI',
        'tier': 'PAID',
        'tier_color': '#f59e0b',
        'note': 'GPT-4o family. Industry baseline.',
        'signup_url': 'https://platform.openai.com',
        'keys_url': 'https://platform.openai.com/api-keys',
        'key_prefix': 'sk-',
        'api_base': 'https://api.openai.com/v1',
        'compat': 'openai',
    },
    {
        'id': 'claude',
        'name': 'Anthropic Claude',
        'tier': 'PAID',
        'tier_color': '#f59e0b',
        'note': 'Most powerful for nuanced sales chat. ~$5 = hundreds of replies.',
        'signup_url': 'https://console.anthropic.com',
        'keys_url': 'https://console.anthropic.com/settings/keys',
        'key_prefix': 'sk-ant-',
        'api_base': 'https://api.anthropic.com/v1',
        'compat': 'anthropic',
    },
]


def get_provider_meta(provider_id):
    for p in PROVIDER_CATALOG:
        if p['id'] == provider_id:
            return p
    return None


# Sample model per provider for connection-test calls — kept tiny + cheap.
_TEST_MODELS = {
    'cerebras': 'llama3.1-8b',
    'groq': 'llama-3.1-8b-instant',
    'together': 'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo',
    'mistral': 'mistral-small-latest',
    'cohere': 'command-r-08-2024',
    'openrouter': 'meta-llama/llama-3.1-8b-instruct:free',
    'deepseek': 'deepseek-chat',
    'openai': 'gpt-4o-mini',
    'claude': 'claude-haiku-4-5',
}


def test_provider_connection(provider_id, override_key=None):
    """Make a tiny live call to confirm the key works. Logs the result.
    Returns (ok: bool, message: str, model_used: str|None)."""
    import requests as _r
    try:
        import database
    except Exception:
        database = None

    meta = get_provider_meta(provider_id)
    if not meta:
        return False, f"Unknown provider {provider_id}", None

    api_key = override_key or get_key(provider_id)
    if not api_key:
        return False, "No key configured", None

    test_model = _TEST_MODELS.get(provider_id)
    base = meta['api_base']

    try:
        if meta.get('compat') == 'anthropic':
            r = _r.post(
                f"{base}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": test_model,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Say ok"}],
                },
                timeout=15,
            )
            if r.status_code == 200:
                if database:
                    database.provider_log_ok(provider_id, test_model)
                return True, "Connected ✅", test_model
            err = f"{r.status_code}: {r.text[:160]}"
            if database:
                database.provider_log_err(provider_id, err)
            return False, err, test_model
        else:
            # OpenAI-compatible
            r = _r.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": test_model,
                    "messages": [{"role": "user", "content": "Say ok"}],
                    "max_tokens": 10,
                },
                timeout=15,
            )
            if r.status_code == 200:
                if database:
                    database.provider_log_ok(provider_id, test_model)
                return True, "Connected ✅", test_model
            err = f"{r.status_code}: {r.text[:160]}"
            if database:
                database.provider_log_err(provider_id, err)
            return False, err, test_model
    except Exception as e:
        if database:
            database.provider_log_err(provider_id, str(e))
        return False, str(e), test_model
