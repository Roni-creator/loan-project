import { useEffect, useState } from "react";
import { apiGet } from "../api.js";
import Hero from "../components/Hero.jsx";
import Stepper from "../components/Stepper.jsx";
import StepHistory from "./apply/StepHistory.jsx";
import StepAbout from "./apply/StepAbout.jsx";
import StepLoan from "./apply/StepLoan.jsx";
import StepResult from "./apply/StepResult.jsx";
import { initialApplication } from "../lib/applyState.js";

export default function Apply() {
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState("");
  const [step, setStep] = useState(1);
  const [app, setApp] = useState(initialApplication);

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/meta")
      .then((m) => !cancelled && setMeta(m))
      .catch((e) => !cancelled && setMetaError(e.message));
    return () => { cancelled = true; };
  }, []);

  const go = (n) => { setStep(n); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const update = (patch) => setApp((a) => ({ ...a, ...patch }));
  const setHistoryValue = (key, value) => setApp((a) => ({ ...a, history: { ...a.history, [key]: value } }));
  const setProfileValue = (key, value) => setApp((a) => ({ ...a, profile: { ...a.profile, [key]: value } }));

  return (
    <>
      <Hero title="Apply for a loan">
        Answer a few questions and get an instant, indicative result <b>with the reasons behind it</b> — no black box.
      </Hero>
      <main className="wrap">
        <Stepper step={step} />
        <section className="card" aria-live="polite">
          {metaError && <p className="msg err">The portal couldn't start: {metaError}</p>}
          {!meta && !metaError && <div className="spin">Loading…</div>}
          {meta && step === 1 && (
            <StepHistory app={app} update={update} setHistoryValue={setHistoryValue} onNext={() => go(2)} />
          )}
          {meta && step === 2 && (
            <StepAbout meta={meta} app={app} setProfileValue={setProfileValue} onBack={() => go(1)} onNext={() => go(3)} />
          )}
          {meta && step === 3 && (
            <StepLoan meta={meta} app={app} update={update} onBack={() => go(2)} onNext={() => go(4)} />
          )}
          {meta && step === 4 && (
            <StepResult
              app={app} setRef={(ref) => update({ ref })}
              onBack={() => go(3)} onReview={() => go(1)}
              onRestart={() => { update({ mode: null, ref: null }); go(1); }}
            />
          )}
        </section>
        <p className="fine">Research prototype. The result is an indicative model output, not a lending decision or credit offer.</p>
      </main>
    </>
  );
}
