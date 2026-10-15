import { useEffect, useState } from "react";
import { apiGet } from "../../api.js";

export default function ModelInsights() {
  const [state, setState] = useState({ status: "loading", data: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/staff/models")
      .then((d) => !cancelled && setState({ status: "ok", data: d, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", data: null, error: e.message }));
    return () => { cancelled = true; };
  }, []);

  if (state.status === "loading") return <div className="spin">Loading model insights…</div>;
  if (state.status === "error") return <p className="msg err">{state.error}</p>;

  const { thresholds, model_runs, top_drivers } = state.data;
  const maxImportance = Math.max(...top_drivers.map((d) => d.rf_importance), 0.0001);

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Model insights</h2>
          <p className="sub">Cut-offs, held-out metrics and the leading Random Forest drivers.</p>
        </div>
      </div>

      <section className="card">
        <h3>Decision cut-offs</h3>
        <p className="sub">A request predicts Good when P(Good) ≥ its model's cut-off.</p>
        <div className="table-scroll">
          <table className="table">
            <thead><tr><th>Model</th><th>P(Good) cut-off</th></tr></thead>
            <tbody>
              {Object.entries(thresholds).map(([name, t]) => (
                <tr key={name}><td>{name}</td><td>{Number(t).toFixed(3)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" style={{ marginTop: 18 }}>
        <h3>Held-out performance</h3>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr><th>Model</th><th>Setting</th><th>Threshold</th><th>Accuracy</th><th>Precision (Bad)</th>
                <th>Recall (Bad)</th><th>F1 (Bad)</th><th>ROC AUC</th><th>PR AUC</th></tr>
            </thead>
            <tbody>
              {model_runs.map((r) => (
                <tr key={`${r.model_name}-${r.setting}`}>
                  <td>{r.model_name}</td><td>{r.setting}</td>
                  <td>{r.threshold != null ? Number(r.threshold).toFixed(3) : "—"}</td>
                  <td>{r.accuracy != null ? Number(r.accuracy).toFixed(3) : "—"}</td>
                  <td>{r.precision_bad != null ? Number(r.precision_bad).toFixed(3) : "—"}</td>
                  <td>{r.recall_bad != null ? Number(r.recall_bad).toFixed(3) : "—"}</td>
                  <td>{r.f1_bad != null ? Number(r.f1_bad).toFixed(3) : "—"}</td>
                  <td>{r.roc_auc != null ? Number(r.roc_auc).toFixed(3) : "—"}</td>
                  <td>{r.pr_auc_bad != null ? Number(r.pr_auc_bad).toFixed(3) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card" style={{ marginTop: 18 }}>
        <h3>Leading Random Forest drivers</h3>
        {top_drivers.length === 0 ? (
          <p className="empty-note">feature_importance.csv is not available.</p>
        ) : (
          <div className="factors">
            {top_drivers.map((d) => (
              <div className="fac" key={d.feature}>
                <span className="mono">{d.feature}</span>
                <div className="track">
                  <div className="bar ability" style={{ left: 0, width: `${(d.rf_importance / maxImportance) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="sub" style={{ marginTop: 12 }}>
          Feature importance describes model behaviour and is not causal evidence.
        </p>
      </section>
    </>
  );
}
