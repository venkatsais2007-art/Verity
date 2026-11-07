import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";

const LINKS = {
  admin: [
    { to: "/knowledge", label: "Knowledge base" },
    { to: "/insights", label: "Insights" },
  ],
  creator: [{ to: "/submissions/new", label: "New submission" }],
  manager: [{ to: "/insights", label: "Insights" }],
  reviewer: [{ to: "/insights", label: "Insights" }],
};

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-6">
          <Link to="/" className="text-xl font-bold text-slate-900">
            Veri<span className="text-indigo-600">ty</span>
          </Link>
          <span className="text-sm text-slate-500">{user.company_name}</span>
          <nav className="flex gap-4 text-sm">
            <Link to="/" className="text-slate-600 hover:text-indigo-600">Home</Link>
            {LINKS[user.role].map((l) => (
              <Link key={l.to} to={l.to} className="text-slate-600 hover:text-indigo-600">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-600">
            {user.name} · <span className="font-medium capitalize text-indigo-600">{user.role}</span>
          </span>
          <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-100">
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-6">{children}</main>
      <footer className="py-6 text-center text-xs text-slate-400">
        Verity uses built-in rule checks and an external AI service (Google Gemini) to assist reviews. A human always makes the final decision.
      </footer>
    </div>
  );
}