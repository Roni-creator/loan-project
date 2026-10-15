import { Link } from "react-router-dom";
import Hero from "../components/Hero.jsx";
import ApiStatus from "../components/ApiStatus.jsx";

export default function Landing() {
  return (
    <>
      <Hero title="Apply for a loan">
        Answer a few questions and get an instant, indicative result <b>with the reasons behind it</b> — no black box.
      </Hero>
      <main className="wrap">
        <section className="card">
          <h2>Welcome</h2>
          <p className="sub">Check your loan request in four short steps and see the reasons behind the result.</p>
          <div className="nav" style={{ marginTop: 0, justifyContent: "flex-start" }}>
            <Link to="/apply"><button type="button" className="primary">Start application</button></Link>
          </div>
          <h3>Connection check</h3>
          <ApiStatus />
        </section>
        <p className="fine">Research prototype. The result is an indicative model output, not a lending decision or credit offer.</p>
      </main>
    </>
  );
}
