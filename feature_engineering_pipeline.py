"""
Feature Engineering & Merge Pipeline
BI-ML Creditworthiness Classification Project

CRISP-DM Phase 3: Data Preparation
Engineers the three willingness-to-pay behavioural features from
trainprevloans.csv, merges all three source files on customerid,
and produces a single analytical dataset ready for missing-value
treatment, encoding, and modelling.
"""



import pandas as pd
from sklearn.preprocessing import LabelEncoder

DEFAULT_LATE_DAYS_THRESHOLD = 3   # prior_default_rate proxy
ROLLOVER_LATE_DAYS_THRESHOLD = 30  # rollover_count proxy
MISSINGNESS_DROP_THRESHOLD = 0.50  # drop columns missing above this rate

DATA_DIR = "."  # adjust to your local path

# Columns confirmed >50% missing on this dataset — dropped before imputation,
# per Section 3.2.3. Kept as an explicit list (not just the threshold check)
# so the drop decision is visible and reviewable, not silently automatic.
HIGH_MISSINGNESS_COLUMNS = [
    "bank_branch_clients",        # 99.2% missing
    "level_of_education_clients", # 89.9% missing
    "referredby",                 # 86.5% missing
]

# Columns dropped for reasons other than missingness (per proposal's
# domain-driven pruning strategy): raw identifiers/dates not usable as
# model features directly, and raw GPS coordinates (privacy + sparsity).
NON_FEATURE_COLUMNS = [
    "customerid", "systemloanid", "approveddate", "creationdate",
    "birthdate", "longitude_gps", "latitude_gps",
]

BINARY_CATEGORICAL_COLUMNS = ["bank_account_type", "employment_status_clients"]
MULTI_CATEGORICAL_COLUMNS = ["bank_name_clients"]

# VIF check on loanamount/totaldue/termdays showed severe collinearity
# between loanamount and totaldue (corr=0.994, VIF>240) — totaldue is
# largely determined by loanamount + interest/fees, so it adds redundant
# rather than independent signal. Dropped in favour of the cleaner,
# more directly interpretable loanamount. termdays VIF=4.44 (acceptable,
# kept as-is).
COLLINEAR_COLUMNS_TO_DROP = ["totaldue"]


def load_raw(data_dir: str = DATA_DIR):
    demo = pd.read_csv(f"{data_dir}/traindemographics.csv")
    perf = pd.read_csv(f"{data_dir}/trainperf.csv")
    prev = pd.read_csv(
        f"{data_dir}/trainprevloans.csv",
        parse_dates=["approveddate", "creationdate", "closeddate",
                     "firstduedate", "firstrepaiddate"],
    )
    return demo, perf, prev


