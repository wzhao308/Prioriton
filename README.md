# Prioriton

Know what to work on next. Prioriton tracks your assignments, your study
time, and your grades, and turns a week of that into AI recommendations
grounded in your own numbers - not generic study advice.

## Features

1. **Assignment Tracker** - syncs due dates and grades automatically from
   Canvas (official REST API), and Gradescope/PrairieLearn (one-time
   interactive browser login, then reused for periodic syncs). This started
   as my other project, ManaPeer's, sync engine - Prioriton is the
   culmination of it: every ManaPeer feature (Home's due-date buckets, the
   month Calendar, per-class Courses to-do/done boards, in-app reminders) is
   now folded into this single app, not split across two. Connections
   themselves live in Settings. You can also skip syncing entirely and add
   classes by hand (see below).
2. **Study Time Tracker** - pick a class, hit start/stop, and Prioriton logs
   the session. Weekly hours per course are computed automatically.
3. **Analytics Dashboard** - average grade per course, grade trends over
   time, study hours per course, study time vs. grade, how early you started
   an assignment vs. the grade you got, and weekly productivity trends.
4. **AI Recommendation System** - once ~1 week of real activity has been
   tracked, Prioriton sends a compact summary of your courses (grades, study
   hours, upcoming assignments) to an LLM and gets back a short list of
   grounded recommendations, e.g. *"You're spending 2.3 fewer hours/week on
   MATH 241 than your other courses average"* or *"CS 225 assignments have
   taken you ~4 hours on average - start this one now."*

## Why "Course" covers both synced and manual classes

Rather than a separate "Subject" concept for the Study Timer, a manually
added class is just another `Course` row (`source = "manual"`). That's what
lets the Study Timer, Analytics, and Recommendations all work fully before
you've connected anything - and what lets study time, grades, and
assignments all correlate per class regardless of where the class came from.

## Architecture

- **Backend:** Python + FastAPI + SQLModel (SQLite), APScheduler for a
  background sync job (every 15 min) and a daily recommendation-eligibility
  check.
- **Frontend:** React + Vite + TypeScript + Tailwind, React Query, React
  Router, Recharts for the Analytics Dashboard.
- **AI:** Anthropic's API (`anthropic` Python SDK). Everything else in
  the app works with no API key set; only Recommendations needs one.

## Setup

The steps below run everything locally (dev servers, `.env` files). For a
real deployment you'd actually use with your own accounts - reachable from
anywhere, HTTPS, Gradescope/PrairieLearn's interactive login working through
a browser tab instead of a local GUI - see **[DEPLOY.md](DEPLOY.md)**. To
instead put up a public, no-real-accounts demo so other people can see it
work (interactive, self-resetting sample data, one lightweight container) -
see **[DEPLOY_DEMO.md](DEPLOY_DEMO.md)**.

### Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
```

Download the Chromium browser Playwright needs (for Gradescope/PrairieLearn
login and headless re-syncs):

```
python -m playwright install chromium
```

Generate a secret key and put it in `.env` as `PRIORITON_SECRET_KEY`:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add your `ANTHROPIC_API_KEY` to `.env` to enable Recommendations (everything
else works without it). Get one at https://console.anthropic.com/.

Run it:

```
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for the interactive API docs.

### Frontend

```
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`.

### Try it with demo data (no Canvas/Anthropic account needed)

```
cd backend
python scripts/seed_demo_data.py
```

Seeds ~2 weeks of realistic courses, graded assignments, and study sessions,
and backdates the "data collection started" clock so Recommendations is
immediately eligible (you'll still need `ANTHROPIC_API_KEY` set to actually
generate one).

### Connect Canvas / Gradescope / PrairieLearn

