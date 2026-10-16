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
    db.create_user("bm", "Bm@nger9pw", "business_manager", email="bm@example.com")
    db.create_user("ca", "An@lyst9pw", "credit_analyst", email="ca@example.com")
    db.create_user("lo", "L0anOff9pw", "loan_officer", email="lo@example.com")
    webapp.app.config["TESTING"] = True
    return webapp.app.test_client()


def register(client, username, password=PASSWORD, full_name=None, email=None):
    if email is None:
        email = f"{username}@example.com"
    resp = client.post("/api/auth/register",
                       json={"username": username, "email": email, "password": password,
                             "full_name": full_name})
    return resp


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


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
    body = resp.get_json()
    assert body["user"]["role"] == "applicant"       # role is never client-chosen
    assert body["user"]["email"] == "alice@example.com"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["user"]["username"] == "alice"
    assert me.get_json()["user"]["email"] == "alice@example.com"

    with db.connect() as con:
        stored = con.execute("SELECT password_hash FROM users WHERE username='alice'").fetchone()[0]
    text = stored.decode() if isinstance(stored, (bytes, bytearray)) else stored
    assert PASSWORD not in text                                  # a hash, never the plaintext
    assert text.startswith(("scrypt:", "pbkdf2:"))               # werkzeug-format hash
    assert db.verify_password(stored, PASSWORD) and not db.verify_password(stored, "wrong")


def test_legacy_bcrypt_password_still_logs_in_and_is_upgraded(client):
    """Accounts hashed by an earlier release keep working and are migrated on login."""
    import bcrypt
    legacy = bcrypt.hashpw(b"LegacyPass9", bcrypt.gensalt())
    with db.connect() as con:
        con.execute("INSERT INTO users(username, email, password_hash, role) VALUES (?,?,?,?)",
                    ("legacy", "legacy@example.com", legacy, "loan_officer"))
    assert login(client, "legacy@example.com", "Nope12345").status_code == 401   # wrong password fails
    assert login(client, "legacy@example.com", "LegacyPass9").status_code == 200  # correct one succeeds
    with db.connect() as con:
        stored = con.execute("SELECT password_hash FROM users WHERE username='legacy'").fetchone()[0]
    text = stored.decode() if isinstance(stored, (bytes, bytearray)) else stored
    assert text.startswith(("scrypt:", "pbkdf2:"))                # transparently upgraded
    assert db.verify_password(stored, "LegacyPass9")
    assert login(client.application.test_client(), "legacy@example.com", "LegacyPass9").status_code == 200


def test_duplicate_username_is_rejected(client):
    assert register(client, "alice").status_code == 200
    # Same username but a different email: the username is still the blocker.
    assert register(client, "alice", email="alice.other@example.com").status_code == 409


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert register(client, "alice", email="Alice@Example.com").status_code == 200
    # Same address, different case and surrounding spaces, another username.
    assert register(client, "alicia", email="  alice@example.COM ").status_code == 409
    with db.connect() as con:
        stored = con.execute("SELECT email FROM users WHERE username='alice'").fetchone()[0]
    assert stored == "alice@example.com"                          # normalised at rest


def test_registration_requires_a_valid_email(client):
    assert register(client, "noemail", email="").status_code == 400
    assert register(client, "bademail", email="not-an-email").status_code == 400


def test_login_is_case_and_whitespace_insensitive(client):
    register(client, "alice", email="Alice@Example.com")
    assert login(client, "  ALICE@example.COM  ", PASSWORD).status_code == 200


def test_login_error_is_generic(client):
    register(client, "alice")
    unknown = login(client, "nobody@example.com", PASSWORD)
    wrong = login(client, "alice@example.com", "wrong-password")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json()["error"] == wrong.get_json()["error"] == "Invalid email or password."


def test_weak_password_and_username_are_rejected(client):
    assert register(client, "short", password="abc").status_code == 400
    assert register(client, "no", password=PASSWORD).status_code == 400


def test_invalid_credentials_rejected_and_audited(client):
    assert login(client, "ghost@example.com", PASSWORD).status_code == 401
    register(client, "alice")
    assert login(client, "alice@example.com", "wrong-password").status_code == 401
    assert login(client, "alice@example.com", PASSWORD).status_code == 200
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
    login(officer, "lo@example.com", "L0anOff9pw")
    assert officer.get("/api/staff/applications").status_code == 200
    assert officer.get("/api/staff/models").status_code == 403        # analyst-only
    csrf = csrf_of(officer.get("/api/auth/me"))
    assert officer.post("/api/applications", json=VALID_APPLICATION,
                        headers={"X-CSRF-Token": csrf}).status_code == 403   # applicant-only

    analyst = client.application.test_client()
    login(analyst, "ca@example.com", "An@lyst9pw")
    assert analyst.get("/api/staff/models").status_code == 200
    acsrf = csrf_of(analyst.get("/api/auth/me"))
    assert analyst.post("/api/staff/applications/1/decision", json={"decision": "approved"},
                        headers={"X-CSRF-Token": acsrf}).status_code == 403

    manager = client.application.test_client()
    login(manager, "bm@example.com", "Bm@nger9pw")
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
    login(officer, "lo@example.com", "L0anOff9pw")
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
    login(officer, "lo@example.com", "L0anOff9pw")
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


