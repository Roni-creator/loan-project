"""
Feature Importance Export for Power BI
BI-ML Creditworthiness Classification Project

Fits the tuned LR and RF pipelines on the training split, then exports
one tidy CSV: feature, LR coefficient, RF importance (sums to 1.0),
ranks, and a driver type (willingness vs ability to pay).

NOTE: the driver-type mapping below is a working assumption -- review it.
"""

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from imblearn.over_sampling import SMOTE

RANDOM_STATE = 42

WILLINGNESS = {
    "prior_loan_count", "prior_default_rate", "rollover_count",
    "days_to_first_repayment", "loannumber",
}


def driver_type(feature: str) -> str:
    if feature in WILLINGNESS:
        return "Willingness to pay"
    return "Ability to pay / profile"


def main(data_path: str = "model_ready_dataset.csv"):
    df = pd.read_csv(data_path)
    df["good_bad_flag"] = df["good_bad_flag"].map({"Good": 1, "Bad": 0})
    X = df.drop(columns=["good_bad_flag"])
    y = df["good_bad_flag"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, random_state=RANDOM_STATE, stratify=y
    )

    # Logistic Regression (scaled, so coefficients are comparable)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_train)
    Xs_res, y_res = SMOTE(random_state=RANDOM_STATE).fit_resample(Xs, y_train)
    lr = LogisticRegression(C=0.1, max_iter=1000, random_state=RANDOM_STATE)
    lr.fit(Xs_res, y_res)

    # Random Forest
    X_res, y_res_rf = SMOTE(random_state=RANDOM_STATE).fit_resample(X_train, y_train)
    rf = RandomForestClassifier(n_estimators=100, min_samples_leaf=5,
                                class_weight="balanced", random_state=RANDOM_STATE)
    rf.fit(X_res, y_res_rf)

    out = pd.DataFrame({
        "feature": X.columns,
        "lr_coefficient": lr.coef_[0],   # positive = pushes toward Good
        "rf_importance": rf.feature_importances_,
    })
    out["lr_abs_coefficient"] = out["lr_coefficient"].abs()
    out["lr_direction"] = out["lr_coefficient"].apply(
        lambda c: "Lowers default risk" if c > 0 else "Raises default risk")
    out["lr_rank"] = out["lr_abs_coefficient"].rank(ascending=False).astype(int)
    out["rf_rank"] = out["rf_importance"].rank(ascending=False).astype(int)
    out["driver_type"] = out["feature"].apply(driver_type)
    out = out.sort_values("rf_rank")

    out.to_csv("feature_importance.csv", index=False)
    print(out.head(15).to_string(index=False))
    print("\nSaved: feature_importance.csv")


if __name__ == "__main__":
    main()