All three work exactly as in ManaPeer - see Settings in the app. Canvas uses
a personal access token (Account -> Settings -> "+ New Access Token").
Gradescope and PrairieLearn open a real browser window for a one-time
interactive login (your school's SSO/Duo, if any), then reuse that session
for periodic background syncs. Credentials/session cookies are encrypted at
rest and only ever sent to the platform itself - see **Security** below for
exactly what that means and where the encryption key actually lives.

## Security

**What's encrypted, and with what.** The Canvas token and the Gradescope/
PrairieLearn session cookie jar are encrypted at rest with Fernet (AES-128 in
CBC mode + HMAC, via the `cryptography` package) - see `app/security.py`.
Nothing else in the database is encrypted (course names, task titles, grades)
since none of it is a credential; only the fields that could let someone log
in as you get this treatment. Your Gradescope/PrairieLearn password itself
never touches this app at all - you type it directly into the real Chromium
window that opens, straight to your school's SSO page.

**Where the encryption key lives.** By default, nowhere in this project's own
files - the first time a key is needed, one is generated and stored in your
OS's own credential store (Windows Credential Manager here, via the `keyring`
package) and reused from there after that. This matters because this project
folder is itself synced by OneDrive: `.gitignore` keeps `.env`, the database,
and the browser-profile folder out of a shared *git* repo, but that has
nothing to do with whether OneDrive's own sync client uploads them - it
uploads everything in a synced folder regardless of git status. A key sitting
in `.env` would have been uploaded right alongside the encrypted data it
unlocks; the OS keyring entry isn't part of that folder tree, so it isn't. If
you ever do set `PRIORITON_SECRET_KEY` explicitly (Docker/CI, or your own
preference), that always takes priority over the keyring - see
`app.security.get_or_create_secret_key`.

**File permissions.** On startup, the database file, `.env`, and the browser-
profile directory are restricted to your own OS user account (`icacls` on
Windows, `chmod` elsewhere) - see `app/file_permissions.py`. This is
defense-in-depth on top of the encryption above, not a substitute for it: it
stops another account on a shared machine from reading the files at all, but
anyone with your own Windows login already has both the files and (via the
OS keyring) the key, same as any local-first app. That limit is inherent to
"runs on your own machine with no server-side login" - a real multi-user
deployment would need its own server-side auth and per-user key material,
which is out of scope for what this app is.

**Network.** The backend only listens on `127.0.0.1` - nothing reaches it
from your network or the internet, only from this machine. CORS is locked to
`PRIORITON_FRONTEND_ORIGIN`, not a wildcard. All outbound traffic (Canvas,
Gradescope, PrairieLearn, Anthropic) goes over normal HTTPS to that platform
only.

### Same class, tracked on two platforms

If a real class is tracked on both Gradescope and PrairieLearn (common -
Gradescope for submissions, PrairieLearn for online homework/exams), every
sync folds them into one course instead of showing "University Physics:
Thermal Physics" and "PHYS 213: Thermal Physics" as two separate classes
everywhere a course is picked or charted. This is decided once, server-side,
by matching each course's extracted "subject + number" code (e.g. "PHYS 213")
across *different* platforms - two rows from the *same* platform sharing a
code (Gradescope's own "ECE 110-ABA" / "-ABE" / "-HOMEWORK", genuinely
different lab sections) are never merged. The merged class shows the shared
code as its name rather than picking one platform's phrasing arbitrarily; its
grades, study hours, and tasks - wherever they were actually recorded, on
either platform's own copy of the course - are combined under it. See
`app/course_merge.py`.

### Current-semester courses vs. archived

Every sync (background or "Sync now") re-derives which semester is "current"
from the synced courses themselves - whichever parsed `(year, season)` is
highest across every Canvas/Gradescope/PrairieLearn course right now, no
hardcoded date - and archives every synced course that isn't in it. That
mirrors how Gradescope's own course-list page already groups by term with
the current semester's section on top, and how PrairieLearn only ever lists
your active courses to begin with. A course whose `term` text doesn't parse
into a real semester (PrairieLearn occasionally sends something like
"Proficiency Exam Practice: PHYS 213" instead) is left alone rather than
guessed into archived. Manually-added classes (`source: "manual"`) are never
touched by this - their archived state is entirely up to you, via Settings.
Archived courses stay visible (and un-archivable) under "Archived" in
Settings; they just drop out of the Study Timer's course picker and the
Analytics/Home overview by default. See `app/term.py` and
`app.sync_service._apply_current_semester_archiving`.

