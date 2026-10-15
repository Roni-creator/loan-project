import { TierBadge } from "./Badge.jsx";

function FactorRows({ factors }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.value)), 0.01);
  return factors.map((f) => {
    const width = (Math.abs(f.value) / max) * 50;
    const side = f.value >= 0 ? { left: "50%" } : { right: "50%" };
    const color = f.driver === "willingness" ? "var(--orange)" : "var(--teal)";
    return (
      <div className="fac" key={f.feature}
        title={`${f.value >= 0 ? "Helps" : "Works against"} the application`}>
        <span>{f.factor}</span>
        <div className="track">
          <div className="bar" style={{ width: `${width}%`, ...side, background: color }} />
        </div>
      </div>
    );
  });
}

// Read-only assessment view shared by applicants and staff: real model
// probabilities plus the Logistic-Regression factor explanations.
export default function Assessment({ recommendation, scores, factors }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.value)), 0.01);
  return (
    <div className="assessment">
      {recommendation && (
        <div className={`banner ${recommendation.tier}`}>
          <TierBadge tier={recommendation.tier} />
          <b>{recommendation.headline}</b>
          <p>{recommendation.message}</p>
        </div>
      )}

      <h3>Model scores</h3>
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr><th>Model</th><th>P(Good)</th><th>Cut-off</th><th>Predicts</th></tr>
          </thead>
          <tbody>
            {Object.entries(scores).map(([name, s]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{s.p_good.toFixed(3)}</td>
                <td>{s.threshold.toFixed(3)}</td>
                <td><span className={`badge ${s.good ? "approved" : "declined"}`}>{s.good ? "Good" : "Bad"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Why the models answered this way</h3>
      <div className="factors">
        {factors.map((f) => {
          const width = (Math.abs(f.value) / max) * 50;
          const side = f.value >= 0 ? { left: "50%" } : { right: "50%" };
          const color = f.driver === "willingness" ? "var(--orange)" : "var(--teal)";
          return (
            <div className="fac" key={f.feature}>
              <span>{f.factor}</span>
              <div className="track">
                <div className="bar" style={{ width: `${width}%`, ...side, background: color }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="legend">
        <span><i className="dot willingness" />Willingness to pay</span>
        <span><i className="dot ability" />Ability to pay / profile</span>
      </div>
      <p className="fine left">
        Bars show how strongly each answer moved the Logistic Regression model
        (coefficient × scaled input). They describe model behaviour, not cause.
      </p>
    </div>
  );
}
