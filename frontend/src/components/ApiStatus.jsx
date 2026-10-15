import { useEffect, useState } from "react";
import { apiGet } from "../api.js";

// Phase One connectivity test: calls GET /api/meta and shows a few fields from it.
// /api/meta returns: banks[], employment[], accounts[], amounts[], terms[],
// interest{term: ratio}, pairs[[term, amount]], lookup (bool).
export default function ApiStatus() {
  const [state, setState] = useState({ status: "loading", meta: null, error: null });

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/meta")
      .then((meta) => !cancelled && setState({ status: "ok", meta, error: null }))
      .catch((error) => !cancelled && setState({ status: "error", meta: null, error: error.message }));
    return () => { cancelled = true; };
  }, []);

  if (state.status === "loading") return <p className="msg">Checking connection to Flask…</p>;

  if (state.status === "error") {
    return (
      <div>
        <p className="msg err">Could not reach the Flask API: {state.error}</p>
        <p className="fine" style={{ textAlign: "left" }}>
          Is Flask running? Start it with <code>python webapp.py</code> (port 8000).
        </p>
      </div>
    );
  }

  const m = state.meta;
  return (
    <div>
      <p className="msg ok">Connected to Flask. /api/meta responded.</p>
      <div className="sum">
        <div className="metric"><small>Banks</small><b>{m.banks.length}</b></div>
        <div className="metric"><small>Loan amounts</small><b>{m.amounts.length}</b></div>
        <div className="metric"><small>Repayment periods</small><b>{m.terms.length}</b></div>
      </div>
      <p className="fine" style={{ textAlign: "left" }}>
        Record lookup available: {m.lookup ? "yes" : "no"} · Employment options: {m.employment.join(", ")}
      </p>
    </div>
  );
}
