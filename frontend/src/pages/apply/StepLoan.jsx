import { ksh } from "../../lib/applyState.js";

function Chips({ values, selected, label, onPick }) {
  return (
    <div className="chips">
      {values.map((val) => (
        <button key={val} type="button" className={"chip" + (selected === val ? " sel" : "")} onClick={() => onPick(val)}>
          {label(val)}
        </button>
      ))}
    </div>
  );
}

export default function StepLoan({ meta, app, update, onBack, onNext }) {
  const interest = meta.interest[app.term] ?? 0;
  const seen = meta.pairs.some(([t, a]) => t === app.term && a === app.amount);

  return (
    <>
      <h2>The loan you want</h2>
      <h3>Amount</h3>
      <Chips values={meta.amounts} selected={app.amount} label={ksh} onPick={(v) => update({ amount: v })} />
      <h3>Repayment period</h3>
      <Chips values={meta.terms} selected={app.term} label={(t) => `${t} days`} onPick={(v) => update({ term: v })} />

      <div className="sum">
        <div className="metric"><small>You borrow</small><b>{ksh(app.amount)}</b></div>
        <div className="metric">
          <small>{`You repay (${Math.round(interest * 100)}% interest)`}</small>
          <b>{ksh(app.amount * (1 + interest))}</b>
        </div>
        <div className="metric"><small>Within</small><b>{`${app.term} days`}</b></div>
      </div>
      <p className="msg">
        {seen ? "" : "⚠️ This amount and period combination is uncommon, so the result may be less reliable."}
      </p>

      <div className="nav">
        <button type="button" onClick={onBack}>Back</button>
        <button className="primary" type="button" onClick={onNext}>Check my application</button>
      </div>
    </>
  );
}
