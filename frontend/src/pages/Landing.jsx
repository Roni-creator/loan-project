import { Link } from "react-router-dom";
import { STAFF_ROLES, homeFor, useAuth } from "../lib/auth.jsx";

const FEATURES = [
  { title: "Instant indicative result", body: "Two trained models score your request in seconds and agree or disagree transparently." },
  { title: "Reasons, not a black box", body: "Every answer is shown with how strongly it moved the model — up or down." },
  { title: "Track your application", body: "Register once, submit, and follow your status and assessment in one place." },
  { title: "Reviewed by a human", body: "Model output guides a loan officer; it is never an automatic decision." },
];

const STEPS = [
  { n: 1, title: "Tell us about your borrowing", body: "Returning customer lookup or a few simple questions." },
  { n: 2, title: "Choose your loan", body: "Amount and repayment period within the lender's range." },
  { n: 3, title: "Get your assessment", body: "Model probabilities plus the factors behind them." },
  { n: 4, title: "Track the outcome", body: "Submit and follow your application in your dashboard." },
];

export default function Landing() {
  const { user } = useAuth();
  const primary = user ? { to: homeFor(user.role), label: user.role === "applicant" ? "Go to my dashboard" : "Go to dashboard" }
    : { to: "/register", label: "Apply for a loan" };
  const secondary = user ? null
    : { to: "/login", label: "Staff / existing user sign in" };

  return (
    <main>
      <section className="hero-section">
        <div className="wrap hero-grid">
          <div>
            <p className="eyebrow">Creditworthiness assessment</p>
            <h1>Borrow with clarity.</h1>
            <p className="lead">
              Apply in a few steps and see an instant, explainable assessment of your request —
              built on alternative financial behaviour data and reviewed by a loan officer.
            </p>
            <div className="hero-actions">
              <Link to={primary.to} className="primary lg">{primary.label}</Link>
              {secondary && <Link to={secondary.to} className="ghost lg">{secondary.label}</Link>}
            </div>
            <p className="hero-note">Research prototype · no credit impact · indicative output only</p>
          </div>
          <div className="hero-card" aria-hidden="true">
            <div className="hero-card-head">
              <span className="dot ok" /> Assessment preview
            </div>
            <div className="hero-row"><span>Logistic Regression</span><b>P(Good) 0.62</b></div>
            <div className="hero-row"><span>Random Forest</span><b>P(Good) 0.58</b></div>
            <div className="hero-bar"><span style={{ width: "58%" }} /></div>
            <p className="hero-card-foot">Reasons shown for every factor.</p>
          </div>
        </div>
      </section>

      <section className="wrap section">
        <h2>Everything you need, nothing hidden</h2>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <article className="feature" key={f.title}>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="band">
        <div className="wrap section">
          <h2>How it works</h2>
          <ol className="how">
            {STEPS.map((s) => (
              <li key={s.n}>
                <span className="how-n">{s.n}</span>
                <div><b>{s.title}</b><p>{s.body}</p></div>
              </li>
            ))}
          </ol>
          {!user && (
            <div className="cta-row">
              <Link to="/register" className="primary">Create your account</Link>
              <Link to="/apply" className="ghost">Preview a check without an account</Link>
            </div>
          )}
        </div>
      </section>

      <section className="wrap section" id="staff">
        <h2>For staff</h2>
        <p className="sub">
          Business managers, credit analysts and loan officers sign in to role-based workspaces.
          Access is enforced by the backend, not just the interface.
        </p>
        <div className="role-grid">
          <div className="role"><h3>Business Manager</h3><p>Portfolio and application summaries.</p></div>
          <div className="role"><h3>Credit Analyst</h3><p>Assessments, model predictions and explanations.</p></div>
          <div className="role"><h3>Loan Officer</h3><p>Application queue, ownership and decisions.</p></div>
        </div>
        <div className="cta-row">
          <Link to="/login" className="primary">Staff sign in</Link>
        </div>
      </section>
    </main>
  );
}
