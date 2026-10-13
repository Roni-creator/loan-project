from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
import streamlit as st
from sklearn.metrics import classification_report, confusion_matrix, f1_score

import db


PROJECT_DIR = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_DIR / "model_ready_extended.csv"   # the 36-feature set the models are trained on
FEATURE_COLUMNS_PATH = PROJECT_DIR / "feature_columns.json"
TEST_SET_PATH = PROJECT_DIR / "test_set.csv"
IMPORTANCE_PATH = PROJECT_DIR / "feature_importance.csv"
THRESHOLDS_PATH = PROJECT_DIR / "thresholds.json"

# Role -> pages that role may open (maps to the three dashboards in the proposal)
ROLE_PAGES = {
    "business_manager": ["Portfolio overview"],
    "credit_analyst": ["Portfolio overview", "Model evaluation"],
    "loan_officer": ["Score applications"],
}

MODEL_ARTIFACTS = {
    "Logistic Regression": PROJECT_DIR / "logistic_regression_pipeline.joblib",
    "Random Forest": PROJECT_DIR / "random_forest_pipeline.joblib",
}


@st.cache_data
def load_dataset(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_resource
def load_model(path: Path):
    return joblib.load(path)


@st.cache_data
def load_thresholds(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as threshold_file:
        return json.load(threshold_file)


def encode_target(target: pd.Series) -> pd.Series:
    labels = {"Good": 1, "Bad": 0, "good": 1, "bad": 0, "1": 1, "0": 0}

    def encode(value):
        if pd.isna(value):
            raise ValueError("The target column contains missing values.")
        if value in (0, 1):
            return int(value)
        if isinstance(value, str) and value.strip() in labels:
            return labels[value.strip()]
        raise ValueError(f"Unrecognized target label: {value!r}. Expected Good/Bad or 0/1.")

    return target.map(encode).astype(int)


def model_feature_names(model) -> list[str] | None:
    names = getattr(model, "feature_names_in_", None)
    if names is not None:
        return list(names)
    final_estimator = getattr(model, "steps", [])[-1][1] if getattr(model, "steps", []) else model
    names = getattr(final_estimator, "feature_names_in_", None)
    return list(names) if names is not None else None


def prepare_features(frame: pd.DataFrame, model) -> pd.DataFrame:
    features = frame.drop(columns=["good_bad_flag"], errors="ignore").copy()
    expected = model_feature_names(model)
    if expected is not None:
        missing = [column for column in expected if column not in features.columns]
        if missing:
            raise ValueError(
                "The input is missing model features: " + ", ".join(missing)
            )
        extras = [column for column in features.columns if column not in expected]
        if extras:
            st.info("Ignoring extra columns: " + ", ".join(extras))
        features = features.loc[:, expected]
    else:
        expected_count = getattr(model, "n_features_in_", None)
        if expected_count is not None and features.shape[1] != expected_count:
            raise ValueError(
                f"This model expects {expected_count} features, but the input has "
                f"{features.shape[1]}."
            )
    return features


def bad_class_probability(model, features: pd.DataFrame):
    probabilities = model.predict_proba(features)
    classes = list(model.classes_)
    if 0 not in classes:
        raise ValueError("This model does not expose class 0 (Bad) probabilities.")
    bad_index = classes.index(0)
    good_index = classes.index(1)
    return probabilities[:, bad_index], probabilities[:, good_index]


def get_threshold(model_name: str, thresholds: dict[str, float]) -> float:
    threshold = float(thresholds.get(model_name, 0.5))
    if not 0 < threshold < 1:
        raise ValueError(f"Invalid P(Good) threshold for {model_name}: {threshold}")
    return threshold


def show_dashboard(dataset: pd.DataFrame):
    st.subheader("Portfolio overview")
    if "good_bad_flag" not in dataset:
        st.error("The prepared dataset has no 'good_bad_flag' target column.")
        return

    try:
        target = encode_target(dataset["good_bad_flag"])
    except ValueError as error:
        st.error(str(error))
        return

    bad_count = int((target == 0).sum())
    good_count = int((target == 1).sum())
    first, second, third = st.columns(3)
    first.metric("Applications", f"{len(dataset):,}")
    second.metric("Good", f"{good_count:,}")
    third.metric("Bad", f"{bad_count:,}")

    chart_col, table_col = st.columns(2)
    with chart_col:
        st.caption("Target distribution")
        st.bar_chart(pd.Series({"Bad": bad_count, "Good": good_count}, name="Applications"))
    with table_col:
        st.caption("Prepared dataset preview")
        st.dataframe(dataset.head(10), use_container_width=True)

    if IMPORTANCE_PATH.exists():
        importance = load_dataset(IMPORTANCE_PATH)
        required = {"feature", "rf_importance"}
        if required.issubset(importance.columns):
            st.subheader("Leading Random Forest drivers")
            top = importance.nlargest(10, "rf_importance").set_index("feature")
            st.bar_chart(top["rf_importance"])
            st.caption(
                "Feature importance describes model behavior; it should not be "
                "interpreted as causal evidence."
            )


def show_evaluation(test_set: pd.DataFrame, model_name: str, model, threshold: float):
    if "good_bad_flag" not in test_set:
        st.error("The held-out test set has no 'good_bad_flag' target column.")
        return
    try:
        y_true = encode_target(test_set["good_bad_flag"])
        features = prepare_features(test_set, model)
        _, p_good = bad_class_probability(model, features)
    except (ValueError, KeyError) as error:
        st.error(f"Could not evaluate this model: {error}")
        return

    predictions = (p_good >= threshold).astype(int)
    bad_f1 = f1_score(y_true, predictions, pos_label=0, zero_division=0)
    st.metric("Bad-class F1", f"{bad_f1:.3f}")

    matrix = confusion_matrix(y_true, predictions, labels=[0, 1])
    st.caption("Confusion matrix — rows are actual, columns are predicted (Bad, Good)")
    st.dataframe(
        pd.DataFrame(matrix, index=["Actual Bad", "Actual Good"],
                     columns=["Predicted Bad", "Predicted Good"]),
        use_container_width=True,
    )
    report = classification_report(
        y_true, predictions, labels=[0, 1], target_names=["Bad", "Good"],
        output_dict=True, zero_division=0,
    )
    st.dataframe(pd.DataFrame(report).transpose(), use_container_width=True)


def show_login() -> bool:
    """Render the login form; return True once a user is authenticated."""
    if st.session_state.get("user"):
        return True
    st.title("Loan Creditworthiness")
    st.subheader("Sign in")
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        user = db.verify_user(username.strip(), password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        st.error("Invalid username or password.")
    return False


def show_scoring(model_name: str, model, threshold: float, user_id=None):
    st.write(
        "Upload a CSV with the same engineered feature columns used to train the "
        "selected model. A target column, if present, is ignored."
    )
    if FEATURE_COLUMNS_PATH.exists():
        columns = json.loads(FEATURE_COLUMNS_PATH.read_text(encoding="utf-8"))
        st.download_button(
            "Download blank template (required columns)",
            data=(",".join(columns) + "\n").encode("utf-8"),
            file_name="scoring_template.csv", mime="text/csv",
        )
        st.caption(f"Models need all {len(columns)} feature columns. "
                   "Use the extended dataset format, not the 26-column baseline.")
    uploaded = st.file_uploader("Applications CSV", type=["csv"], key="score_upload")
    if uploaded is None:
        st.info("Upload a CSV to generate predictions.")
        return
    try:
        input_frame = pd.read_csv(uploaded)
        features = prepare_features(input_frame, model)
        p_bad, p_good = bad_class_probability(model, features)
    except (ValueError, KeyError, pd.errors.ParserError) as error:
        st.error(f"Could not score this file: {error}")
        return

    results = input_frame.drop(columns=["good_bad_flag"], errors="ignore").copy()
    results["probability_bad"] = p_bad
    results["probability_good"] = p_good
    results["prediction"] = ["Good" if probability >= threshold else "Bad"
                             for probability in p_good]
    st.dataframe(results.head(100), use_container_width=True)
    if st.button("Save predictions to database"):
        feature_rows = features.head(500).to_dict("records")
        for row, pb in zip(feature_rows, p_bad[:500]):
            db.log_prediction(row, model_name, float(pb), threshold, user_id=user_id)
        st.success(f"Saved {len(feature_rows)} predictions.")
    st.download_button(
        "Download scored CSV",
        data=results.to_csv(index=False).encode("utf-8"),
        file_name=f"{model_name.lower().replace(' ', '_')}_scored.csv",
        mime="text/csv",
    )


def main():
    st.set_page_config(page_title="Loan Creditworthiness", page_icon="📊", layout="wide")
    db.init_db()
    if not show_login():
        st.stop()
    user = st.session_state["user"]
    st.title("Loan Creditworthiness")
    st.caption("Explore the prepared portfolio, review model performance, and score applications.")

    if not DATASET_PATH.exists():
        st.error(f"Prepared dataset not found: {DATASET_PATH.name}")
        st.stop()
    dataset = load_dataset(DATASET_PATH)

    st.sidebar.write(f"Signed in as **{user['username']}** ({user['role'].replace('_', ' ')})")
    if st.sidebar.button("Sign out"):
        st.session_state.pop("user", None)
        st.rerun()
    pages = ROLE_PAGES[user["role"]]
    page = st.sidebar.radio("Workspace", pages)
    model_name = st.sidebar.selectbox("Model", list(MODEL_ARTIFACTS))
    artifact = MODEL_ARTIFACTS[model_name]
    if not artifact.exists():
        st.error(f"Model artifact not found: {artifact.name}")
        st.stop()

    try:
        model = load_model(artifact)
        threshold = get_threshold(model_name, load_thresholds(THRESHOLDS_PATH))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        st.error(f"Could not load model settings: {error}")
        st.stop()

    st.sidebar.caption(f"Bad classification threshold: P(Good) < {threshold:.2f}")

    if page == "Portfolio overview":
        show_dashboard(dataset)
    elif page == "Model evaluation":
        if not TEST_SET_PATH.exists():
            st.error(f"Held-out test set not found: {TEST_SET_PATH.name}")
            st.stop()
        show_evaluation(load_dataset(TEST_SET_PATH), model_name, model, threshold)
    else:
        show_scoring(model_name, model, threshold, user_id=user["user_id"])


if __name__ == "__main__":
    main()