import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../../api.js";
import { StatusBadge, TierBadge } from "../../components/Badge.jsx";
import { naira } from "../../lib/applyState.js";

const FILTERS = [
  ["all", "All"],
  ["submitted", "Awaiting review"],
  ["assigned", "In review"],
  ["more_info", "More info needed"],
  ["approved", "Approved"],
  ["declined", "Declined"],
];

export default function StaffApplications() {
  const [state, setState] = useState({ status: "loading", items: [], error: "" });
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/staff/applications")
      .then((d) => !cancelled && setState({ status: "ok", items: d.applications, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", items: [], error: e.message }));
    return () => { cancelled = true; };
  }, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return state.items.filter((a) => {
      if (filter !== "all" && a.status !== filter) return false;
      if (!q) return true;
      return [a.reference, a.applicant_username, a.applicant_name, a.officer_username]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
    });
  }, [state.items, filter, query]);

  if (state.status === "loading") return <div className="spin">Loading applications…</div>;
  if (state.status === "error") return <p className="msg err">{state.error}</p>;

  return (
    <>
      <div className="page-head">
        <div>
          <h2>Applications</h2>
          <p className="sub">All submitted applications and their assessments.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="chips">
          {FILTERS.map(([value, label]) => (
            <button key={value} type="button" className={"chip" + (filter === value ? " sel" : "")}
              onClick={() => setFilter(value)}>
              {label}
            </button>
          ))}
        </div>
        <input type="text" placeholder="Search reference or applicant" value={query}
          onChange={(e) => setQuery(e.target.value)} className="search" />
      </div>

      {rows.length === 0 ? (
        <p className="empty-note">No applications match this view.</p>
      ) : (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Reference</th><th>Applicant</th><th>Amount</th><th>Assessment</th>
                <th>Status</th><th>Officer</th><th>Submitted</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.application_id}>
                  <td className="mono">{a.reference}</td>
                  <td>{a.applicant_name || a.applicant_username}</td>
                  <td>{a.amount ? naira(a.amount) : "—"}</td>
                  <td><TierBadge tier={a.tier} /></td>
                  <td><StatusBadge status={a.status} /></td>
                  <td>{a.officer_username || "—"}</td>
                  <td>{new Date(a.created_at).toLocaleDateString()}</td>
                  <td><Link className="link" to={`/staff/applications/${a.application_id}`}>Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
