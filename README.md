# Loan Creditworthiness (BI-ML framework)

Interpretable loan-default classification (Logistic Regression and Random Forest) on
alternative financial behaviour data, with:

- a **React + Flask applicant/staff portal** with real server-side authentication,
  role-based authorization and a database-backed application workflow, and
- the original **login-protected Streamlit app** (unchanged) plus a SQLite database and
  CSV exports for the Power BI dashboards.

Both front-ends are powered by the same scoring code (`portal_core.py`), so a prediction
is computed in exactly one place.

## Architecture

| Piece | File(s) | Role |
|---|---|---|
| ML pipeline | `feature_engineering_pipeline.py`, `extra_features_experiment.py`, `threshold_tuning.py` | merges data, trains Logistic Regression + Random Forest, tunes thresholds |
| Scoring core | `portal_core.py` | validation, the 36-column feature row, both pipelines, LR explanations — one source of truth |
| SQLite layer | `db.py` | users, sessions, applications, assignments, decisions, audit log, exports |
| Auth helpers | `auth.py` | bcrypt passwords, session cookies, CSRF, `@require_auth` / `@require_roles` |
| JSON API | `api_routes.py` | authentication, applicant and staff endpoints |
| Flask app | `webapp.py` | JSON API + serves the built React SPA (and the legacy static page) |
| React frontend | `frontend/` | landing, applicant portal, staff dashboards |
| Streamlit app | `app.py`, `login.py`, `applicant_portal.py` | the original app, still works |

The Flask API is the **only** place scoring happens on the server: `portal_core.build_features`
+ `portal_core.score` are reused by both the Streamlit app and the React portal. Nothing
re-implements the models or fabricates predictions.

## Setup from a fresh clone

Git ignores all `*.csv`, `*.joblib` and the database, so a clone contains code only.
Everything else is generated.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

For the web portal also build the frontend (needs Node.js 18+):

```powershell
cd frontend
npm install
npm run build
```

### Data

