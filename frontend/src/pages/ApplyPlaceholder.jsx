import { Link } from "react-router-dom";
import Hero from "../components/Hero.jsx";

export default function ApplyPlaceholder() {
  return (
    <>
      <Hero title="Apply for a loan">Routing works. The four-step form comes in Phase Two.</Hero>
      <main className="wrap">
        <section className="card">
          <h2>Coming next</h2>
          <p className="sub">History, About you, The loan, Result.</p>
          <div className="nav" style={{ marginTop: 0, justifyContent: "flex-start" }}>
            <Link to="/"><button type="button">Back</button></Link>
          </div>
        </section>
      </main>
    </>
  );
}
