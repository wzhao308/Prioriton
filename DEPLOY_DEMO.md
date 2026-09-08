# Deploying a public demo

For letting people see the app working - not for real use with a real
account. One container, `Dockerfile.demo` (built from the project root, not
`backend/`), no Basic Auth (it's meant to be public), no Xvfb/noVNC (Canvas/
Gradescope/PrairieLearn connecting is disabled entirely in demo mode - see
`app/config.py`'s `demo_mode` and `app/routers/integrations.py`). If you want
a deployment real students would actually use with their real accounts, see
[DEPLOY.md](DEPLOY.md) instead - that's a different, heavier setup.

**What demo mode actually does** (all in `app/demo.py` and the `demo_mode`
checks in `app/routers/integrations.py` / `app/routers/recommendations.py`):
- Seeds ~2 weeks of realistic sample data (4 courses, graded assignments,
  study sessions) on first boot if the database is empty.
- Every feature works and is fully interactive - starting timers, marking
  tasks done, adding classes, everything - **except** connecting a real
  Canvas/Gradescope/PrairieLearn account (403) and generating a new AI
  recommendation on demand (403, since that's a real, billable Anthropic API
  call anyone could otherwise trigger repeatedly on a shared public
  instance). The Recommendations page ships with one hand-written example
  instead - grounded in the exact seeded numbers, in the same voice the real
  system uses.
- **Resets itself** every `PRIORITON_DEMO_RESET_INTERVAL_HOURS` (default 3) -
  wipes everything and reseeds fresh, so one visitor's changes don't linger
  for the next. This is also why persistent storage is optional here, unlike
  the real VPS deploy: the data is disposable by design.

Verified locally before writing this: built and ran `Dockerfile.demo`,
confirmed the seeded data appears, both `Connect Canvas` and `Generate now`
correctly return 403, interactive actions (starting a timer, marking a task
done) work normally, and every frontend page loads correctly through the
`/api`-prefixed routing this image uses (a real bug - `/courses`,
`/settings`, and `/recommendations` are both frontend pages and real API
paths, so a plain single-origin setup made the browser hit the raw API JSON
instead of the page - fixed by moving the API behind `/api` whenever a
frontend build is baked into the image; see `app/main.py`).

## Required environment variable

Only one thing is truly required beyond `PRIORITON_DEMO_MODE=true` (already
set by `fly.toml`/the Dockerfile):

```
PRIORITON_SECRET_KEY=<generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

There's no OS keyring inside a container, so this is required, not optional
(same reasoning as the real VPS deploy - see `app/security.py`). Since demo
mode never stores anything sensitive (no real tokens, ever), the exact value
doesn't matter much - it just needs to be *a* valid Fernet key so the app can
start.

`ANTHROPIC_API_KEY` is never needed here - live generation is disabled.

## Fly.io

```
brew install flyctl   # or see fly.io/docs/flyctl/install
flyctl auth login
flyctl launch --no-deploy   # detects fly.toml; rename the app if "prioriton-demo" is taken
flyctl secrets set PRIORITON_SECRET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
flyctl deploy
```

Your app is live at `https://<app-name>.fly.dev` with HTTPS already handled.

## Railway

1. New Project → Deploy from GitHub repo → pick this repo.
2. Settings → set the Dockerfile path to `Dockerfile.demo` and the build
   context to the repo root (not `backend/`).
3. Variables → add `PRIORITON_SECRET_KEY` (generate as above) and
   `PRIORITON_DEMO_MODE=true`.
4. Deploy. Railway assigns a public `*.up.railway.app` URL with HTTPS
   automatically - Settings → Networking → Generate Domain if it doesn't by default.

## Render

1. New → Web Service → connect this repo.
2. Runtime: Docker. Dockerfile path: `Dockerfile.demo`. Docker build context:
   `.` (repo root).
3. Environment → add `PRIORITON_SECRET_KEY` and `PRIORITON_DEMO_MODE=true`.
4. Health check path: `/health`.
5. Render's free tier has no persistent disk - every deploy/restart wipes
   the container filesystem. For this demo that's fine (it's designed to
   reset anyway); just know a restart means an *immediate* reset rather than
   waiting for the scheduled one.

## Optional: a real persistent volume

None of the platforms above strictly need one here (demo data is disposable
by design), but if you'd rather the seeded data survive a restart between
scheduled resets: mount a volume at `/data` (where `PRIORITON_DB_PATH`
already points - see the Dockerfile) - Fly: `fly volumes create` + a
`[mounts]` block in `fly.toml`; Railway/Render: their respective Volume
settings pointed at `/data`.

## Tuning the reset interval

```
PRIORITON_DEMO_RESET_INTERVAL_HOURS=3   # default
```

Lower it if you expect heavy traffic and want a cleaner slate more often;
raise it if you'd rather a visitor's own changes stick around longer during
a demo session.
