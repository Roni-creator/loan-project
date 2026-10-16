import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { ROLE_LABELS, STAFF_ROLES, homeFor, useAuth } from "../lib/auth.jsx";
import { useToast } from "../lib/toast.jsx";
import { setCsrfToken } from "../api.js";

function linksFor(user) {
  if (!user) {
    return [
      { to: "/", label: "Home", end: true },
      { to: "/register", label: "Apply" },
    ];
  }
  if (user.role === "applicant") {
    return [
      { to: "/", label: "Home", end: true },
      { to: "/apply", label: "New application" },
      { to: "/dashboard", label: "My applications" },
    ];
  }
  if (STAFF_ROLES.includes(user.role)) {
    // Business managers get a management overview only; personal applicant
    // records are for credit analysts and loan officers.
    const links = [{ to: "/staff", label: "Dashboard", end: true }];
    if (user.role === "business_manager") return links;
    links.push({ to: "/staff/applications", label: "Applications" });
    if (user.role === "credit_analyst") links.push({ to: "/staff/models", label: "Model insights" });
    return links;
  }
  return [{ to: "/", label: "Home", end: true }];
}

export default function Layout() {
  const { user, logout } = useAuth();
  const notify = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const onLogout = async () => {
    await logout();
    setCsrfToken(null);
    setOpen(false);
    notify("You have been signed out.", "success");
    navigate("/");
  };

  const links = linksFor(user);

  return (
    <>
      <header className="nav-bar">
        <div className="nav-inner">
          <Link to={user ? homeFor(user.role) : "/"} className="brand" onClick={() => setOpen(false)}>
            <span className="brand-mark">LC</span>
            <span className="brand-text">LoanCredit</span>
          </Link>

          <button
            type="button" className="nav-toggle" aria-expanded={open} aria-label="Toggle navigation"
            onClick={() => setOpen((v) => !v)}
          >
            <span /><span /><span />
          </button>

          <nav className={`nav-links ${open ? "open" : ""}`}>
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} onClick={() => setOpen(false)}
                className={({ isActive }) => (isActive ? "active" : "")}>
                {l.label}
              </NavLink>
            ))}

            <div className="nav-account">
              {user ? (
                <>
                  <span className="who">
                    <b>{user.full_name || user.username}</b>
                    <small>{ROLE_LABELS[user.role] || user.role}</small>
                  </span>
                  <button type="button" className="ghost" onClick={onLogout}>Sign out</button>
                </>
              ) : (
                <>
                  <Link to="/login" className="ghost" onClick={() => setOpen(false)}>Sign in</Link>
                  <Link to="/register" className="primary sm" onClick={() => setOpen(false)}>Create account</Link>
                </>
              )}
            </div>
          </nav>
        </div>
      </header>

      <Outlet />

      <footer className="site-footer">
        <div className="wrap">
          <p>Research prototype · indicative model output, not a lending decision or credit offer.</p>
        </div>
      </footer>
    </>
  );
}
