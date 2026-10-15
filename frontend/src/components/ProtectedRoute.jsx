import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth.jsx";
import Forbidden from "../pages/Forbidden.jsx";

// Guards a route: waits for the session check, redirects anonymous visitors to
// /login, and shows a 403 page when the signed-in role is not allowed.
export default function ProtectedRoute({ roles, children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <div className="spin">Checking your session…</div>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (roles && !roles.includes(user.role)) return <Forbidden />;
  return children;
}
