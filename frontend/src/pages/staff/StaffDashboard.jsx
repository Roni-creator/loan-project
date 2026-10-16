import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../api.js";
import { StatusBadge, TierBadge } from "../../components/Badge.jsx";
import { useAuth } from "../../lib/auth.jsx";
import { ksh } from "../../lib/applyState.js";

function Metric({ label, value, hint }) {
  return (
    <div className="metric">
      <small>{label}</small>
      <b>{value}</b>
      {hint ? <small className="hint">{hint}</small> : null}
    </div>
  );
}

function RecentTable({ rows }) {
  if (!rows.length) return <p className="empty-note">No applications have been submitted yet.</p>;
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr><th>Reference</th><th>Applicant</th><th>Amount</th><th>Assessment</th><th>Status</th><th>Officer</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.application_id}>
              <td className="mono">{r.reference}</td>
              <td>{r.applicant_name || r.applicant_username}</td>
              <td>{r.amount ? ksh(r.amount) : "—"}</td>
              <td><TierBadge tier={r.tier} /></td>
              <td><StatusBadge status={r.status} /></td>
              <td>{r.officer_username || "—"}</td>
              <td><Link className="link" to={`/staff/applications/${r.application_id}`}>Open</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelPanel({ models }) {
  if (!models) return null;
  return (
    <section className="card" style={{ marginTop: 18 }}>
      <h3>Trained models</h3>
      <p className="sub">Decision rule: predict Good when P(Good) ≥ the tuned cut-off.</p>
      <div className="table-scroll">
        <table className="table">
          <thead><tr><th>Model</th><th>Cut-off</th><th>Accuracy</th><th>ROC AUC</th><th>PR AUC (Bad)</th></tr></thead>
          <tbody>
            {Object.entries(models.thresholds).map(([name, t]) => {
              const run = (models.model_runs || []).find((r) => r.model_name === name) || {};
              return (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{Number(t).toFixed(3)}</td>
                  <td>{run.accuracy != null ? Number(run.accuracy).toFixed(3) : "—"}</td>
                  <td>{run.roc_auc != null ? Number(run.roc_auc).toFixed(3) : "—"}</td>
                  <td>{run.pr_auc_bad != null ? Number(run.pr_auc_bad).toFixed(3) : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function StaffDashboard() {
  const { user } = useAuth();
  const [summary, setSummary] = useState(null);
  const [models, setModels] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/staff/summary")
      .then((d) => !cancelled && setSummary(d))
      .catch((e) => !cancelled && setError(e.message));
    if (user.role === "credit_analyst") {
      apiGet("/api/staff/models").then((d) => !cancelled && setModels(d)).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [user.role]);

  if (error) return <p className="msg err">{error}</p>;
  if (!summary) return <div className="spin">Loading dashboard…</div>;

  const roleHint = {
    business_manager: "Portfolio summary — read-only oversight of loan applications.",
    credit_analyst: "Assessment workspace — model predictions and explanations.",
    loan_officer: "Your queue — review and decide the applications assigned to you.",
  }[user.role];
  // Personal applicant records are for analysts and officers; a business manager
  // gets aggregate management information only.
  const isManager = user.role === "business_manager";

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Welcome, {user.full_name || user.username}</h2>
          <p className="sub">{roleHint}</p>
        </div>
        {!isManager && <Link to="/staff/applications" className="primary">All applications</Link>}
      </div>

      <div className="sum">
        <Metric label="Total applications" value={summary.total_applications} />
        <Metric label="Awaiting review" value={(summary.by_status.submitted || 0) + (summary.by_status.assigned || 0)} />
        <Metric label="Approved" value={summary.by_status.approved || 0} />
        <Metric label="Declined" value={summary.by_status.declined || 0} />
        {summary.assigned_to_me != null && <Metric label="Assigned to me" value={summary.assigned_to_me} />}
        <Metric label="Borrower accounts" value={summary.accounts?.applicant || 0} />
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>Assessment mix</h3>
          <div className="mix">
            <div><TierBadge tier="likely" /><b>{summary.by_tier.likely || 0}</b></div>
            <div><TierBadge tier="review" /><b>{summary.by_tier.review || 0}</b></div>
            <div><TierBadge tier="refer" /><b>{summary.by_tier.refer || 0}</b></div>
          </div>
          <p className="sub" style={{ marginTop: 10 }}>
            Model tier is indicative; a loan officer makes the decision.
          </p>
        </div>
        <div className="card">
          <h3>Staff accounts</h3>
          <ul className="stats-list">
            <li><span>Business managers</span><b>{summary.accounts?.business_manager || 0}</b></li>
            <li><span>Credit analysts</span><b>{summary.accounts?.credit_analyst || 0}</b></li>
            <li><span>Loan officers</span><b>{summary.accounts?.loan_officer || 0}</b></li>
          </ul>
        </div>
      </div>

      {isManager ? (
        <section className="card" style={{ marginTop: 18 }}>
          <h3>Portfolio overview</h3>
          <p className="sub">
            Management view: counts and assessment mix across all applications. Personal
            applicant records are accessible to credit analysts and loan officers only.
          </p>
        </section>
      ) : (
        <section className="card" style={{ marginTop: 18 }}>
          <div className="card-head">
            <h3>Recent applications</h3>
            <Link className="link" to="/staff/applications">View all</Link>
          </div>
          <RecentTable rows={summary.recent} />
        </section>
      )}

      {models && <ModelPanel models={models} />}
    </>
  );
}
