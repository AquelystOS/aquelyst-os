"""Outreach message generation for AqueLyst Hunter.

Backwards-compatible wrapper around ai_providers (the new multi-tier router).
Templates remain the final fallback when no AI provider is available.
"""

import requests
import json

OLLAMA_BASE_URL = "http://localhost:11434"

# New: import the AI router for tiered generation
try:
    import ai_providers
    AI_ROUTER_AVAILABLE = True
except ImportError:
    AI_ROUTER_AVAILABLE = False

# Message templates for when Ollama is unavailable
EMAIL_TEMPLATES = {
    "cold_email": """Subject: Proven Solution for {business_type} Odor & Flies - {days_free} Day Trial

Hi {contact_name},

I work with {business_type}s and barns struggling with {problem_area}.

Most solutions mask odor. {company_name} actually eliminates it at the source—by neutralizing ammonia and reducing fly-attracting compounds.

Customers typically see results in the first week. We offer a 7-day barn trial at no cost.

Worth a quick call?

{your_name}
{phone}
""",
    "reply_to_inbound": """Hi {contact_name},

Thanks for reaching out about {product_name}.

You mentioned {pain_point}—that's exactly what we solve. Our customers in {business_type} see {benefit} within the first week.

I'd love to walk you through a 7-day trial. No obligation. When is a good time for a 15-minute call?

Looking forward,
{your_name}
{phone}
""",
    "instagram_dm": """Hey {contact_name}! 👋

Saw your {business_type} and thought of you.

Managing odor and flies in barns is brutal. We've helped {business_type}s like yours eliminate {problem_area} in the first week.

7-day trial. No risk.

Interested in more info?
""",
    "facebook_message": """Hi {contact_name},

Quick question—are you still dealing with odor and flies at {business_name}?

There's a proven solution that works in {business_type} facilities. I think it could help.

Happy to send details or set up a quick trial.

{your_name}
""",
    "phone_opener": """Hi {contact_name}, this is {your_name} from {company_name}.

The reason for my call is I work with {business_type}s dealing with odor and flies, and I think {business_name} might benefit from what we offer.

Do you have 30 seconds?
""",
    "follow_up_education": """Subject: How {business_type}s Eliminate Barn Odor (Not Just Mask It)

Hi {contact_name},

Since we connected, I wanted to share how our solution works:

Most barn odor comes from ammonia in urine and manure. That ammonia attracts flies.

Our product neutralizes ammonia at the source. No fragrances. No chemicals. Just results.

Check it out: [link to case study or proof]

Questions? Reply or call anytime.

{your_name}
""",
    "trial_offer": """Subject: Your 7-Day {business_type} Odor Trial – No Cost

Hi {contact_name},

Ready to see what {product_name} can do?

We'll ship a trial kit to {business_name}. You test it for 7 days on your stalls/trailers. No charge. No obligation to buy.

Most customers see flies drop and smell improve within days.

Ready to start?

{your_name}
{phone}
""",
    "social_proof": """Subject: How {similar_business_type} Used {product_name} to Fix Odor & Flies

Hi {contact_name},

I work with a lot of {business_type}s. One of our best clients is a {similar_business_type} in {state} managing {number_of_stalls} stalls.

They were where you are—odor, flies, constant struggle.

After one week with {product_name}, they said it was the biggest improvement they'd made in years.

Worth a conversation?

{your_name}
{phone}
""",
    "objection_budget": """I hear you. Budget is real.

Here's the thing: a 7-day trial costs nothing. If it works (and it usually does), the payoff is huge—better horse health, fewer flies, happier staff.

Most customers tell us the product pays for itself in reduced fly treatments and bedding costs within a month.

Let's do the trial. If it doesn't work, zero cost. If it does, you've solved a big problem.

{your_name}
""",
    "objection_timing": """Totally understand. Timing can be tricky.

The best time to solve an odor problem is before it gets worse. Summer fly season is coming (or here).

One week trial. No pressure. You'll know in days if it's worth continuing.

When can we get started?

{your_name}
""",
}

