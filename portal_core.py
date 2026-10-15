"""
portal_core.py - scoring logic for the applicant web portal (no web framework here).

Turns an applicant's answers into the exact 36-column model input, scores it with
BOTH trained pipelines, and explains the result with Logistic Regression
coefficient x scaled input (no SHAP/LIME, per the project delimitations).

CONVENTIONS (same as threshold_tuning.py): Bad = 0, Good = 1,
P(Good) = pipeline.predict_proba(X)[:, 1]; predict GOOD if P(Good) >= threshold.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_FILES = {
    "Logistic Regression": PROJECT_DIR / "logistic_regression_pipeline.joblib",
    "Random Forest": PROJECT_DIR / "random_forest_pipeline.joblib",
}
THRESHOLDS_PATH = PROJECT_DIR / "thresholds.json"
COLUMNS_PATH = PROJECT_DIR / "feature_columns.json"
TRAIN_PATH = PROJECT_DIR / "model_ready_extended.csv"
DEMO_PATH = PROJECT_DIR / "traindemographics.csv"
PREV_PATH = PROJECT_DIR / "trainprevloans.csv"
LOG_PATH = PROJECT_DIR / "applications_log.csv"
REQUIRED = [*MODEL_FILES.values(), THRESHOLDS_PATH, COLUMNS_PATH, TRAIN_PATH]

# Same label-encoding the data-prep pipeline used (sklearn LabelEncoder = alphabetical)
ACCOUNT_TYPES = {"Current": 0, "Other": 1, "Savings": 2}
EMPLOYMENT = {"Contract": 0, "Permanent": 1, "Retired": 2,
              "Self-Employed": 3, "Student": 4, "Unemployed": 5}
BASE_BANK = "Access Bank"   # dropped by get_dummies(drop_first=True)

WILLINGNESS = {
    "loannumber", "prior_loan_count", "prior_default_rate", "rollover_count",
    "days_to_first_repayment", "prior_max_days_late", "prior_ontime_rate",
    "has_prior_history",
}
LABELS = {
    "loannumber": "Number of loans with us",
    "loanamount": "Loan amount requested",
    "termdays": "Repayment period",
    "bank_account_type": "Account type",
    "employment_status_clients": "Employment status",
    "prior_loan_count": "Number of previous loans",
    "prior_default_rate": "Past loans repaid >3 days late",
    "rollover_count": "Past loans repaid >30 days late",
    "days_to_first_repayment": "Average days vs. due date",
    "interest_ratio": "Interest charged on this loan",
    "app_hour": "Time of day applied",
    "app_dayofweek": "Day of week applied",
    "age": "Age",
    "prior_avg_loanamount": "Average size of past loans",
    "prior_avg_termdays": "Average length of past loans",
    "prior_max_days_late": "Longest past delay",
    "prior_ontime_rate": "Share of past loans repaid on time",
    "loan_to_prior_avg": "This loan vs. past loan sizes",
    "has_prior_history": "Has a borrowing history",
    "bank": "Bank",
}
_log_lock = threading.Lock()


def missing_files() -> list[str]:
    return [p.name for p in REQUIRED if not p.exists()]


# ----------------------------------------------------------------- loading --
@lru_cache(maxsize=1)
def models():
    return {name: joblib.load(path) for name, path in MODEL_FILES.items()}


@lru_cache(maxsize=1)
def reference():
    train = pd.read_csv(TRAIN_PATH)
    columns = json.loads(COLUMNS_PATH.read_text(encoding="utf-8"))
    return {
        "thresholds": json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8")),
        "columns": columns,
        "medians": train.drop(columns=["good_bad_flag"]).median(numeric_only=True).to_dict(),
        "interest": {int(k): float(v) for k, v in train.groupby("termdays")["interest_ratio"].median().items()},
        "pairs": set(zip(train["termdays"].astype(int), train["loanamount"].astype(float))),
        "age_range": (float(train["age"].min()), float(train["age"].max())),
        "amounts": [int(a) for a in sorted(train["loanamount"].unique())],
        "terms": sorted(int(t) for t in train["termdays"].unique()),
        "banks": [BASE_BANK] + sorted(c.removeprefix("bank_name_clients_")
                                      for c in columns if c.startswith("bank_name_clients_")),
    }


@lru_cache(maxsize=1)
def records():
    """Optional lender records used for 'find my record'. (None, None) if absent."""
    if not (DEMO_PATH.exists() and PREV_PATH.exists()):
        return None, None
    demo = pd.read_csv(DEMO_PATH)
    prev = pd.read_csv(PREV_PATH, parse_dates=["approveddate", "creationdate", "closeddate",
                                               "firstduedate", "firstrepaiddate"])
    return demo, prev


def lookup_available() -> bool:
    return records()[0] is not None


def sample_customer_id() -> str | None:
    _, prev = records()
    return None if prev is None else str(prev["customerid"].sample(1).iloc[0])


def lookup_customer(customer_id: str) -> dict | None:
    demo, prev = records()
    if prev is None:
        return None
    cid = customer_id.strip()
    rows = prev[prev["customerid"] == cid]
    if rows.empty:
        return None
    dl = (rows["firstrepaiddate"] - rows["firstduedate"]).dt.days
    on_time, very_late = int((dl <= 0).sum()), int((dl > 30).sum())
    late = int(((dl > 3) & (dl <= 30)).sum())
    slight = len(rows) - on_time - late - very_late          # 1-3 days late (and unknowns)
    rec = {"history": {
        "on_time": on_time, "slight": slight, "late": late, "very_late": very_late,
        "max_late": float(dl.max()) if dl.notna().any() else 0.0,
        "avg_late": round(float(dl.mean()), 1) if dl.notna().any() else 0.0,
        "avg_amount": round(float(rows["loanamount"].mean()), -2),
        "avg_term": round(float(rows["termdays"].mean())),
    }}
    d = demo[demo["customerid"] == cid]
    if not d.empty:
        d = d.iloc[0]
        if pd.notna(d["birthdate"]):
            rec["dob"] = pd.to_datetime(d["birthdate"]).date().isoformat()
        for key, col in (("bank", "bank_name_clients"), ("account", "bank_account_type"),
                         ("employment", "employment_status_clients")):
            if pd.notna(d[col]):
                rec[key] = str(d[col])
    return rec


# ------------------------------------------------------------- validation ---
def _num(v, name, lo, hi, integer=False):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a number.")
    if not (lo <= x <= hi) or x != x:
        raise ValueError(f"'{name}' must be between {lo} and {hi}.")
    return int(x) if integer else x


def validate(payload: dict) -> dict:
    """Return a clean application dict or raise ValueError with a user-safe message."""
    ref = reference()
    mode = payload.get("mode")
    if mode not in ("lookup", "manual", "first"):
        raise ValueError("Choose how to provide your borrowing history.")
    try:
        dob = date.fromisoformat(str(payload.get("dob")))
    except ValueError:
        raise ValueError("Enter a valid date of birth.")
    age = (date.today() - dob).days / 365.25
    if not 18 <= age <= 100:
        raise ValueError("Applicants must be 18 or older.")
    p = {"mode": mode, "dob": dob}
    for key, allowed in (("employment", EMPLOYMENT), ("account", ACCOUNT_TYPES), ("bank", ref["banks"])):
        if payload.get(key) not in allowed:
            raise ValueError(f"Choose a valid option for '{key}'.")
        p[key] = payload[key]
    p["amount"] = _num(payload.get("amount"), "amount", 0, 1e7)
    p["term"] = _num(payload.get("term"), "term", 0, 1000, integer=True)
    if int(p["amount"]) not in ref["amounts"] or p["term"] not in ref["terms"]:
        raise ValueError("Choose one of the available loan amounts and repayment periods.")

    if mode == "first":
        p["history"] = None
    else:
        h = payload.get("history") or {}
        p["history"] = {
            "on_time": _num(h.get("on_time"), "on time", 0, 60, True),
            "slight": _num(h.get("slight"), "1-3 days late", 0, 60, True),
            "late": _num(h.get("late"), "4-30 days late", 0, 60, True),
            "very_late": _num(h.get("very_late"), "over 30 days late", 0, 60, True),
            "avg_late": _num(h.get("avg_late"), "typical days vs. due date", -30, 120),
            "max_late": _num(h.get("max_late"), "longest delay", -30, 400),
            "avg_amount": _num(h.get("avg_amount"), "typical past loan", 5000, 100000),
            "avg_term": _num(h.get("avg_term"), "typical past period", 7, 120),
        }
        if sum(p["history"][k] for k in ("on_time", "slight", "late", "very_late")) == 0:
            raise ValueError("Enter at least one previous loan, or choose 'This is my first loan'.")
    return p


# -------------------------------------------------------- feature building --
def build_features(p: dict) -> pd.DataFrame:
    """Turn the applicant's answers into the exact 36-column model input."""
    ref = reference()
    columns, medians = ref["columns"], ref["medians"]
    h, now = p["history"], datetime.now()
    f = {c: 0 for c in columns}
    f.update(
        loanamount=float(p["amount"]), termdays=int(p["term"]),
        bank_account_type=ACCOUNT_TYPES[p["account"]],
        employment_status_clients=EMPLOYMENT[p["employment"]],
        interest_ratio=ref["interest"].get(int(p["term"]), medians["interest_ratio"]),
        app_hour=now.hour, app_dayofweek=now.weekday(),
        age=(date.today() - p["dob"]).days / 365.25,
    )
    if p["bank"] != BASE_BANK:
        f[f"bank_name_clients_{p['bank']}"] = 1

    if h is None:   # first loan: same treatment as training (count=0, rest median-imputed)
        for c in ("prior_default_rate", "rollover_count", "days_to_first_repayment",
                  "prior_avg_loanamount", "prior_avg_termdays", "prior_max_days_late",
                  "prior_ontime_rate", "loan_to_prior_avg"):
            f[c] = medians[c]
        f.update(prior_loan_count=0, loannumber=1, has_prior_history=0)
    else:
        n = h["on_time"] + h["slight"] + h["late"] + h["very_late"]
        f.update(
            prior_loan_count=n, loannumber=n + 1, has_prior_history=1,
            prior_default_rate=(h["late"] + h["very_late"]) / n,
            rollover_count=h["very_late"], days_to_first_repayment=h["avg_late"],
            prior_avg_loanamount=h["avg_amount"], prior_avg_termdays=h["avg_term"],
            prior_max_days_late=h["max_late"], prior_ontime_rate=h["on_time"] / n,
            loan_to_prior_avg=p["amount"] / h["avg_amount"],
        )
    return pd.DataFrame([f])[columns]


