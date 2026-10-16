"""
applicant_portal.py - Loan applicant web portal (Streamlit)
BI-ML Creditworthiness Classification Project

The applicant-facing side of the system: a borrower applies for a loan, the
system assembles the same 36 engineered features the models were trained on,
scores the application with BOTH trained pipelines, and returns a plain-language
indicative outcome with the reasons behind it (Logistic Regression
coefficient x scaled input - no SHAP/LIME, per the project delimitations).

Run:  python -m streamlit run applicant_portal.py

Needs in the same folder (all produced by threshold_tuning.py):
    logistic_regression_pipeline.joblib, random_forest_pipeline.joblib,
    thresholds.json, feature_columns.json, model_ready_extended.csv
Optional (enables "find my record"): traindemographics.csv, trainprevloans.csv
Submitted applications are appended to applications_log.csv (feeds Power BI).

CONVENTIONS (same as threshold_tuning.py): Bad = 0, Good = 1,
P(Good) = pipeline.predict_proba(X)[:, 1], predict GOOD if P(Good) >= threshold.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path

import altair as alt
import joblib
import numpy as np
import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_FILES = {
    "Logistic Regression": PROJECT_DIR / "logistic_regression_pipeline.joblib",
    "Random Forest": PROJECT_DIR / "random_forest_pipeline.joblib",
}
THRESHOLDS_PATH = PROJECT_DIR / "thresholds.json"
COLUMNS_PATH = PROJECT_DIR / "feature_columns.json"
TRAIN_PATH = PROJECT_DIR / "model_ready_extended.csv"
DEMO_PATH = PROJECT_DIR / "traindemographics.csv"
PREV_PATH = PROJECT_DIR / "trainprevloans.csv"
LOG_PATH = PROJECT_DIR / "applications_log.csv"

NAVY, TEAL, GOLD = "#14243A", "#2C7A68", "#DDA85A"

# Same label-encoding the pipeline used (sklearn LabelEncoder = alphabetical)
ACCOUNT_TYPES = {"Current": 0, "Other": 1, "Savings": 2}
EMPLOYMENT = {"Contract": 0, "Permanent": 1, "Retired": 2,
              "Self-Employed": 3, "Student": 4, "Unemployed": 5}
# get_dummies(drop_first=True) dropped the alphabetically first bank
BASE_BANK = "Access Bank"

WILLINGNESS = {
    "loannumber", "prior_loan_count", "prior_default_rate", "rollover_count",
    "days_to_first_repayment", "prior_max_days_late", "prior_ontime_rate",
    "has_prior_history",
}
LABELS = {
    "loannumber": "Number of loans with us",
    "loanamount": "Loan amount requested",
    "termdays": "Repayment period",
    "bank_account_type": "Account type",
    "employment_status_clients": "Employment status",
    "prior_loan_count": "Number of previous loans",
    "prior_default_rate": "Past loans repaid >3 days late",
    "rollover_count": "Past loans repaid >30 days late",
    "days_to_first_repayment": "Average days vs. due date",
    "interest_ratio": "Interest charged on this loan",
    "app_hour": "Time of day applied",
    "app_dayofweek": "Day of week applied",
    "age": "Age",
    "prior_avg_loanamount": "Average size of past loans",
    "prior_avg_termdays": "Average length of past loans",
    "prior_max_days_late": "Longest past delay",
    "prior_ontime_rate": "Share of past loans repaid on time",
    "loan_to_prior_avg": "This loan vs. past loan sizes",
    "has_prior_history": "Has a borrowing history",
    "bank": "Bank",
}


# ----------------------------------------------------------------- loading --
@st.cache_resource
def load_models():
    return {name: joblib.load(path) for name, path in MODEL_FILES.items()}


@st.cache_data
def load_reference():
    thresholds = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    columns = json.loads(COLUMNS_PATH.read_text(encoding="utf-8"))
    train = pd.read_csv(TRAIN_PATH)
    medians = train.drop(columns=["good_bad_flag"]).median(numeric_only=True).to_dict()
    interest_by_term = train.groupby("termdays")["interest_ratio"].median().to_dict()
    seen_pairs = set(zip(train["termdays"].astype(int), train["loanamount"].astype(float)))
    ranges = {"age": (float(train["age"].min()), float(train["age"].max()))}
    amounts = sorted(train["loanamount"].unique())
    terms = sorted(int(t) for t in train["termdays"].unique())
    return thresholds, columns, medians, interest_by_term, seen_pairs, ranges, amounts, terms


@st.cache_data
def load_records():
    """Optional lender records used for 'find my record'."""
    if not (DEMO_PATH.exists() and PREV_PATH.exists()):
        return None, None
    demo = pd.read_csv(DEMO_PATH)
    prev = pd.read_csv(PREV_PATH, parse_dates=["approveddate", "creationdate", "closeddate",
                                               "firstduedate", "firstrepaiddate"])
    return demo, prev


def lookup_customer(customer_id: str, demo: pd.DataFrame, prev: pd.DataFrame):
    rows = prev[prev["customerid"] == customer_id.strip()]
    if rows.empty:
        return None
    dl = (rows["firstrepaiddate"] - rows["firstduedate"]).dt.days
    on_time, very_late = int((dl <= 0).sum()), int((dl > 30).sum())
    late = int(((dl > 3) & (dl <= 30)).sum())
    slight = len(rows) - on_time - late - very_late   # 1-3 days late (and unknowns)
    rec = {
        "history": {
            "on_time": on_time, "slight": slight, "late": late, "very_late": very_late,
            "max_late": float(dl.max()) if dl.notna().any() else 0.0,
            "avg_late": float(dl.mean()) if dl.notna().any() else 0.0,
            "avg_amount": float(rows["loanamount"].mean()),
            "avg_term": float(rows["termdays"].mean()),
        }
    }
    d = demo[demo["customerid"] == customer_id.strip()]
    if not d.empty:
        d = d.iloc[0]
        rec["dob"] = pd.to_datetime(d["birthdate"]).date() if pd.notna(d["birthdate"]) else None
        rec["bank"] = d["bank_name_clients"] if pd.notna(d["bank_name_clients"]) else None
        rec["account"] = d["bank_account_type"] if pd.notna(d["bank_account_type"]) else None
        rec["employment"] = d["employment_status_clients"] if pd.notna(d["employment_status_clients"]) else None
    return rec


# -------------------------------------------------------- feature building --
def build_features(p: dict, columns, medians, interest_by_term) -> pd.DataFrame:
    """Turn the applicant's answers into the exact 36-column model input."""
    h = p["history"]
    now = datetime.now()
    f = {c: 0 for c in columns}
    age = (date.today() - p["dob"]).days / 365.25
    f.update(
        loanamount=float(p["amount"]), termdays=int(p["term"]),
        bank_account_type=ACCOUNT_TYPES[p["account"]],
        employment_status_clients=EMPLOYMENT[p["employment"]],
        interest_ratio=interest_by_term.get(int(p["term"]), medians["interest_ratio"]),
        app_hour=now.hour, app_dayofweek=now.weekday(), age=age,
    )
    if p["bank"] != BASE_BANK:
        f[f"bank_name_clients_{p['bank']}"] = 1

    if h is None:   # first loan: same treatment as training (count=0, rest median-imputed)
        for c in ("prior_default_rate", "rollover_count", "days_to_first_repayment",
                  "prior_avg_loanamount", "prior_avg_termdays", "prior_max_days_late",
                  "prior_ontime_rate", "loan_to_prior_avg"):
            f[c] = medians[c]
        f.update(prior_loan_count=0, loannumber=1, has_prior_history=0)
    else:
        n = h["on_time"] + h["slight"] + h["late"] + h["very_late"]
        f.update(
            prior_loan_count=n, loannumber=n + 1, has_prior_history=1,
            prior_default_rate=(h["late"] + h["very_late"]) / n,
            rollover_count=h["very_late"],
            days_to_first_repayment=h["avg_late"],
            prior_avg_loanamount=h["avg_amount"], prior_avg_termdays=h["avg_term"],
            prior_max_days_late=h["max_late"], prior_ontime_rate=h["on_time"] / n,
            loan_to_prior_avg=p["amount"] / h["avg_amount"],
        )
    return pd.DataFrame([f])[columns]


