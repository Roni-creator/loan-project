import { Link } from "react-router-dom";
import Hero from "../components/Hero.jsx";

export default function NotFound() {
  return (
    <>
      <Hero title="Page not found">That address does not exist.</Hero>
      <main className="wrap">
        <section className="card">
          <Link to="/" className="primary">Go home</Link>
        </section>
      </main>
    </>
  );
}
