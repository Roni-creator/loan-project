import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../api.js";
import { StatusBadge, TierBadge } from "../../components/Badge.jsx";
import { naira } from "../../lib/applyState.js";

export default function MyApplications() {
  const [state, setState] = useState({ status: "loading", items: [], error: "" });

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/applications")
      .then((d) => !cancelled && setState({ status: "ok", items: d.applications, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", items: [], error: e.message }));
    return () => { cancelled = true; };
  }, []);

  if (state.status === "loading") return <div className="spin">Loading your applications…</div>;
  if (state.status === "error") return <p className="msg err">{state.error}</p>;

  return (
    <>
      <div className="page-head">
        <div>
          <h2>My applications</h2>
          <p className="sub">Every application you have submitted and its current status.</p>
        </div>
        <Link to="/apply" className="primary">New application</Link>
      </div>

      {state.items.length === 0 ? (
        <div className="empty">
          <p>You have not submitted any applications yet.</p>
          <Link to="/apply" className="primary">Start an application</Link>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Reference</th><th>Submitted</th><th>Amount</th><th>Term</th>
                <th>Assessment</th><th>Status</th><th />
              </tr>
            </thead>
            <tbody>
              {state.items.map((a) => (
                <tr key={a.application_id}>
                  <td className="mono">{a.reference}</td>
                  <td>{new Date(a.created_at).toLocaleDateString()}</td>
                  <td>{a.amount ? naira(a.amount) : "—"}</td>
                  <td>{a.term ? `${a.term} days` : "—"}</td>
                  <td><TierBadge tier={a.tier} /></td>
                  <td><StatusBadge status={a.status} /></td>
                  <td><Link className="link" to={`/dashboard/applications/${a.application_id}`}>View</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
