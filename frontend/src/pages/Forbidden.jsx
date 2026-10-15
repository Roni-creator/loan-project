import { Link } from "react-router-dom";
import { homeFor, useAuth } from "../lib/auth.jsx";

export default function Forbidden() {
  const { user } = useAuth();
  return (
    <main className="wrap page">
      <section className="card center">
        <h2>Access denied</h2>
        <p className="sub">
          Your account{user ? ` (${user.role.replace(/_/g, " ")})` : ""} does not have permission to view this page.
        </p>
        <div className="nav" style={{ justifyContent: "center" }}>
          <Link to={user ? homeFor(user.role) : "/"} className="primary">Go to my dashboard</Link>
        </div>
      </section>
    </main>
  );
}
