FROM python:3.12-slim

# System deps:
# - xvfb + x11vnc + novnc/websockify: the virtual display + web VNC chain
#   that lets Gradescope/PrairieLearn's interactive SSO login run on a
#   headless server. app/browser_login.py needs zero code changes for this -
#   Playwright's Chromium just respects the DISPLAY env var like any X11 app;
#   x11vnc shares that display over VNC, and websockify/novnc bridge that to
#   a plain web page (see docker/supervisord.conf and the "vnc" Caddy site).
# - supervisor: runs xvfb, x11vnc, novnc, and uvicorn together in one
#   container so DISPLAY is naturally shared between all of them.
# - curl: HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright's own runtime dependencies for Chromium (fonts, codecs, etc.) -
# --with-deps installs them via apt on top of what's already here.
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY scripts ./scripts
COPY docker/supervisord.conf /etc/supervisor/conf.d/prioriton.conf

ENV DISPLAY=:99 \
    PRIORITON_DB_PATH=/data/prioriton.db \
    PYTHONUNBUFFERED=1

# app.browser_login.PROFILE_ROOT resolves to <app package's parent>/.browser_profiles,
# i.e. /app/.browser_profiles here - docker-compose.yml mounts the persistent
# volume at this exact path; this just makes sure it (and /data, for the
# SQLite DB) exist before the very first run.
RUN mkdir -p /app/.browser_profiles /data

EXPOSE 8000 6080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/prioriton.conf"]
