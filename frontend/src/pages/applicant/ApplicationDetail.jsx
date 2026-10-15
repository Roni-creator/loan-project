import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet } from "../../api.js";
import Assessment from "../../components/Assessment.jsx";
import { StatusBadge } from "../../components/Badge.jsx";
import { naira } from "../../lib/applyState.js";

export default function ApplicantApplicationDetail() {
  const { id } = useParams();
  const [state, setState] = useState({ status: "loading", application: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    apiGet(`/api/applications/${id}`)
      .then((d) => !cancelled && setState({ status: "ok", application: d.application, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", application: null, error: e.message }));
    return () => { cancelled = true; };
  }, [id]);

  if (state.status === "loading") return <div className="spin">Loading application…</div>;
  if (state.status === "error") {
    return (
      <div className="empty">
        <p className="msg err">{state.error}</p>
        <Link to="/dashboard" className="ghost">Back to my applications</Link>
      </div>
    );
  }

  const a = state.application;
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb"><Link to="/dashboard">← My applications</Link></p>
          <h2>Application <span className="mono">{a.reference}</span></h2>
          <p className="sub">Submitted {new Date(a.created_at).toLocaleString()}</p>
        </div>
        <StatusBadge status={a.status} />
      </div>

      <div className="sum">
        <div className="metric"><small>Amount</small><b>{a.amount ? naira(a.amount) : "—"}</b></div>
        <div className="metric"><small>Term</small><b>{a.term ? `${a.term} days` : "—"}</b></div>
        <div className="metric"><small>Employment</small><b>{a.answers?.employment || "—"}</b></div>
      </div>

      {a.decisions?.length > 0 && (
        <section className="card" style={{ marginTop: 18 }}>
          <h3>Decision history</h3>
          <ul className="timeline">
            {a.decisions.map((d, i) => (
              <li key={i}>
                <b>{d.decision.replace(/_/g, " ")}</b>
                {d.note ? <span> — {d.note}</span> : null}
                <small>{new Date(d.created_at).toLocaleString()}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card" style={{ marginTop: 18 }}>
        <h3>Assessment</h3>
        <Assessment recommendation={a.recommendation} scores={a.scores} factors={a.factors} />
      </section>
    </>
  );
}
