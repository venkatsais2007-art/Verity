import { Link } from "react-router-dom";
import { useAuth } from "../useAuth";
import { confirmLeave } from "../dirty";

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
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-center gap-x-6 gap-y-2">
          <Link to="/" onClick={(e) => { if (!confirmLeave()) e.preventDefault(); }} className="text-xl font-bold text-slate-900">
            Veri<span className="text-indigo-600">ty</span>
          </Link>
          <span className="hidden text-sm text-slate-500 sm:inline">{user.company_name}</span>
          <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
            <Link to="/" onClick={(e) => { if (!confirmLeave()) e.preventDefault(); }} className="text-slate-600 hover:text-indigo-600">Home</Link>
            {LINKS[user.role].map((l) => (
              <Link key={l.to} to={l.to} onClick={(e) => { if (!confirmLeave()) e.preventDefault(); }} className="text-slate-600 hover:text-indigo-600">
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="text-slate-600">
            {user.name} · <span className="font-medium capitalize text-indigo-600">{user.role}</span>
          </span>
          <button onClick={() => { if (confirmLeave()) logout(); }} className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-100">
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-4 sm:p-6">{children}</main>
      <footer className="py-6 text-center text-xs text-slate-400">
        Verity uses built-in rule checks and an external AI service (Google Gemini) to assist reviews. A human always makes the final decision.
      </footer>
    </div>
  );
}