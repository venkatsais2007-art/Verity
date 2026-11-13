import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../useAuth";

const ROLES = [
  { role: "admin", label: "Admin", desc: "Knowledge base & users", emp: "admin01", icon: "🛡️" },
  { role: "creator", label: "Creator", desc: "Submit content", emp: "creator01", icon: "✍️" },
  { role: "manager", label: "Manager", desc: "Approve or reject", emp: "manager01", icon: "📋" },
  { role: "reviewer", label: "Reviewer", desc: "Approval queue", emp: "reviewer01", icon: "🔍" },
];

const FEATURES = [
  "Checks content against your approved guidelines and facts",
  "Explains every issue and suggests fixes you control",
  "Nothing is published without human sign-off",
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [company, setCompany] = useState("NORTHWIND");
  const [emp, setEmp] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (user) return <Navigate to="/" replace />;

  function pickRole(r) {
    setEmp(r.emp);
    setPassword("demo123");
    setError("");
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(company, emp, password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const inputClass =
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Left brand panel */}
      <div className="hidden lg:flex flex-col justify-between bg-gradient-to-br from-indigo-700 via-indigo-600 to-violet-700 p-12 text-white">
        <div className="text-2xl font-bold tracking-tight">
          Veri<span className="text-indigo-200">ty</span>
        </div>
        <div>
          <h1 className="text-4xl font-bold leading-tight">
            Catch brand mistakes
            <br />
            before you publish.
          </h1>
          <ul className="mt-8 space-y-4">
            {FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-3 text-indigo-50">
                <span className="mt-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-white/20 text-xs">
                  ✓
                </span>
                {f}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-sm text-indigo-200">
          AI-assisted review. Humans make the final call.
        </p>
      </div>

      {/* Right form panel */}
      <div className="flex items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-6 text-2xl font-bold text-slate-900">
            Veri<span className="text-indigo-600">ty</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Welcome back</h2>
          <p className="mt-1 text-sm text-slate-500">Who are you? Pick a role, then sign in.</p>

          <div className="mt-5 grid grid-cols-2 gap-3">
            {ROLES.map((r) => (
              <button
                key={r.role}
                type="button"
                onClick={() => pickRole(r)}
                className={`rounded-xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                  emp === r.emp
                    ? "border-indigo-600 bg-indigo-50 ring-2 ring-indigo-200"
                    : "border-slate-200 bg-white"
                }`}
              >
                <div className="text-xl">{r.icon}</div>
                <div className="mt-1 text-sm font-semibold text-slate-900">{r.label}</div>
                <div className="text-xs text-slate-500">{r.desc}</div>
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Company ID</label>
              <input className={inputClass} value={company}
                     onChange={(e) => setCompany(e.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Employee ID</label>
              <input className={inputClass} value={emp}
                     onChange={(e) => setEmp(e.target.value)} required />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Password</label>
              <input className={inputClass} type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} required />
            </div>
            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
            )}
            <button
              disabled={loading}
              className="w-full rounded-xl bg-indigo-600 py-2.5 font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
          <p className="mt-4 text-center text-xs text-slate-400">
            Demo company NORTHWIND · password demo123
          </p>
        </div>
      </div>
    </div>
  );
}