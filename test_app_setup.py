"""Setup tests: database seeding, login, feature schema, leakage, clean startup.
Run:  python -m pytest -q"""
import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import db
import threshold_tuning as tt

HERE = Path(__file__).resolve().parent
ARTIFACTS = [HERE / f for f in ("random_forest_pipeline.joblib", "logistic_regression_pipeline.joblib",
                                "feature_columns.json", "model_ready_extended.csv")]
have_artifacts = all(p.exists() for p in ARTIFACTS)


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("CREDITSCORE_DB", str(p))
    return p


@pytest.fixture
def runs_csv(tmp_path):
    p = tmp_path / "runs.csv"
    pd.DataFrame({
        "model": ["LR", "LR", "RF", "Baseline"], "setting": ["a", "b", "a", "n/a"],
        "threshold_P_good": [0.5, 0.6, 0.7, np.nan], "accuracy": [.7, .6, .8, .2],
        "precision_bad": [.4, .3, .5, .2], "recall_bad": [.5, .6, .2, 1.0],
        "f1_bad": [.45, .4, .29, .36], "roc_auc": [.7, .7, .68, .5], "pr_auc_bad": [.4, .4, .37, .2],
    }).to_csv(p, index=False)
    return str(p)


# ------------------------------ database ------------------------------------
def test_seed_is_idempotent(dbpath, runs_csv):
    for _ in range(3):
        db.seed_demo(runs_csv=runs_csv)
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert con.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 3  # baseline row skipped


def test_init_removes_existing_duplicate_runs(dbpath, runs_csv):
    db.seed_demo(runs_csv=runs_csv)
    with db.connect() as con:                      # simulate the old, un-deduped database
        con.execute("DROP INDEX ux_model_runs")
        con.execute("INSERT INTO model_runs(model_name,setting,threshold,accuracy,precision_bad,"
                    "recall_bad,f1_bad,roc_auc,pr_auc_bad) SELECT model_name,setting,threshold,accuracy,"
                    "precision_bad,recall_bad,f1_bad,roc_auc,pr_auc_bad FROM model_runs")
        assert con.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 6
    db.init_db()
    with db.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM model_runs").fetchone()[0] == 3


def test_login_verification(dbpath):
    db.init_db()
    db.create_user("amy", "s3cret", "credit_analyst")
    assert db.verify_user("amy", "s3cret")["role"] == "credit_analyst"
    assert db.verify_user("amy", "wrong") is None
    assert db.verify_user("nobody", "s3cret") is None
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("amy", "x", "loan_officer")
    with pytest.raises(ValueError):
        db.create_user("bob", "x", "admin")
    with db.connect() as con:                      # stored as a hash, never plain text
        assert b"s3cret" not in con.execute("SELECT password_hash FROM users").fetchone()[0]


def test_log_prediction_decision_rule(dbpath):
    db.init_db()
    _, bad = db.log_prediction({"a": 1}, "Random Forest", p_bad=0.6, threshold=0.5)
    _, good = db.log_prediction({"a": 1}, "Random Forest", p_bad=0.2, threshold=0.5)
    assert (bad, good) == ("Bad", "Good")


# --------------------------- leakage / pipeline ------------------------------
def test_imputer_uses_train_statistics_only():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})
    y = pd.Series((rng.random(200) > 0.25).astype(int))
    X.loc[::10, "a"] = np.nan
    X_train, X_test = X.iloc[:150].copy(), X.iloc[150:].copy()
    X_test["a"] = X_test["a"] + 1000                # extreme test values must not move the imputer
    pipe = tt.build_pipeline("Logistic Regression").fit(X_train, y.iloc[:150])
    stats = pipe.named_steps["imputer"].statistics_
    assert stats[0] == pytest.approx(X_train["a"].median())
    assert pipe.predict_proba(X_test).shape == (50, 2)   # NaNs in test handled without error


def test_model_ready_files_keep_nans_for_in_pipeline_imputation():
    if not have_artifacts:
        pytest.skip("run the pipeline first")
    df = pd.read_csv(HERE / "model_ready_extended.csv")
    assert df.isna().any().any()                     # nothing was imputed on the full dataset
    assert "bank_name_clients_Unknown" in df.columns


# ------------------------------ feature schema -------------------------------
def test_feature_columns_match_trained_models():
    if not have_artifacts:
        pytest.skip("run the pipeline first")
    cols = json.loads((HERE / "feature_columns.json").read_text())
    for f in ("random_forest_pipeline.joblib", "logistic_regression_pipeline.joblib"):
        assert list(joblib.load(HERE / f).feature_names_in_) == cols
    data = pd.read_csv(HERE / "model_ready_extended.csv").drop(columns=["good_bad_flag"])
    assert list(data.columns) == cols


def test_scoring_rejects_missing_feature_columns():
    import app
    model = tt.build_pipeline("Logistic Regression").fit(
        pd.DataFrame({"a": [0., 1, 2, 3, 4, 5], "b": [1., 0, 1, 0, 1, 0]}), [0, 1, 1, 1, 1, 0])
    with pytest.raises(ValueError, match="missing model features"):
        app.prepare_features(pd.DataFrame({"a": [1.0]}), model)
    ok = app.prepare_features(pd.DataFrame({"b": [1.0], "a": [2.0]}), model)
    assert list(ok.columns) == ["a", "b"]            # reordered to the model's schema


# ------------------------- app startup, login, roles -------------------------
@pytest.fixture
def app_test(dbpath, runs_csv):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    db.seed_demo(runs_csv=runs_csv)
    return AppTest.from_file(str(HERE / "app.py"), default_timeout=90)


