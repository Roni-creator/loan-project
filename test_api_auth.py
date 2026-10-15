"""Authentication, authorization and applicant-isolation tests for the Flask API.

Run:  python -m pytest test_api_auth.py -q
These tests use a temporary SQLite database (CREDITSCORE_DB), so they never touch
the real creditscore.db. Model artifacts must exist (they do after build_all.py).
"""
import json

import pytest

import db

pytestmark = pytest.mark.skipif(
    not (db.DB_PATH.parent / "logistic_regression_pipeline.joblib").exists(),
    reason="run build_all.py / threshold_tuning.py first",
)

PASSWORD = "Str0ngPass1"
VALID_APPLICATION = {"mode": "first", "dob": "1992-01-01", "employment": "Permanent",
                     "bank": "Access Bank", "account": "Savings", "amount": 10000, "term": 30}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDITSCORE_DB", str(tmp_path / "test.db"))
    import webapp
    db.init_db()
    db.create_user("bm", "Bm@nger9pw", "business_manager")
    db.create_user("ca", "An@lyst9pw", "credit_analyst")
    db.create_user("lo", "L0anOff9pw", "loan_officer")
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def register(client, username, password=PASSWORD, full_name=None):
    resp = client.post("/api/auth/register",
                       json={"username": username, "password": password, "full_name": full_name})
    return resp


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def logout(client, csrf):
    return client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})


def csrf_of(resp):
    return resp.get_json()["csrf_token"]


# ------------------------------------------------------------ public/auth ----
def test_public_endpoints_need_no_auth(client):
    assert client.get("/api/meta").status_code == 200
    assert client.post("/api/score", json=VALID_APPLICATION).status_code == 200


def test_protected_endpoints_reject_anonymous(client):
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/staff/applications").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/lookup", json={"customer_id": "1"}).status_code == 401
    assert client.post("/api/applications", json=VALID_APPLICATION).status_code == 401


def test_register_login_me_and_hash_storage(client):
    resp = register(client, "alice", full_name="Alice A")
    assert resp.status_code == 200
    assert resp.get_json()["user"]["role"] == "applicant"       # role is never client-chosen
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["user"]["username"] == "alice"

    with db.connect() as con:
        stored = con.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
    assert PASSWORD.encode() not in stored                       # bcrypt hash, not plaintext


def test_duplicate_username_is_rejected(client):
    assert register(client, "alice").status_code == 200
    assert register(client, "alice", password="Oth3rPass1").status_code == 409


def test_weak_password_and_username_are_rejected(client):
    assert register(client, "short", password="abc").status_code == 400
    assert register(client, "no", password=PASSWORD).status_code == 400


def test_invalid_credentials_rejected_and_audited(client):
    resp = login(client, "alice", "wrong-password")
    assert resp.status_code == 401
    assert register(client, "alice").status_code == 200
    assert login(client, "alice", "wrong-password").status_code == 401
    assert login(client, "alice", PASSWORD).status_code == 200
    with db.connect() as con:
        failed = con.execute("SELECT COUNT(*) FROM audit_log WHERE action='login_failed'").fetchone()[0]
    assert failed >= 1


def test_logout_invalidates_the_session(client):
    register(client, "alice")
    csrf = csrf_of(client.get("/api/auth/me"))
    assert client.post("/api/applications", json=VALID_APPLICATION,
                       headers={"X-CSRF-Token": csrf}).status_code == 201
    assert logout(client, csrf).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/applications").status_code == 401       # cookie no longer works
    assert client.post("/api/applications", json=VALID_APPLICATION,
                       headers={"X-CSRF-Token": csrf}).status_code == 401


def test_csrf_token_required_for_writes(client):
    register(client, "alice")
    assert client.post("/api/applications", json=VALID_APPLICATION).status_code == 403
    assert client.post("/api/applications", json=VALID_APPLICATION,
                       headers={"X-CSRF-Token": "not-the-token"}).status_code == 403


def test_session_token_is_hashed_at_rest(client):
    register(client, "alice")
    cookie = client.get_cookie("loan_session").value
    with db.connect() as con:
        stored = con.execute("SELECT session_id FROM auth_sessions").fetchone()[0]
    assert stored != cookie and len(stored) == 64                # sha256 hex


