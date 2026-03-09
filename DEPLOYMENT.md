# Deployment Guide — RUNWAY AI

This guide shows you how to run RUNWAY AI continuously in the cloud so it
scrapes data in the background, builds a growing database, and keeps your AI
API keys private.

All platforms listed below are **free or covered by the GitHub Student
Developer Pack**.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Environment variables you need to set](#environment-variables)
3. [Option A — Railway (recommended for beginners)](#option-a--railway)
4. [Option B — Render](#option-b--render)
5. [Option C — Fly.io](#option-c--flyio)
6. [Keeping the database after redeploys](#keeping-the-database)
7. [Testing that auth works](#testing-that-auth-works)
8. [FAQ](#faq)

---

## How it works

Set `SCRAPE_INTERVAL_MINUTES=120` (or any positive number) in your platform's
environment-variable dashboard.  When the app starts, a background thread
wakes up every N minutes and runs a full data ingest — saving news articles,
Reddit posts, trend scores, and forecasts to the SQLite database automatically.

Your AI API keys (`GROQ_API_KEY`, `OPENAI_API_KEY`) are set as **secret
environment variables** on the platform — they are never stored in the code
or in Git.

The `APP_API_KEY` variable protects the AI and data-ingest endpoints so no
one else can use up your API quota.

---

## Environment Variables

Set **all** of these through the platform's dashboard — never commit them to Git.

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Random string for Flask sessions. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `APP_API_KEY` | ✅ | Protects AI + ingest endpoints. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `GROQ_API_KEY` | ⭐ | Groq API key (free tier available at console.groq.com) |
| `OPENAI_API_KEY` | optional | OpenAI key (falls back to Groq → Ollama → rule-based) |
| `SCRAPE_INTERVAL_MINUTES` | ✅ | How often to auto-ingest data. `120` = every 2 hours |
| `DEBUG` | ✅ | Set to `False` in production |
| `CACHE_TTL` | optional | Cache lifetime in seconds (default `300`) |

---

## Option A — Railway

Railway gives GitHub Student accounts **$5/month free credit** (enough for a
small always-on app).

### Step 1 — Create a Railway account

1. Go to <https://railway.app> and click **Login with GitHub**.
2. Verify you are on the Student plan: <https://railway.app/account/plans>
   (use your GitHub Student Developer Pack).

### Step 2 — Deploy the app

1. In the Railway dashboard click **New Project → Deploy from GitHub repo**.
2. Authorise Railway to access your GitHub account, then select the
   `trendforecasting` repository.
3. Railway auto-detects a Python/Flask project and creates a deployment.

### Step 3 — Set environment variables

1. Click the deployed service → **Variables** tab.
2. Click **New Variable** for each entry in the table above.
3. Example values:
   ```
   SECRET_KEY=<output of python -c "import secrets; print(secrets.token_hex(32))">
   APP_API_KEY=<output of python -c "import secrets; print(secrets.token_urlsafe(32))">
   GROQ_API_KEY=gsk_xxxxxxxxxxxx
   SCRAPE_INTERVAL_MINUTES=120
   DEBUG=False
   ```
4. Railway redeploys automatically after you save.

### Step 4 — Add a start command (if needed)

In **Settings → Deploy → Start Command**, set:
```
gunicorn "app:create_app()" --workers 2 --timeout 120
```

### Step 5 — Add a persistent volume for the database

The SQLite database lives in `app/data/fashion_trends.db`.  By default
Railway's filesystem is ephemeral — add a volume so data survives redeploys.

1. Click your service → **Volumes** tab → **Add Volume**.
2. Mount path: `/app/app/data`  
   (`/app` is the container working directory; the second `app` is the
   Python package directory where the SQLite database is created.)
3. Railway will attach a persistent disk at that path.

### Step 6 — Verify

Open the Railway-provided URL (e.g. `https://yourapp.up.railway.app`).
The dashboard loads, and the scheduler starts ingesting data in the
background every 2 hours.

---

## Option B — Render

Render's **free tier** is sufficient for a personal project (spins down after
inactivity; upgrade to paid to keep it always-on).

### Step 1 — Create a Render account

Go to <https://render.com> and sign in with GitHub.

### Step 2 — Create a Web Service

1. Click **New → Web Service**.
2. Connect your `trendforecasting` GitHub repository.
3. **Runtime**: Python 3
4. **Build Command**: `pip install -r requirements.txt`
5. **Start Command**: `gunicorn "app:create_app()" --workers 2 --timeout 120`

### Step 3 — Set environment variables

In the **Environment** tab add all variables from the table above.

### Step 4 — Add a persistent disk for the database

1. In your service go to **Disks → Add Disk**.
2. **Mount Path**: `/app/app/data`  
   (`/app` is the container working directory; the second `app` is the
   Python package directory where the SQLite database is created.)
3. This keeps the SQLite database between redeploys.

### Step 5 — Deploy

Click **Manual Deploy → Deploy Latest Commit**.  The app will be live at
`https://yourapp.onrender.com`.

---

## Option C — Fly.io

Fly.io has a **free allowance** (3 shared-CPU VMs, 256 MB RAM each).

### Step 1 — Install the Fly CLI

```bash
# macOS / Linux
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex
```

### Step 2 — Login and initialise

```bash
fly auth login
cd trendforecasting
fly launch          # accept defaults; choose a region close to you
```

This creates a `fly.toml` in the project root.

### Step 3 — Set secrets (environment variables)

```bash
fly secrets set \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  APP_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  GROQ_API_KEY="gsk_xxxxxxxxxxxx" \
  SCRAPE_INTERVAL_MINUTES="120" \
  DEBUG="False"
```

Secrets are **encrypted at rest** and never appear in logs or the UI.

### Step 4 — Add a persistent volume for the database

```bash
fly volumes create runway_data --size 1   # 1 GB, free tier allows up to 3 GB
```

Add the volume mount to `fly.toml`:

```toml
[mounts]
  source      = "runway_data"
  destination = "/app/app/data"
```

### Step 5 — Deploy

```bash
fly deploy
```

The app is live at `https://yourapp.fly.dev`.

---

## Keeping the database after redeploys

All three platforms support **persistent volumes** (instructions above).
Without a volume the SQLite file is recreated empty on every redeploy.

If your platform does not support volumes, consider switching the database
backend to a hosted database (e.g. PostgreSQL via Railway or Render's free
PostgreSQL add-on).  That change requires updating `app/database.py` to use
SQLAlchemy instead of sqlite3 — outside the scope of this guide.

---

## Testing that auth works

After deploying, verify that AI endpoints are protected:

```bash
# ❌ Should return 401 Unauthorized
curl https://yourapp.up.railway.app/api/ai/overview

# ✅ Should return the AI analysis JSON
curl -H "Authorization: Bearer YOUR_APP_API_KEY" \
     https://yourapp.up.railway.app/api/ai/overview
```

In the browser dashboard, click the **🔑 API Key** button in the top-right
corner and paste your `APP_API_KEY` — it is stored in your browser's
`localStorage` and sent automatically with every AI / ingest request.

---

## FAQ

**Q: Where do I get a free Groq API key?**  
A: Sign up at <https://console.groq.com> — the free tier is generous for
personal use (check <https://console.groq.com/docs/rate-limits> for current
limits, as they may change over time).

**Q: What happens if `APP_API_KEY` is not set?**  
A: The server runs in open (dev) mode — AI endpoints are accessible without
a key.  Always set `APP_API_KEY` on a public deployment.

**Q: How do I increase the scraping frequency?**  
A: Lower `SCRAPE_INTERVAL_MINUTES`.  A value of `60` ingests every hour.
Be careful not to exceed rate limits on data sources (Google Trends in
particular rate-limits aggressive polling).

**Q: The database is growing too large.  How do I trim it?**  
A: Connect to the SQLite file and delete old rows, for example:
```sql
DELETE FROM fashion_news   WHERE saved_at < datetime('now', '-90 days');
DELETE FROM reddit_posts   WHERE saved_at < datetime('now', '-90 days');
DELETE FROM trend_snapshots WHERE snapshot_date < date('now', '-180 days');
VACUUM;
```

**Q: Can I run this locally for free with no API keys?**  
A: Yes.  The app falls back to rule-based analysis when no API keys are
configured.  Set `APP_API_KEY=` (empty) in `.env` for open dev mode.