FOLLOW_UP_SEQUENCE = [
    {
        "day": 0,
        "type": "initial_contact",
        "name": "Initial Contact",
        "template": "cold_email"
    },
    {
        "day": 3,
        "type": "education",
        "name": "Education Follow-up",
        "template": "follow_up_education"
    },
    {
        "day": 7,
        "type": "trial_offer",
        "name": "Barn Trial Offer",
        "template": "trial_offer"
    },
    {
        "day": 14,
        "type": "social_proof",
        "name": "Social Proof / Testimonial",
        "template": "social_proof"
    },
    {
        "day": 21,
        "type": "seasonal",
        "name": "Seasonal Reminder (Fly/Ammonia)",
        "template": "follow_up_education"
    },
    {
        "day": 35,
        "type": "final",
        "name": "Final Check-in",
        "template": "cold_email"
    }
]


def check_ollama_available():
    """Check if Ollama is running and available."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except (requests.RequestException, requests.ConnectionError):
        return False


def get_available_models():
    """Get list of available Ollama models."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [model['name'] for model in data.get('models', [])]
            return models if models else ["mistral", "llama2"]
        return ["mistral", "llama2"]
    except:
        return ["mistral", "llama2"]


def generate_with_ollama(prompt, model="mistral"):
    """Generate message using Ollama local LLM."""
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('response', '').strip()
    except Exception as e:
        print(f"Ollama error: {e}")
    return None


def generate_outreach(message_type, lead_data, use_ollama=False, model="mistral"):
    """
    Generate outreach message.
    Falls back to templates if Ollama unavailable or use_ollama=False.
    """
    contact_name = lead_data.get('contact_name', 'there')
    business_name = lead_data.get('business_name', 'your business')
    business_type = lead_data.get('business_type', 'barn')
    email = lead_data.get('email', '')
    phone = lead_data.get('phone', '')
    message = lead_data.get('message', '')
    pain = lead_data.get('pain_hypothesis', 'odor and flies')
    state = lead_data.get('state', 'your area')
    city = lead_data.get('city', '')

    # Try Ollama first if requested and available
    if use_ollama and check_ollama_available():
        prompt = build_ollama_prompt(message_type, lead_data)
        result = generate_with_ollama(prompt, model)
        if result:
            return {
                "subject": f"Outreach to {contact_name}",
                "content": result,
                "source": "ollama"
            }

    # Fall back to templates
    template = EMAIL_TEMPLATES.get(message_type, EMAIL_TEMPLATES.get("cold_email"))

    # Format template with available data
    format_data = {
        "contact_name": contact_name.split()[0] if contact_name else "there",
        "business_name": business_name,
        "business_type": business_type,
        "problem_area": pain.lower() if pain else "odor and flies",
        "days_free": "7",
        "company_name": "AqueLyst",
        "product_name": "Duo Equine",
        "benefit": "results",
        "pain_point": pain.lower() if pain else "odor",
        "state": state,
        "similar_business_type": business_type,
        "number_of_stalls": lead_data.get('number_of_stalls', '10'),
        "your_name": "Joseph",
        "phone": "joseph@aquelyst.com",
    }

    try:
        content = template.format(**format_data)
    except KeyError:
        content = template

    subject_map = {
        "cold_email": f"Proven Solution for {business_type} Odor & Flies",
        "reply_to_inbound": f"Re: {business_name} — Odor Solution",
        "instagram_dm": f"Hey {contact_name}",
        "facebook_message": f"Message from AqueLyst",
        "phone_opener": f"Quick call for {contact_name}",
        "follow_up_education": "How Barns Eliminate Odor (Not Just Mask It)",
        "trial_offer": f"Your Free 7-Day Odor Trial",
        "social_proof": f"How Similar Facilities Fixed Their Odor Problem",
        "objection_budget": "About That Budget Concern",
        "objection_timing": "About That Timing",
    }

    subject = subject_map.get(message_type, "Message from AqueLyst")

    return {
        "subject": subject,
        "content": content,
        "source": "template"
    }