def _login(at, user, pw):
    at.text_input[0].set_value(user)
    at.text_input[1].set_value(pw)
    at.button[0].click()
    return at.run()


def test_clean_startup_shows_login_and_blocks_app(app_test):
    at = app_test.run()
    assert not at.exception
    assert [s.value for s in at.subheader] == ["Sign in"]
    assert len(at.sidebar.radio) == 0                # nothing reachable before login


def test_bad_login_is_rejected(app_test):
    at = _login(app_test.run(), "officer", "wrong")
    assert any("Invalid" in e.value for e in at.error)
    assert len(at.sidebar.radio) == 0


@pytest.mark.skipif(not have_artifacts, reason="run the pipeline first")
@pytest.mark.parametrize("user,pw,pages", [
    ("manager", "ChangeMe!1", ["Portfolio overview"]),
    ("analyst", "ChangeMe!2", ["Portfolio overview", "Model evaluation"]),
    ("officer", "ChangeMe!3", ["Score applications"]),
])
def test_roles_see_only_their_pages(app_test, user, pw, pages):
    at = _login(app_test.run(), user, pw)
    assert not at.exception
    assert list(at.sidebar.radio[0].options) == pages


# ------------------------ fresh-clone provisioning ---------------------------
def test_build_all_reports_missing_raw_files(tmp_path):
    import build_all
    assert build_all.missing_raw_files(tmp_path) == build_all.RAW_FILES
    (tmp_path / "trainperf.csv").write_text("x")
    assert "trainperf.csv" not in build_all.missing_raw_files(tmp_path)


def test_login_page_tells_user_to_seed_when_no_accounts(dbpath):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(HERE / "app.py"), default_timeout=90).run()
    assert not at.exception
    assert any("python db.py" in w.value for w in at.warning)


def test_db_cli_add_user_and_set_password(dbpath, monkeypatch, capsys):
    pws = iter(["first-pw", "second-pw"])
    monkeypatch.setattr("getpass.getpass", lambda *_: next(pws))
    db.main(["add-user", "jane", "credit_analyst"])
    assert db.verify_user("jane", "first-pw")
    db.main(["set-password", "jane"])
    assert db.verify_user("jane", "second-pw") and db.verify_user("jane", "first-pw") is None
    db.main(["list-users"])
    out = capsys.readouterr().out
    assert "jane" in out and "second-pw" not in out


# ------------------------ raw category uploads -------------------------------
def _decode_to_raw(df, maps):
    """Turn encoded rows back into the raw text form a user might upload."""
    raw = df.copy()
    for col, mapping in maps["label"].items():
        inverse = {v: k for k, v in mapping.items()}
        raw[col] = raw[col].map(inverse)
    spec = maps["onehot"]["bank_name_clients"]
    dummies = [f"bank_name_clients_{c}" for c in spec["kept"]]
    raw["bank_name_clients"] = [
        next((c for c, flag in zip(spec["kept"], row) if flag), spec["baseline"])
        for row in raw[dummies].astype(int).values
    ]
    return raw.drop(columns=dummies)


@pytest.mark.skipif(not (HERE / "encoding_maps.json").exists() or not have_artifacts,
                    reason="run build_all.py first")
def test_raw_text_categories_round_trip_to_training_codes():
    import encoding
    maps = encoding.load_maps(HERE / "encoding_maps.json")
    cols = json.loads((HERE / "feature_columns.json").read_text())
    X = pd.read_csv(HERE / "model_ready_extended.csv").drop(columns=["good_bad_flag"]).head(300)
    X = X.astype({c: int for c in X.select_dtypes("bool").columns})
    raw = _decode_to_raw(X, maps)
    assert not pd.api.types.is_numeric_dtype(raw["bank_account_type"])   # really is text, e.g. "Savings"
    back = encoding.encode_raw_categoricals(raw, maps)[cols]
    pd.testing.assert_frame_equal(back.reset_index(drop=True), X[cols].reset_index(drop=True),
                                  check_dtype=False)
    model = joblib.load(HERE / "random_forest_pipeline.joblib")   # and the model accepts it
    assert model.predict_proba(back).shape == (300, 2)


def test_numeric_uploads_pass_through_and_bad_categories_fail():
    import encoding
    maps = {"label": {"bank_account_type": {"Savings": 2, "Unknown": 3},
                      "employment_status_clients": {"Permanent": 1, "Unknown": 6}},
            "onehot": {"bank_name_clients": {"baseline": "Access Bank", "kept": ["GT Bank"]}}}
    numeric = pd.DataFrame({"bank_account_type": [2], "employment_status_clients": [1]})
    pd.testing.assert_frame_equal(encoding.encode_raw_categoricals(numeric, None), numeric)
    with pytest.raises(ValueError, match="Unrecognised bank_account_type"):
        encoding.encode_raw_categoricals(pd.DataFrame({"bank_account_type": ["Piggy"]}), maps)
    with pytest.raises(ValueError, match="Unrecognised bank_name_clients"):
        encoding.encode_raw_categoricals(pd.DataFrame({"bank_name_clients": ["Nope Bank"]}), maps)
    with pytest.raises(ValueError, match="build_all"):
        encoding.encode_raw_categoricals(pd.DataFrame({"bank_account_type": ["Savings"]}), None)
    ok = encoding.encode_raw_categoricals(
        pd.DataFrame({"bank_account_type": ["Savings", None], "bank_name_clients": ["GT Bank", "Access Bank"]}), maps)
    assert ok["bank_account_type"].tolist() == [2, 3] and ok["bank_name_clients_GT Bank"].tolist() == [1, 0]