The data is the Zindi competition dataset
[Data Science Nigeria Challenge #1: Loan Default Prediction](https://zindi.world/competitions/data-science-nigeria-challenge-1-loan-default-prediction).
It is not redistributed in this repository: download it yourself from the competition's
Data tab (this needs a free Zindi account and acceptance of the competition rules; check the
data licence before sharing derived files).

Put these three files in the project folder (next to `build_all.py`):

- `traindemographics.csv`
- `trainperf.csv`
- `trainprevloans.csv`

### Build everything

```powershell
python build_all.py
```

This runs, in order: merge and feature engineering, extended features, model training and
threshold tuning, then creates `creditscore.db` with the demo accounts. If a raw file is
missing it stops and says which one.

## Run the web portal (recommended)

Flask serves the built React app and the JSON API from one origin:

```powershell
.venv\Scripts\python webapp.py
```

Then open <http://127.0.0.1:8000>. `main()` fails fast if the model artifacts are missing
(run `threshold_tuning.py`/`build_all.py` first) and applies any pending database migrations
on startup.

### Frontend development

To work on the UI with hot reload, run Flask and Vite side by side. Vite proxies `/api`
to Flask, so the React dev server and the session cookie share an origin:

```powershell
# terminal 1
.venv\Scripts\python webapp.py         # http://127.0.0.1:8000

# terminal 2
cd frontend
npm install
npm run dev                            # http://127.0.0.1:5173
```

Change the proxy target with `frontend/.env` (`VITE_API_TARGET`, see `frontend/.env.example`).

### Run the Streamlit app (unchanged)

```powershell
.venv\Scripts\python -m streamlit run app.py
```

## Accounts, roles and what each role can do

Accounts live in `creditscore.db` (see `db.py`). `python build_all.py` (or `python db.py`)
creates three **demo** staff accounts; change them before showing anyone.

| Username | Password | Role | Can do |
|---|---|---|---|
| `manager` | `ChangeMe!1` | business_manager | Portfolio summaries over all applications |
| `analyst` | `ChangeMe!2` | credit_analyst | Everything `manager` can, plus model insights (metrics, thresholds, drivers) |
| `officer` | `ChangeMe!3` | loan_officer | Everything `manager` can, plus claim applications and record decisions |
| _self-registered_ | — | applicant | Submit applications and view **only their own** history/status/results |

Role checks are enforced by Flask on every request from the server-side session; the
frontend only hides UI, it is never the source of truth for authorization.

### Applicant flow

1. Register at `/register` (username 3–32 chars; password ≥8 chars with a letter and a number).
2. Complete the multi-step application (`/apply`) and submit.
3. The backend validates, scores with the real models, stores the application, and returns a
   reference (`APP-XXXXXXXX`). See your list at `/my-applications` and open one for the
   model assessment, contributing factors and any decision notes.

### Staff flow

1. Sign in at `/login` → you land on the dashboard for your role.
2. `/staff/applications` lists every application (filterable). Open one for the full
   assessment (recomputed from the stored answers with the same models the applicant saw).
3. Loan officers claim an application ("Assign to me"), then record a decision
   (`approved` / `declined` / `more_info`). `declined` and `more_info` require a note.
4. Credit analysts get `/staff/models`: model-run metrics, tuned thresholds and top drivers.

## Authentication and security

- **Passwords** are stored as bcrypt hashes (the same hashes the Streamlit app already used,
  so existing logins keep working). Login verifies server-side; failures are audited.
- **Sessions** are opaque random tokens in an `HttpOnly` cookie (`SameSite=Lax`, optional
  `Secure`). Only a SHA-256 hash of the token is stored in `auth_sessions`, so a database
  leak cannot be replayed as a live session. Logout deletes the row, invalidating the cookie.
- **CSRF**: every state-changing request must send the per-session token in the `X-CSRF-Token`
  header. Exempt: `/api/auth/login`, `/api/auth/register` (no session yet) and `/api/score`
  (read-only preview that stores nothing). With a valid session, a missing/bad token returns
  403; without a session, protected routes return 401.
- **Authorization** is server-side via `@require_auth` / `@require_roles(...)`; roles come from
  the session, never from client input.
- **Ownership**: an applicant can only read applications where `user_id` matches. Someone
  else's application returns 404 (indistinguishable from "not found").
- **Audit**: logins, failed logins, logout, registrations, submissions, assignments and
  decisions are written to `audit_logs`.
- API responses set `Cache-Control: no-store`; `X-Content-Type-Options`, `X-Frame-Options`
  and `Referrer-Policy` are set on every response.

### Configuration (environment variables)

Copy `.env.example` to `.env` (git-ignored) and adjust as needed; everything has a safe
default so the app runs with nothing set.

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | `dev-only-change-me` | Flask secret — set a long random value in production |
| `SESSION_COOKIE_NAME` | `loan_session` | session cookie name |
| `SESSION_LIFETIME_HOURS` | `12` | session TTL |
| `COOKIE_SECURE` | `0` | set to `1` when served over HTTPS to add the `Secure` flag |
| `CREDITSCORE_DB` | `creditscore.db` | path to the SQLite database |
| `VITE_API_TARGET` | `http://127.0.0.1:8000` | Vite dev proxy target (`frontend/.env`) |

Never commit a real `.env` — the repository's `.gitignore` excludes `.env`/`.env.*` and the
database/CSV/joblib artifacts.

### Account management

```powershell
python db.py set-password manager          # prompts for a new password
python db.py add-user jane credit_analyst  # prompts for a password
python db.py list-users
```

`python db.py` is idempotent: rerunning it never duplicates users or model-run rows, and it
applies schema migrations (including adding the `applicant` role to older databases) without
losing data.

## API reference

Public:

| Method | Path | Notes |
|---|---|---|
| GET | `/api/meta` | reference values for the application form |
| POST | `/api/score` | read-only model preview; stores nothing |
| POST | `/api/auth/register` | applicant self-registration (role forced to `applicant`) |
| POST | `/api/auth/login` | credential check + session cookie |

Authenticated (any role): `GET /api/auth/me`, `POST /api/auth/logout`,
`GET /api/sample-id`, `POST /api/lookup`.

Applicant only: `POST /api/applications`, `GET /api/applications`,
`GET /api/applications/<id>` (plus the legacy `POST /api/submit` alias).

Staff (`/api/staff/*`): `summary`, `applications`, `applications/<id>` for all staff;
`applications/<id>/assign` and `applications/<id>/decision` for loan officers only;
`models` for credit analysts only.

## Database schema

`db.py` creates/migrates these tables in `creditscore.db`:

- `users` — username, bcrypt `password_hash`, `role`, `full_name` (`applicant` allowed).
- `auth_sessions` — session `token_hash`, `csrf_token`, `user_id` FK, expiry.
- `applicants` / `predictions` / `model_runs` — the original scored-application and model
  tables, kept for the Power BI exports.
- `loan_applications` — one row per submission: reference, `user_id` FK, answers JSON, tier,
  status, `assigned_officer_id` FK, timestamps.
- `application_decisions` — decision, note, officer FK, timestamp.
- `audit_log` — action, actor, detail, IP, timestamp.

Foreign keys and constraints are enforced; `init_db()` is idempotent and safe to run against an
existing database.

## What gets generated (and is git-ignored)

| File | Produced by | Used by |
|---|---|---|
| `model_ready_dataset.csv` | `feature_engineering_pipeline.py` | input to the extended features only |
| `model_ready_extended.csv` | `extra_features_experiment.py` | model training, Portfolio overview |
| `encoding_maps.json` | `feature_engineering_pipeline.py` | translates raw category text in uploads to training codes |
| `*_pipeline.joblib`, `thresholds.json`, `feature_columns.json` | `threshold_tuning.py` | scoring and evaluation |
| `test_set.csv`, `*_test_predictions.csv`, `threshold_comparison.csv` | `threshold_tuning.py` | evaluation, Power BI |
| `feature_importance.csv` | `threshold_tuning.py` | overview, driver dashboard, staff model insights |
| `creditscore.db` | `db.py` | accounts, sessions, applications, decisions, audit |
| `frontend/dist/` | `npm run build` | served by `webapp.py` |

Scoring files must contain the same columns as `feature_columns.json` (the app offers a
blank template download). Raw category text is accepted for `bank_account_type`,
`employment_status_clients` and `bank_name_clients` (e.g. `Savings`, `Permanent`, `GT Bank`);
the app converts it to the training codes. Already-encoded numbers also work. Missing numeric
values are allowed; the model fills them with medians learned from the training data only.

## Power BI

```powershell
python -c "import db; db.export_tables('.')"
```

writes `db_applicants.csv`, `db_predictions.csv`, `db_model_runs.csv` and `db_users.csv`
(no password hashes). Load them, plus `feature_importance.csv` and `threshold_comparison.csv`,
with the Text/CSV connector.

## Tests

```powershell
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest -q
```

`test_api_auth.py` covers backend authentication and authorization end to end: valid/invalid
login, logout invalidates the session, unauthenticated requests are blocked, role restrictions,
applicant data isolation, database persistence, CSRF enforcement, and that scoring returns real
model output. Tests that need generated artifacts skip themselves until you have run
`build_all.py`.

## Method notes

- Target: Bad (default) = 0, Good (repaid) = 1. Decision rule: predict Good when
  P(Good) >= the per-model threshold in `thresholds.json`.
- Thresholds are tuned on out-of-fold training predictions; the 30% test set is used once.
- Preprocessing that learns from data (median imputation, scaling) runs inside the model
  pipeline on training folds only. Missing categories become an explicit "Unknown" level.
- Predictions and feature importance describe model behaviour; they are not causal
  evidence or credit decisions.
