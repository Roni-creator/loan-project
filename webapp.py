"""
webapp.py - Flask backend for the loan portal (React frontend + JSON API).

Run:   python webapp.py          then open  http://127.0.0.1:8000

The React app is served from frontend/dist when it has been built
(`cd frontend && npm run build`); otherwise the previous static page is used.

Routes
  GET  /                  the React app (or legacy static/index.html)
  GET  /api/meta          dropdown options, loan amounts/periods, lookup availability
  POST /api/score         application  -> outcome, reasons, what-if   (public; read-only)
  GET  /api/sample-id     a random customer ID (demo helper)          (requires login)
  POST /api/lookup        {customer_id} -> history + profile          (requires login)
  POST /api/submit        application + consent -> DB record + reference (applicant only)

Authentication, applicant-portal and staff endpoints live in api_routes.py and are
registered below; they all verify the server-side session and enforce roles.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import api_routes
import auth
import db
import portal_core as core

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "frontend" / "dist"

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

api_routes.register(app)


def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# ----------------------------------------------------------- auth plumbing ---
@app.before_request
def _load_auth_and_guard_csrf():
    auth.load_current_user()
    # CSRF is only meaningful for logged-in callers; without a session the route
    # decorators return 401 (so anonymous probes get the honest status).
    if (request.path.startswith("/api/") and request.method in auth.UNSAFE_METHODS
            and auth.current_user() is not None
            and request.path not in auth.CSRF_EXEMPT and not auth.csrf_ok()):
        return jsonify(error="Invalid or missing CSRF token."), 403
    return None


@app.after_request
def _security_headers(response):
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Request body is too large."), 413


@app.errorhandler(500)
def server_error(_):
    return jsonify(error="Something went wrong on the server."), 500


def _spa() -> bool:
    return (DIST_DIR / "index.html").exists()


# ------------------------------------------------------------------ pages ----
@app.get("/")
def index():
    if _spa():
        return send_from_directory(str(DIST_DIR), "index.html")
    return send_from_directory("static", "index.html")


@app.get("/<path:path>")
def frontend(path: str):
    if path.startswith("api/") or path.startswith("static/"):
        return jsonify(error="Not found."), 404
    if _spa():
        candidate = DIST_DIR / path
        if candidate.is_file():
            return send_from_directory(str(DIST_DIR), path)
        return send_from_directory(str(DIST_DIR), "index.html")
    return send_from_directory("static", "index.html")


# ----------------------------------------------------------- public API ------
@app.get("/api/meta")
def meta():
    ref = core.reference()
    return jsonify(
        banks=ref["banks"], employment=list(core.EMPLOYMENT), accounts=list(core.ACCOUNT_TYPES),
        amounts=ref["amounts"], terms=ref["terms"], interest=ref["interest"],
        pairs=[[t, int(a)] for t, a in sorted(ref["pairs"])],
        lookup=core.lookup_available(),
    )


@app.post("/api/score")
def score_application():
    """Read-only preview. Requires no login and stores nothing."""
    return jsonify(core.evaluate(core.validate(_json_body())))


# ---------------------------------------------------- authenticated API ------
@app.get("/api/sample-id")
@auth.require_auth
def sample_id():
    cid = core.sample_customer_id()
    if cid is None:
        return jsonify(error="Record lookup is not available."), 404
    return jsonify(customer_id=cid)


@app.post("/api/lookup")
@auth.require_auth
def lookup():
    cid = str(_json_body().get("customer_id", "")).strip()
    if not cid or len(cid) > 64:
        return jsonify(error="Enter your customer ID."), 400
    rec = core.lookup_customer(cid)
    if rec is None:
        return jsonify(error="We couldn't find that customer ID. Check it, or enter your history yourself."), 404
    return jsonify(rec)


@app.post("/api/submit")
@auth.require_roles(db.APPLICANT_ROLE)
def submit():
    """Legacy alias for POST /api/applications (now database-backed)."""
    data = _json_body()
    if data.get("consent") is not True:
        return jsonify(error="Please confirm the details and give your consent to submit."), 400
    body, status = api_routes.submit_application(data)
    return jsonify(body), status


def main():
    missing = core.missing_files()
    if missing:
        sys.exit("Missing files (run threshold_tuning.py first): " + ", ".join(missing))
    core.models(), core.reference()          # fail fast on bad artifacts
    db.init_db()                             # apply schema/migrations on startup
    app.run(host="127.0.0.1", port=8000, debug=False)


if __name__ == "__main__":
    main()
