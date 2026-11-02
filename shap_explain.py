"""
shap_explain.py - SHAP explanations for the BI-ML creditworthiness project.

Run AFTER threshold_tuning.py:   python shap_explain.py

Reads   : the two fitted pipelines (*.joblib), thresholds.json, model_ready_extended.csv
Writes  : shap_global.csv  - one row per (model, feature): importance, direction, rank
          shap_local.csv   - one row per (borrower, model, top-N feature): why this borrower
                             got this score

CONVENTIONS (same as threshold_tuning.py)
  * Bad (default) = 0, Good (repaid) = 1.
  * Every SHAP value here is expressed TOWARD BAD:
        positive shap_value  -> pushes the borrower toward default (raises risk)
        negative shap_value  -> pushes the borrower toward repayment (lowers risk)
  * Units differ by model, so never compare raw SHAP numbers across models:
        Logistic Regression -> log-odds of Bad
        Random Forest       -> probability of Bad
    Use `importance_share` and `rank` to compare models.
  * The 17 one-hot bank_name_clients_* columns are summed into one feature,
    "bank_name_clients" (SHAP values are additive, so this is exact).

The functions below are importable, so the Streamlit app can explain uploaded
applications live with the same logic:  from shap_explain import explain_frame
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression

# ------------------------------- CONFIG -------------------------------------
OUT_DIR = Path(".")        # must match where threshold_tuning.py wrote its files
BACKGROUND_SIZE = 100      # training rows used as the reference for Logistic Regression
TOP_N_LOCAL = 8            # drivers kept per borrower in shap_local.csv
RANK_AGREE_WITHIN = 3      # models "agree" on a feature if ranks differ by <= this
ADDITIVITY_TOL = 1e-3      # SHAP values + base value must rebuild the model output
BAD, GOOD = 0, 1

BANK_PREFIX = "bank_name_clients_"
BANK_GROUP = "bank_name_clients"

# Working assumption (same idea as export_feature_importance.py) - REVIEW THIS.
# Willingness to pay = repayment behaviour/intent. Everything else = ability / profile.
WILLINGNESS = {
    "loannumber", "prior_loan_count", "prior_default_rate", "rollover_count",
    "days_to_first_repayment", "prior_max_days_late", "prior_ontime_rate",
    "has_prior_history",
}
# ----------------------------------------------------------------------------


def driver_type(feature: str) -> str:
    return "Willingness to pay" if feature in WILLINGNESS else "Ability to pay / profile"


# --------------------------- core explain logic -----------------------------
def preprocess(pipe, X: pd.DataFrame) -> np.ndarray:
    """Apply every pipeline step except the classifier (scaler, imputer, ...).
    Samplers such as SMOTE have no transform() and are skipped, as at predict time."""
    Xt = X
    for _, step in pipe.steps[:-1]:
        if hasattr(step, "transform"):
            Xt = step.transform(Xt)
    Xt = np.asarray(Xt, dtype=float)
    if Xt.shape[1] != X.shape[1]:
        raise ValueError(
            f"Preprocessing changed the column count ({X.shape[1]} -> {Xt.shape[1]}); "
            "this script assumes no encoding happens inside the pipeline.")
    return Xt


def _class_slice(raw, cls: int) -> np.ndarray:
    """Normalise the different shapes shap returns for tree models."""
    if isinstance(raw, list):
        return np.asarray(raw[cls])
    raw = np.asarray(raw)
    if raw.ndim == 3:
        return raw[:, :, cls]
    raise ValueError(f"Unexpected SHAP output shape {raw.shape} for a tree model.")


def explain_rows(pipe, X: pd.DataFrame, background: pd.DataFrame | None = None) -> dict:
    """SHAP values toward Bad for every row of X, on the ungrouped feature columns.

    Returns dict: values (n, f), base (float), scale (str), p_bad (n,)
    """
    clf = pipe.steps[-1][1]
    if list(clf.classes_) != [BAD, GOOD]:
        raise ValueError(f"Unexpected class order {list(clf.classes_)}; expected [0, 1].")

    Xe = preprocess(pipe, X)
    p_bad = clf.predict_proba(Xe)[:, BAD]

    if isinstance(clf, LogisticRegression):
        if background is None:
            raise ValueError("Logistic Regression needs a background sample.")
        explainer = shap.LinearExplainer(clf, preprocess(pipe, background))
        sv_good = np.asarray(explainer.shap_values(Xe))
        values = -sv_good                                   # flip Good -> Bad
        base = -float(np.atleast_1d(explainer.expected_value)[0])
        scale = "log-odds of Bad"
        target = -clf.decision_function(Xe)                 # log-odds of Bad
    else:
        explainer = shap.TreeExplainer(clf)
        values = _class_slice(explainer.shap_values(Xe, check_additivity=False), BAD)
        base = float(np.atleast_1d(explainer.expected_value)[BAD])
        scale = "probability of Bad"
        target = p_bad

    gap = float(np.max(np.abs(base + values.sum(axis=1) - target)))
    if gap > ADDITIVITY_TOL:
        raise ValueError(f"SHAP additivity check failed (max gap {gap:.5f}). "
                         "Sign, scaling or class order is wrong.")
    return {"values": values, "base": base, "scale": scale, "p_bad": p_bad, "gap": gap}


def group_banks(values: np.ndarray, X: pd.DataFrame):
    """Collapse the one-hot bank columns into one feature.

    Returns (grouped_values, names, numeric_values, value_text), all (n, f_grouped).
    numeric_values is NaN for the bank group; value_text is the readable value
    (the bank name for the bank group)."""
    cols = list(X.columns)
    bank_idx = [i for i, c in enumerate(cols) if c.startswith(BANK_PREFIX)]
    other_idx = [i for i, c in enumerate(cols) if not c.startswith(BANK_PREFIX)]

    names = [cols[i] for i in other_idx]
    gvals = values[:, other_idx]
    num = X.iloc[:, other_idx].to_numpy(dtype=float)
    text = np.vectorize(lambda v: f"{v:.4g}")(num).astype(object)

    if bank_idx:
        names.append(BANK_GROUP)
        gvals = np.column_stack([gvals, values[:, bank_idx].sum(axis=1)])
        dummies = X.iloc[:, bank_idx].to_numpy(dtype=float)
        labels = np.array([c[len(BANK_PREFIX):] for c in (cols[i] for i in bank_idx)],
                          dtype=object)
        bank_text = np.where(dummies.max(axis=1) > 0, labels[dummies.argmax(axis=1)],
                             "Other / baseline bank").astype(object)
        num = np.column_stack([num, np.full(len(X), np.nan)])
        text = np.column_stack([text, bank_text])
    return gvals, names, num, text


def explain_frame(pipe, X: pd.DataFrame, background: pd.DataFrame | None = None) -> dict:
    """One-call helper for the Streamlit app: explain X and group the bank columns."""
    out = explain_rows(pipe, X, background)
    gvals, names, num, text = group_banks(out["values"], X)
    return {**out, "grouped_values": gvals, "names": names,
            "numeric_values": num, "value_text": text}


# ----------------------------- table builders -------------------------------
def build_global(model_name: str, res: dict) -> pd.DataFrame:
    g, names, num = res["grouped_values"], res["names"], res["numeric_values"]
    mean_abs = np.abs(g).mean(axis=0)
    corr = []
    for j in range(g.shape[1]):
        x = num[:, j]
        ok = ~np.isnan(x)
        if ok.sum() < 3 or np.nanstd(x) == 0 or np.std(g[:, j]) == 0:
            corr.append(np.nan)
        else:
            corr.append(float(np.corrcoef(x[ok], g[ok, j])[0, 1]))
    corr = np.array(corr)

    def direction(c, name):
        if name == BANK_GROUP:
            return "Categorical (see per-bank effect in shap_local)"
        if np.isnan(c) or abs(c) < 0.1:
            return "Mixed / non-linear"
        return "Higher values raise default risk" if c > 0 else "Higher values lower default risk"

    df = pd.DataFrame({
        "model": model_name,
        "feature": names,
        "driver_type": [driver_type(n) if n != BANK_GROUP else "Ability to pay / profile"
                        for n in names],
        "mean_abs_shap": mean_abs,
        "importance_share": mean_abs / mean_abs.sum(),
        "mean_shap_signed": g.mean(axis=0),
        "value_shap_corr": corr,
        "direction": [direction(c, n) for c, n in zip(corr, names)],
        "shap_scale": res["scale"],
    })
    df["rank"] = df["mean_abs_shap"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank").reset_index(drop=True)


def add_model_agreement(glob: pd.DataFrame) -> pd.DataFrame:
    """Add each feature's rank in the other model(s) and an agree/differ flag."""
    wide = glob.pivot(index="feature", columns="model", values="rank")
    models = list(wide.columns)
    if len(models) != 2:
        return glob
    a, b = models
    other = {a: wide[b], b: wide[a]}
    glob = glob.copy()
    glob["rank_in_other_model"] = [int(other[m][f]) for m, f in zip(glob["model"], glob["feature"])]
    glob["rank_gap"] = (glob["rank"] - glob["rank_in_other_model"]).abs()
    glob["models_agree"] = np.where(glob["rank_gap"] <= RANK_AGREE_WITHIN, "Agree", "Differ")
    return glob


