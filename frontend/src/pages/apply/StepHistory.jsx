import { useState } from "react";
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
        {f("avg_amount", "Typical past loan (KSh)", { min: 5000, max: 100000, step: 1000 })}
        {f("avg_term", "Typical past period (days)", { min: 7, max: 120 })}
      </div>
    </div>
  );
}

// Step 1. The applicant always enters their own borrowing history. There is no
// shared "sample customer" lookup: that would show another person's record as the
// signed-in user's own details.
export default function StepHistory({ app, update, setHistoryValue, onNext }) {
  const [msg, setMsg] = useState({ cls: "msg", text: "" });

  const modes = [
    ["manual", "I'll enter my history myself", "Tell us how you repaid your earlier loans."],
    ["first", "This is my first loan", "No history needed."],
  ];

  const next = () => {
    const err = (text) => setMsg({ cls: "msg err", text });
    if (!app.mode) return err("Choose an option to continue.");
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
              type="radio" name="mode" checked={app.mode === val}
              onChange={() => { update({ mode: val }); setMsg({ cls: "msg", text: "" }); }}
            />
            <div><b>{title}</b><p>{desc}</p></div>
          </label>
        ))}
      </div>

      <div>
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
