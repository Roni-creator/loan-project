import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { homeFor, useAuth } from "../lib/auth.jsx";
import { useToast } from "../lib/toast.jsx";

export default function Login() {
  const { user, loading, login } = useAuth();
  const notify = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to={homeFor(user.role)} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.username.trim() || !form.password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      const account = await login(form.username.trim(), form.password);
      notify(`Welcome back, ${account.full_name || account.username}.`, "success");
      const dest = location.state?.from || homeFor(account.role);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="wrap page auth-page">
      <section className="card auth-card">
        <h2>Sign in</h2>
        <p className="sub">Access your loan applications or staff workspace.</p>
        <form onSubmit={submit} noValidate>
          <label className="f">
            Username
            <input
              type="text" autoComplete="username" value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </label>
          <label className="f" style={{ marginTop: 12 }}>
            Password
            <input
              type="password" autoComplete="current-password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </label>
          {error && <p className="msg err" role="alert">{error}</p>}
          <button className="primary wide" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="muted-line">
          New borrower? <Link to="/register">Create an account</Link>
        </p>
      </section>
    </main>
  );
}
