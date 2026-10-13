"""
build_all.py - one command to generate everything a fresh clone is missing.

    python build_all.py

Prerequisite: the three raw files (traindemographics.csv, trainperf.csv,
trainprevloans.csv) must be in this folder. Git ignores *.csv, so they are never
in the repository. Source: Zindi, Data Science Nigeria Challenge #1: Loan Default
Prediction - see README.md "Data".

Generates (all git-ignored): model_ready_dataset.csv, model_ready_extended.csv,
test_set.csv, feature_importance.csv, threshold_comparison.csv, *_test_predictions.csv,
*.joblib models, thresholds.json, feature_columns.json, encoding_maps.json, and creditscore.db with demo users.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_FILES = ["traindemographics.csv", "trainperf.csv", "trainprevloans.csv"]

STEPS = [
    ("Merge + feature engineering", ["feature_engineering_pipeline.py"]),
    ("Extended features", ["-c", "import extra_features_experiment as e; e.build_extended()"]),
    ("Train, tune thresholds, export", ["threshold_tuning.py"]),
]


def missing_raw_files(folder=HERE):
    return [f for f in RAW_FILES if not (Path(folder) / f).exists()]


def main():
    missing = missing_raw_files()
    if missing:
        sys.exit("Missing raw data file(s): " + ", ".join(missing) +
                 f"\nDownload them from the Zindi competition page (see README.md > Data), "
                 f"place them in {HERE}, then rerun.")
    for label, args in STEPS:
        print(f"\n=== {label} ===", flush=True)
        if subprocess.run([sys.executable, *args], cwd=HERE).returncode != 0:
            sys.exit(f"Step failed: {label}")
    print("\n=== Database + demo accounts ===", flush=True)
    import db
    db.seed_demo(runs_csv=HERE / "threshold_comparison.csv")
    print("\nDone. Start the app with:  python -m streamlit run app.py")


if __name__ == "__main__":
    main()