def score(models, thresholds, X: pd.DataFrame) -> dict:
    out = {}
    for name, pipe in models.items():
        pg = float(pipe.predict_proba(X)[:, 1][0])
        out[name] = {"p_good": pg, "threshold": thresholds[name], "good": pg >= thresholds[name]}
    return out


def recommendation(scores: dict):
    votes = [s["good"] for s in scores.values()]
    if all(votes):
        return "likely", "Looks good", "success", \
            "Both scoring models see this request as likely to be repaid. A loan officer will confirm the final decision."
    if not any(votes):
        return "refer", "Needs a loan officer's review", "error", \
            "Both scoring models flag a higher chance of repayment difficulty for this request. " \
            "That is not a final decline - a loan officer will review it, and the options below may help."
    return "review", "Needs a closer look", "warning", \
        "The two scoring models disagree on this request, so a loan officer will review it manually."


def lr_contributions(models, X: pd.DataFrame) -> pd.DataFrame:
    """Per-feature push on the Logistic Regression log-odds of Good (coef x scaled input)."""
    pipe = models["Logistic Regression"]
    scaler, clf = pipe.named_steps["scaler"], pipe.named_steps["clf"]
    z = scaler.transform(X)[0]
    contrib = pd.Series(clf.coef_[0] * z, index=X.columns)
    bank = contrib[[c for c in contrib.index if c.startswith("bank_name_clients_")]].sum()
    contrib = contrib.drop([c for c in contrib.index if c.startswith("bank_name_clients_")])
    contrib["bank"] = bank
    df = contrib.rename("contribution").reset_index().rename(columns={"index": "feature"})
    df["factor"] = df["feature"].map(LABELS)
    df["driver"] = np.where(df["feature"].isin(WILLINGNESS),
                            "Willingness to pay", "Ability to pay / profile")
    df["effect"] = np.where(df["contribution"] >= 0, "Helps your application", "Works against it")
    return df