def score(X: pd.DataFrame) -> dict:
    thresholds = reference()["thresholds"]
    out = {}
    for name, pipe in models().items():
        pg = float(pipe.predict_proba(X)[:, 1][0])
        out[name] = {"p_good": pg, "threshold": float(thresholds[name]), "good": bool(pg >= thresholds[name])}
    return out


def recommendation(scores: dict) -> dict:
    votes = [s["good"] for s in scores.values()]
    if all(votes):
        return {"tier": "likely", "headline": "Looks good",
                "message": "Both scoring models see this request as likely to be repaid. "
                           "A loan officer will confirm the final decision."}
    if not any(votes):
        return {"tier": "refer", "headline": "Needs a loan officer's review",
                "message": "Both scoring models flag a higher chance of repayment difficulty for this request. "
                           "That is not a final decline - a loan officer will review it, and the options below may help."}
    return {"tier": "review", "headline": "Needs a closer look",
            "message": "The two scoring models disagree on this request, so a loan officer will review it manually."}


def contributions(X: pd.DataFrame, top: int = 7) -> list[dict]:
    """Per-feature push on the Logistic Regression log-odds of Good (coef x scaled input)."""
    pipe = models()["Logistic Regression"]
    scaler, clf = pipe.named_steps["scaler"], pipe.named_steps["clf"]
    contrib = pd.Series(clf.coef_[0] * scaler.transform(X)[0], index=X.columns)
    bank_cols = [c for c in contrib.index if c.startswith("bank_name_clients_")]
    bank = float(contrib[bank_cols].sum())
    contrib = contrib.drop(bank_cols)
    contrib["bank"] = bank
    rows = [{"feature": k, "factor": LABELS[k], "value": round(float(v), 4),
             "driver": "willingness" if k in WILLINGNESS else "ability"}
            for k, v in contrib.items()]
    rows.sort(key=lambda r: abs(r["value"]), reverse=True)
    return rows[:top]


