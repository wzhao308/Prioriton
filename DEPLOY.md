# Deploying Prioriton to a VPS

Docker Compose + Caddy, on any VPS with Docker installed. Two containers:
`backend` (the FastAPI app, plus a virtual display + web VNC so Gradescope/
PrairieLearn's interactive SSO login works without a local GUI) and `caddy`
(serves the built frontend, reverse-proxies to the backend/noVNC, and
handles HTTPS automatically via Let's Encrypt). See `docker-compose.yml`,
`backend/Dockerfile`, `backend/docker/supervisord.conf`,
`frontend/Dockerfile`, and `frontend/Caddyfile` for exactly what each piece
does - every file has comments explaining its role.

**The only access control here is HTTP Basic Auth**, applied to all three
subdomains by Caddy. There's no separate login inside the app itself - keep
the password real.

## 1. Provision the server

Any VPS with a public IP and Docker + the Compose plugin installed works
(DigitalOcean, Linode, a home server with port forwarding, etc.). 1 vCPU /
1-2GB RAM is enough - Chromium via Playwright is the heaviest thing running,
and it only runs during a sync or an interactive login, not continuously.

```
curl -fsSL https://get.docker.com | sh
```

## 2. Point DNS at it

Create three A records, all pointing at the server's public IP:

```
app.<yourdomain>
api.<yourdomain>
vnc.<yourdomain>
```

Caddy requests a Let's Encrypt certificate for each on first request - this
needs ports 80 and 443 reachable from the internet (Let's Encrypt's HTTP-01
challenge) and the DNS records already resolving, or it'll fail to issue.

## 3. Configure secrets

```
cp .env.production.example .env
```

Fill in `.env`:
- `DOMAIN`, `ACME_EMAIL`
- `BASIC_AUTH_USER` + `BASIC_AUTH_HASH` - generate the hash with:
  ```
  docker run --rm caddy:2-alpine caddy hash-password --plaintext 'your-password-here'
  ```
  **Double every `$` to `$$` when you paste it into `.env`** (e.g.
  `$2a$14$abc...` becomes `$$2a$$14$$abc...`) - Docker Compose treats a bare
  `$` in a `.env` file as its own variable syntax and will silently mangle
  the hash otherwise, breaking Basic Auth with no obvious error. Verified
  this exact failure mode while building this deploy setup.
- `PRIORITON_SECRET_KEY` - **required** here (unlike local dev, where it
  auto-provisions into the OS keyring - a container has no keyring, so
  `app.security.get_or_create_secret_key()` falls back to requiring this
  explicitly):
  ```
  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- `ANTHROPIC_API_KEY` - optional, only needed for AI Recommendations.

## 4. Bring it up

```
docker compose build
docker compose up -d
docker compose logs -f
```

Check `https://api.<yourdomain>/health` returns `{"status":"ok"}` (prompts
for the Basic Auth credentials first) and `https://app.<yourdomain>` loads
the app.

## 5. Connect Canvas / Gradescope / PrairieLearn

- **Canvas** works immediately - it's just a token, no browser needed.
- **Gradescope / PrairieLearn**: click Connect in Settings as usual. Instead
  of a local Chromium window opening, go to `https://vnc.<yourdomain>` in a
  browser tab (same Basic Auth) - that's a live view of the exact same
  browser window, running headless-in-appearance-only inside the container's
  virtual display. Complete SSO/Duo there. The connection then auto-detects
  success and closes, exactly as it does locally. You'll only need to revisit
  `vnc.<yourdomain>` again if a session actually expires later.

## Operating notes

- **Never scale the backend past one worker or one replica.** APScheduler's
  background jobs and the login-tracking locks in `app/browser_login.py` are
  process-global state - a second worker/replica would duplicate scheduled
  syncs and race on login serialization. `supervisord.conf` already pins
  `--workers 1`; don't change that, and don't add `deploy.replicas > 1` to
  the `backend` service.
- **Data lives in named Docker volumes** (`db_data`, `browser_profiles`,
  `caddy_data`/`caddy_config`), not the container filesystem, so
  `docker compose down && docker compose up -d` (without `-v`) is safe and
  keeps everything. `docker compose down -v` deletes it all, including your
  synced courses/grades and the browser session cookies - only do that
  deliberately.
- **Updating**: `git pull && docker compose build && docker compose up -d`.
  The SQLite DB auto-migrates on startup (`app.db.init_db`), same as local dev.
- **Backups**: `docker run --rm -v prioriton_db_data:/data -v "$PWD":/backup alpine tar czf /backup/prioriton-db-backup.tgz -C /data .`
  (adjust the volume name if your Compose project directory isn't named
  `prioriton` - check with `docker volume ls`).
