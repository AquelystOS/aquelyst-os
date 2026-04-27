# Deploying AqueLyst OS to Streamlit Cloud

This guide gets your team a public URL like `https://aquelyst-os.streamlit.app` in about 30 minutes. Free.

## Phase A — get something deployed today (this guide)

What you'll have at the end:
- ✅ Public URL the team can visit
- ✅ Password protected
- ✅ Cerebras AI configured
- ✅ Web3Forms wired up
- ⚠️ Database resets when the container sleeps (Phase B fixes this — move to Supabase Postgres)
- ⚠️ Background bots only run when the page is open (Phase C fixes this — separate worker)

---

## Step 1 — Create a free GitHub account (5 min)

If you already have one, skip.

1. Go to https://github.com/signup
2. Use `joseph@aquelyst.com`
3. Verify email

---

## Step 2 — Create a private GitHub repo (3 min)

1. Click the **+** icon top-right → **New repository**
2. Repository name: `aquelyst-os`
3. Set to **Private** (important — your code stays internal)
4. Do NOT add README/license/.gitignore (we have our own)
5. Click **Create repository**
6. **Copy the repository URL** (looks like `https://github.com/yourname/aquelyst-os.git`)

---

## Step 3 — Push your code (5 min)

Open Terminal on your Mac and run:

```bash
cd /Users/debraleblang/Desktop/AqueLyst-Hunter

# First time only — initialize git
git init
git branch -M main

# Connect to your GitHub repo (paste your repo URL)
git remote add origin https://github.com/YOUR-USERNAME/aquelyst-os.git

# Stage everything respecting .gitignore (secrets won't be committed)
git add .

# First commit
git commit -m "Initial AqueLyst OS deploy"

# Push to GitHub
git push -u origin main
```

If GitHub asks for password — you need a **personal access token**, not your password:
1. Go to https://github.com/settings/tokens/new
2. Note: "AqueLyst OS deploy"
3. Expiration: 90 days
4. Check the `repo` scope
5. Click **Generate token**
6. Copy the token (starts with `ghp_...`)
7. When git asks for "password", paste the token

---

## Step 4 — Deploy to Streamlit Cloud (10 min)

1. Go to https://share.streamlit.io
2. Click **Sign in with GitHub**
3. Click **Create app** (top right)
4. Select **Deploy a public app from GitHub**
5. Repository: `YOUR-USERNAME/aquelyst-os`
6. Branch: `main`
7. Main file path: `app.py`
8. App URL: `aquelyst-os` (gives you `https://aquelyst-os.streamlit.app`)
9. Click **Advanced settings** → **Python version** → 3.11
10. Click **Deploy!**

The first deploy takes ~5 minutes. Watch the logs.

---

## Step 5 — Configure secrets (5 min)

Once deployed, the app loads but won't work yet — we need to add secrets.

1. In Streamlit Cloud, click your app → **⋮** menu → **Settings**
2. Click **Secrets**
3. Paste this in (fill in your real values):

```toml
TEAM_PASSWORD = "Pick-a-strong-password-here"

# Cerebras AI key (free at cloud.cerebras.ai)
CEREBRAS_API_KEY = "csk-your-real-key-here"

# Optional: Claude
# CLAUDE_API_KEY = "sk-ant-..."

# Web3Forms (already wired)
WEB3FORMS_KEY = "993ac019-1740-49b2-866c-e1fb4cf4aa15"

# Tells the app it's running in cloud mode
CLOUD_DEPLOYMENT = true
```

4. Click **Save**
5. The app auto-reboots with the new secrets

---

## Step 6 — Test it (2 min)

1. Visit `https://aquelyst-os.streamlit.app`
2. You should see the **🐴 AqueLyst OS** password screen
3. Enter the team password
4. App loads → go to Setup → Email and connect your email
5. Done ✅

---

## Step 7 — Share with the team (1 min)

Send this to Erika, Dani, Debra, and Wyatt:

> Hey team — AqueLyst OS is live at:
>
> 🔗 https://aquelyst-os.streamlit.app
> 🔑 Password: [the TEAM_PASSWORD you set]
>
> First time you log in:
> 1. Go to ⚙️ Setup → 📧 Email
> 2. Enter YOUR email + create an App Password
> 3. Connect it
>
> The app remembers your email so you sign emails as YOU.
>
> Questions → DM me.

---

## What's still missing (Phase B + C)

### Phase B — Persistent database (next week, ~4 hours)
Right now SQLite resets when the container sleeps (every 7 days of inactivity, or randomly).

**Fix:** Move the database to Supabase Postgres (free tier).

Steps when you're ready:
1. Sign up free at https://supabase.com
2. Create a new project
3. Get the Postgres connection string
4. Add to Streamlit secrets as `DATABASE_URL`
5. We'll write a migration script to copy SQLite data → Postgres
6. Update `database.py` to use Postgres instead

### Phase C — 24/7 background bots (later, ~3 hours)
Streamlit Cloud sleeps containers, so Autopilot/Watcher/Engagement only run while someone's on the page.

**Fix:** Run a worker on your Mac (or a $5 VPS) that:
- Connects to the same Supabase Postgres
- Runs the bots 24/7
- Pushes data the cloud app reads

Or use:
- **GitHub Actions** (free) to schedule cron jobs that run the bots every 15 min
- **Railway** ($5/mo) for a separate always-on Python service

We'll cover this in Phase C.

---

## Troubleshooting

**"App can't reach Cerebras"**
- Check the `CEREBRAS_API_KEY` secret is correct (no quotes around the key, no spaces)

**"Page won't load / 502 error"**
- Streamlit Cloud is rebooting. Wait 30 seconds and refresh.

**"My data disappeared"**
- Container slept and SQLite reset. This is the Phase B issue. Until then, export your customers to CSV regularly via the Customers tab.

**"Background bots aren't running"**
- Expected on cloud. Open the page → click the bot toggle → it runs while you're on the page.

**"Can't push to GitHub"**
- Use a personal access token instead of password (Step 3)

---

## Costs

| Service | Cost |
|---|---|
| Streamlit Cloud Community | $0/mo |
| Cerebras (free tier) | $0/mo |
| Web3Forms (free tier) | $0/mo |
| GitHub (private repos free) | $0/mo |
| **Total** | **$0/mo** |

Phase B adds:
- Supabase free tier (500MB) | $0/mo

Phase C optional:
- Railway worker | $5/mo
- OR keep your Mac on as worker | $0
