import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, apiPost } from "../../api.js";
import Assessment from "../../components/Assessment.jsx";
import { StatusBadge } from "../../components/Badge.jsx";
import { useAuth } from "../../lib/auth.jsx";
import { useToast } from "../../lib/toast.jsx";
import { naira } from "../../lib/applyState.js";

function AnswerList({ answers }) {
  const h = answers.history;
  const rows = [
    ["Borrowing history", answers.mode === "first" ? "First loan" : "Returning borrower"],
    ["Date of birth", answers.dob],
    ["Employment", answers.employment],
    ["Bank", answers.bank],
    ["Account type", answers.account],
    ["Amount", answers.amount ? naira(answers.amount) : "—"],
    ["Term", answers.term ? `${answers.term} days` : "—"],
  ];
  if (h) {
    rows.push(["Previous loans", h.on_time + h.slight + h.late + h.very_late],
      ["Repaid on time", h.on_time], ["1–3 days late", h.slight],
      ["4–30 days late", h.late], ["Over 30 days late", h.very_late],
      ["Typical days vs. due", h.avg_late], ["Longest delay", h.max_late],
      ["Typical past loan", naira(h.avg_amount)], ["Typical past term", `${h.avg_term} days`]);
  }
  return (
    <div className="table-scroll">
      <table className="table compact">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}><th>{k}</th><td>{String(v)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function StaffApplicationDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const notify = useToast();
  const [state, setState] = useState({ status: "loading", application: null, error: "" });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  const load = useCallback(() => {
    apiGet(`/api/staff/applications/${id}`)
      .then((d) => setState({ status: "ok", application: d.application, error: "" }))
      .catch((e) => setState({ status: "error", application: null, error: e.message }));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const claim = async () => {
    setBusy(true); setActionError("");
    try {
      await apiPost(`/api/staff/applications/${id}/assign`, {});
      notify("Application assigned to you.", "success");
      load();
    } catch (e) { setActionError(e.message); }
    finally { setBusy(false); }
  };

  const decide = async (decision) => {
    setBusy(true); setActionError("");
    try {
      await apiPost(`/api/staff/applications/${id}/decision`, { decision, note });
      notify(`Decision recorded: ${decision.replace(/_/g, " ")}.`, "success");
      setNote("");
      load();
    } catch (e) { setActionError(e.message); }
    finally { setBusy(false); }
  };

  if (state.status === "loading") return <div className="spin">Loading application…</div>;
  if (state.status === "error") {
    return (
      <div className="empty">
        <p className="msg err">{state.error}</p>
        <Link to="/staff/applications" className="ghost">Back to applications</Link>
      </div>
    );
  }

  const a = state.application;
  const canAct = user.role === "loan_officer";
  const mine = a.assigned_officer_id === user.user_id;
  const open = ["submitted", "assigned", "more_info"].includes(a.status);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb"><Link to="/staff/applications">← Applications</Link></p>
          <h2>Application <span className="mono">{a.reference}</span></h2>
          <p className="sub">
            {a.applicant_name || a.applicant_username} · submitted {new Date(a.created_at).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={a.status} />
      </div>

      <div className="grid-2">
        <section className="card">
          <h3>Borrower &amp; request</h3>
          <AnswerList answers={a.answers} />
        </section>

        <section className="card">
          <h3>Assessment</h3>
          <Assessment recommendation={a.recommendation} scores={a.scores} factors={a.factors} />
        </section>
      </div>

      <section className="card" style={{ marginTop: 18 }}>
        <h3>Decision history</h3>
        {a.decisions.length === 0 ? (
          <p className="empty-note">No decisions recorded yet.</p>
        ) : (
          <ul className="timeline">
            {a.decisions.map((d, i) => (
              <li key={i}>
                <b>{d.decision.replace(/_/g, " ")}</b> by {d.officer}
                {d.note ? <span> — {d.note}</span> : null}
                <small>{new Date(d.created_at).toLocaleString()}</small>
              </li>
            ))}
          </ul>
        )}
      </section>

      {canAct && (
        <section className="card" style={{ marginTop: 18 }}>
          <h3>Your action</h3>
          {!open ? (
            <p className="empty-note">This application is closed ({a.status}).</p>
          ) : !mine ? (
            <>
              <p className="sub">
                {a.officer_username
                  ? `Currently assigned to ${a.officer_username}.`
                  : "This case is unassigned."}
              </p>
              {!a.officer_username && (
                <button className="primary" type="button" disabled={busy} onClick={claim}>
                  {busy ? "Claiming…" : "Claim this application"}
                </button>
              )}
            </>
          ) : (
            <>
              <label className="f">
                Note (required to decline or request more info)
                <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="action-row">
                <button className="primary" type="button" disabled={busy} onClick={() => decide("approved")}>Approve</button>
                <button className="ghost" type="button" disabled={busy} onClick={() => decide("more_info")}>Request more info</button>
                <button className="danger" type="button" disabled={busy} onClick={() => decide("declined")}>Decline</button>
              </div>
            </>
          )}
          {actionError && <p className="msg err">{actionError}</p>}
        </section>
      )}
    </>
  );
}