# ------------------------------------------- role scopes / data separation ----
def _submit(applicant, amount=10000):
    """Register 'alice' on a fresh client and file one application."""
    register(applicant, "alice")
    csrf = csrf_of(applicant.get("/api/auth/me"))
    resp = applicant.post("/api/applications", json=dict(VALID_APPLICATION, amount=amount),
                          headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 201
    return resp.get_json()


def test_lookup_and_sample_are_staff_only(client):
    # An applicant must not be able to pull a (shared) dataset record as their own.
    register(client, "alice")
    csrf = csrf_of(client.get("/api/auth/me"))
    assert client.post("/api/lookup", json={"customer_id": "1"},
                       headers={"X-CSRF-Token": csrf}).status_code == 403
    assert client.get("/api/sample-id").status_code == 403

    # Staff may still use the dataset lookup for review.
    officer = client.application.test_client()
    login(officer, "lo@example.com", "L0anOff9pw")
    assert officer.get("/api/sample-id").status_code == 200


def test_role_is_read_from_the_session_not_the_client(client):
    register(client, "alice")                      # applicant session
    # Spoofed role via header/body must not grant staff access.
    assert client.get("/api/staff/summary",
                      headers={"X-Role": "business_manager"}).status_code == 403
    assert client.get("/api/staff/applications",
                      headers={"X-User-Role": "credit_analyst"}).status_code == 403
    csrf = csrf_of(client.get("/api/auth/me"))
    assert client.post("/api/staff/applications/1/assign", json={"role": "loan_officer"},
                       headers={"X-CSRF-Token": csrf}).status_code == 403


def test_two_applicants_have_distinct_linked_records(client):
    alice = client.application.test_client()
    a = _submit(alice)
    bob = client.application.test_client()
    register(bob, "bob")
    bcsrf = csrf_of(bob.get("/api/auth/me"))
    b = bob.post("/api/applications", json=dict(VALID_APPLICATION, amount=20000),
                 headers={"X-CSRF-Token": bcsrf}).get_json()
    assert a["reference"] != b["reference"]

    with db.connect() as con:
        rows = {r["reference"]: r for r in con.execute("SELECT * FROM loan_applications")}
        a_row, b_row = rows[a["reference"]], rows[b["reference"]]
        a_name = con.execute("SELECT username FROM users WHERE user_id=?", (a_row["user_id"],)).fetchone()[0]
        b_name = con.execute("SELECT username FROM users WHERE user_id=?", (b_row["user_id"],)).fetchone()[0]
        a_owner = con.execute("SELECT created_by FROM applicants WHERE applicant_id=?",
                              (a_row["applicant_id"],)).fetchone()[0]
        b_owner = con.execute("SELECT created_by FROM applicants WHERE applicant_id=?",
                              (b_row["applicant_id"],)).fetchone()[0]
    # Each application + scored row is linked to its own account.
    assert (a_name, b_name) == ("alice", "bob")
    assert a_owner == a_row["user_id"] and b_owner == b_row["user_id"]
    assert a_row["applicant_id"] != b_row["applicant_id"]

    # Each account lists only its own record, and cannot read the other's.
    assert [x["reference"] for x in alice.get("/api/applications").get_json()["applications"]] == [a["reference"]]
    assert [x["reference"] for x in bob.get("/api/applications").get_json()["applications"]] == [b["reference"]]
    assert bob.get(f"/api/applications/{a['application_id']}").status_code == 404
    assert alice.get(f"/api/applications/{b['application_id']}").status_code == 404


def test_business_manager_gets_aggregates_not_personal_details(client):
    applicant = client.application.test_client()
    app = _submit(applicant)

    bm = client.application.test_client()
    login(bm, "bm@example.com", "Bm@nger9pw")
    summary = bm.get("/api/staff/summary")
    assert summary.status_code == 200
    body = summary.get_json()
    assert body["total_applications"] == 1
    assert body["by_tier"] and body["by_status"]             # management information
    # recent rows carry no personal applicant identifiers
    assert body["recent"] and "applicant_username" not in body["recent"][0]
    assert "applicant_name" not in body["recent"][0]
    # and no access to individual applicant records
    assert bm.get("/api/staff/applications").status_code == 403
    assert bm.get(f"/api/staff/applications/{app['application_id']}").status_code == 403
    assert bm.get("/api/staff/models").status_code == 403


def test_credit_analyst_can_assess_but_not_decide(client):
    applicant = client.application.test_client()
    app = _submit(applicant)

    ca = client.application.test_client()
    login(ca, "ca@example.com", "An@lyst9pw")
    csrf = csrf_of(ca.get("/api/auth/me"))
    assert len(ca.get("/api/staff/applications").get_json()["applications"]) == 1
    detail = ca.get(f"/api/staff/applications/{app['application_id']}")
    assert detail.status_code == 200
    body = detail.get_json()["application"]
    assert body["applicant_username"] == "alice"             # authorised applicant info
    assert body["scores"] and body["factors"]                # real assessment
    assert ca.post(f"/api/staff/applications/{app['application_id']}/assign",
                   headers={"X-CSRF-Token": csrf}).status_code == 403
    assert ca.post(f"/api/staff/applications/{app['application_id']}/decision",
                   json={"decision": "approved", "note": "x"},
                   headers={"X-CSRF-Token": csrf}).status_code == 403


def test_loan_officer_only_sees_unassigned_and_own(client):
    db.create_user("lo2", "L0anOff9pw2", "loan_officer", email="lo2@example.com")
    applicant = client.application.test_client()
    register(applicant, "alice")
    acsrf = csrf_of(applicant.get("/api/auth/me"))
    app1 = applicant.post("/api/applications", json=VALID_APPLICATION,
                          headers={"X-CSRF-Token": acsrf}).get_json()["application_id"]
    app2 = applicant.post("/api/applications", json=VALID_APPLICATION,
                          headers={"X-CSRF-Token": acsrf}).get_json()["application_id"]

    o1 = client.application.test_client()
    login(o1, "lo@example.com", "L0anOff9pw")
    o1csrf = csrf_of(o1.get("/api/auth/me"))
    assert o1.post(f"/api/staff/applications/{app1}/assign",
                   headers={"X-CSRF-Token": o1csrf}).status_code == 200

    o2 = client.application.test_client()
    login(o2, "lo2@example.com", "L0anOff9pw2")
    visible = {a["application_id"] for a in o2.get("/api/staff/applications").get_json()["applications"]}
    assert app1 not in visible and app2 in visible           # scoped to own + queue
    assert o2.get(f"/api/staff/applications/{app1}").status_code == 403
    assert o2.get(f"/api/staff/applications/{app2}").status_code == 200
    o2csrf = csrf_of(o2.get("/api/auth/me"))
    assert o2.post(f"/api/staff/applications/{app1}/decision",
                   json={"decision": "approved", "note": "x"},
                   headers={"X-CSRF-Token": o2csrf}).status_code == 403


def test_full_workflow_for_every_role(client):
    # Applicant: register -> session -> submit -> own list -> logout
    applicant = client.application.test_client()
    app = _submit(applicant)
    assert len(applicant.get("/api/applications").get_json()["applications"]) == 1
    acsrf = csrf_of(applicant.get("/api/auth/me"))
    assert logout(applicant, acsrf).status_code == 200
    assert applicant.get("/api/applications").status_code == 401

    # Business manager: aggregate dashboard only, then logout
    bm = client.application.test_client()
    assert login(bm, "bm@example.com", "Bm@nger9pw").status_code == 200
    assert bm.get("/api/staff/summary").status_code == 200
    assert bm.get("/api/staff/applications").status_code == 403
    bmcsrf = csrf_of(bm.get("/api/auth/me"))
    assert logout(bm, bmcsrf).status_code == 200
    assert bm.get("/api/staff/summary").status_code == 401

    # Credit analyst: assessments + model insights, no decisions, then logout
    ca = client.application.test_client()
    assert login(ca, "ca@example.com", "An@lyst9pw").status_code == 200
    assert ca.get("/api/staff/applications").status_code == 200
    assert ca.get("/api/staff/models").status_code == 200
    cacsrf = csrf_of(ca.get("/api/auth/me"))
    assert ca.post(f"/api/staff/applications/{app['application_id']}/assign",
                   headers={"X-CSRF-Token": cacsrf}).status_code == 403
    assert logout(ca, cacsrf).status_code == 200

    # Loan officer: queue -> claim -> decide; no model insights; then logout
    lo = client.application.test_client()
    assert login(lo, "lo@example.com", "L0anOff9pw").status_code == 200
    ids = {a["application_id"] for a in lo.get("/api/staff/applications").get_json()["applications"]}
    assert app["application_id"] in ids
    locsrf = csrf_of(lo.get("/api/auth/me"))
    assert lo.post(f"/api/staff/applications/{app['application_id']}/assign",
                   headers={"X-CSRF-Token": locsrf}).status_code == 200
    assert lo.post(f"/api/staff/applications/{app['application_id']}/decision",
                   json={"decision": "approved", "note": "ok"},
                   headers={"X-CSRF-Token": locsrf}).status_code == 200
    assert lo.get("/api/staff/models").status_code == 403
    assert logout(lo, locsrf).status_code == 200
