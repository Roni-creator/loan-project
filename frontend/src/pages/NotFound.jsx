import { Link } from "react-router-dom";
import Hero from "../components/Hero.jsx";

export default function NotFound() {
  return (
    <>
      <Hero title="Page not found">That address does not exist.</Hero>
      <main className="wrap">
        <section className="card">
          <Link to="/"><button type="button" className="primary">Go home</button></Link>
        </section>
      </main>
    </>
  );
}