def engineer_behavioural_features(prev: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate trainprevloans.csv (one row per previous loan) into
    one row per customerid with three willingness-to-pay features.
    """ 
    prev = prev.copy()

    # Days between due date and first repayment date, per previous loan.
    # Positive = late, zero/negative = on-time or early.
    prev["days_late"] = (
        prev["firstrepaiddate"] - prev["firstduedate"]
    ).dt.days

    prev["is_proxy_default"] = prev["days_late"] > DEFAULT_LATE_DAYS_THRESHOLD
    prev["is_rollover"] = prev["days_late"] > ROLLOVER_LATE_DAYS_THRESHOLD

    agg = (
        prev.groupby("customerid")
        .agg(
            prior_loan_count=("systemloanid", "count"),
            prior_default_rate=("is_proxy_default", "mean"),
            rollover_count=("is_rollover", "sum"),
            days_to_first_repayment=("days_late", "mean"),
        )
        .reset_index()
    )
    return agg


def merge_datasets(
    demo: pd.DataFrame, perf: pd.DataFrame, behavioural: pd.DataFrame
) -> pd.DataFrame:
    """
    Left join anchored on trainperf (the target file), per Section 3.2.3:
    trainperf -> traindemographics -> aggregated trainprevloans.
    Customers with no prior loans get nulls on behavioural features,
    which are imputed (not dropped) in the next pipeline stage.
    """
    # traindemographics has duplicate customerids (4,346 rows, 4,334 unique);
    # a plain join would duplicate loan rows, so keep one row per customer.
    demo = demo.drop_duplicates(subset="customerid", keep="first")
    merged = perf.merge(demo, on="customerid", how="left")
    merged = merged.merge(behavioural, on="customerid", how="left")

    # No prior loan history -> prior_loan_count is genuinely 0, not missing.
    merged["prior_loan_count"] = merged["prior_loan_count"].fillna(0)

    return merged


def drop_high_missingness(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns above MISSINGNESS_DROP_THRESHOLD, per Section 3.2.3."""
    df = df.copy()
    cols_to_drop = [c for c in HIGH_MISSINGNESS_COLUMNS if c in df.columns]
    return df.drop(columns=cols_to_drop)


def treat_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Numeric columns (<50% missing): median imputation.
    Categorical columns (<50% missing): mode imputation.
    Applied after high-missingness columns are already dropped.
    """
    df = df.copy()
    numeric_cols = df.select_dtypes(include="number").columns
    categorical_cols = df.select_dtypes(include="object").columns

    for col in numeric_cols:
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    for col in categorical_cols:
        if df[col].isna().any():
            mode_val = df[col].mode(dropna=True)
            if len(mode_val) > 0:
                df[col] = df[col].fillna(mode_val.iloc[0])

    return df


def encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Binary categoricals -> label encoding.
    Multi-category nominal -> one-hot encoding, first dummy dropped
    (avoids multicollinearity in Logistic Regression), per Section 3.2.3.
    """
    df = df.copy()

    for col in BINARY_CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = LabelEncoder().fit_transform(df[col].astype(str))

    multi_cols = [c for c in MULTI_CATEGORICAL_COLUMNS if c in df.columns]
    if multi_cols:
        df = pd.get_dummies(df, columns=multi_cols, drop_first=True)

    return df


def drop_collinear_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop columns flagged by the VIF/correlation check in Section 3.2.3.
    loanamount vs totaldue: corr=0.994, VIF>240 for both -> drop totaldue.
    termdays: VIF=4.44, acceptable, kept.
    """
    df = df.copy()
    cols_to_drop = [c for c in COLLINEAR_COLUMNS_TO_DROP if c in df.columns]
    return df.drop(columns=cols_to_drop)


def check_vif(df: pd.DataFrame, columns=("loanamount", "totaldue", "termdays")) -> pd.DataFrame:
    """
    Run the VIF check referenced in Section 3.2.3. Requires statsmodels.
    Returns a small DataFrame of VIF scores per column for reporting.
    """
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor

    cols = [c for c in columns if c in df.columns]
    X = sm.add_constant(df[cols].dropna())
    results = []
    for i, col in enumerate(X.columns):
        if col == "const":
            continue
        results.append({"feature": col, "vif": variance_inflation_factor(X.values, i)})
    return pd.DataFrame(results)


def drop_non_feature_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop identifiers/dates/raw GPS not usable directly as model input."""
    df = df.copy()
    cols_to_drop = [c for c in NON_FEATURE_COLUMNS if c in df.columns]
    return df.drop(columns=cols_to_drop)


def run_pipeline(data_dir: str = DATA_DIR) -> pd.DataFrame:
    demo, perf, prev = load_raw(data_dir)
    behavioural = engineer_behavioural_features(prev)
    merged = merge_datasets(demo, perf, behavioural)
    merged = drop_high_missingness(merged)
    merged = treat_missing_values(merged)
    merged = encode_categoricals(merged)
    return merged


def run_pipeline_model_ready(data_dir: str = DATA_DIR) -> pd.DataFrame:
    """
    Full pipeline including removal of identifier/date/GPS columns and
    the VIF-flagged collinear column — output is ready to feed directly
    into train-test split and modelling (customerid retained separately
    if needed for lookups).
    """
    df = run_pipeline(data_dir)
    df = drop_non_feature_columns(df)
    df = drop_collinear_columns(df)
    return df


if __name__ == "__main__":
    # Stage 1 output: merged + feature-engineered, before cleaning.
    raw_merged = merge_datasets(*load_raw()[:2], engineer_behavioural_features(load_raw()[2]))
    print(f"Stage 1 (merged, raw) shape: {raw_merged.shape}")
    print(f"Missing values remaining:\n{raw_merged.isna().sum()[raw_merged.isna().sum() > 0]}\n")

    # VIF check, run before the collinear column is dropped, for the record.
    cleaned_for_vif = drop_high_missingness(raw_merged)
    cleaned_for_vif = treat_missing_values(cleaned_for_vif)
    vif_report = check_vif(cleaned_for_vif)
    print("VIF check (loanamount, totaldue, termdays):")
    print(vif_report)
    print()

    # Stage 2 output: cleaned, imputed, encoded, de-collinearised, model-ready.
    df = run_pipeline_model_ready()
    print(f"Stage 2 (model-ready) shape: {df.shape}")
    print(f"Missing values remaining: {df.isna().sum().sum()} (should be 0)")
    print(f"'totaldue' present: {'totaldue' in df.columns} (should be False)")
    print()
    print(df.head(5))

    df.to_csv("model_ready_dataset.csv", index=False)
    print("\nSaved: model_ready_dataset.csv")