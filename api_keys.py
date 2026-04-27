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
    """Save an API key for a provider."""
    data = _load_raw()
    data[provider] = base64.b64encode(api_key.encode()).decode()
    _save_raw(data)


def get_key(provider):
    """Retrieve an API key for a provider.

    Priority order:
    1. Streamlit secrets (cloud deployment) — `st.secrets["CEREBRAS_API_KEY"]` etc.
    2. Environment variables — `CEREBRAS_API_KEY`
    3. Local encoded file (api_keys.json) — for local dev installs
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

    # 3. Local file (legacy / dev mode)
    data = _load_raw()
    encoded = data.get(provider)
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded).decode()
    except Exception:
        return None


def delete_key(provider):
    """Remove an API key."""
    data = _load_raw()
    if provider in data:
        del data[provider]
        _save_raw(data)
        return True
    return False


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
