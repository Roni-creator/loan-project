# Loan Creditworthiness (BI-ML framework)

Interpretable loan-default classification (Logistic Regression and Random Forest) on
alternative financial behaviour data, with:

- a **React + Flask applicant/staff portal** with real server-side authentication,
  role-based authorization and a database-backed application workflow, and
- the original **login-protected Streamlit app**  plus a SQLite database and
  CSV exports for the Power BI dashboards.

Both front-ends are powered by the same scoring code (`portal_core.py`), so a prediction
is computed in exactly one place.

## Architecture

| Piece | File(s) | Role |
|---|---|---|
| ML pipeline | `feature_engineering_pipeline.py`, `extra_features_experiment.py`, `threshold_tuning.py` | merges data, trains Logistic Regression + Random Forest, tunes thresholds |
| Scoring core | `portal_core.py` | validation, the 36-column feature row, both pipelines, LR explanations — one source of truth |
| SQLite layer | `db.py` | users (username + email), sessions, applications, assignments, decisions, audit log, exports |
| Auth helpers | `auth.py` | email sign-in, werkzeug password hashes (bcrypt legacy fallback), session cookies, CSRF, `@require_auth` / `@require_roles` |
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

#### Currency and data provenance (important)

The **training data is Nigerian** — loan amounts in the source dataset run roughly
10,000–60,000, consistent with naira micro-loans. The models were trained on those values and
have **not** been recalibrated or converted.

The **user-facing portal is Kenyan**: money is displayed and labelled in **Kenyan Shillings
(KES / `KSh`)**. Switching the label did not change any number, model feature, threshold or
prediction — the same amounts (10,000–60,000) and terms (15/30/60/90 days) are used everywhere.
In other words: the *amounts* are numerically identical, only the currency *label* changed from
`₦` to `KSh`.

This is a deliberate, documented relabelling, not a currency conversion. If the models are ever
retrained on Kenyan data, the amounts and thresholds should be re-derived there; the KES label
here does not imply that has happened.

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

### Run the Streamlit app (still supported)

```powershell
.venv\Scripts\python -m streamlit run app.py
```

It shares the same database, so it now also signs in with **email + password** (the same
accounts as the web portal).

## Accounts, roles and what each role can do

Accounts live in `creditscore.db` (see `db.py`). **Sign-in is by email address + password**
(the username is still stored and shown in the UI, but it is no longer used to log in).
`python build_all.py` (or `python db.py`) creates three **demo** staff accounts; change them
before showing anyone. Their emails use the reserved `.example` TLD so they can never receive
real mail.

| Email | Password | Role | Can do |
|---|---|---|---|
| `manager@loancredit.example` | `ChangeMe!1` | business_manager | Aggregate portfolio summaries (counts, mix, model metrics) — **no personal applicant records** |
| `analyst@loancredit.example` | `ChangeMe!2` | credit_analyst | Read applications and assessments (read-only), plus model insights (metrics, thresholds, drivers) |
| `officer@loancredit.example` | `ChangeMe!3` | loan_officer | See the unassigned queue and **their own** cases; claim and record decisions |
| _self-registered_ | — | applicant | Submit applications and view **only their own** history/status/results |

Role checks are enforced by Flask on every request from the server-side session; the
frontend only hides UI, it is never the source of truth for authorization. A business
manager never receives another applicant's personal details, and a loan officer cannot open
a case assigned to a different officer.

### Applicant flow

1. Register at `/register` (username 3–32 chars; **email** address; password ≥8 chars with a
   letter and a number). You sign in later with the email + password.
2. Complete the multi-step application (`/apply`) and submit. The applicant enters their **own**
   personal fields and borrowing history; there is no shared "sample customer" shortcut.
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

- **Sign-in identifier** is the email address. Emails are normalised (trimmed + lower-cased)
  before lookup and before storage, so `A@B.com ` and `a@b.com` are the same account. A
  database-level unique index on `lower(email)` guarantees one account per address (legacy rows
  with no email yet are allowed to coexist as `NULL`).
