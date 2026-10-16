import { Link } from "react-router-dom";
import { homeFor, useAuth } from "../lib/auth.jsx";

const FEATURES = [
  { title: "Easy to Apply", body: "Complete your application in a few straightforward steps." },
  { title: "Understand Your Assessment", body: "See the factors considered in your assessment." },
  { title: "Track Your Progress", body: "Follow your application status from your account." },
];

const STEPS = [
  "Create your account",
  "Enter your application details",
  "Receive your assessment",
  "Track your application",
];

export default function Landing() {
  const { user } = useAuth();
  const primary = user
    ? { to: homeFor(user.role), label: user.role === "applicant" ? "Go to my dashboard" : "Go to dashboard" }
    : { to: "/apply", label: "Apply for a Loan" };
  const secondary = user ? null : { to: "/register", label: "Create an Account" };

  return (
    <main>
      <section className="hero-section">
        <div className="wrap hero-content">
          <p className="eyebrow">Creditworthiness assessment</p>
          <h1>A clearer way to access credit.</h1>
          <p className="lead">
            Apply for a loan in a few simple steps, receive an assessment of your application,
            and track your progress in one place.
          </p>
          <div className="hero-actions">
            <Link to={primary.to} className="primary lg">{primary.label}</Link>
            {secondary && <Link to={secondary.to} className="ghost lg">{secondary.label}</Link>}
          </div>
          <p className="hero-note">No impact on your credit score.</p>
        </div>
      </section>

      <section className="wrap section">
        <h2>A simple application process.</h2>
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
            {STEPS.map((label, i) => (
              <li key={label}>
                <span className="how-n">{i + 1}</span>
                <b>{label}</b>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </main>
  );
}