def build_local(model_name: str, res: dict, borrower_ids, y_true, threshold: float) -> pd.DataFrame:
    g, names = res["grouped_values"], np.array(res["names"], dtype=object)
    num, text = res["numeric_values"], res["value_text"]
    n, k = g.shape[0], min(TOP_N_LOCAL, g.shape[1])

    order = np.argsort(-np.abs(g), axis=1)[:, :k]
    rows = np.repeat(np.arange(n), k)
    cols = order.ravel()

    p_bad = res["p_bad"]
    flagged_bad = ((1 - p_bad) < threshold).astype(int)
    feat = names[cols]
    return pd.DataFrame({
        "borrower_id": np.asarray(borrower_ids)[rows],
        "model": model_name,
        "p_bad": p_bad[rows],
        "predicted": np.where(flagged_bad[rows] == 1, "Bad", "Good"),
        "actual": np.where(np.asarray(y_true)[rows] == BAD, "Bad", "Good"),
        "rank_in_borrower": np.tile(np.arange(1, k + 1), n),
        "feature": feat,
        "driver_type": [driver_type(f) if f != BANK_GROUP else "Ability to pay / profile"
                        for f in feat],
        "feature_value": num[rows, cols],
        "value_text": text[rows, cols],
        "shap_value": g[rows, cols],
        "effect": np.where(g[rows, cols] > 0, "Raises default risk", "Lowers default risk"),
        "shap_scale": res["scale"],
    })