- **Passwords** are stored as werkzeug hashes (`scrypt` by default). Hashes written by an earlier
  release (`bcrypt`) still verify and are transparently re-hashed to the werkzeug format on the
  next successful sign-in, so no account needs a password reset. Login verifies server-side; the
  same generic message (`Invalid email or password.`) is returned whether the email is unknown or
  the password is wrong, so the API does not reveal which addresses have accounts. Failures are
  audited.
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
python db.py set-password manager                    # prompts for a new password
python db.py set-email manager manager@example.org   # set/replace the sign-in email
python db.py add-user jane credit_analyst --email jane@example.org   # prompts for a password
python db.py list-users
```

`add-user` accepts an optional `--email`. An account with no email cannot sign in; give it one
with `set-email`.

### Migrating an existing database to email sign-in

`init_db()` (run by `webapp.py`, `build_all.py`, `db.py` and the tests) **adds the `email`
column and its unique index in place** the first time it runs against an older database:

- Existing rows keep their `user_id`, `password_hash`, `role`, `full_name` and all their
  applications/decisions — nothing is recreated and no hash is changed.
- Existing accounts are left with **no email** (we never invent addresses), so they cannot sign
  in until an operator sets one: `python db.py set-email <username> <email>`.
- The three demo staff accounts get their documented `.example` emails automatically (only if
  they have none; an operator-set email is never overwritten).

Migrations are additive and idempotent. **Back up the database file before upgrading** anyway:

```powershell
copy creditscore.db creditscore.backup.db
```

`python db.py` is idempotent: rerunning it never duplicates users or model-run rows, and it
applies schema migrations (including adding the `applicant` role and the `email` column to older
databases) without losing data.

## API reference

Public:

| Method | Path | Notes |
|---|---|---|
| GET | `/api/meta` | reference values for the application form |
| POST | `/api/score` | read-only model preview; stores nothing |
| POST | `/api/auth/register` | applicant self-registration (username + email + password; role forced to `applicant`) |
| POST | `/api/auth/login` | email + password check + session cookie |

Authenticated (any role): `GET /api/auth/me`, `POST /api/auth/logout`.

Staff only (credit analyst / loan officer): `GET /api/sample-id`, `POST /api/lookup`
(these read the training dataset for review, never the signed-in user's own record).

Applicant only: `POST /api/applications`, `GET /api/applications`,
`GET /api/applications/<id>` (plus the legacy `POST /api/submit` alias).

Staff (`/api/staff/*`): `summary` for all staff (business managers get aggregates without
personal details); `applications` and `applications/<id>` for credit analysts and loan
officers (a loan officer sees the unassigned queue plus their own cases);
`applications/<id>/assign` and `applications/<id>/decision` for loan officers only;
`models` for credit analysts only.

## Database schema

`db.py` creates/migrates these tables in `creditscore.db`:

- `users` — `username`, `email` (unique, lower-cased; nullable for legacy rows), `password_hash`
  (werkzeug; legacy bcrypt accepted), `role`, `full_name` (`applicant` allowed).
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
model output. It also covers the email changes: email registration and login, case/whitespace
normalisation, duplicate-email rejection, the generic login error, and server-side email
validation. `test_app_setup.py` adds database-level tests for the in-place email migration
(preserving ids, hashes and roles of pre-existing accounts), the email uniqueness rule and the
`add-user --email` / `set-email` CLI. Tests that need generated artifacts skip themselves until
you have run `build_all.py`.

## Method notes

- Target: Bad (default) = 0, Good (repaid) = 1. Decision rule: predict Good when
  P(Good) >= the per-model threshold in `thresholds.json`.
- Thresholds are tuned on out-of-fold training predictions; the 30% test set is used once.
- Preprocessing that learns from data (median imputation, scaling) runs inside the model
  pipeline on training folds only. Missing categories become an explicit "Unknown" level.
- Predictions and feature importance describe model behaviour; they are not causal
  evidence or credit decisions.