def outcome_icon(scores) -> str:
    votes = [s["good"] for s in scores.values()]
    return "✅ Looks good" if all(votes) else ("🟠 Closer look" if any(votes) else "🔴 Review")


def log_application(ref: str, p: dict, X: pd.DataFrame, scores: dict, tier: str):
    row = X.copy()
    row.insert(0, "reference", ref)
    row.insert(1, "submitted_at", datetime.now().isoformat(timespec="seconds"))
    row["history_source"] = p["mode"]
    row["p_good_lr"] = scores["Logistic Regression"]["p_good"]
    row["p_good_rf"] = scores["Random Forest"]["p_good"]
    row["recommendation"] = tier
    row.to_csv(LOG_PATH, mode="a", header=not LOG_PATH.exists(), index=False)


# ------------------------------------------------------------------- UI -----
def hero():
    st.markdown(
        f"""
        <div style="background:{NAVY};padding:1.4rem 1.6rem;border-radius:14px;color:white;margin-bottom:1rem">
          <div style="font-size:1.7rem;font-weight:700">Apply for a loan</div>
          <div style="opacity:.85;margin-top:.2rem">
            Tell us about yourself and the loan you want. You'll get an instant indicative result
            <b>and the reasons behind it</b> - no black box.
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def history_inputs(mode: str, rec: dict | None, key: str):
    """Returns the history dict (or None for first loan) for the chosen mode."""
    if mode == "This is my first loan":
        st.info("No borrowing history needed. Note: the models learned almost entirely from "
                "returning borrowers, so results for a first loan are less certain.")
        return None
    h = (rec or {}).get("history", {})
    if mode.startswith("I'll enter"):
        st.caption("Think back over your **previous** loans with us. How did you repay each one?")
    else:
        st.caption("Pulled from your record - you can adjust anything that looks wrong.")
    c1, c2, c3, c4 = st.columns(4)
    on_time = c1.number_input("On time or early", 0, 60, int(h.get("on_time", 3)), key=f"ot_{key}")
    slight = c2.number_input("1-3 days late", 0, 60, int(h.get("slight", 0)), key=f"sl_{key}")
    late = c3.number_input("4-30 days late", 0, 60, int(h.get("late", 0)), key=f"la_{key}")
    very = c4.number_input("Over 30 days late", 0, 60, int(h.get("very_late", 0)), key=f"vl_{key}")
    if on_time + slight + late + very == 0:
        st.warning("Enter at least one previous loan, or choose 'This is my first loan'.")
        return "invalid"
    c5, c6, c7, c8 = st.columns(4)
    avg_late = c5.number_input("Typical days vs. due date", -30.0, 120.0,
                               float(round(h.get("avg_late", 0.0), 1)), 0.5, key=f"al_{key}",
                               help="Negative = you usually pay early. Positive = late.")
    max_late = c6.number_input("Longest delay (days)", -30.0, 400.0,
                               float(h.get("max_late", 0.0)), 1.0, key=f"ml_{key}")
    avg_amt = c7.number_input("Typical past loan (KSh)", 5000.0, 100000.0,
                              float(round(h.get("avg_amount", 15000.0), -2)), 1000.0, key=f"aa_{key}")
    avg_term = c8.number_input("Typical past period (days)", 7.0, 120.0,
                               float(round(h.get("avg_term", 30.0))), 1.0, key=f"at_{key}")
    return {"on_time": on_time, "slight": slight, "late": late, "very_late": very,
            "avg_late": avg_late, "max_late": max_late, "avg_amount": avg_amt, "avg_term": avg_term}


def main():
    st.set_page_config(page_title="Apply for a loan", page_icon="💳", layout="centered")
    needed = [*MODEL_FILES.values(), THRESHOLDS_PATH, COLUMNS_PATH, TRAIN_PATH]
    missing = [p.name for p in needed if not p.exists()]
    if missing:
        st.error("Missing files (run threshold_tuning.py first): " + ", ".join(missing))
        st.stop()

    models = load_models()
    thresholds, columns, medians, interest_by_term, seen_pairs, ranges, amounts, terms = load_reference()
    demo, prev = load_records()
    banks = [BASE_BANK] + sorted(c.removeprefix("bank_name_clients_") for c in columns
                                 if c.startswith("bank_name_clients_"))

    hero()

    # ---- Step 1: how should we get your history? (outside the form so it reacts instantly)
    st.subheader("1 · Your borrowing history")
    modes = ["This is my first loan", "I'll enter my history myself"]
    if demo is not None:
        modes.insert(0, "I'm a returning customer - find my record")
    mode = st.radio("How would you like to tell us?", modes, label_visibility="collapsed")

    rec, rec_id = None, "manual"
    if mode.startswith("I'm a returning"):
        c1, c2 = st.columns([3, 1])
        cid = c1.text_input("Customer ID", key="cid", placeholder="Paste your customer ID")
        if c2.button("Use a sample ID", help="Demo: picks a random customer from the dataset"):
            st.session_state["cid"] = str(prev["customerid"].sample(1).iloc[0])
            st.rerun()
        if cid:
            rec = lookup_customer(cid, demo, prev)
            if rec is None:
                st.error("We couldn't find that customer ID. Check it, or enter your history yourself.")
                st.stop()
            rec_id = cid.strip()
            n = sum(rec["history"][k] for k in ("on_time", "slight", "late", "very_late"))
            st.success(f"Found your record: {n} previous loan(s).")
        else:
            st.stop()

    history = history_inputs(mode, rec, rec_id)

    # ---- Step 2-3: about you + the loan (a form, so it submits once)
    with st.form("application"):
        st.subheader("2 · About you")
        a1, a2 = st.columns(2)
        default_dob = (rec or {}).get("dob") or date(1992, 1, 1)
        dob = a1.date_input("Date of birth", default_dob, min_value=date(1940, 1, 1),
                            max_value=date(date.today().year - 18, 12, 31), key=f"dob_{rec_id}")
        emp_default = (rec or {}).get("employment")
        employment = a2.selectbox("Employment status", list(EMPLOYMENT),
                                  index=list(EMPLOYMENT).index(emp_default) if emp_default in EMPLOYMENT else 1,
                                  key=f"emp_{rec_id}")
        b1, b2 = st.columns(2)
        bank_default = (rec or {}).get("bank")
        bank = b1.selectbox("Your bank", banks,
                            index=banks.index(bank_default) if bank_default in banks else 0, key=f"bank_{rec_id}")
        acc_default = (rec or {}).get("account")
        account = b2.selectbox("Account type", list(ACCOUNT_TYPES),
                               index=list(ACCOUNT_TYPES).index(acc_default) if acc_default in ACCOUNT_TYPES else 2,
                               key=f"acc_{rec_id}")

        st.subheader("3 · The loan you want")
        l1, l2 = st.columns(2)
        amount = l1.select_slider("Amount (KSh)", options=[int(a) for a in amounts], value=10000,
                                  format_func=lambda v: f"{v:,}")
        term = l2.select_slider("Repayment period (days)", options=terms, value=30)
        submitted = st.form_submit_button("Check my application", type="primary", use_container_width=True)

    if submitted:
        if history == "invalid":
            st.stop()
        st.session_state["p"] = {"mode": mode, "history": history, "dob": dob, "employment": employment,
                                 "bank": bank, "account": account, "amount": amount, "term": term}
        st.session_state["ref"] = "APP-" + uuid.uuid4().hex[:8].upper()
        st.session_state.pop("logged", None)

    p = st.session_state.get("p")
    if not p:
        return

    X = build_features(p, columns, medians, interest_by_term)
    scores = score(models, thresholds, X)
    tier, headline, kind, message = recommendation(scores)

    st.divider()
    st.subheader("Your indicative result")
    getattr(st, kind)(f"**{headline}.** {message}")
    interest = interest_by_term.get(int(p["term"]), 0.0)
    m1, m2, m3 = st.columns(3)
    m1.metric("You borrow", f"KSh {p['amount']:,.0f}")
    m2.metric("You repay", f"KSh {p['amount'] * (1 + interest):,.0f}", f"{interest:.0%} interest", delta_color="off")
    m3.metric("Within", f"{p['term']} days")

    notes = []
    if p["history"] is None:
        notes.append("First-time borrower: the models saw almost no first-time borrowers while learning, so treat this as low-confidence.")
    if (int(p["term"]), float(p["amount"])) not in seen_pairs:
        notes.append("This amount and period combination is rare or absent in the training data.")
    age = float(X["age"].iloc[0])
    if not ranges["age"][0] <= age <= ranges["age"][1]:
        notes.append("Your age is outside the range the models learned from.")
    for n in notes:
        st.caption("⚠️ " + n)

    # ---- why
    st.markdown("#### Why this result")
    contrib = lr_contributions(models, X)
    top = contrib.reindex(contrib["contribution"].abs().sort_values(ascending=False).index).head(7)
    chart = (
        alt.Chart(top).mark_bar().encode(
            x=alt.X("contribution:Q", title="← works against you        helps you →"),
            y=alt.Y("factor:N", sort=alt.EncodingSortField("contribution", order="descending"), title=None),
            color=alt.Color("driver:N", title="Type of signal",
                            scale=alt.Scale(domain=["Willingness to pay", "Ability to pay / profile"],
                                            range=[GOLD, TEAL])),
            tooltip=["factor", "effect", alt.Tooltip("contribution:Q", format=".2f"), "driver"],
        ).properties(height=260)
    )
    st.altair_chart(chart, use_container_width=True)
    st.caption("Bars show how strongly each answer moved the Logistic Regression model. "
               "**Willingness to pay** = how you've repaid before. **Ability to pay / profile** = the loan and your circumstances. "
               "These describe model behaviour - they are not proof of cause.")

    # ---- what-if
    st.markdown("#### What if I change my request?")
    w1, w2 = st.columns(2)
    alt_rows = []
    for a in amounts:
        if (int(p["term"]), float(a)) in seen_pairs:
            s = score(models, thresholds, build_features({**p, "amount": a}, columns, medians, interest_by_term))
            alt_rows.append({"Amount (KSh)": f"{int(a):,}", "Result": outcome_icon(s) + ("  ← you" if a == p["amount"] else "")})
    w1.caption(f"Different amount, {p['term']} days")
    w1.dataframe(pd.DataFrame(alt_rows), hide_index=True, use_container_width=True)
    term_rows = []
    for t in terms:
        if (int(t), float(p["amount"])) in seen_pairs:
            s = score(models, thresholds, build_features({**p, "term": t}, columns, medians, interest_by_term))
            term_rows.append({"Period (days)": t, "Result": outcome_icon(s) + ("  ← you" if t == p["term"] else "")})
    w2.caption(f"Different period, KSh {p['amount']:,.0f}")
    w2.dataframe(pd.DataFrame(term_rows), hide_index=True, use_container_width=True)

    with st.expander("Technical details"):
        st.write("Scores are P(Good) from each model. A request is flagged when the score is below that model's tuned cut-off. "
                 "Scores are rankings, not calibrated probabilities of repayment.")
        st.dataframe(pd.DataFrame(scores).T.rename(columns={"p_good": "P(Good)", "threshold": "Cut-off", "good": "Predicts Good"})
                     .round(3), use_container_width=True)
        st.dataframe(X.T.rename(columns={0: "value"}), use_container_width=True)

    # ---- submit
    st.divider()
    ref = st.session_state["ref"]
    if st.session_state.get("logged") == ref:
        st.success(f"Application submitted. Your reference is **{ref}**.")
    else:
        agree = st.checkbox("I confirm these details are correct and agree to them being used to review my application.")
        if st.button("Submit application", disabled=not agree):
            log_application(ref, p, X, scores, tier)
            st.session_state["logged"] = ref
            st.rerun()
    st.caption("This is a research prototype. The result is an indicative model output, not a lending decision or credit offer.")


if __name__ == "__main__":
    main()