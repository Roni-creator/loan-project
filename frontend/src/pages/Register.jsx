import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth.jsx";
import { useToast } from "../lib/toast.jsx";

const USERNAME_RE = /^[A-Za-z0-9._-]{3,32}$/;

export default function Register() {
  const { user, loading, register } = useAuth();
  const notify = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", username: "", password: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/dashboard" replace />;

  const validate = () => {
    if (!/^[A-Za-z0-9._-]{3,32}$/.test(form.username.trim()))
      return "Username must be 3-32 characters (letters, numbers, . _ -).";
    if (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password))
      return "Password must be at least 8 characters and include a letter and a number.";
    if (form.password !== form.confirm) return "The two passwords do not match.";
    return "";
  };

  const submit = async (e) => {
    e.preventDefault();
    const problem = validate();
    setError(problem);
    if (problem) return;
    setBusy(true);
    try {
      await register({
        username: form.username.trim(), password: form.password,
        full_name: form.full_name.trim() || null,
      });
      notify("Your account is ready. You can apply for a loan.", "success");
      navigate("/apply", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="wrap page auth-page">
      <section className="card auth-card">
        <h2>Create your account</h2>
        <p className="sub">Borrower accounts only. Staff accounts are created by an administrator.</p>
        <form onSubmit={submit} noValidate>
          <label className="f">
            Full name <small>Optional</small>
            <input type="text" autoComplete="name" value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </label>
          <label className="f" style={{ marginTop: 12 }}>
            Username
            <input type="text" autoComplete="username" value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </label>
          <label className="f" style={{ marginTop: 12 }}>
            Password
            <input type="password" autoComplete="new-password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          <label className="f" style={{ marginTop: 12 }}>
            Confirm password
            <input type="password" autoComplete="new-password" value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
          </label>
          {error && <p className="msg err" role="alert">{error}</p>}
          <button className="primary wide" type="submit" disabled={busy}>
            {busy ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="muted-line">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
