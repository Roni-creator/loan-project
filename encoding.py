"""
Translate RAW categorical values (e.g. bank_account_type = "Savings") into the numeric
codes the models were trained on, using encoding_maps.json written by
feature_engineering_pipeline.py. Used by the app so uploads may contain either raw
text categories or already-encoded numbers.
"""
import json
from pathlib import Path

import pandas as pd

MAPS_PATH = Path(__file__).resolve().parent / "encoding_maps.json"
LABEL_COLUMNS = ("bank_account_type", "employment_status_clients")
ONEHOT_COLUMN = "bank_name_clients"


def load_maps(path=MAPS_PATH):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _clean(series: pd.Series) -> pd.Series:
    return series.fillna("Unknown").astype(str).str.strip()


def encode_raw_categoricals(frame: pd.DataFrame, maps) -> pd.DataFrame:
    """Return a copy with any raw text category columns replaced by training codes.
    Numeric (already encoded) columns pass through untouched."""
    out = frame.copy()
    text_label = [c for c in LABEL_COLUMNS
                  if c in out and not pd.api.types.is_numeric_dtype(out[c])]
    has_bank = ONEHOT_COLUMN in out
    if not text_label and not has_bank:
        return out
    if maps is None:
        raise ValueError("encoding_maps.json not found; run `python build_all.py` first "
                         "so raw categories can be translated.")

    for col in text_label:
        mapping = maps["label"][col]
        values = _clean(out[col])
        bad = sorted(set(values) - set(mapping))
        if bad:
            raise ValueError(f"Unrecognised {col} value(s) {bad}. Allowed: {sorted(mapping)}")
        out[col] = values.map(mapping).astype(int)

    if has_bank:
        spec = maps["onehot"][ONEHOT_COLUMN]
        values = _clean(out[ONEHOT_COLUMN])
        bad = sorted(set(values) - set(spec["kept"]) - {spec["baseline"]})
        if bad:
            raise ValueError(f"Unrecognised {ONEHOT_COLUMN} value(s) {bad}. "
                             f"Allowed: {sorted(spec['kept'] + [spec['baseline']])}")
        for category in spec["kept"]:
            out[f"{ONEHOT_COLUMN}_{category}"] = (values == category).astype(int)
        out = out.drop(columns=[ONEHOT_COLUMN])
    return out