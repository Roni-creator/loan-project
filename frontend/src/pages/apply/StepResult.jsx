import { useEffect, useState } from "react";
import { apiPost } from "../../api.js";
import { buildPayload } from "../../lib/applyState.js";
import ResultView from "./ResultView.jsx";

// Step 4. Sends the answers to Flask (/api/score), shows what comes back,
// and submits with consent (/api/submit). All scoring happens on the server.
export default function StepResult({ app, setRef, onBack, onReview, onRestart }) {
  const [state, setState] = useState({ status: "loading", result: null, error: "" });
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    apiPost("/api/score", buildPayload(app))
      .then((result) => !cancelled && setState({ status: "ok", result, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", result: null, error: e.message }));
    return () => { cancelled = true; };
    // Score once each time this step opens, like the old page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async () => {
    setBusy(true);
    setMessage("");
    try {
      const { reference } = await apiPost("/api/applications", buildPayload(app));
      setRef(reference);
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (state.status === "loading") return <div className="spin">Checking your application…</div>;

  if (state.status === "error") {
    return (
      <>
        <h2>We couldn't check that</h2>
        <p className="msg err">{state.error}</p>
        <div className="nav">
          <button type="button" onClick={onReview}>Review my answers</button>
          <span />
        </div>
      </>
    );
  }

  return (
    <ResultView
      r={state.result} reference={app.ref} consent={consent} onConsent={setConsent}
      onSubmit={submit} busy={busy} message={message} onBack={onBack} onRestart={onRestart}
    />
  );
}