def _outcome(p: dict) -> str:
    votes = [s["good"] for s in score(build_features(p)).values()]
    return "likely" if all(votes) else ("review" if any(votes) else "refer")


def what_if(p: dict) -> dict:
    ref = reference()
    amounts = [{"value": a, "outcome": _outcome({**p, "amount": a}), "current": a == p["amount"]}
               for a in ref["amounts"] if (p["term"], float(a)) in ref["pairs"]]
    terms = [{"value": t, "outcome": _outcome({**p, "term": t}), "current": t == p["term"]}
             for t in ref["terms"] if (t, float(p["amount"])) in ref["pairs"]]
    return {"amounts": amounts, "terms": terms}


def evaluate(p: dict) -> dict:
    """Full applicant-facing result for a validated application."""
    ref = reference()
    X = build_features(p)
    scores = score(X)
    interest = ref["interest"].get(p["term"], 0.0)
    notes = []
    if p["history"] is None:
        notes.append("First-time borrower: the models saw almost no first-time borrowers while learning, "
                     "so treat this as low-confidence.")
    if (p["term"], float(p["amount"])) not in ref["pairs"]:
        notes.append("This amount and period combination is rare or absent in the training data.")
    age = float(X["age"].iloc[0])
    if not ref["age_range"][0] <= age <= ref["age_range"][1]:
        notes.append("Your age is outside the range the models learned from.")
    return {
        **recommendation(scores),
        "loan": {"amount": p["amount"], "term": p["term"], "interest": interest,
                 "repay": round(p["amount"] * (1 + interest))},
        "notes": notes,
        "factors": contributions(X),
        "what_if": what_if(p),
        "scores": scores,
        "features": {k: round(float(v), 4) for k, v in X.iloc[0].items()},
    }


def log_application(p: dict) -> str:
    """Re-score server-side (never trust client-sent scores) and append to the CSV log."""
    X = build_features(p)
    scores = score(X)
    tier = recommendation(scores)["tier"]
    ref = "APP-" + uuid.uuid4().hex[:8].upper()
    row = X.copy()
    row.insert(0, "reference", ref)
    row.insert(1, "submitted_at", datetime.now().isoformat(timespec="seconds"))
    row["history_source"] = p["mode"]
    row["p_good_lr"] = scores["Logistic Regression"]["p_good"]
    row["p_good_rf"] = scores["Random Forest"]["p_good"]
    row["recommendation"] = tier
    with _log_lock:
        row.to_csv(LOG_PATH, mode="a", header=not LOG_PATH.exists(), index=False)
    return ref