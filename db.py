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


def connect(path=DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db(path=DB_PATH):
    with connect(path) as con:
        con.executescript(SCHEMA)


def create_user(username: str, password: str, role: str, path=DB_PATH):
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    with connect(path) as con:
        con.execute("INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                    (username, pw, role))


def verify_user(username: str, password: str, path=DB_PATH):
    """Return {'user_id','username','role'} if credentials are valid, else None."""
    with connect(path) as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"]):
        return {"user_id": row["user_id"], "username": row["username"], "role": row["role"]}
    return None


def log_prediction(features: dict, model_name: str, p_bad: float, threshold: float,
                   user_id=None, actual=None, path=DB_PATH):
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


def load_model_runs(csv="threshold_comparison.csv", path=DB_PATH):
    df = pd.read_csv(csv).dropna(subset=["threshold_P_good"])
    with connect(path) as con:
        for r in df.itertuples():
            con.execute(
                "INSERT INTO model_runs(model_name,setting,threshold,accuracy,precision_bad,"
                "recall_bad,f1_bad,roc_auc,pr_auc_bad) VALUES (?,?,?,?,?,?,?,?,?)",
                (r.model, r.setting, r.threshold_P_good, r.accuracy, r.precision_bad,
                 r.recall_bad, r.f1_bad, r.roc_auc, r.pr_auc_bad))


def export_tables(out_dir=".", path=DB_PATH):
    """CSV export of every table for Power BI (Text/CSV connector). Password hashes excluded."""
    with connect(path) as con:
        for t in ("applicants", "predictions", "model_runs"):
            pd.read_sql_query(f"SELECT * FROM {t}", con).to_csv(f"{out_dir}/db_{t}.csv", index=False)
        pd.read_sql_query("SELECT user_id, username, role, created_at FROM users", con)\
          .to_csv(f"{out_dir}/db_users.csv", index=False)


if __name__ == "__main__":
    init_db()
    for u, pw, role in [("manager", "ChangeMe!1", "business_manager"),
                        ("analyst", "ChangeMe!2", "credit_analyst"),
                        ("officer", "ChangeMe!3", "loan_officer")]:
        try:
            create_user(u, pw, role)
        except sqlite3.IntegrityError:
            pass
    load_model_runs()
    print(f"DB ready: {DB_PATH.name} (demo passwords are placeholders - change them)")
