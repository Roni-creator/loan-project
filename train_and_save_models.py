"""
Model Training & Serialisation
BI-ML Creditworthiness Classification Project

CRISP-DM Phase 4: Modelling
Loads model_ready_dataset.csv, reproduces the same 70/30 stratified
split used to produce test_set.csv, applies SMOTE to the training
fold only, fits Logistic Regression and Random Forest, and saves
the artifacts model_evaluation.py expects:
lr_model.joblib, lr_scaler.joblib, rf_model.joblib
"""

import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from imblearn.over_sampling import SMOTE

RANDOM_STATE = 42
TEST_SIZE = 0.30  # confirmed: reproduces test_set.csv exactly at random_state=42

DATA_DIR = "."


def load_and_encode_target(data_dir: str = DATA_DIR) -> pd.DataFrame:
    df = pd.read_csv(f"{data_dir}/model_ready_dataset.csv")
    # Good = 1, Bad = 0, per confirmed convention (matches model_evaluation.py
    # target_names=["Bad (0)", "Good (1)"])
    df["good_bad_flag"] = df["good_bad_flag"].map({"Good": 1, "Bad": 0})
    return df


def split(df: pd.DataFrame):
    X = df.drop(columns=["good_bad_flag"])
    y = df["good_bad_flag"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    return X_train, X_test, y_train, y_test


def train_logistic_regression(X_train, y_train):
    """
    Scaled inputs + class_weight='balanced' + SMOTE-resampled training
    fold, per Section 3.2.4 of the proposal.
    """
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    smote = SMOTE(random_state=RANDOM_STATE)
    X_res, y_res = smote.fit_resample(X_train_scaled, y_train)

    model = LogisticRegression(
        penalty="l2", class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
    )
    model.fit(X_res, y_res)
    return model, scaler


def train_random_forest(X_train, y_train):
    """
    Random Forest trained on raw (unscaled) features, SMOTE-resampled,
    per Section 3.2.4.
    """
    smote = SMOTE(random_state=RANDOM_STATE)
    X_res, y_res = smote.fit_resample(X_train, y_train)

    model = RandomForestClassifier(random_state=RANDOM_STATE)
    model.fit(X_res, y_res)
    return model


def main():
    df = load_and_encode_target()
    X_train, X_test, y_train, y_test = split(df)

    print(f"Train shape: {X_train.shape} | Test shape: {X_test.shape}")
    print(f"Train class balance:\n{y_train.value_counts()}")

    lr_model, lr_scaler = train_logistic_regression(X_train, y_train)
    rf_model = train_random_forest(X_train, y_train)

    joblib.dump(lr_model, "lr_model.joblib")
    joblib.dump(lr_scaler, "lr_scaler.joblib")
    joblib.dump(rf_model, "rf_model.joblib")

    print("\nSaved: lr_model.joblib, lr_scaler.joblib, rf_model.joblib")
    print("Ready for model_evaluation.py")


if __name__ == "__main__":
    main()
