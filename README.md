# Loan Creditworthiness (BI-ML framework)

Interpretable loan-default classification (Logistic Regression and Random Forest) on
alternative financial behaviour data, with a login-protected Streamlit app, a SQLite
database, and CSV exports for the Power BI dashboards.

## Setup from a fresh clone

Git ignores all `*.csv`, `*.joblib` and the database, so a clone contains code only.
Everything else is generated.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### Data

The data is the Zindi competition dataset
[Data Science Nigeria Challenge #1: Loan Default Prediction](https://zindi.world/competitions/data-science-nigeria-challenge-1-loan-default-prediction).
It is not redistributed in this repository: download it yourself from the competition's
Data tab (this needs a free Zindi account and acceptance of the competition rules; check the
data licence before sharing derived files).

Put these three files in the project folder (next to `build_all.py`):

- `traindemographics.csv`
- `trainperf.csv`
- `trainprevloans.csv`

### Build everything

```powershell
python build_all.py
```

This runs, in order: merge and feature engineering, extended features, model training and
threshold tuning, then creates `creditscore.db` with the demo accounts. If a raw file is
missing it stops and says which one.

### Run

```powershell
python -m streamlit run app.py
```

## Accounts and roles

`python build_all.py` (or `python db.py`) creates three **demo** accounts. They exist so a
fresh install can log in; change them before showing anyone.

| Username | Password | Role | Pages |
|---|---|---|---|
| `manager` | `ChangeMe!1` | business_manager | Portfolio overview |
| `analyst` | `ChangeMe!2` | credit_analyst | Portfolio overview, Model evaluation |
| `officer` | `ChangeMe!3` | loan_officer | Score applications |

```powershell
python db.py set-password manager          # prompts for a new password
python db.py add-user jane credit_analyst  # prompts for a password
python db.py list-users
```

`python db.py` is idempotent: rerunning it never duplicates users or model-run rows.
Passwords are stored as bcrypt hashes. If you open the app before seeding, the login page
tells you to run `python db.py`.

## What gets generated (and is git-ignored)

| File | Produced by | Used by |
|---|---|---|
| `model_ready_dataset.csv` | `feature_engineering_pipeline.py` | input to the extended features only |
| `model_ready_extended.csv` | `extra_features_experiment.py` | model training, app Portfolio overview |
| `encoding_maps.json` | `feature_engineering_pipeline.py` | app: translates raw category text in uploads to training codes |
| `*_pipeline.joblib`, `thresholds.json`, `feature_columns.json` | `threshold_tuning.py` | app scoring and evaluation |
| `test_set.csv`, `*_test_predictions.csv`, `threshold_comparison.csv` | `threshold_tuning.py` | app evaluation, Power BI |
| `feature_importance.csv` | `threshold_tuning.py` | app overview, Power BI driver dashboard |
| `creditscore.db` | `db.py` | login, saved predictions |

Scoring files must contain the same columns as `feature_columns.json` (the app offers a
blank template download). Raw category text is accepted for `bank_account_type`,
`employment_status_clients` and `bank_name_clients` (e.g. `Savings`, `Permanent`, `GT Bank`);
the app converts it to the training codes. Already-encoded numbers also work. Missing numeric values are allowed; the model fills them with
medians learned from the training data only.

## Power BI

```powershell
python -c "import db; db.export_tables('.')"
```

writes `db_applicants.csv`, `db_predictions.csv`, `db_model_runs.csv` and `db_users.csv`
(no password hashes). Load them, plus `feature_importance.csv` and `threshold_comparison.csv`,
with the Text/CSV connector.

## Tests

```powershell
python -m pip install pytest
python -m pytest -q
```

Tests that need the generated files skip themselves until you have run `build_all.py`.

## Method notes

- Target: Bad (default) = 0, Good (repaid) = 1. Decision rule: predict Good when
  P(Good) >= the per-model threshold in `thresholds.json`.
- Thresholds are tuned on out-of-fold training predictions; the 30% test set is used once.
- Preprocessing that learns from data (median imputation, scaling) runs inside the model
  pipeline on training folds only. Missing categories become an explicit "Unknown" level.
- Predictions and feature importance describe model behaviour; they are not causal
  evidence or credit decisions.