import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "../components/Layout";
import StatusBadge from "../components/StatusBadge";
import { STATUS } from "../statusConfig";
import { useAuth } from "../useAuth";
import { api } from "../api";

const TITLES = {
  admin: "Admin dashboard",
  creator: "My submissions",
  manager: "Approval queue",
  reviewer: "Approval queue",
};

export default function Dashboard() {
  const { user, token } = useAuth();
  const isReviewer = user.role === "manager" || user.role === "reviewer";
  const [rows, setRows] = useState([]);
  const [team, setTeam] = useState([]);
  const [kbCount, setKbCount] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(isReviewer ? "in_human_review" : "all");

  useEffect(() => {
    api("/submissions", { token })
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    if (user.role === "admin") {
      api("/users", { token }).then(setTeam).catch(() => {});
      api("/kb", { token }).then((k) => setKbCount(k.length)).catch(() => {});
    }
  }, []);

  const counts = {};
  rows.forEach((r) => {
    counts[r.status] = (counts[r.status] || 0) + 1;
  });
  const shown = filter === "all" ? rows : rows.filter((r) => r.status === filter);

  return (
    <Layout>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">{TITLES[user.role]}</h1>
        {user.role === "creator" && (
          <Link
            to="/submissions/new"
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            + New submission
          </Link>
        )}
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ["Total", rows.length, "all"],
          ["Needs changes", counts.needs_changes || 0, "needs_changes"],
          ["In human review", counts.in_human_review || 0, "in_human_review"],
          ["Approved", counts.approved || 0, "approved"],
          ["Published", counts.published || 0, "published"],
        ].map(([label, n, key]) => (
          <button
            key={label}
            onClick={() => setFilter(key)}
            className={`rounded-2xl border bg-white p-4 text-left shadow-sm hover:shadow-md ${
              filter === key ? "border-indigo-500 ring-2 ring-indigo-100" : "border-slate-200"
            }`}
          >
            <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
            <div className="mt-1 text-2xl font-bold text-slate-900">{n}</div>
          </button>
        ))}
      </div>

      {user.role === "admin" && (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Link
            to="/knowledge"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md"
          >
            <div className="text-2xl">📚</div>
            <div className="mt-2 font-semibold text-slate-900">Brand knowledge base</div>
            <div className="text-sm text-slate-500">
              {kbCount !== null ? `${kbCount} active items. ` : ""}Guidelines, facts, terminology and assets
            </div>
          </Link>
          <Link
            to="/insights"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:shadow-md"
          >
            <div className="text-2xl">📊</div>
            <div className="mt-2 font-semibold text-slate-900">Governance insights</div>
            <div className="text-sm text-slate-500">Repeated mistakes, teams and unclear guidelines</div>
          </Link>
        </div>
      )}

      {user.role === "admin" && team.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-3 font-semibold text-slate-900">Users ({team.length})</div>
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Employee ID</th>
                <th className="px-4 py-2">Role</th>
                <th className="px-4 py-2">Team</th>
              </tr>
            </thead>
            <tbody>
              {team.map((u) => (
                <tr key={u.employee_id} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-medium">{u.name}</td>
                  <td className="px-4 py-2">{u.employee_id}</td>
                  <td className="px-4 py-2 capitalize">{u.role}</td>
                  <td className="px-4 py-2">{u.team}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="mt-6 flex flex-wrap gap-2 text-sm">
        <button
          onClick={() => setFilter("all")}
          className={`rounded-full px-3 py-1 font-medium ${
            filter === "all" ? "bg-indigo-600 text-white" : "border border-slate-200 bg-white text-slate-600"
          }`}
        >
          All ({rows.length})
        </button>
        {Object.keys(STATUS).map((k) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={`rounded-full px-3 py-1 font-medium ${
              filter === k ? "bg-indigo-600 text-white" : "border border-slate-200 bg-white text-slate-600"
            }`}
          >
            {STATUS[k].label} ({counts[k] || 0})
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Channel</th>
              {user.role !== "creator" && <th className="px-4 py-3">Creator</th>}
              <th className="px-4 py-3">Risk</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Updated</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium">
                  <Link to={`/submissions/${r.id}`} className="text-indigo-600 hover:underline">
                    {r.title}
                  </Link>
                </td>
                <td className="px-4 py-3 capitalize">{r.channel}</td>
                {user.role !== "creator" && (
                  <td className="px-4 py-3">
                    {r.creator_name} <span className="text-slate-400">· {r.creator_team}</span>
                  </td>
                )}
                <td className="px-4 py-3 capitalize">{r.risk_level || "-"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-4 py-3 text-slate-500">{r.updated_at.slice(0, 16)}</td>
              </tr>
            ))}
            {!loading && shown.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  Nothing here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}