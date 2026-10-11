"""
Decision Threshold Tuning for Bad-Class F1
BI-ML Creditworthiness Classification Project

Uses out-of-fold predicted probabilities on the TRAINING set only
(SMOTE re-fit inside each fold) to pick the threshold that maximises
Bad-class (0) F1. The chosen threshold is then applied once to the
untouched test set -- no test-set leakage.
"""

import json
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, cross_val_predict, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

RANDOM_STATE = 42
TEST_SIZE = 0.30
THRESHOLDS = np.arange(0.20, 0.80, 0.01)  # threshold on P(Good)


def load_and_split():
    df = pd.read_csv("model_ready_dataset.csv")
    df["good_bad_flag"] = df["good_bad_flag"].map({"Good": 1, "Bad": 0})
    X = df.drop(columns=["good_bad_flag"])
    y = df["good_bad_flag"]
    return train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y)


def build_pipelines():
    # Best params from tune_models.py
    lr = ImbPipeline([
        ("smote", SMOTE(random_state=RANDOM_STATE)),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.1, class_weight=None, max_iter=1000,
                                   random_state=RANDOM_STATE)),
    ])
    rf = ImbPipeline([
        ("smote", SMOTE(random_state=RANDOM_STATE)),
        ("clf", RandomForestClassifier(n_estimators=100, min_samples_leaf=5,
                                       max_depth=None, class_weight="balanced",
                                       random_state=RANDOM_STATE)),
    ])
    return {"Logistic Regression": lr, "Random Forest": rf}


def best_threshold(y_true, p_good):
    """Threshold on P(Good): predict Bad (0) when P(Good) < t."""
    scores = []
    for t in THRESHOLDS:
        preds = (p_good >= t).astype(int)
        scores.append(f1_score(y_true, preds, pos_label=0))
    i = int(np.argmax(scores))
    return float(THRESHOLDS[i]), float(scores[i])


def main():
    X_train, X_test, y_train, y_test = load_and_split()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    chosen = {}

    for name, pipe in build_pipelines().items():
        oof = cross_val_predict(pipe, X_train, y_train, cv=cv,
                                method="predict_proba", n_jobs=-1)[:, 1]
        t, cv_f1 = best_threshold(y_train, oof)
        chosen[name] = t
        print(f"{name}: best threshold = {t:.2f} | OOF Bad-class F1 = {cv_f1:.4f}")

        pipe.fit(X_train, y_train)
        p_test = pipe.predict_proba(X_test)[:, 1]

        default_preds = (p_test >= 0.5).astype(int)
        tuned_preds = (p_test >= t).astype(int)
        print(f"  Test Bad F1 @0.50: {f1_score(y_test, default_preds, pos_label=0):.4f}")
        print(f"  Test Bad F1 @{t:.2f}: {f1_score(y_test, tuned_preds, pos_label=0):.4f}")
        print(confusion_matrix(y_test, tuned_preds))
        print(classification_report(y_test, tuned_preds,
                                    target_names=["Bad (0)", "Good (1)"]))

        # Save fitted final pipeline for downstream use
        joblib.dump(pipe, f"{name.lower().replace(' ', '_')}_pipeline.joblib")

    with open("thresholds.json", "w") as f:
        json.dump(chosen, f, indent=2)
    print("Saved thresholds.json and *_pipeline.joblib")


if __name__ == "__main__":
    main()
