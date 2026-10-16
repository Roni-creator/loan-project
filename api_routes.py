"""
api_routes.py - authenticated JSON API for the React frontend.

Reuses portal_core for every model call (validation, the 36-column feature row,
both trained pipelines, Logistic-Regression explanations). Nothing here re-implements
scoring or invents predictions - staff see exactly what the models output.

Endpoints
  Public
    POST /api/auth/register   applicant self-registration with email (role forced to 'applicant')
    POST /api/auth/login      email + password check + session cookie
    GET  /api/auth/me         current account + CSRF token
    POST /api/auth/logout     destroy the server-side session
  Applicant (role = applicant)
    POST /api/applications            validate, score, persist, return reference
    GET  /api/applications            own submission history
    GET  /api/applications/<id>       own application detail + explanation
  Staff (business_manager / credit_analyst / loan_officer)
    GET  /api/staff/summary                     portfolio counts + thresholds (all staff;
                                                business managers get aggregates, no personal data)
    GET  /api/staff/applications                application list (credit_analyst / loan_officer;
                                                a loan officer sees the unassigned queue + own cases)
    GET  /api/staff/applications/<id>           full assessment + explanation (same roles)
    POST /api/staff/applications/<id>/assign    loan_officer claims a case
    POST /api/staff/applications/<id>/decision  loan_officer decision + note
    GET  /api/staff/models                      model metrics/drivers (credit_analyst)
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date

from flask import Blueprint, g, jsonify, request

import auth
import db
import portal_core as core

bp = Blueprint("api", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
DECISIONS = ("approved", "declined", "more_info")
STATUSES = ("submitted", "assigned", "approved", "declined", "more_info")


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _bad(message: str, code: int = 400):
    return jsonify(error=message), code


# ----------------------------------------------------------- serialization ---
def _json_p(p: dict) -> dict:
    """JSON-safe copy of a validated application (dates -> ISO strings)."""
    out = dict(p)
    out["dob"] = p["dob"].isoformat()
    return out


def _parse_p(raw: dict) -> dict:
    p = dict(raw)
    p["dob"] = date.fromisoformat(raw["dob"])
    return p


def _application_summary(row) -> dict:
    answers = json.loads(row["answers"]) if row["answers"] else {}
    return {
        "application_id": row["application_id"],
        "reference": row["reference"],
        "status": row["status"],
        "tier": row["tier"],
        "amount": answers.get("amount"),
        "term": answers.get("term"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _staff_application_row(row, include_personal: bool = True) -> dict:
    data = _application_summary(row)
    keys = row.keys()
    if "applicant_username" in keys:
        data["assigned_officer_id"] = row["assigned_officer_id"]
        data["officer_username"] = row["officer_username"]
        if include_personal:
            data["applicant_username"] = row["applicant_username"]
            data["applicant_name"] = row["applicant_name"]
    return data


def _assessment(p: dict) -> dict:
    """Recompute the model assessment + explanation for a stored application."""
    X = core.build_features(p)
    scores = core.score(X)
    return {
        "recommendation": core.recommendation(scores),
        "scores": scores,
        "factors": core.contributions(X),
        "features": {k: round(float(v), 4) for k, v in X.iloc[0].items()},
    }


# --------------------------------------------------------------- auth --------
def _email_taken(email: str) -> bool:
    with db.connect() as con:
        return con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() is not None


def _username_taken(username: str) -> bool:
    with db.connect() as con:
        return con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None


@bp.post("/api/auth/register")
def register():
    data = _json_body()
    username = str(data.get("username", "")).strip()
    email = db.normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    full_name = str(data.get("full_name", "")).strip() or None
    if not USERNAME_RE.match(username):
        return _bad("Username must be 3-32 characters (letters, numbers, . _ -).")
    if not db.valid_email(email):
        return _bad("Enter a valid email address.")
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return _bad("Password must be at least 8 characters and include a letter and a number.")
    if _email_taken(email):
        return _bad("That email address is already registered.", 409)
    if _username_taken(username):
        return _bad("That username is already taken.", 409)
    try:
        # The public registration path always creates an applicant; the role is
        # never taken from the request body.
        user_id = db.create_user(username, password, db.APPLICANT_ROLE, full_name, email=email)
    except sqlite3.IntegrityError:
        # Lost the race between the check above and the insert.
        return _bad("That email address or username is already registered.", 409)
    session = db.create_session(user_id)
    user = {"user_id": user_id, "username": username, "email": email,
            "role": db.APPLICANT_ROLE, "full_name": full_name}
    auth.audit("register", "applicant self-registration", user_id=user_id, actor=username)
    resp = jsonify(user=auth.public_user(user), csrf_token=session["csrf_token"],
                   expires_at=session["expires_at"])
    return auth.set_session_cookie(resp, session["token"], session["expires_at"])


@bp.post("/api/auth/login")
def login():
    data = _json_body()
    email = db.normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    user = db.verify_user(email, password) if email and password else None
    if user is None:
        # Generic message: it must not reveal whether the email has an account.
        db.log_audit("login_failed", "invalid credentials", actor=email or None,
                     ip=request.remote_addr)
        return _bad("Invalid email or password.", 401)
    session = db.create_session(user["user_id"])
    auth.audit("login", f"role={user['role']}", user_id=user["user_id"], actor=user["username"])
    resp = jsonify(user=auth.public_user(user), csrf_token=session["csrf_token"],
                   expires_at=session["expires_at"])
    return auth.set_session_cookie(resp, session["token"], session["expires_at"])


@bp.post("/api/auth/logout")
@auth.require_auth
def logout():
    token = auth.session_token()
    db.delete_session(token)
    auth.audit("logout")
    return auth.clear_session_cookie(jsonify(ok=True))


@bp.get("/api/auth/me")
@auth.require_auth
def me():
    return jsonify(user=auth.public_user(auth.current_user()), csrf_token=auth.current_csrf())


# ------------------------------------------------------------ applicant ------
def submit_application(payload: dict):
    """Validate, score (real models) and persist a submission for the current user.

    Shared by POST /api/applications and the legacy POST /api/submit.
    """
    user = auth.current_user()
    try:
        p = core.validate(payload)
    except ValueError as error:
        return {"error": str(error)}, 400
    X = core.build_features(p)
    scores = core.score(X)
    tier = core.recommendation(scores)["tier"]

    model_scores = {
        name: {"p_bad": 1 - s["p_good"], "p_good": s["p_good"],
               "threshold": s["threshold"], "decision": "Good" if s["good"] else "Bad"}
        for name, s in scores.items()
    }
    features = {k: round(float(v), 6) for k, v in X.iloc[0].items()}
    applicant_id = db.record_scored_application(features, model_scores, user_id=user["user_id"])
    reference = "APP-" + uuid.uuid4().hex[:8].upper()
    application_id = db.create_application(reference, user["user_id"], _json_p(p), tier,
                                           applicant_id=applicant_id)
    auth.audit("application_submitted", f"reference={reference} tier={tier}")
    return {"application_id": application_id, "reference": reference, "status": "submitted",
            "tier": tier, "scores": scores}, 201


@bp.post("/api/applications")
@auth.require_roles(db.APPLICANT_ROLE)
def create_application():
    body, status = submit_application(_json_body())
    return jsonify(body), status


@bp.get("/api/applications")
@auth.require_roles(db.APPLICANT_ROLE)
def my_applications():
    rows = db.list_applications(auth.current_user()["user_id"])
    return jsonify(applications=[_application_summary(r) for r in rows])


@bp.get("/api/applications/<int:application_id>")
@auth.require_roles(db.APPLICANT_ROLE)
def my_application(application_id: int):
    user = auth.current_user()
    row = db.get_application(application_id)
    # Ownership check: a missing row and someone else's row look identical.
    if row is None or row["user_id"] != user["user_id"]:
        return _bad("Application not found.", 404)
    p = _parse_p(json.loads(row["answers"]))
    detail = _application_summary(row)
    detail["answers"] = json.loads(row["answers"])
    detail.update(_assessment(p))
    detail["decisions"] = [
        {"decision": d["decision"], "note": d["note"], "created_at": d["created_at"]}
        for d in db.list_application_decisions(application_id)
    ]
    return jsonify(application=detail)


# ---------------------------------------------------------------- staff ------
@bp.get("/api/staff/summary")
@auth.require_roles(*db.STAFF_ROLES)
def staff_summary():
    user = auth.current_user()
    # A loan officer's figures cover only what they may act on (unassigned + own);
    # managers and analysts get the whole portfolio.
    scope_officer = user["user_id"] if user["role"] == "loan_officer" else None
    rows = db.list_staff_applications(scope_officer)
    # Business managers see aggregate management information only, never personal
    # applicant details; analysts and officers may see them.
    include_personal = user["role"] != "business_manager"
    by_status = {s: 0 for s in STATUSES}
    by_tier = {"likely": 0, "review": 0, "refer": 0}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    with db.connect() as con:
        users = con.execute(
            "SELECT role, COUNT(*) AS n FROM users GROUP BY role").fetchall()
        runs = con.execute(
            "SELECT model_name, setting, threshold, accuracy, precision_bad, recall_bad,"
            " f1_bad, roc_auc, pr_auc_bad FROM model_runs ORDER BY model_name, setting").fetchall()
    frequencies = {u["role"]: u["n"] for u in users}
    mine = (sum(1 for r in rows if r["assigned_officer_id"] == user["user_id"])
            if user["role"] == "loan_officer" else None)
    return jsonify(
        total_applications=len(rows),
        by_status=by_status,
        by_tier=by_tier,
        accounts=frequencies,
        assigned_to_me=mine,
        recent=[_staff_application_row(r, include_personal) for r in rows[:10]],
        model_runs=[dict(r) for r in runs],
        thresholds=core.reference()["thresholds"],
    )


@bp.get("/api/staff/applications")
@auth.require_roles("credit_analyst", "loan_officer")
def staff_applications():
    user = auth.current_user()
    scope_officer = user["user_id"] if user["role"] == "loan_officer" else None
    rows = db.list_staff_applications(scope_officer)
    return jsonify(applications=[_staff_application_row(r) for r in rows])


@bp.get("/api/staff/applications/<int:application_id>")
@auth.require_roles("credit_analyst", "loan_officer")
def staff_application(application_id: int):
    user = auth.current_user()
    row = db.get_application(application_id)
    if row is None:
        return _bad("Application not found.", 404)
    # A loan officer may only open the unassigned queue and their own caseload.
    if user["role"] == "loan_officer" and row["assigned_officer_id"] not in (None, user["user_id"]):
        auth.audit("unauthorized", f"GET application {application_id} (assigned to another officer)")
        return _bad("That application is assigned to another officer.", 403)
    with db.connect() as con:
        full = con.execute("""
            SELECT a.*, u.username AS applicant_username, u.full_name AS applicant_name,
                   o.username AS officer_username
            FROM loan_applications a
            JOIN users u ON u.user_id = a.user_id
            LEFT JOIN users o ON o.user_id = a.assigned_officer_id
            WHERE a.application_id = ?""", (application_id,)).fetchone()
    p = _parse_p(json.loads(row["answers"]))
    detail = _staff_application_row(full)
    detail["answers"] = json.loads(row["answers"])
    detail.update(_assessment(p))
    detail["decisions"] = [
        {"decision": d["decision"], "note": d["note"], "officer": d["officer_username"],
         "created_at": d["created_at"]}
        for d in db.list_application_decisions(application_id)
    ]
    return jsonify(application=detail)


@bp.post("/api/staff/applications/<int:application_id>/assign")
@auth.require_roles("loan_officer")
def assign(application_id: int):
    user = auth.current_user()
    row = db.get_application(application_id)
    if row is None:
        return _bad("Application not found.", 404)
    if row["assigned_officer_id"] not in (None, user["user_id"]):
        return _bad("This application is already assigned to another officer.", 409)
    db.assign_application(application_id, user["user_id"])
    auth.audit("application_assigned", f"id={application_id}")
    return jsonify(ok=True, assigned_officer_id=user["user_id"], status="assigned")


@bp.post("/api/staff/applications/<int:application_id>/decision")
@auth.require_roles("loan_officer")
def decide(application_id: int):
    user = auth.current_user()
    body = _json_body()
    decision = str(body.get("decision", "")).strip()
    note = str(body.get("note", "")).strip()
    if decision not in DECISIONS:
        return _bad("Decision must be one of: " + ", ".join(DECISIONS) + ".")
    row = db.get_application(application_id)
    if row is None:
        return _bad("Application not found.", 404)
    if row["assigned_officer_id"] != user["user_id"]:
        return _bad("Claim this application before recording a decision.", 403)
    if decision in ("declined", "more_info") and not note:
        return _bad("Please add a note explaining the decision.")
    db.decide_application(application_id, user["user_id"], decision, note)
    auth.audit("application_decision", f"id={application_id} decision={decision}")
    return jsonify(ok=True, status=decision)


@bp.get("/api/staff/models")
@auth.require_roles("credit_analyst")
def staff_models():
    with db.connect() as con:
        runs = con.execute(
            "SELECT * FROM model_runs ORDER BY model_name, setting").fetchall()
    drivers = []
    path = core.PROJECT_DIR / "feature_importance.csv"
    if path.exists():
        import pandas as pd
        imp = pd.read_csv(path)
        if {"feature", "rf_importance"}.issubset(imp.columns):
            top = imp.nlargest(10, "rf_importance")
            drivers = [{"feature": r.feature, "rf_importance": float(r.rf_importance)}
                       for r in top.itertuples()]
    return jsonify(thresholds=core.reference()["thresholds"],
                   model_runs=[dict(r) for r in runs], top_drivers=drivers)


def register(app) -> None:
    app.register_blueprint(bp)
