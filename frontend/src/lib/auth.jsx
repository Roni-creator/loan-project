// Authentication context: current account, CSRF token and login/logout helpers.
// The session lives in an HttpOnly cookie owned by Flask; React only holds the
// public account info returned by /api/auth/me.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost, setCsrfToken } from "../api.js";

const AuthContext = createContext(null);

export const ROLE_LABELS = {
  applicant: "Applicant",
  business_manager: "Business Manager",
  credit_analyst: "Credit Analyst",
  loan_officer: "Loan Officer",
};

export const STAFF_ROLES = ["business_manager", "credit_analyst", "loan_officer"];

export function homeFor(role) {
  if (role === "applicant") return "/dashboard";
  if (STAFF_ROLES.includes(role)) return "/staff";
  return "/";
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const clear = useCallback(() => {
    setUser(null);
    setCsrfToken(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/auth/me")
      .then((data) => {
        if (cancelled) return;
        setUser(data.user);
        setCsrfToken(data.csrf_token);
      })
      .catch(() => { /* not signed in */ })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const handler = () => clear();
    window.addEventListener("auth:unauthorized", handler);
    return () => window.removeEventListener("auth:unauthorized", handler);
  }, [clear]);

  const login = useCallback(async (email, password) => {
    const data = await apiPost("/api/auth/login", { email, password });
    setUser(data.user);
    setCsrfToken(data.csrf_token);
    return data.user;
  }, []);

  const register = useCallback(async (payload) => {
    const data = await apiPost("/api/auth/register", payload);
    setUser(data.user);
    setCsrfToken(data.csrf_token);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout", {});
    } finally {
      clear();
    }
  }, [clear]);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
