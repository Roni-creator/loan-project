"""
Extra Feature Engineering Experiment
BI-ML Creditworthiness Classification Project

Rebuilds the merged dataset in the SAME row order as the existing pipeline,
adds extra features, then compares baseline vs extended features on the
SAME 70/30 stratified split (random_state=42). Nothing is tuned on test.
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, roc_auc_score
from imblearn.over_sampling import SMOTE

import feature_engineering_pipeline as fe

RANDOM_STATE = 42


def build_extra_features(data_dir="."):
    demo, perf, prev = fe.load_raw(data_dir)
    behavioural = fe.engineer_behavioural_features(prev)
    merged = fe.merge_datasets(demo, perf, behavioural)  # same row order as pipeline

    extra = pd.DataFrame(index=merged.index)

    # --- from current application (trainperf) ---
    extra["interest_ratio"] = merged["totaldue"] / merged["loanamount"] - 1

    approved = pd.to_datetime(merged["approveddate"])
    extra["app_hour"] = approved.dt.hour
    extra["app_dayofweek"] = approved.dt.dayofweek

    # --- from demographics ---
    birth = pd.to_datetime(merged["birthdate"])
    extra["age"] = (approved - birth).dt.days / 365.25

    # --- from previous loans (extra aggregates) ---
    prev = prev.copy()
    prev["days_late"] = (prev["firstrepaiddate"] - prev["firstduedate"]).dt.days
    agg = prev.groupby("customerid").agg(
        prior_avg_loanamount=("loanamount", "mean"),
        prior_avg_termdays=("termdays", "mean"),
        prior_max_days_late=("days_late", "max"),
        prior_ontime_rate=("days_late", lambda s: (s <= 0).mean()),
    ).reset_index()
    tmp = merged[["customerid"]].merge(agg, on="customerid", how="left")
    for col in agg.columns.drop("customerid"):
        extra[col] = tmp[col].values

    extra["loan_to_prior_avg"] = merged["loanamount"].values / extra["prior_avg_loanamount"]
    extra["has_prior_history"] = (merged["prior_loan_count"] > 0).astype(int)

    extra = extra.replace([np.inf, -np.inf], np.nan)
    for col in extra.columns:
        extra[col] = extra[col].fillna(extra[col].median())
    return extra


def evaluate(X, y, label):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, random_state=RANDOM_STATE, stratify=y
    )
    results = {}

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_train)
    Xs_res, y_res = SMOTE(random_state=RANDOM_STATE).fit_resample(Xs, y_train)
    lr = LogisticRegression(C=0.1, max_iter=1000, random_state=RANDOM_STATE).fit(Xs_res, y_res)
    p = lr.predict_proba(scaler.transform(X_test))[:, 1]
    results["LR"] = (f1_score(y_test, (p >= 0.5).astype(int), pos_label=0),
                     roc_auc_score(y_test, p))

    X_res, y_res = SMOTE(random_state=RANDOM_STATE).fit_resample(X_train, y_train)
    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5,
                                class_weight="balanced", random_state=RANDOM_STATE).fit(X_res, y_res)
    p = rf.predict_proba(X_test)[:, 1]
    results["RF"] = (f1_score(y_test, (p >= 0.5).astype(int), pos_label=0),
                     roc_auc_score(y_test, p))

    for m, (f1, auc) in results.items():
        print(f"{label:<10} {m}: Bad-class F1 = {f1:.4f} | AUC = {auc:.4f}")
    return rf, X_train.columns


def build_extended(out="model_ready_extended.csv"):
    """Rebuild model_ready_extended.csv from model_ready_dataset.csv (no model fitting)."""
    base = pd.read_csv("model_ready_dataset.csv")
    extra = build_extra_features()
    assert len(extra) == len(base), "row count mismatch -- alignment broken"
    X_ext = pd.concat([base.drop(columns=["good_bad_flag"]).reset_index(drop=True),
                       extra.reset_index(drop=True)], axis=1)
    X_ext.assign(good_bad_flag=base["good_bad_flag"]).to_csv(out, index=False)
    return X_ext


def main():
    base = pd.read_csv("model_ready_dataset.csv")
    y = base["good_bad_flag"].map({"Good": 1, "Bad": 0})
    X_base = base.drop(columns=["good_bad_flag"])

    extra = build_extra_features()
    assert len(extra) == len(X_base), "row count mismatch -- alignment broken"

    X_ext = pd.concat([X_base.reset_index(drop=True), extra.reset_index(drop=True)], axis=1)

    evaluate(X_base, y, "Baseline")
    rf, cols = evaluate(X_ext, y, "Extended")

    imp = pd.Series(rf.feature_importances_, index=cols).sort_values(ascending=False)
    print("\nTop 10 RF importances (extended):")
    print(imp.head(10).round(4).to_string())

    X_ext.assign(good_bad_flag=base["good_bad_flag"]).to_csv(
        "model_ready_extended.csv", index=False)
    print("\nSaved: model_ready_extended.csv")


if __name__ == "__main__":
    main()
