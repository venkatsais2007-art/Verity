import { Navigate } from "react-router-dom";
import { useAuth } from "../useAuth";

export default function ProtectedRoute({ roles, children }) {
  const { user, loading, verified, logout } = useAuth();
  if (loading) return <div role="status" className="p-6 text-sm text-gray-600">Checking your session...</div>;
  if (user && !verified) {
    return (
      <div role="alert" className="p-6 text-sm text-gray-600">
        <p>Unable to verify your session. Please check your connection and sign in again.</p>
        <button onClick={logout} className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-100">
          Sign out
        </button>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}