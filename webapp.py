"""
web_app.py - Loan applicant web portal (Flask backend + static HTML/JS front end).

Run:   python web_app.py          then open  http://127.0.0.1:8000

Routes
  GET  /                  the applicant portal (static/index.html)
  GET  /api/meta          dropdown options, loan amounts/periods, whether record lookup is available
  GET  /api/sample-id     a random customer ID (demo helper)
  POST /api/lookup        {customer_id}  -> history + profile from the lender's records
  POST /api/score         application    -> outcome, reasons, what-if table
  POST /api/submit        application + consent -> logs to applications_log.csv, returns reference

No login (proof of concept). Scores are always recomputed server-side.
"""
from __future__ import annotations

import sys

from flask import Flask, jsonify, request, send_from_directory

import portal_core as core

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024   # applications are tiny; reject anything bigger


def _json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Send a JSON object.")
    return data


@app.errorhandler(ValueError)
def bad_request(err):
    return jsonify(error=str(err)), 400


@app.after_request
def no_store_api(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/meta")
def meta():
    ref = core.reference()
    return jsonify(
        banks=ref["banks"], employment=list(core.EMPLOYMENT), accounts=list(core.ACCOUNT_TYPES),
        amounts=ref["amounts"], terms=ref["terms"], interest=ref["interest"],
        pairs=[[t, int(a)] for t, a in sorted(ref["pairs"])],
        lookup=core.lookup_available(),
    )


@app.get("/api/sample-id")
def sample_id():
    cid = core.sample_customer_id()
    if cid is None:
        return jsonify(error="Record lookup is not available."), 404
    return jsonify(customer_id=cid)


@app.post("/api/lookup")
def lookup():
    cid = str(_json().get("customer_id", "")).strip()
    if not cid or len(cid) > 64:
        raise ValueError("Enter your customer ID.")
    rec = core.lookup_customer(cid)
    if rec is None:
        return jsonify(error="We couldn't find that customer ID. Check it, or enter your history yourself."), 404
    return jsonify(rec)


@app.post("/api/score")
def score_application():
    return jsonify(core.evaluate(core.validate(_json())))


@app.post("/api/submit")
def submit():
    data = _json()
    if data.get("consent") is not True:
        raise ValueError("Please confirm the details and give your consent to submit.")
    return jsonify(reference=core.log_application(core.validate(data)))


def main():
    missing = core.missing_files()
    if missing:
        sys.exit("Missing files (run threshold_tuning.py first): " + ", ".join(missing))
    core.models(), core.reference()          # fail fast on bad artifacts
    app.run(host="127.0.0.1", port=8000, debug=False)


if __name__ == "__main__":
    main()