import pandas as pd
import joblib

# Load everything saved from training — no need to retrain
lr_model = joblib.load("lr_model.joblib")
lr_scaler = joblib.load("lr_scaler.joblib")
rf_model = joblib.load("rf_model.joblib")

test_df = pd.read_csv("test_set.csv")
X_test = test_df.drop(columns=["good_bad_flag"])
y_test = test_df["good_bad_flag"]

print("Test set loaded:", X_test.shape)
print(y_test.value_counts())

from sklearn.metrics import confusion_matrix, classification_report

# Random Forest predicts directly on raw features (no scaling needed)
rf_preds = rf_model.predict(X_test)

# Logistic Regression needs the SAME scaler used during training,
# applied here with .transform() (not .fit_transform() — we don't
# want to re-fit the scaler on test data, only apply what it already learned)
X_test_scaled = lr_scaler.transform(X_test)
lr_preds = lr_model.predict(X_test_scaled)

print("=== Random Forest ===")
print(confusion_matrix(y_test, rf_preds))
print(classification_report(y_test, rf_preds, target_names=["Bad (0)", "Good (1)"]))

print("=== Logistic Regression ===")
print(confusion_matrix(y_test, lr_preds))
print(classification_report(y_test, lr_preds, target_names=["Bad (0)", "Good (1)"]))