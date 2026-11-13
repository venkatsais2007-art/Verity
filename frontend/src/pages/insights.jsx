import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../useAuth";
import { api } from "../api";

const CAT_COLOR = {
  tone: "bg-violet-500",
  terminology: "bg-indigo-500",
  messaging: "bg-sky-500",
  claims: "bg-red-500",
  outdated_facts: "bg-amber-500",
  visual: "bg-pink-500",
  accessibility: "bg-emerald-500",
};

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export default function Insights() {
  const { token } = useAuth();
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/insights", { token }).then(setD).catch((e) => setError(e.message));
  }, []);

  if (error) return <Layout><p className="text-red-600">{error}</p></Layout>;
  if (!d) return <Layout><p className="text-slate-500">Loading...</p></Layout>;

  const maxCat = Math.max(1, ...d.by_category.map((c) => c.n));
  const maxTeam = Math.max(1, ...d.teams.map((t) => t.flags_per_submission));
  const unclear = d.guidelines.filter((g) => g.unclear);

  return (
    <Layout>
      <h1 className="text-2xl font-bold text-slate-900">Governance insights</h1>
      <p className="mt-1 text-sm text-slate-500">
        Patterns across all submissions: what goes wrong most, who needs support, and which guidelines may be unclear.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label="Submissions" value={d.total_submissions} />
        <Stat label="AI flags raised" value={d.total_flags} />
        <Stat label="Avg score, first draft" value={d.avg_score_first ?? "-"} />
        <Stat
          label="Avg score, latest"
          value={d.avg_score_latest ?? "-"}
          hint={
            d.avg_score_first != null && d.avg_score_latest != null
              ? `${d.avg_score_latest - d.avg_score_first >= 0 ? "+" : ""}${d.avg_score_latest - d.avg_score_first} after revisions`
              : ""
          }
        />
        <Stat label="Published" value={d.by_status.published || 0} hint="all human-approved" />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold text-slate-900">Most repeated violations by category</h2>
          <div className="mt-4 space-y-3">
            {d.by_category.map((c) => (
              <div key={c.category}>
                <div className="flex justify-between text-sm">
                  <span className="capitalize text-slate-700">{c.category.replace("_", " ")}</span>
                  <span className="font-medium text-slate-900">{c.n}</span>
                </div>
                <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${CAT_COLOR[c.category] || "bg-slate-500"}`}
                    style={{ width: `${(c.n / maxCat) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            {d.by_category.length === 0 && <p className="text-sm text-slate-400">No flags yet.</p>}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="font-semibold text-slate-900">Most repeated phrases</h2>
          <ol className="mt-4 space-y-2">
            {d.top_phrases.map((p, i) => (
              <li key={i} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span>
                  <span className="mr-2 text-slate-400">{i + 1}.</span>
                  “{p.phrase}”{" "}
                  <span className="text-xs capitalize text-slate-400">({p.category.replace("_", " ")})</span>
                </span>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs font-bold text-white">{p.n}×</span>
              </li>
            ))}
            {d.top_phrases.length === 0 && <p className="text-sm text-slate-400">No flags yet.</p>}
          </ol>
        </section>
      </div>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="font-semibold text-slate-900">Rule-breakers by team</h2>
        <p className="text-xs text-slate-500">Flags per submission, so busy teams aren't unfairly ranked higher.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2">Team</th>
                <th className="py-2">Submissions</th>
                <th className="py-2">Flags</th>
                <th className="py-2">High severity</th>
                <th className="py-2 w-1/3">Flags per submission</th>
              </tr>
            </thead>
            <tbody>
              {d.teams.map((t) => (
                <tr key={t.team} className="border-t border-slate-100">
                  <td className="py-2 font-medium">{t.team}</td>
                  <td className="py-2">{t.submissions}</td>
                  <td className="py-2">{t.flags}</td>
                  <td className="py-2">{t.high}</td>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-indigo-500"
                          style={{ width: `${(t.flags_per_submission / maxTeam) * 100}%` }}
                        />
                      </div>
                      <span className="w-8 text-right font-medium">{t.flags_per_submission}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="font-semibold text-slate-900">Guidelines flagged most, and how often creators dismiss them</h2>
        <p className="text-xs text-slate-500">
          A high dismissal rate can mean the guideline is unclear, too strict, or missing an exception.
        </p>
        {unclear.length > 0 && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {unclear.length} guideline{unclear.length > 1 ? "s" : ""} may need clarification:{" "}
            {unclear.map((g) => g.title).join(", ")}.
          </p>
        )}
        <div className="mt-4 space-y-3">
          {d.guidelines.map((g) => (
            <div key={g.title} className="rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-900">{g.title}</span>
                {g.unclear && (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                    May be unclear
                  </span>
                )}
                <span className="ml-auto text-sm text-slate-500">
                  flagged {g.flagged}× · dismissed {g.dismissed}× ({g.dismiss_rate}%)
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-amber-500" style={{ width: `${g.dismiss_rate}%` }} />
              </div>
              {g.reasons.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">
                  {g.reasons.map((r, i) => (
                    <li key={i}>Creators said: “{r}”</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {d.guidelines.length === 0 && <p className="text-sm text-slate-400">No data yet.</p>}
        </div>
      </section>
    </Layout>
  );
}