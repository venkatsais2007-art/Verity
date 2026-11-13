import { useEffect, useState } from "react";
import { useAuth } from "../useAuth";
import { api } from "../api";

const inputClass =
  "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

const KIND = {
  approval: { label: "Approved", cls: "bg-emerald-100 text-emerald-700" },
  request_changes: { label: "Changes requested", cls: "bg-amber-100 text-amber-800" },
  rejection: { label: "Rejected", cls: "bg-red-100 text-red-700" },
  escalation: { label: "Creator note", cls: "bg-violet-100 text-violet-700" },
};

const ACTION = {
  submission_created: "Submission created",
  sent_for_ai_review: "Sent for AI review",
  ai_review_completed: "AI review completed",
  finding_accepted: "Flag accepted",
  finding_edited: "Flag marked for manual edit",
  finding_dismissed: "Flag dismissed",
  finding_reopened: "Flag decision undone",
  revised: "New version submitted",
  escalated: "Sent to human review",
  sent_to_human_review: "Sent to human review",
  comment_added: "Comment added",
  approved: "Approved",
  changes_requested: "Changes requested",
  rejected: "Rejected",
  published: "Published",
  brand_logo_uploaded: "Approved logo uploaded",
  brand_logo_removed: "Approved logo removed",
};

const DOT = {
  approved: "bg-emerald-500",
  published: "bg-green-600",
  rejected: "bg-red-500",
  changes_requested: "bg-amber-500",
  ai_review_completed: "bg-blue-500",
};