# ------------------------------------------------------- applicant portal ----
def test_application_is_persisted_with_real_predictions(client):
    register(client, "alice")
    csrf = csrf_of(client.get("/api/auth/me"))
    resp = client.post("/api/applications", json=VALID_APPLICATION, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["reference"].startswith("APP-")
    assert set(body["scores"]) == {"Logistic Regression", "Random Forest"}

    with db.connect() as con:
        app_row = con.execute("SELECT * FROM loan_applications WHERE reference=?",
                              (body["reference"],)).fetchone()
        preds = con.execute("SELECT model_name, p_good FROM predictions WHERE applicant_id=?",
                            (app_row["applicant_id"],)).fetchall()
    assert app_row is not None and app_row["status"] == "submitted"
    assert {p["model_name"] for p in preds} == {"Logistic Regression", "Random Forest"}
    assert all(0.0 <= p["p_good"] <= 1.0 for p in preds)

    history = client.get("/api/applications").get_json()["applications"]
    assert len(history) == 1 and history[0]["reference"] == body["reference"]

    detail = client.get(f"/api/applications/{body['application_id']}")
    assert detail.status_code == 200
    assert detail.get_json()["application"]["factors"]                  # explanations present


def test_applicants_cannot_read_each_others_records(client):
    register(client, "alice")
    csrf = csrf_of(client.get("/api/auth/me"))
    app_id = client.post("/api/applications", json=VALID_APPLICATION,
                         headers={"X-CSRF-Token": csrf}).get_json()["application_id"]

    other = client.application.test_client()
    register(other, "bob")
    assert other.get(f"/api/applications/{app_id}").status_code == 404   # not 403: no leak
    assert other.get("/api/applications").get_json()["applications"] == []


# --------------------------------------------------------------- roles -------
def test_applicant_cannot_reach_staff_endpoints(client):
    register(client, "alice")
    assert client.get("/api/staff/summary").status_code == 403
    assert client.get("/api/staff/applications").status_code == 403
    assert client.get("/api/staff/models").status_code == 403


def test_staff_role_matrix(client):
    officer = client
    login(officer, "lo", "L0anOff9pw")
    assert officer.get("/api/staff/applications").status_code == 200
    assert officer.get("/api/staff/models").status_code == 403        # analyst-only
    csrf = csrf_of(officer.get("/api/auth/me"))
    assert officer.post("/api/applications", json=VALID_APPLICATION,
                        headers={"X-CSRF-Token": csrf}).status_code == 403   # applicant-only

    analyst = client.application.test_client()
    login(analyst, "ca", "An@lyst9pw")
    assert analyst.get("/api/staff/models").status_code == 200
    acsrf = csrf_of(analyst.get("/api/auth/me"))
    assert analyst.post("/api/staff/applications/1/decision", json={"decision": "approved"},
                        headers={"X-CSRF-Token": acsrf}).status_code == 403

    manager = client.application.test_client()
    login(manager, "bm", "Bm@nger9pw")
    assert manager.get("/api/staff/summary").status_code == 200
    assert manager.get("/api/staff/models").status_code == 403


def test_officer_workflow_assign_and_decide(client):
    # applicant files an application
    applicant = client.application.test_client()
    register(applicant, "alice")
    acsrf = csrf_of(applicant.get("/api/auth/me"))
    app_id = applicant.post("/api/applications", json=VALID_APPLICATION,
                            headers={"X-CSRF-Token": acsrf}).get_json()["application_id"]

    officer = client.application.test_client()
    login(officer, "lo", "L0anOff9pw")
    ocsrf = csrf_of(officer.get("/api/auth/me"))

    # cannot decide before claiming
    assert officer.post(f"/api/staff/applications/{app_id}/decision",
                        json={"decision": "approved", "note": "fine"},
                        headers={"X-CSRF-Token": ocsrf}).status_code == 403
    # claim then decide
    assert officer.post(f"/api/staff/applications/{app_id}/assign",
                        headers={"X-CSRF-Token": ocsrf}).status_code == 200
    assert officer.post(f"/api/staff/applications/{app_id}/decision",
                        json={"decision": "approved", "note": "verified"},
                        headers={"X-CSRF-Token": ocsrf}).status_code == 200

    detail = officer.get(f"/api/staff/applications/{app_id}").get_json()["application"]
    assert detail["status"] == "approved"
    assert detail["decisions"][0]["decision"] == "approved"
    assert detail["scores"] and detail["factors"]            # real assessment, not fabricated


def test_decision_note_required_for_decline(client):
    applicant = client.application.test_client()
    register(applicant, "alice")
    acsrf = csrf_of(applicant.get("/api/auth/me"))
    app_id = applicant.post("/api/applications", json=VALID_APPLICATION,
                            headers={"X-CSRF-Token": acsrf}).get_json()["application_id"]
    officer = client.application.test_client()
    login(officer, "lo", "L0anOff9pw")
    ocsrf = csrf_of(officer.get("/api/auth/me"))
    officer.post(f"/api/staff/applications/{app_id}/assign", headers={"X-CSRF-Token": ocsrf})
    assert officer.post(f"/api/staff/applications/{app_id}/decision",
                        json={"decision": "declined"},
                        headers={"X-CSRF-Token": ocsrf}).status_code == 400


def test_invalid_application_input_is_rejected_not_fabricated(client):
    register(client, "alice")
    csrf = csrf_of(client.get("/api/auth/me"))
    bad = dict(VALID_APPLICATION, amount=-5)
    assert client.post("/api/applications", json=bad,
                       headers={"X-CSRF-Token": csrf}).status_code == 400
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM loan_applications").fetchone()[0] == 0
