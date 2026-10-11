"""Targeted checks. Run:  python -m pytest -q"""
import json

import joblib
import numpy as np
import pandas as pd
import pytest

import threshold_tuning as tt


def test_string_labels_map_to_bad0_good1():
    s = pd.Series(["Good"] * 8 + ["Bad"] * 2)
    out = tt.normalise_target(s)
    assert out.tolist() == [1] * 8 + [0] * 2


def test_numeric_labels_pass_through():
    s = pd.Series([1] * 8 + [0] * 2)
    assert tt.normalise_target(s).tolist() == s.tolist()


def test_unknown_label_fails_loudly():
    with pytest.raises(ValueError):
        tt.normalise_target(pd.Series(["Good", "Bad", "Maybe"] * 3))


def test_reversed_encoding_is_caught():
    with pytest.raises(ValueError):          # 0 is the majority -> likely reversed
        tt.normalise_target(pd.Series([0] * 8 + [1] * 2))


def test_decision_rule_direction():
    assert tt.predict_good([0.30, 0.70], 0.5).tolist() == [0, 1]   # low P(Good) -> Bad


def test_best_threshold_separates_clean_data():
    y = np.array([0] * 20 + [1] * 80)
    p = np.r_[np.full(20, 0.2), np.full(80, 0.8)]
    thr, f1 = tt.best_threshold(y, p)
    assert 0.2 < thr <= 0.8 and f1 == 1.0


def test_end_to_end_artifacts(tmp_path, monkeypatch):
    rng = np.random.default_rng(1)
    n = 600
    X = pd.DataFrame(rng.normal(size=(n, 4)), columns=list("abcd"))
    bad = rng.random(n) < 1 / (1 + np.exp(-(-1.5 + X.a)))
    df = X.assign(customerid=range(n), good_bad_flag=np.where(bad, "Bad", "Good"))
    csv = tmp_path / "d.csv"
    df.to_csv(csv, index=False)
    monkeypatch.setattr(tt, "DATA_PATH", str(csv))
    monkeypatch.setattr(tt, "OUT_DIR", tmp_path)
    tt.main()

    thr = json.loads((tmp_path / "thresholds.json").read_text())
    assert set(thr) == {"Logistic Regression", "Random Forest"}
    assert all(0 < v < 1 for v in thr.values())
    for fname in tt.MODEL_FILES.values():
        pipe = joblib.load(tmp_path / fname)
        assert list(pipe.classes_) == [0, 1]
        assert pipe.predict_proba(X.head(3)).shape == (3, 2)