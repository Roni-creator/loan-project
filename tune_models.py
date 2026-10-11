"""
Hyperparameter Tuning for Bad-Class F1
BI-ML Creditworthiness Classification Project

CRISP-DM Phase 4/5: Modelling / Evaluation
Grid-searches Logistic Regression and Random Forest, scoring directly
on F1 for the minority "Bad" (0) class. SMOTE is placed INSIDE an
imblearn Pipeline so it is re-fit on each CV fold's training portion
only -- avoids leaking synthetic minority samples into validation folds,
which the earlier single-pass SMOTE-then-split approach did not guard
against during model selection.
"""

import pandas as pd
import joblib
from sklearn.model_selection import train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import make_scorer, f1_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline

RANDOM_STATE = 42
TEST_SIZE = 0.30
DATA_DIR = "."

bad_class_f1 = make_scorer(f1_score, pos_label=0)


def load_and_split(data_dir: str = DATA_DIR):
    df = pd.read_csv(f"{data_dir}/model_ready_dataset.csv")
    df["good_bad_flag"] = df["good_bad_flag"].map({"Good": 1, "Bad": 0})
    X = df.drop(columns=["good_bad_flag"])
    y = df["good_bad_flag"]
    return train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y)


def tune_logistic_regression(X_train, y_train):
    pipe = ImbPipeline([
        ("smote", SMOTE(random_state=RANDOM_STATE)),
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)),
    ])
    param_grid = {
        "clf__C": [0.01, 0.1, 1, 10, 100],
        "clf__class_weight": [None, "balanced"],
    }
    search = GridSearchCV(pipe, param_grid, scoring=bad_class_f1, cv=3, n_jobs=-1)
    search.fit(X_train, y_train)
    return search


def tune_random_forest(X_train, y_train):
    pipe = ImbPipeline([
        ("smote", SMOTE(random_state=RANDOM_STATE)),
        ("clf", RandomForestClassifier(random_state=RANDOM_STATE)),
    ])
    param_grid = {
        "clf__n_estimators": [100, 200, 300],
        "clf__max_depth": [None, 10, 20],
        "clf__min_samples_leaf": [1, 2, 5],
        "clf__class_weight": [None, "balanced", "balanced_subsample"],
    }
    # Randomized search (not full grid) to stay within the environment's
    # execution time limit -- cv trimmed to 3, capped at 12 candidates.
    search = RandomizedSearchCV(
        pipe, param_grid, scoring=bad_class_f1, cv=3, n_jobs=-1,
        n_iter=12, random_state=RANDOM_STATE,
    )
    search.fit(X_train, y_train)
    return search


def evaluate(name, model, X_test, y_test):
    preds = model.predict(X_test)
    print(f"=== {name} (tuned) ===")
    print(confusion_matrix(y_test, preds))
    print(classification_report(y_test, preds, target_names=["Bad (0)", "Good (1)"]))


def main():
    X_train, X_test, y_train, y_test = load_and_split()

    print("Tuning Logistic Regression...")
    lr_search = tune_logistic_regression(X_train, y_train)
    print(f"Best params: {lr_search.best_params_}")
    print(f"Best CV Bad-class F1: {lr_search.best_score_:.4f}\n")

    print("Tuning Random Forest...")
    rf_search = tune_random_forest(X_train, y_train)
    print(f"Best params: {rf_search.best_params_}")
    print(f"Best CV Bad-class F1: {rf_search.best_score_:.4f}\n")

    evaluate("Logistic Regression", lr_search.best_estimator_, X_test, y_test)
    evaluate("Random Forest", rf_search.best_estimator_, X_test, y_test)

    # Save tuned artifacts in the same shape model_evaluation.py expects:
    # separate scaler + classifier for LR, single classifier for RF.
    lr_scaler = lr_search.best_estimator_.named_steps["scaler"]
    lr_clf = lr_search.best_estimator_.named_steps["clf"]
    rf_clf = rf_search.best_estimator_.named_steps["clf"]

    joblib.dump(lr_clf, "lr_model.joblib")
    joblib.dump(lr_scaler, "lr_scaler.joblib")
    joblib.dump(rf_clf, "rf_model.joblib")
    print("Saved tuned models: lr_model.joblib, lr_scaler.joblib, rf_model.joblib")


if __name__ == "__main__":
    main()
