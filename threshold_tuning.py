"""
threshold_tuning.py - canonical train / tune / export script.

Run:  python threshold_tuning.py

CONVENTIONS (every consumer - Streamlit app, Power BI exports, evaluation - must follow these)
  * Target encoding : Bad (default) = 0, Good (repaid) = 1
  * Probability     : P(Good) = pipeline.predict_proba(X)[:, 1]
  * Threshold       : thresholds.json holds one P(Good) cut-off per model.
                      Predict GOOD if P(Good) >= threshold, otherwise BAD.
  * Model keys      : "Logistic Regression", "Random Forest" (title case)

The threshold is chosen on out-of-fold predictions from the TRAINING set only
(F1 of the Bad class). The test set is used once, for the final report.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import (StratifiedKFold, cross_val_predict,
                                     train_test_split)
from sklearn.preprocessing import StandardScaler

# ------------------------------- CONFIG -------------------------------------
DATA_PATH = "model_ready_extended.csv"      # <-- your prepared, numeric, merged dataset
TARGET_COL = "good_bad_flag"         # <-- target column name
DROP_COLS = []           # <-- identifiers / columns not used as features
OUT_DIR = Path(".")                  # <-- must match where the Streamlit app looks
RANDOM_STATE = 42
TEST_SIZE = 0.30
USE_SMOTE = False

MODEL_FILES = {                      # <-- confirm these match the filenames the app loads
    "Logistic Regression": "logistic_regression_pipeline.joblib",
    "Random Forest": "random_forest_pipeline.joblib",
}
BAD, GOOD = 0, 1

# Willingness-to-pay = behavioural proxies from prior loan history; everything else = ability / profile.
WILLINGNESS = {
    "prior_loan_count", "prior_default_rate", "rollover_count",
    "days_to_first_repayment", "loannumber", "prior_max_days_late",
    "prior_ontime_rate", "has_prior_history",
}
THRESHOLD_GRID = np.round(np.arange(0.05, 0.951, 0.005), 3)
# ----------------------------------------------------------------------------


def normalise_target(s: pd.Series) -> pd.Series:
    """Return the target as int with Bad=0, Good=1. Fails loudly on anything else."""
    if pd.api.types.is_numeric_dtype(s):
        out = s
    else:
        key = s.astype(str).str.strip().str.lower()
        out = key.map({"bad": BAD, "good": GOOD, "0": BAD, "1": GOOD})
    if out.isna().any():
        raise ValueError(f"Unmapped/missing target values: "
                         f"{sorted(s[out.isna()].astype(str).unique())[:5]}")
    if not set(out.unique()) <= {BAD, GOOD}:
        raise ValueError(f"Target must be Bad=0 / Good=1, found {sorted(out.unique())}")
    out = out.astype(int)
    if out.mean() < 0.5:   # Good should be the majority class in credit data
        raise ValueError("Class 0 (Bad) is the majority - the encoding looks reversed. "
                         "Check which label means default before continuing.")
    return out


def load_data(path: str | None = None):
    path = path or DATA_PATH
    df = pd.read_csv(path)
    if TARGET_COL not in df.columns:
        raise KeyError(f"Target column '{TARGET_COL}' not found in {path}")
    y = normalise_target(df[TARGET_COL])
    X = df.drop(columns=[TARGET_COL] + [c for c in DROP_COLS if c in df.columns])
    bool_cols = X.select_dtypes(include="bool").columns   # get_dummies gives True/False
    X = X.astype({c: int for c in bool_cols})
    non_numeric = X.select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        raise TypeError(f"Non-numeric feature columns (encode them first): {non_numeric}")
    if X.isna().any().any():
        raise ValueError("Missing values in features - impute before this step.")
    return X, y


def build_pipeline(model_name: str) -> Pipeline:
    clf = {
        "Logistic Regression": LogisticRegression(
            class_weight="balanced", max_iter=1000,   # default penalty is L2
            random_state=RANDOM_STATE),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, random_state=RANDOM_STATE, n_jobs=-1),
    }[model_name]
    steps = [("scaler", StandardScaler())]
    if USE_SMOTE:   # inside the pipeline: only ever applied to training folds
        steps.append(("smote", SMOTE(random_state=RANDOM_STATE)))
    steps.append(("clf", clf))
    return Pipeline(steps)


def predict_good(p_good, threshold):
    """The single decision rule used everywhere: 1 = Good, 0 = Bad."""
    return (np.asarray(p_good) >= threshold).astype(int)


def best_threshold(y_true, p_good):
    """Threshold on P(Good) that maximises F1 of the Bad class."""
    y_bad = (np.asarray(y_true) == BAD).astype(int)
    scores = [f1_score(y_bad, (predict_good(p_good, t) == BAD).astype(int),
                       zero_division=0) for t in THRESHOLD_GRID]
    i = int(np.argmax(scores))
    return float(THRESHOLD_GRID[i]), float(scores[i])


def bad_class_metrics(y_true, p_good, threshold):
    y_bad = (np.asarray(y_true) == BAD).astype(int)
    pred_bad = (predict_good(p_good, threshold) == BAD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_bad, pred_bad, labels=[0, 1]).ravel()
    return {
        "threshold_P_good": round(float(threshold), 3),
        "accuracy": accuracy_score(y_bad, pred_bad),
        "precision_bad": precision_score(y_bad, pred_bad, zero_division=0),
        "recall_bad": recall_score(y_bad, pred_bad, zero_division=0),
        "f1_bad": f1_score(y_bad, pred_bad, zero_division=0),
        # threshold-free ranking quality of the Bad class (same for any threshold)
        "roc_auc": roc_auc_score(y_bad, 1 - np.asarray(p_good)),
        "pr_auc_bad": average_precision_score(y_bad, 1 - np.asarray(p_good)),
        "TP_bad": tp, "FN_bad": fn, "FP_bad": fp, "TN_bad": tn,
    }


def naive_baseline_row(y_true):
    """Reference row: flag every borrower as Bad (what a model must beat)."""
    y_bad = (np.asarray(y_true) == BAD).astype(int)
    pred = np.ones_like(y_bad)
    return {
        "model": "Baseline: flag all as Bad", "setting": "n/a",
        "threshold_P_good": np.nan,
        "accuracy": accuracy_score(y_bad, pred),
        "precision_bad": precision_score(y_bad, pred, zero_division=0),
        "recall_bad": recall_score(y_bad, pred),
        "f1_bad": f1_score(y_bad, pred),
        "roc_auc": 0.5, "pr_auc_bad": float(y_bad.mean()),
    }


def main():
    X, y = load_data()
    print(f"Loaded {X.shape[0]} rows x {X.shape[1]} features | "
          f"Bad share = {(y == BAD).mean():.1%}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    thresholds, rows = {}, []
    importance = {}

    for name in MODEL_FILES:
        pipe = build_pipeline(name)

        # 1) choose threshold on out-of-fold TRAIN predictions
        oof_p_good = cross_val_predict(pipe, X_train, y_train, cv=cv,
                                       method="predict_proba")[:, GOOD]
        thr, cv_f1 = best_threshold(y_train, oof_p_good)
        thresholds[name] = thr
        print(f"{name}: tuned P(Good) threshold = {thr:.3f} (CV Bad-class F1 = {cv_f1:.3f})")

        # 2) fit on full train, evaluate once on the held-out test set
        pipe.fit(X_train, y_train)
        assert list(pipe.classes_) == [BAD, GOOD], "unexpected class order"
        p_good_test = pipe.predict_proba(X_test)[:, GOOD]

        for label, t in [("default_0.50", 0.50), ("tuned", thr)]:
            rows.append({"model": name, "setting": label,
                         **bad_class_metrics(y_test, p_good_test, t)})

        clf = pipe.named_steps["clf"]
        if name == "Logistic Regression":
            importance["lr_coefficient"] = clf.coef_[0]      # on scaled features; + = toward Good
        else:
            importance["rf_importance"] = clf.feature_importances_

        # 3) artifacts
        joblib.dump(pipe, OUT_DIR / MODEL_FILES[name])
        pd.DataFrame({
            "p_good": p_good_test,
            "p_bad": 1 - p_good_test,
            "actual": y_test.values,
            "predicted": predict_good(p_good_test, thr),
        }).to_csv(OUT_DIR / f"{name.lower().replace(' ', '_')}_test_predictions.csv",
                  index=False)

    # held-out test set + feature importance, from the SAME deployed pipelines
    X_test.assign(**{TARGET_COL: y_test.values}).to_csv(OUT_DIR / "test_set.csv", index=False)
    fi = pd.DataFrame({"feature": X.columns, **importance})
    fi["lr_abs_coefficient"] = fi["lr_coefficient"].abs()
    fi["lr_direction"] = np.where(fi["lr_coefficient"] > 0, "Lowers default risk", "Raises default risk")
    fi["lr_rank"] = fi["lr_abs_coefficient"].rank(ascending=False).astype(int)
    fi["rf_rank"] = fi["rf_importance"].rank(ascending=False).astype(int)
    fi["driver_type"] = np.where(fi["feature"].isin(WILLINGNESS),
                                 "Willingness to pay", "Ability to pay / profile")
    fi.sort_values("rf_rank").to_csv(OUT_DIR / "feature_importance.csv", index=False)

    # keep thresholds.json a plain {model: float} map so consumers can't trip on extra keys
    (OUT_DIR / "thresholds.json").write_text(json.dumps(thresholds, indent=2))
    (OUT_DIR / "feature_columns.json").write_text(json.dumps(list(X.columns), indent=2))
    rows.append(naive_baseline_row(y_test))
    comparison = pd.DataFrame(rows).round(3)
    comparison.to_csv(OUT_DIR / "threshold_comparison.csv", index=False)
    print("\n", comparison.to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, TypeError, ValueError) as e:
        sys.exit(f"ERROR: {e}")