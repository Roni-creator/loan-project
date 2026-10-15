import { naira } from "../../lib/applyState.js";

const OUTCOME = { likely: "Looks good", review: "Closer look", refer: "Review" };

function FactorRows({ factors }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.value)), 0.01);
  return factors.map((f) => {
    const width = (Math.abs(f.value) / max) * 50;
    const side = f.value >= 0 ? { left: "50%" } : { right: "50%" };
    const color = f.driver === "willingness" ? "var(--orange)" : "var(--teal)";
    return (
      <div className="fac" key={f.feature} title={`${f.value >= 0 ? "Helps" : "Works against"} your application`}>
        <span>{f.factor}</span>
        <div className="track">
          <div className="bar" style={{ width: `${width}%`, ...side, background: color }} />
        </div>
      </div>
    );
  });
}

function WhatIf({ title, items, fmtVal }) {
  return (
    <div>
      <h4>{title}</h4>
      {items.map((i) => (
        <span className={"wchip" + (i.current ? " cur" : "")} key={i.value}>
          <i className={"dot " + i.outcome} />
          {fmtVal(i.value)}{" – " + OUTCOME[i.outcome] + (i.current ? " (you)" : "")}
        </span>
      ))}
    </div>
  );
}

// Shows a finished /api/score response. Purely visual: no fetching in here.
export default function ResultView({ r, reference, consent, onConsent, onSubmit, busy, message, onBack, onRestart }) {
  return (
    <>
      <h2>Your indicative result</h2>
      <div className={"banner " + r.tier}><b>{r.headline}</b><p>{r.message}</p></div>

      <div className="sum">
        <div className="metric"><small>You borrow</small><b>{naira(r.loan.amount)}</b></div>
        <div className="metric">
          <small>{`You repay (${Math.round(r.loan.interest * 100)}% interest)`}</small>
          <b>{naira(r.loan.repay)}</b>
        </div>
        <div className="metric"><small>Within</small><b>{`${r.loan.term} days`}</b></div>
      </div>

      {r.notes.length > 0 && <ul className="notes">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>}

      <h3>Why this result</h3>
      <FactorRows factors={r.factors} />
      <div className="axis"><span>{"← works against you"}</span><span>{"helps you →"}</span></div>
      <div className="legend">
        <span><i className="dot" style={{ background: "var(--orange)" }} />Willingness to pay (how you've repaid before)</span>
        <span><i className="dot" style={{ background: "var(--teal)" }} />Ability to pay / profile (the loan and your circumstances)</span>
      </div>
      <p className="fine" style={{ textAlign: "left" }}>
        Bars show how strongly each answer moved the Logistic Regression model. They describe model behaviour, not cause.
      </p>

      <h3>What if I change my request?</h3>
      <div className="wi">
        <WhatIf title={`Different amount, ${r.loan.term} days`} items={r.what_if.amounts} fmtVal={naira} />
        <WhatIf title={`Different period, ${naira(r.loan.amount)}`} items={r.what_if.terms} fmtVal={(t) => `${t} days`} />
      </div>

      <details>
        <summary>Technical details</summary>
        <p>
          Scores are P(Good) from each model. A request is flagged when the score is below that model's tuned cut-off.
          Scores are rankings, not calibrated probabilities of repayment.
        </p>
        <table>
          <thead><tr><th>Model</th><th>P(Good)</th><th>Cut-off</th><th>Predicts Good</th></tr></thead>
          <tbody>
            {Object.entries(r.scores).map(([m, s]) => (
              <tr key={m}><td>{m}</td><td>{s.p_good.toFixed(3)}</td><td>{s.threshold.toFixed(3)}</td><td>{s.good ? "Yes" : "No"}</td></tr>
            ))}
          </tbody>
        </table>
      </details>

      <hr style={{ border: 0, borderTop: "1px solid var(--line)", margin: "22px 0" }} />

      <div>
        {reference ? (
          <div className="banner likely">
            <b>Application submitted</b>
            <p>Your reference is <b style={{ display: "inline" }}>{reference}</b>. A loan officer will be in touch.</p>
          </div>
        ) : (
          <>
            <label className="consent">
              <input type="checkbox" checked={consent} onChange={(e) => onConsent(e.target.checked)} />
              I confirm these details are correct and agree to them being used to review my application.
            </label>
            <button className="primary" type="button" disabled={!consent || busy} onClick={onSubmit}>Submit application</button>
            <p className={message ? "msg err" : "msg"}>{message}</p>
          </>
        )}
      </div>

      <div className="nav">
        <button type="button" onClick={onBack}>Change my request</button>
        <button type="button" onClick={onRestart}>Start over</button>
      </div>
    </>
  );
}
