# Loan Creditworthiness Project

## Run the Streamlit app

Install the project dependencies and start the app from the project directory:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app expects `model_ready_dataset.csv`, the fitted model pipeline artifacts
(`logistic_regression_pipeline.joblib` and `random_forest_pipeline.joblib`), and
optionally `test_set.csv`, `thresholds.json`, and `feature_importance.csv` in the
same directory as `app.py`.

Use **Portfolio overview** to inspect the prepared dataset and feature drivers,
**Model evaluation** to review metrics on the held-out test set, and **Score
applications** to upload a CSV and download model predictions. Scoring files
must contain the same engineered feature columns used by the selected model;
extra columns are ignored.

Predictions and feature importance are model outputs, not causal conclusions
or credit decisions. Review the model and applicable lending requirements
before using outputs operationally.