# --------------------------------- main -------------------------------------
def main():
    import threshold_tuning as tt          # reuse the exact data loading and split
    from sklearn.model_selection import train_test_split

    X, y = tt.load_data()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=tt.TEST_SIZE, stratify=y, random_state=tt.RANDOM_STATE)

    fc = OUT_DIR / "feature_columns.json"
    if fc.exists() and json.loads(fc.read_text()) != list(X.columns):
        raise ValueError("feature_columns.json does not match the dataset columns. "
                         "Re-run threshold_tuning.py first.")

    thresholds = json.loads((OUT_DIR / "thresholds.json").read_text())
    background = X_train.sample(min(BACKGROUND_SIZE, len(X_train)), random_state=tt.RANDOM_STATE)

    globals_, locals_ = [], []
    for name, fname in tt.MODEL_FILES.items():
        path = OUT_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"{fname} not found - run threshold_tuning.py first.")
        pipe = joblib.load(path)
        print(f"Explaining {name} on {len(X_test)} test borrowers ...")
        res = explain_frame(pipe, X_test, background)
        print(f"  additivity check passed (max gap {res['gap']:.2e}); scale = {res['scale']}")
        globals_.append(build_global(name, res))
        locals_.append(build_local(name, res, X_test.index.to_numpy(), y_test.to_numpy(),
                                   float(thresholds[name])))

    glob = add_model_agreement(pd.concat(globals_, ignore_index=True))
    loc = pd.concat(locals_, ignore_index=True)
    glob.round(6).to_csv(OUT_DIR / "shap_global.csv", index=False)
    loc.round(6).to_csv(OUT_DIR / "shap_local.csv", index=False)

    for name in tt.MODEL_FILES:
        print(f"\nTop 8 drivers - {name}")
        print(glob[glob.model == name].head(8)[
            ["rank", "feature", "driver_type", "importance_share", "direction"]
        ].round(3).to_string(index=False))
    print(f"\nSaved: shap_global.csv ({len(glob)} rows), shap_local.csv ({len(loc)} rows)")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, KeyError, TypeError, ValueError) as e:
        sys.exit(f"ERROR: {e}")
