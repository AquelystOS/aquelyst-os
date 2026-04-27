# AqueLyst OS

Internal sales operating system for the AqueLyst team.

**Live URL:** `https://aquelyst-os.streamlit.app` (after deploy)

## What it does

- **Autopilot** — autonomously discovers horse barns, equestrian centers, kennels, marinas, etc., across 5 product lines (Duo Equine, Pets, SpillMaster, AMR, HouseHold)
- **CRM** — tracks every prospect with AI-scored quality, sales-stage progress, full conversation threads
- **Aqua AI** — NEPQ-trained sales assistant; reads inbound emails, classifies intent, drafts NEPQ-aligned replies, escalates pricing >$5k or angry customers to humans
- **Multi-tenant team** — Joseph, Erika, Dani, Debra, Wyatt — each connects their own email and the bot signs as them
- **Audit log** — every transaction logged with second-level timestamps + hash chain for tamper-evidence

## Stack

- Streamlit 1.32+ (UI)
- SQLite locally → Postgres in cloud (Phase B)
- Cerebras AI (qwen-3-235b primary) + optional Claude/OpenAI fallback
- IMAP/SMTP for email
- Web3Forms webhook for inbound leads

## Deployment

See [DEPLOY.md](./DEPLOY.md) for step-by-step Streamlit Cloud setup.

## Local dev

```bash
git clone https://github.com/YOUR-USERNAME/aquelyst-os.git
cd aquelyst-os
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./launch.sh
```

App opens at http://localhost:8501

## Team setup (after deploy)

1. Visit the app URL
2. Enter team password (set in Streamlit secrets as `TEAM_PASSWORD`)
3. Setup → 📧 Email → enter YOUR email + create App Password
4. Done — emails sign as you

## License

Proprietary · AqueLyst LLC
