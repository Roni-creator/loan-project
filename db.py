"""
SQLite layer for the BI-ML credit project (creditscore.db).

Tables
  users        - login accounts; role maps to the dashboard each actor uses
  applicants   - one row per scored loan application (features stored as JSON)
  predictions  - model output per applicant (P(Bad), decision, threshold used)
  model_runs   - metrics + threshold for each training run (audit trail)

Roles -> dashboards: business_manager -> D1, credit_analyst -> D2, loan_officer -> D3

Run once:  python db.py     (creates DB, seeds demo users, loads model_runs + test predictions)
"""
import json
import os
import sqlite3
from pathlib import Path

import bcrypt
import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "creditscore.db"
ROLES = ("business_manager", "credit_analyst", "loan_officer")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash BLOB NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('business_manager','credit_analyst','loan_officer')),
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
CREATE INDEX IF NOT EXISTS idx_pred_applicant ON predictions(applicant_id);
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


def init_db(path=None):
    """Create tables, remove any duplicate model_runs, and enforce uniqueness going forward."""
    with connect(path) as con:
        con.executescript(SCHEMA)
        con.execute(f"DELETE FROM model_runs WHERE run_id NOT IN "
                    f"(SELECT MIN(run_id) FROM model_runs GROUP BY {_MODEL_RUN_KEY})")
        con.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_model_runs ON model_runs({_MODEL_RUN_KEY})")


def create_user(username: str, password: str, role: str, path=None):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with connect(path) as con:
        con.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                    (username, pw, role))


def has_users(path=None) -> bool:
    with connect(path) as con:
        return con.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def set_password(username: str, password: str, path=None) -> bool:
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with connect(path) as con:
        return con.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                           (pw, username)).rowcount == 1


def verify_user(username: str, password: str, path=None):
    """Return {'user_id','username','role'} if credentials are valid, else None."""
    with connect(path) as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"]):
        return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}
    return None


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