function History({ sid, refreshKey }) {
  const { token } = useAuth();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [showVersion, setShowVersion] = useState(null);

  useEffect(() => {
    api(`/submissions/${sid}/audit`, { token }).then(setData).catch(() => setData(null));
  }, [sid, refreshKey]);

  if (!data) return null;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between text-left">
        <h2 className="font-semibold text-slate-900">
          Revision history & audit trail ({data.versions.length} version{data.versions.length === 1 ? "" : "s"},{" "}
          {data.events.length} events)
        </h2>
        <span className="text-sm text-indigo-600">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="mt-4 grid gap-6 md:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-700">Versions</h3>
            <div className="mt-2 space-y-2">
              {data.versions.map((v) => (
                <div key={v.version} className="rounded-xl border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-slate-800">Version {v.version}</span>
                    <span className="text-xs text-slate-500">{v.created_at.slice(0, 16)}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Score: <b>{v.score ?? "-"}</b> · AI flags: <b>{v.findings_count}</b>
                  </p>
                  <button
                    onClick={() => setShowVersion(showVersion === v.version ? null : v.version)}
                    className="mt-1 text-xs text-indigo-600 hover:underline"
                  >
                    {showVersion === v.version ? "Hide text" : "View text"}
                  </button>
                  {showVersion === v.version && (
                    <p className="mt-2 whitespace-pre-line rounded-lg bg-slate-50 p-2 text-slate-700">{v.content}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-700">Activity</h3>
            <ol className="mt-2 space-y-3 border-l-2 border-slate-200 pl-4">
              {data.events.map((e) => (
                <li key={e.id} className="relative text-sm">
                  <span
                    className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ${DOT[e.action] || "bg-slate-400"}`}
                  />
                  <div className="font-medium text-slate-800">{ACTION[e.action] || e.action.replace(/_/g, " ")}</div>
                  <div className="text-xs text-slate-500">
                    {e.name ? `${e.name} (${e.role})` : "Verity (automated)"} · {e.created_at.slice(0, 16)}
                  </div>
                  {e.detail && <div className="mt-0.5 text-xs text-slate-600">{e.detail}</div>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReviewPanel({ submission, findings, reload }) {
  const { user, token } = useAuth();
  const [comments, setComments] = useState([]);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyKey, setHistoryKey] = useState(0);
  const sid = submission.id;
  const isReviewer = ["manager", "reviewer"].includes(user.role);
  const highRisk = submission.risk_level === "high";
  const cannotApprove = highRisk && user.role !== "manager";

  const counts = {
    accepted: findings.filter((f) => f.decision === "accepted").length,
    edited: findings.filter((f) => f.decision === "edited").length,
    dismissed: findings.filter((f) => f.decision === "dismissed").length,
    open: findings.filter((f) => f.decision === "open").length,
  };

  async function loadComments() {
    try {
      setComments(await api(`/submissions/${sid}/comments`, { token }));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadComments();
    setHistoryKey((k) => k + 1);
  }, [sid, submission.status, submission.current_version]);

  async function addComment() {
    if (!text.trim()) {
      setError("Please write a comment before posting.");
      return;
    }
    setError("");
    try {
      await api(`/submissions/${sid}/comments`, { method: "POST", token, body: { body: text } });
      setText("");
      await loadComments();
      setHistoryKey((k) => k + 1);
    } catch (e) {
      setError(e.message);
    }
  }

  async function act(action) {
    setBusy(true);
    setError("");
    try {
      await api(`/submissions/${sid}/approval`, { method: "POST", token, body: { action, comment: note } });
      setNote("");
      await reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    setBusy(true);
    setError("");
    try {
      await api(`/submissions/${sid}/publish`, { method: "POST", token });
      await reload();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 space-y-4">
      {submission.status === "in_human_review" && isReviewer && (
        <div className="rounded-2xl border border-violet-200 bg-violet-50/60 p-5">
          <h2 className="font-semibold text-slate-900">Human review</h2>
          <p className="mt-1 text-sm text-slate-600">
            Risk: <b className="capitalize">{submission.risk_level || "none"}</b> · {findings.length} AI flag
            {findings.length === 1 ? "" : "s"} · creator decisions: {counts.accepted} accepted, {counts.edited} edited,{" "}
            {counts.dismissed} dismissed, {counts.open} undecided
          </p>
          {cannotApprove && (
            <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This content is high risk, so only a manager can approve it. You can still comment or request changes.
            </p>
          )}
          <textarea
            className={`${inputClass} mt-3 h-20`}
            placeholder="Your note to the creator (required for Request changes and Reject)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <button
              onClick={() => act("approve")}
              disabled={busy || cannotApprove}
              className="rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
            >
              Approve
            </button>
            <button
              onClick={() => act("request_changes")}
              disabled={busy}
              className="rounded-lg bg-amber-500 px-4 py-2 font-medium text-white hover:bg-amber-600 disabled:opacity-40"
            >
              Request changes
            </button>
            <button
              onClick={() => act("reject")}
              disabled={busy}
              className="rounded-lg bg-red-600 px-4 py-2 font-medium text-white hover:bg-red-700 disabled:opacity-40"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {submission.status === "in_human_review" && !isReviewer && (
        <p className="rounded-xl bg-violet-50 px-4 py-3 text-sm text-violet-800">
          Waiting for a manager or reviewer to review this content.
        </p>
      )}

      {submission.status === "approved" && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
          <p className="font-semibold text-emerald-800">Approved by a human reviewer</p>
          <p className="mt-1 text-sm text-emerald-700">It is not live yet. A manager or reviewer must publish it.</p>
          {isReviewer && (
            <button
              onClick={publish}
              disabled={busy}
              className="mt-3 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
            >
              Mark as published
            </button>
          )}
        </div>
      )}

      {submission.status === "published" && (
        <p className="rounded-xl bg-green-50 px-4 py-3 text-sm font-medium text-green-800">
          Published. This content was approved by a human before going live.
        </p>
      )}
      {submission.status === "rejected" && (
        <p className="rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
          Rejected by a reviewer. See the comments below for the reason.
        </p>
      )}

      {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="font-semibold text-slate-900">Comments ({comments.length})</h2>
        {comments.length === 0 && <p className="mt-2 text-sm text-slate-400">No comments yet.</p>}
        <div className="mt-3 space-y-3">
          {comments.map((c) => (
            <div key={c.id} className="rounded-xl bg-slate-50 p-3">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span className="font-semibold text-slate-800">{c.name}</span>
                <span className="capitalize">{c.role}</span>
                {KIND[c.kind] && (
                  <span className={`rounded-full px-2 py-0.5 font-medium ${KIND[c.kind].cls}`}>
                    {KIND[c.kind].label}
                  </span>
                )}
                <span className="ml-auto">{c.created_at.slice(0, 16)}</span>
              </div>
              <p className="mt-1 whitespace-pre-line text-sm text-slate-700">{c.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          <input
            className={inputClass}
            placeholder="Write a comment..."
            value={text}
            onChange={(e) => { setText(e.target.value); if (error) setError(""); }}
            onKeyDown={(e) => e.key === "Enter" && addComment()}
          />
          <button
            onClick={addComment}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Post
          </button>
        </div>
      </div>

      <History sid={sid} refreshKey={historyKey} />
    </div>
  );
}