import { useState } from "react";
import { apiGet, apiPost } from "../../api.js";
import { COUNT_KEYS } from "../../lib/applyState.js";
import { NumField } from "../../components/Fields.jsx";

function HistoryGrid({ app, setHistoryValue }) {
  const f = (key, label, o = {}) => (
    <NumField
      key={`${key}-${app.historyVersion}`} label={label} value={app.history[key]}
      onValue={(v) => setHistoryValue(key, v)} {...o}
    />
  );
  return (
    <div>
      <h3>How did you repay your previous loans?</h3>
      <div className="grid">
        {f("on_time", "On time or early", { min: 0, max: 60 })}
        {f("slight", "1–3 days late", { min: 0, max: 60 })}
        {f("late", "4–30 days late", { min: 0, max: 60 })}
        {f("very_late", "Over 30 days late", { min: 0, max: 60 })}
      </div>
      <div className="grid" style={{ marginTop: 12 }}>
        {f("avg_late", "Typical days vs. due date", { min: -30, max: 120, step: 0.5, hint: "Negative = you usually pay early" })}
        {f("max_late", "Longest delay (days)", { min: -30, max: 400 })}
        {f("avg_amount", "Typical past loan (₦)", { min: 5000, max: 100000, step: 1000 })}
        {f("avg_term", "Typical past period (days)", { min: 7, max: 120 })}
      </div>
    </div>
  );
}

export default function StepHistory({ meta, app, update, setHistoryValue, onNext }) {
  const [cidInput, setCidInput] = useState(app.cid || "");
  const [msg, setMsg] = useState({ cls: "msg", text: "" });

  const modes = [
    ...(meta.lookup ? [["lookup", "I'm a returning customer", "We'll find your record using your customer ID."]] : []),
    ["manual", "I'll enter my history myself", "Tell us how you repaid your earlier loans."],
    ["first", "This is my first loan", "No history needed."],
  ];

  const find = async (id) => {
    setMsg({ cls: "msg", text: "Looking…" });
    try {
      const rec = await apiPost("/api/lookup", { customer_id: id });
      const profile = { ...app.profile };
      for (const k of ["dob", "employment", "bank", "account"]) if (rec[k]) profile[k] = rec[k];
      update({
        cid: id.trim(), found: true, profile,
        history: { ...app.history, ...rec.history },
        historyVersion: app.historyVersion + 1,
      });
      const n = COUNT_KEYS.reduce((a, k) => a + rec.history[k], 0);
      setMsg({ cls: "msg ok", text: `Found your record: ${n} previous loan(s). Adjust anything that looks wrong.` });
    } catch (e) {
      update({ found: false });
      setMsg({ cls: "msg err", text: e.message });
    }
  };

  const sample = async () => {
    try {
      const { customer_id } = await apiGet("/api/sample-id");
      setCidInput(customer_id);
      find(customer_id);
    } catch (e) {
      setMsg({ cls: "msg err", text: e.message });
    }
  };

  const next = () => {
    const err = (text) => setMsg({ cls: "msg err", text });
    if (!app.mode) return err("Choose an option to continue.");
    if (app.mode === "lookup" && !app.found) return err("Find your record first, or enter your history yourself.");
    if (app.mode !== "first" && COUNT_KEYS.reduce((a, k) => a + app.history[k], 0) === 0)
      return err("Enter at least one previous loan, or choose 'This is my first loan'.");
    onNext();
  };

  return (
    <>
      <h2>Your borrowing history</h2>
      <p className="sub">Your past repayments are the strongest signal of your willingness to repay.</p>
      <div className="opts">
        {modes.map(([val, title, desc]) => (
          <label key={val} className={"opt" + (app.mode === val ? " sel" : "")}>
            <input
              type="radio" name="mode" value={val} checked={app.mode === val}
              onChange={() => { update({ mode: val }); setMsg({ cls: "msg", text: "" }); }}
            />
            <div><b>{title}</b><span>{desc}</span></div>
          </label>
        ))}
      </div>

      <div>
        {app.mode === "lookup" && (
          <>
            <div className="row">
              <label className="f grow">
                Customer ID
                <input
                  type="text" placeholder="Paste your customer ID" autoComplete="off"
                  value={cidInput} onChange={(e) => setCidInput(e.target.value)}
                />
              </label>
              <button type="button" onClick={() => find(cidInput)}>Find my record</button>
              <button type="button" title="Demo: picks a random customer" onClick={sample}>Use a sample ID</button>
            </div>
            {app.found && <HistoryGrid app={app} setHistoryValue={setHistoryValue} />}
          </>
        )}
        {app.mode === "manual" && <HistoryGrid app={app} setHistoryValue={setHistoryValue} />}
        {app.mode === "first" && (
          <p className="msg">
            No borrowing history needed. Note: the models learned almost entirely from returning borrowers, so a first-loan result is less certain.
          </p>
        )}
      </div>

      <p className={msg.cls}>{msg.text}</p>
      <div className="nav">
        <span />
        <button className="primary" type="button" onClick={next}>Continue</button>
      </div>
    </>
  );
}
