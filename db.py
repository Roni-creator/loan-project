"""
SQLite layer for the BI-ML credit project (creditscore.db).

Tables
  users                 - login accounts; role maps to the dashboard each actor uses
  applicants            - one row per scored loan application (features stored as JSON)
  predictions           - model output per applicant (P(Bad), decision, threshold used)
  model_runs            - metrics + threshold for each training run (audit trail)
  auth_sessions         - server-side login sessions (opaque token hash + CSRF token)
  loan_applications     - DB-backed applicant submissions (status, assignment, answers)
  application_decisions - officer decisions (approve/decline/more info) with notes
  audit_log             - security-relevant events (no passwords/tokens stored)

Roles -> dashboards: business_manager -> D1, credit_analyst -> D2, loan_officer -> D3,
applicant -> borrower portal.

Run once:  python db.py     (creates DB, seeds demo users, loads model_runs + test predictions)
"""
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "creditscore.db"
STAFF_ROLES = ("business_manager", "credit_analyst", "loan_officer")
APPLICANT_ROLE = "applicant"
ROLES = STAFF_ROLES + (APPLICANT_ROLE,)
DEFAULT_SESSION_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "12"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash BLOB NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('business_manager','credit_analyst','loan_officer','applicant')),
    full_name     TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS applicants (
    applicant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    features     TEXT NOT NULL,              -- JSON of the model input row
    actual_flag  INTEGER,                    -- 0 Bad / 1 Good, if known (test set)
    created_by   INTEGER REFERENCES users(user_id),
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id  INTEGER NOT NULL REFERENCES applicants(applicant_id),
    model_name    TEXT NOT NULL,
    p_bad         REAL NOT NULL,
    p_good        REAL NOT NULL,
    threshold     REAL NOT NULL,             -- P(Good) cut-off used
    decision      TEXT NOT NULL CHECK (decision IN ('Good','Bad')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS model_runs (
    run_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    setting    TEXT NOT NULL,
    threshold  REAL, accuracy REAL, precision_bad REAL, recall_bad REAL,
    f1_bad REAL, roc_auc REAL, pr_auc_bad REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id     TEXT PRIMARY KEY,          -- sha256 of the opaque cookie token
    user_id        INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    csrf_token     TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS loan_applications (
    application_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    reference           TEXT NOT NULL UNIQUE,
    user_id             INTEGER NOT NULL REFERENCES users(user_id),
    applicant_id        INTEGER REFERENCES applicants(applicant_id),
    answers             TEXT NOT NULL,        -- JSON of the validated application
    tier                TEXT NOT NULL,        -- likely / review / refer
    status              TEXT NOT NULL DEFAULT 'submitted'
                        CHECK (status IN ('submitted','assigned','approved','declined','more_info')),
    assigned_officer_id INTEGER REFERENCES users(user_id),
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS application_decisions (
    decision_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES loan_applications(application_id),
    officer_id     INTEGER NOT NULL REFERENCES users(user_id),
    decision       TEXT NOT NULL CHECK (decision IN ('approved','declined','more_info','assigned')),
    note           TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(user_id),
    actor      TEXT,                          -- username snapshot at the time
    action     TEXT NOT NULL,
    detail     TEXT,
    ip         TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pred_applicant ON predictions(applicant_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_app_user ON loan_applications(user_id);
CREATE INDEX IF NOT EXISTS idx_app_status ON loan_applications(status);
CREATE INDEX IF NOT EXISTS idx_decisions_app ON application_decisions(application_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
"""


def _resolve(path=None):
    """Explicit path > CREDITSCORE_DB env var > default file next to this module."""
    return path or os.environ.get("CREDITSCORE_DB") or DB_PATH


def connect(path=None) -> sqlite3.Connection:
    con = sqlite3.connect(_resolve(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


_MODEL_RUN_KEY = ("model_name, setting, threshold, accuracy, precision_bad, recall_bad, "
                  "f1_bad, roc_auc, pr_auc_bad")


def _migrate_users_role(con: sqlite3.Connection) -> None:
    """Add the applicant role (and extra columns) to an older users table.

    SQLite cannot ALTER a CHECK constraint, so the table is rebuilt in place.
    Foreign keys are disabled and legacy ALTER semantics are used so existing
    `applicants.created_by -> users(user_id)` references stay intact.
    """
    row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if row is None:
        return
    sql = row["sql"] or ""
    if "applicant" in sql:
        columns = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
        if "full_name" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        if "is_active" not in columns:
            con.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        return

    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("PRAGMA legacy_alter_table = ON")
    con.execute("""
        CREATE TABLE users_new (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash BLOB NOT NULL,
            role          TEXT NOT NULL CHECK (role IN ('business_manager','credit_analyst','loan_officer','applicant')),
            full_name     TEXT,
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
    con.execute("""INSERT INTO users_new(user_id, username, password_hash, role, is_active, created_at)
                   SELECT user_id, username, password_hash, role, 1, created_at FROM users""")
    con.execute("DROP TABLE users")
    con.execute("ALTER TABLE users_new RENAME TO users")
    con.execute("PRAGMA legacy_alter_table = OFF")
    con.execute("PRAGMA foreign_keys = ON")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db(path=None):
    """Create/migrate the schema, prune duplicates and stale sessions. Idempotent."""
    with connect(path) as con:
        _migrate_users_role(con)
        con.executescript(SCHEMA)
        con.execute(f"DELETE FROM model_runs WHERE run_id NOT IN "
                    f"(SELECT MIN(run_id) FROM model_runs GROUP BY {_MODEL_RUN_KEY})")
        con.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_model_runs ON model_runs({_MODEL_RUN_KEY})")
        con.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (_now(),))


def create_user(username: str, password: str, role: str, full_name: str | None = None, path=None):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO users(username, password_hash, role, full_name) VALUES (?,?,?,?)",
            (username, pw, role, full_name))
    return cur.lastrowid


def has_users(path=None) -> bool:
    with connect(path) as con:
        return con.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def set_password(username: str, password: str, path=None) -> bool:
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with connect(path) as con:
        return con.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                           (pw, username)).rowcount == 1


def get_user(user_id: int, path=None):
    with connect(path) as con:
        return con.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def verify_user(username: str, password: str, path=None):
    """Return the public account dict if credentials are valid, else None."""
    with connect(path) as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and row["is_active"] and bcrypt.checkpw(password.encode(), row["password_hash"]):
        return {"user_id": row["user_id"], "username": row["username"], "role": row["role"],
                "full_name": row["full_name"]}
    return None


# ------------------------------------------------------------- sessions ------
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int, hours: int = None, path=None):
    """Create a server-side session. Returns {token, csrf_token, expires_at} (token shown once)."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    hours = DEFAULT_SESSION_HOURS if hours is None else hours
    expires = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=hours)
    with connect(path) as con:
        con.execute(
            "INSERT INTO auth_sessions(session_id, user_id, csrf_token, expires_at) VALUES (?,?,?,?)",
            (_hash_token(token), user_id, csrf, expires.isoformat()))
    return {"token": token, "csrf_token": csrf, "expires_at": expires.isoformat()}


def get_session(token: str, path=None):
    """Return {'user_id','username','role','full_name','csrf_token'} for a live session, else None."""
    if not token:
        return None
    sid = _hash_token(token)
    with connect(path) as con:
        row = con.execute("""
            SELECT s.session_id, s.csrf_token, s.expires_at, u.user_id, u.username, u.role, u.full_name
            FROM auth_sessions s JOIN users u ON u.user_id = s.user_id
            WHERE s.session_id = ? AND u.is_active = 1""", (sid,)).fetchone()
        if row is None:
            return None
        try:
            expired = datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc)
        except ValueError:
            expired = True
        if expired:
            con.execute("DELETE FROM auth_sessions WHERE session_id = ?", (sid,))
            return None
        con.execute("UPDATE auth_sessions SET last_seen = ? WHERE session_id = ?", (_now(), sid))
    return {"user_id": row["user_id"], "username": row["username"], "role": row["role"],
            "full_name": row["full_name"], "csrf_token": row["csrf_token"]}


def delete_session(token: str, path=None) -> bool:
    if not token:
        return False
    with connect(path) as con:
        return con.execute("DELETE FROM auth_sessions WHERE session_id = ?",
                           (_hash_token(token),)).rowcount == 1


def delete_user_sessions(user_id: int, path=None) -> int:
    with connect(path) as con:
        return con.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,)).rowcount


# --------------------------------------------------------- applications ------
def create_application(reference: str, user_id: int, answers: dict, tier: str,
                       applicant_id: int | None = None, path=None):
    with connect(path) as con:
        cur = con.execute(
            "INSERT INTO loan_applications(reference, user_id, applicant_id, answers, tier)"
            " VALUES (?,?,?,?,?)",
            (reference, user_id, applicant_id, json.dumps(answers), tier))
    return cur.lastrowid


def list_applications(user_id: int, path=None) -> list[sqlite3.Row]:
    with connect(path) as con:
        return con.execute(
            "SELECT * FROM loan_applications WHERE user_id = ? ORDER BY application_id DESC",
            (user_id,)).fetchall()


def get_application(application_id: int, path=None):
    with connect(path) as con:
        return con.execute("SELECT * FROM loan_applications WHERE application_id = ?",
                           (application_id,)).fetchone()


def list_staff_applications(path=None) -> list[sqlite3.Row]:
    with connect(path) as con:
        return con.execute("""
            SELECT a.*, u.username AS applicant_username, u.full_name AS applicant_name,
                   o.username AS officer_username
            FROM loan_applications a
            JOIN users u ON u.user_id = a.user_id
            LEFT JOIN users o ON o.user_id = a.assigned_officer_id
            ORDER BY a.application_id DESC""").fetchall()


def assign_application(application_id: int, officer_id: int, path=None) -> bool:
    with connect(path) as con:
        return con.execute(
            "UPDATE loan_applications SET assigned_officer_id = ?, status = 'assigned',"
            " updated_at = ? WHERE application_id = ?",
            (officer_id, _now(), application_id)).rowcount == 1


def decide_application(application_id: int, officer_id: int, decision: str, note: str = "",
                       path=None) -> bool:
    if decision not in ("approved", "declined", "more_info"):
        raise ValueError("Invalid decision")
    with connect(path) as con:
        changed = con.execute(
            "UPDATE loan_applications SET status = ?, updated_at = ? WHERE application_id = ?",
            (decision, _now(), application_id)).rowcount == 1
        if changed:
            con.execute(
                "INSERT INTO application_decisions(application_id, officer_id, decision, note)"
                " VALUES (?,?,?,?)", (application_id, officer_id, decision, note))
    return changed


def list_application_decisions(application_id: int, path=None) -> list[sqlite3.Row]:
    with connect(path) as con:
        return con.execute(
            "SELECT d.*, u.username AS officer_username FROM application_decisions d"
            " JOIN users u ON u.user_id = d.officer_id"
            " WHERE d.application_id = ? ORDER BY d.decision_id", (application_id,)).fetchall()


# -------------------------------------------------------------- audit --------
def log_audit(action: str, detail: str = "", user_id: int | None = None,
              actor: str | None = None, ip: str | None = None, path=None):
    """Append a security-relevant event. Never store passwords or session tokens."""
    with connect(path) as con:
        con.execute(
            "INSERT INTO audit_log(user_id, actor, action, detail, ip) VALUES (?,?,?,?,?)",
            (user_id, actor, action, detail, ip))


def recent_audit(limit: int = 100, path=None) -> list[sqlite3.Row]:
    with connect(path) as con:
        return con.execute(
            "SELECT * FROM audit_log ORDER BY log_id DESC LIMIT ?", (limit,)).fetchall()


def record_scored_application(features: dict, model_scores: dict, user_id=None,
                              actual=None, path=None):
    """Insert one `applicants` row plus one `predictions` row per model.

    Keeps the Power BI exports (`db_applicants.csv`, `db_predictions.csv`) populated
    from the same scoring result that is returned to the user - no duplicate logic.
    """
    with connect(path) as con:
        aid = con.execute(
            "INSERT INTO applicants(features, actual_flag, created_by) VALUES (?,?,?)",
            (json.dumps(features), actual, user_id)).lastrowid
        for name, s in model_scores.items():
            con.execute(
                "INSERT INTO predictions(applicant_id, model_name, p_bad, p_good, threshold, decision)"
                " VALUES (?,?,?,?,?,?)",
                (aid, name, float(s["p_bad"]), float(s["p_good"]), float(s["threshold"]),
                 "Good" if s["p_good"] >= s["threshold"] else "Bad"))
    return aid


def log_prediction(features: dict, model_name: str, p_bad: float, threshold: float,
                   user_id=None, actual=None, path=None):
    p_good = 1 - p_bad
    decision = "Good" if p_good >= threshold else "Bad"
    with connect(path) as con:
        aid = con.execute(
            "INSERT INTO applicants(features, actual_flag, created_by) VALUES (?,?,?)",
            (json.dumps(features), actual, user_id)).lastrowid
        con.execute(
            "INSERT INTO predictions(applicant_id, model_name, p_bad, p_good, threshold, decision)"
            " VALUES (?,?,?,?,?,?)", (aid, model_name, p_bad, p_good, threshold, decision))
    return aid, decision


def load_model_runs(csv="threshold_comparison.csv", path=None):
    df = pd.read_csv(csv).dropna(subset=["threshold_P_good"])
    with connect(path) as con:
        for r in df.itertuples():
            con.execute(
                "INSERT OR IGNORE INTO model_runs(model_name,setting,threshold,accuracy,precision_bad,"
                "recall_bad,f1_bad,roc_auc,pr_auc_bad) VALUES (?,?,?,?,?,?,?,?,?)",
                (r.model, r.setting, r.threshold_P_good, r.accuracy, r.precision_bad,
                 r.recall_bad, r.f1_bad, r.roc_auc, r.pr_auc_bad))


def export_tables(out_dir=".", path=None):
    """CSV export of every table for Power BI (Text/CSV connector). Password hashes excluded."""
    with connect(path) as con:
        for t in ("applicants", "predictions", "model_runs"):
            pd.read_sql_query(f"SELECT * FROM {t}", con).to_csv(f"{out_dir}/db_{t}.csv", index=False)
        pd.read_sql_query("SELECT user_id, username, role, created_at FROM users", con)\
          .to_csv(f"{out_dir}/db_users.csv", index=False)


DEMO_USERS = [("manager", "ChangeMe!1", "business_manager"),
              ("analyst", "ChangeMe!2", "credit_analyst"),
              ("officer", "ChangeMe!3", "loan_officer")]


def seed_demo(path=None, runs_csv="threshold_comparison.csv"):
    """Idempotent: safe to run any number of times."""
    init_db(path)
    for u, pw, role in DEMO_USERS:
        try:
            create_user(u, pw, role, path)
        except sqlite3.IntegrityError:
            pass
    if Path(runs_csv).exists():
        load_model_runs(runs_csv, path)


def main(argv=None):
    import argparse
    import getpass
    ap = argparse.ArgumentParser(description="Manage creditscore.db")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("seed", help="create the DB, demo users and model_runs (default; idempotent)")
    a = sub.add_parser("add-user", help="create a user")
    a.add_argument("username"); a.add_argument("role", choices=ROLES)
    p = sub.add_parser("set-password", help="change a user's password")
    p.add_argument("username")
    sub.add_parser("list-users", help="list accounts (never shows passwords)")
    args = ap.parse_args(argv)

    if args.cmd in (None, "seed"):
        seed_demo()
        print("DB ready (demo passwords are placeholders - change them with: "
              "python db.py set-password <username>)")
    elif args.cmd == "add-user":
        init_db()
        create_user(args.username, getpass.getpass("Password: "), args.role)
        print(f"Created {args.username} ({args.role})")
    elif args.cmd == "set-password":
        ok = set_password(args.username, getpass.getpass("New password: "))
        print("Password updated" if ok else "No such user")
    elif args.cmd == "list-users":
        init_db()
        with connect() as con:
            for r in con.execute("SELECT username, role FROM users ORDER BY user_id"):
                print(f"{r['username']:<20} {r['role']}")


if __name__ == "__main__":
    main()