def generate_smart(message_type, lead_data, provider='auto', model=None):
    """
    Smart generation using the tiered AI router.

    Tries: Claude → Cerebras → OpenAI → Ollama → Templates
    (or whichever provider is specified)

    Returns dict: {subject, content, source, tier, tier_label, model}
    """
    if not AI_ROUTER_AVAILABLE:
        # Old templates path
        result = generate_outreach(message_type, lead_data, use_ollama=False)
        result['tier'] = 4
        result['tier_label'] = '⚡ Templates'
        result['model'] = 'fallback'
        return result

    result = ai_providers.generate(message_type, lead_data, provider=provider, model=model)
    text = result.get('text', '')

    # Try to extract subject from "Subject: ..." prefix
    subject, body = ai_providers.parse_subject_from_text(text)

    if not subject:
        # Generate a fallback subject
        subject_map = {
            "cold_email": f"Quick question about {lead_data.get('business_name', 'your barn')}",
            "reply_to_inbound": f"Re: {lead_data.get('business_name', 'your inquiry')}",
            "instagram_dm": "",
            "facebook_message": f"Hi from AqueLyst",
            "phone_opener": "",
            "follow_up_education": "How barn odor actually works",
            "trial_offer": "Your free 7-day Duo Equine trial",
            "social_proof": "How a similar facility solved this",
            "objection_budget": "Re: budget question",
            "objection_timing": "Re: timing thoughts",
        }
        subject = subject_map.get(message_type, "Message from AqueLyst")
        body = text

    return {
        'subject': subject,
        'content': body,
        'source': result.get('source', 'unknown'),
        'tier': result.get('tier', 4),
        'tier_label': result.get('tier_label', '⚡ Unknown'),
        'model': result.get('model', '')
    }


def build_ollama_prompt(message_type, lead_data):
    """Build a prompt for Ollama to generate personalized outreach."""
    contact_name = lead_data.get('contact_name', 'there')
    business_name = lead_data.get('business_name', '')
    business_type = lead_data.get('business_type', '')
    pain = lead_data.get('pain_hypothesis', '')
    message = lead_data.get('message', '')

    prompts = {
        "cold_email": f"""Write a professional but friendly cold email to {contact_name} at {business_name} ({business_type}).

They mentioned: {pain} {message}

Our product (Duo Equine) eliminates odor and flies in barns by neutralizing ammonia at the source.

Keep it short (5-7 sentences). Offer a 7-day trial with no obligation. End with a call-to-action.
Professional tone. No sales jargon.

Email:""",

        "reply_to_inbound": f"""Write a reply email to {contact_name}'s inquiry about our barn odor solution.

They're concerned about: {pain}

Acknowledge their concern, explain how our solution works (neutralizes ammonia), offer a quick call or trial.
Short and friendly. Professional.

Email:""",

        "instagram_dm": f"""Write a short, friendly Instagram DM to {contact_name} at {business_name}.

They run a {business_type}. We help with {pain}.

Keep it 2-3 sentences. Casual tone. Mention a free trial. Ask if they're interested.

DM:""",

        "follow_up_education": f"""Write an educational follow-up email to {contact_name} explaining how barn odor actually works.

Key points:
- Most barn odor comes from ammonia in urine/manure
- Ammonia attracts flies
- Our product neutralizes ammonia at the source

Keep it informative, not salesy. 4-5 sentences. End with an invite to chat.

Email:""",

        "trial_offer": f"""Write an email to {contact_name} offering a free 7-day trial of our barn odor solution.

Include:
- No cost
- No obligation
- Ship trial kit to their facility
- Most customers see results in days

Professional, direct, confident. 4-5 sentences.

Email:""",

        "social_proof": f"""Write an email to {contact_name} with a brief customer story.

Make up a realistic example of another {business_type} (not their facility) that solved odor and fly problems with our product.

Keep it short and credible. 5-6 sentences. End with an invite to discuss.

Email:""",

        "phone_opener": f"""Write a 20-30 second phone script opener for {contact_name} at {business_name}.

You're calling because they're a {business_type} and we help with {pain}.

Be confident, friendly, ask for 30 seconds of their time.

Script:""",
    }

    return prompts.get(message_type, "Generate a friendly outreach message.")


def get_follow_up_sequence():
    """Return the standard 7-touch follow-up sequence."""
    return FOLLOW_UP_SEQUENCE