## Project layout

```
backend/app/
  main.py                 FastAPI app, CORS, router mounting, scheduler startup; serves the built
                           frontend + mounts the API under /api when DEPLOY_DEMO.md's image is used
  config.py                Settings (secret key, DB path, sync/recommendation intervals, Anthropic key)
  db.py                     SQLModel engine/session, add-missing-columns migration helper
  security.py                Fernet encrypt/decrypt for stored credentials; OS-keyring-backed key (see Security)
  file_permissions.py          Restricts the DB/.env/browser-profile dir to your OS user at startup
  browser_login.py               Interactive-login mechanism (Gradescope/PrairieLearn)
  models.py                    Course, Task, Integration, Reminder, StudySession, Recommendation, AppSettings
  schemas.py                    Pydantic request/response models
  activity.py                    Stamps when data collection started (feeds the 7-day eligibility gate)
  term.py                          Parses a course's term into (year, season) - current-semester archiving
  course_merge.py                    Folds the same real class synced on >1 platform into one canonical
                                      course - every reader (analytics, study sessions, recommendations)
                                      resolves through this
  sync_service.py                     Assignment Tracker engine - runs adapters, upserts Course/Task,
                                       merges cross-platform duplicates, archives non-current-semester courses
  analytics_service.py             Analytics Dashboard's aggregation queries
  recommendation_service.py         AI Recommendation System - builds the summary, calls the LLM, stores results
  llm_client.py                      LLM API wrapper (Anthropic SDK)
  reminders.py                        Reminder generation + lead-time settings
  scheduler.py                         Background sync job + daily recommendation check
  adapters/                             Canvas / Gradescope / PrairieLearn (same adapter pattern as ManaPeer)
  routers/                               integrations, courses, tasks, sync, reminders, settings,
                                          study_sessions, analytics, recommendations
  demo.py                                  Public-demo mode: seed/wipe/reset sample data + a
                                            pre-written example recommendation - see DEPLOY_DEMO.md
  scripts/seed_demo_data.py                 CLI wrapper around app.demo.seed_demo_data, for trying
                                             the app locally without live accounts

frontend/src/
  api/client.ts             Typed fetch wrapper for the backend API
  lib/                        date.ts, sourceColors.ts (ported from ManaPeer),
                               chartPalette.ts (validated categorical palette for Analytics)
  components/                  TaskCard, CalendarGrid, CourseManager, ConnectCanvasForm,
                                ConnectPlatformButton, NotificationBell, ReminderSettings
  pages/
    Home.tsx                     This week's stats + recommendation highlight + the full
                                  Overdue/Today/This week/Later/No due date/Done/Dismissed task browser
    StudyTimer.tsx                 Start/stop timer, weekly hours per course
    Calendar.tsx                     Month view of due dates (ManaPeer's Calendar, ported)
    Courses.tsx                       Per-class to-do/done board, current-semester tabs + archived
                                       (ManaPeer's Courses, ported; cross-platform merging is the
                                       backend's job now - see app/course_merge.py)
    Analytics.tsx                      The six charts described above (Recharts)
    Recommendations.tsx                 Latest AI recommendations, "Generate now"
    Settings.tsx                         Connect Canvas/Gradescope/PrairieLearn, reminders, manage classes
```

## Relationship to ManaPeer

Prioriton is the culmination of ManaPeer, not a separate app that happens to
reuse its engine. Everything ManaPeer did - Canvas/Gradescope/PrairieLearn
syncing, the due-date dashboard (Home's Overdue/Today/This week/Later/Done/
Dismissed buckets), the month Calendar, per-class Courses to-do/done boards
(including merging the same real class tracked on two platforms), and in-app
reminders - lives here too, on top of what ManaPeer never had: a Study Timer,
an Analytics Dashboard correlating study time against grades, and an AI
Recommendation System. ManaPeer's own repo still exists as the original,
standalone version of that engine, but day to day there's just Prioriton.
