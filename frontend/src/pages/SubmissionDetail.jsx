import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import Layout from "../components/Layout";
import StatusBadge, { PIPELINE, STATUS } from "../components/StatusBadge";
import ReviewPanel from "../components/ReviewPanel";
import { useAuth } from "../AuthContext";
import { api } from "../api";

const SEV = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-sky-100 text-sky-700",
};

const MARK = {
  high: "bg-red-200 decoration-red-500",
  medium: "bg-amber-200 decoration-amber-500",
  low: "bg-sky-200 decoration-sky-500",
};

function buildSegments(text, findings) {
  const ranges = [];
  findings.forEach((f, i) => {
    const needle = (f.flagged_text || "").trim();
    if (!needle) return;
    const start = text.toLowerCase().indexOf(needle.toLowerCase());
    if (start === -1) return;
    const end = start + needle.length;
    if (ranges.some((r) => start < r.end && end > r.start)) return;
    ranges.push({ start, end, num: i + 1, id: f.id, severity: f.severity });
  });
  ranges.sort((a, b) => a.start - b.start);
  const segs = [];
  let pos = 0;
  for (const r of ranges) {
    if (r.start > pos) segs.push({ text: text.slice(pos, r.start) });
    segs.push({ text: text.slice(r.start, r.end), num: r.num, id: r.id, severity: r.severity });
    pos = r.end;
  }
  if (pos < text.length) segs.push({ text: text.slice(pos) });
  return segs;
}

function diffWords(a, b) {
  const A = (a || "").split(/(\s+)/);
  const B = (b || "").split(/(\s+)/);
  const n = A.length;
  const m = B.length;
  if (n * m > 4000000) return null;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      ops.push({ t: "same", v: A[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ t: "del", v: A[i] });
      i++;
    } else {
      ops.push({ t: "add", v: B[j] });
      j++;
    }
  }
  while (i < n) ops.push({ t: "del", v: A[i++] });
  while (j < m) ops.push({ t: "add", v: B[j++] });
  return ops;
}

const DECISION = {
  open: { label: "Needs your decision", cls: "bg-amber-100 text-amber-800" },
  accepted: { label: "Accepted: will fix", cls: "bg-emerald-100 text-emerald-700" },
  edited: { label: "Will edit manually", cls: "bg-blue-100 text-blue-700" },
  dismissed: { label: "Dismissed", cls: "bg-slate-200 text-slate-700" },
};

const inputClass =
  "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

export default function SubmissionDetail() {
  const { id } = useParams();
  const { user, token } = useAuth();
  const [data, setData] = useState(null);
  const [compare, setCompare] = useState(null);
  const [error, setError] = useState("");
  const [imageUrl, setImageUrl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState("");
  const [dismissFor, setDismissFor] = useState(null);
  const [reasonText, setReasonText] = useState("");
  const [escalating, setEscalating] = useState(false);
  const [note, setNote] = useState("");
  const imageLoaded = useRef(false);
  const editorRef = useRef(null);

  async function load() {
    try {
      const d = await api(`/submissions/${id}`, { token });
      setData(d);
      try {
        setCompare(await api(`/submissions/${id}/compare`, { token }));
      } catch {
        setCompare(null);
      }
      const current = d.versions[0];
      if (current.file_type === "image" && !imageLoaded.current) {
        imageLoaded.current = true;
        const res = await fetch(`/api/submissions/${id}/file`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) setImageUrl(URL.createObjectURL(await res.blob()));
      }
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [id]);

  const status = data?.submission.status;
  useEffect(() => {
    if (status !== "ai_review") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [status]);

  const currentVersion = data?.submission.current_version;
  useEffect(() => {
    if (data) setDraft(data.versions[0].content || "");
  }, [currentVersion]);

  async function sendForReview() {
    setBusy(true);
    setError("");
    try {
      await api(`/submissions/${id}/submit`, { method: "POST", token });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(fid, decision, reason = "") {
    setError("");
    try {
      await api(`/submissions/${id}/findings/${fid}/decision`, {
        method: "POST",
        token,
        body: { decision, reason },
      });
      setDismissFor(null);
      setReasonText("");
      await load();
      if (decision === "edited" && editorRef.current) {
        editorRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
        editorRef.current.focus();
      }
    } catch (e) {
      setError(e.message);
    }
  }

  async function resubmit() {
    setBusy(true);
    setError("");
    try {
      await api(`/submissions/${id}/revise`, { method: "POST", token, body: { content: draft } });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function escalate() {
    setBusy(true);
    setError("");
    try {
      await api(`/submissions/${id}/escalate`, { method: "POST", token, body: { note } });
      setEscalating(false);
      setNote("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function jumpTo(fid) {
    setActiveId(fid);
    const el = document.getElementById(`finding-${fid}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  if (!data) {
    return (
      <Layout>
        {error ? <p className="text-red-600">{error}</p> : <p className="text-slate-500">Loading...</p>}
      </Layout>
    );
  }

  const s = data.submission;
  const v = data.versions[0];
  const findings = data.findings;
  const reviewed = v.score !== null && v.score !== undefined;
  const isCreator = user.role === "creator";
  const canSend = isCreator && s.status === "draft";
  const canDecide = isCreator && s.status === "needs_changes";
  const openCount = findings.filter((f) => f.decision === "open").length;
  const originalName = v.file_name ? v.file_name.split("_").slice(1).join("_") : null;
  const segments =
    reviewed && s.status !== "ai_review"
      ? buildSegments(v.content || "", findings)
      : [{ text: v.content || "(no text)" }];
  const isNote = s.review_error && s.review_error.startsWith("Note:");

  let resolved = [];
  let ops = null;
  if (compare?.has_previous && reviewed) {
    const keys = new Set(findings.map((f) => `${(f.flagged_text || "").toLowerCase()}|${f.category}`));
    resolved = compare.previous_findings.filter(
      (f) => !keys.has(`${(f.flagged_text || "").toLowerCase()}|${f.category}`)
    );
    ops = diffWords(compare.previous_content, v.content);
  }

  return (
    <Layout>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{s.title}</h1>
          <p className="mt-1 text-sm text-slate-500">
            <span className="capitalize">{s.channel}</span> · by {s.creator_name} ({s.creator_team}) · version{" "}
            {s.current_version}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {reviewed && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-center">
              <div className="text-xs text-slate-500">Brand score</div>
              <div className="text-xl font-bold text-slate-900">{v.score}</div>
            </div>
          )}
          {s.risk_level && (
            <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-center">
              <div className="text-xs text-slate-500">Risk</div>
              <div className="text-xl font-bold capitalize text-slate-900">{s.risk_level}</div>
            </div>
          )}
          <StatusBadge status={s.status} />
        </div>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {PIPELINE.map((p, i) => (
          <div key={p} className="flex items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                p === s.status ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"
              }`}
            >
              {STATUS[p].label}
            </span>
            {i < PIPELINE.length - 1 && <span className="text-slate-300">→</span>}
          </div>
        ))}
      </div>

      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {s.review_error && (
        <p
          className={`mt-4 rounded-lg px-3 py-2 text-sm ${
            isNote ? "bg-amber-50 text-amber-800" : "bg-red-50 text-red-700"
          }`}
        >
          {s.review_error}
        </p>
      )}

      {s.status === "ai_review" && (
        <div className="mt-6 rounded-2xl border border-blue-200 bg-blue-50 p-5">
          <p className="font-medium text-blue-800">AI review in progress</p>
          <p className="mt-1 text-sm text-blue-700">{s.review_progress || "Starting..."}</p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-blue-100">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
          </div>
        </div>
      )}

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {s.purpose && (
          <p className="mb-4 text-sm text-slate-500">
            <span className="font-medium text-slate-700">Purpose:</span> {s.purpose}
          </p>
        )}
        {imageUrl && (
          <img src={imageUrl} alt={v.content || "Submitted image"} className="mb-4 max-h-96 rounded-xl border" />
        )}
        {v.file_type === "document" && originalName && (
          <p className="mb-3 text-sm text-slate-500">📄 {originalName} (text extracted)</p>
        )}
        <p className="whitespace-pre-line leading-8 text-slate-800">
          {segments.map((seg, i) =>
            seg.num ? (
              <mark
                key={i}
                onClick={() => jumpTo(seg.id)}
                title="Click to see this finding"
                className={`cursor-pointer rounded px-1 underline decoration-2 underline-offset-4 ${MARK[seg.severity]}`}
              >
                {seg.text}
                <sup className="ml-0.5 text-[10px] font-bold">{seg.num}</sup>
              </mark>
            ) : (
              <span key={i}>{seg.text}</span>
            )
          )}
        </p>
        {reviewed && s.status !== "ai_review" && findings.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-3 border-t border-slate-100 pt-3 text-xs text-slate-500">
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-red-200" /> High</span>
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-amber-200" /> Medium</span>
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded bg-sky-200" /> Low</span>
            <span>Click a highlight to jump to its explanation.</span>
          </div>
        )}
      </div>

      <ReviewPanel submission={s} findings={findings} reload={load} />

      {canSend && (
        <div className="mt-6">
          <button
            onClick={sendForReview}
            disabled={busy}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Sending..." : "Send for AI review"}
          </button>
          <p className="mt-2 text-xs text-slate-400">
            AI disclosure: built-in brand rules check your content first. When enabled, the content is also sent to
            an external AI service (Google Gemini) for deeper analysis. A human makes the final decision.
          </p>
        </div>
      )}

      {canDecide && (
        <div className="mt-6 rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5">
          <h2 className="font-semibold text-slate-900">Edit your content</h2>
          <p className="mt-1 text-xs text-slate-500">
            Suggestions are never applied automatically. You write the changes yourself, then resubmit for a re-check.
          </p>
          <textarea
            ref={editorRef}
            className={`${inputClass} mt-3 h-48`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              onClick={resubmit}
              disabled={busy || openCount > 0}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Submitting..." : "Resubmit for re-check"}
            </button>
            <button
              onClick={() => setEscalating(true)}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Send to human review
            </button>
            {openCount > 0 && (
              <span className="text-sm text-amber-700">
                Decide on {openCount} more flag{openCount > 1 ? "s" : ""} below to enable resubmit.
              </span>
            )}
          </div>
          {escalating && (
            <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-sm font-medium text-slate-800">
                Explain to the reviewer why this should go to human review with flags still open
              </p>
              <textarea
                className={`${inputClass} mt-2 h-20`}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="mt-2 flex gap-2">
                <button
                  onClick={escalate}
                  disabled={busy}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  Send to human review
                </button>
                <button
                  onClick={() => setEscalating(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {compare?.has_previous && reviewed && s.status !== "ai_review" && (
        <section className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">
            Changes since version {compare.previous_version}
          </h2>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <span className="rounded-lg bg-slate-100 px-3 py-1.5">
              Score: <b>{compare.previous_score ?? "-"}</b> → <b>{v.score}</b>
              {compare.previous_score !== null && (
                <span className={v.score >= compare.previous_score ? "text-emerald-600" : "text-red-600"}>
                  {" "}({v.score - compare.previous_score >= 0 ? "+" : ""}{v.score - compare.previous_score})
                </span>
              )}
            </span>
            <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-emerald-700">
              Resolved: <b>{resolved.length}</b>
            </span>
            <span className="rounded-lg bg-amber-50 px-3 py-1.5 text-amber-800">
              Remaining: <b>{findings.length}</b>
            </span>
          </div>
          {resolved.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-slate-600">
              {resolved.map((f) => (
                <li key={f.id}>
                  ✓ <span className="line-through">“{f.flagged_text}”</span>{" "}
                  <span className="text-xs capitalize text-slate-400">({f.category.replace("_", " ")})</span>
                </li>
              ))}
            </ul>
          )}
          <h3 className="mt-5 text-sm font-semibold text-slate-700">Before / after</h3>
          {ops ? (
            <p className="mt-2 whitespace-pre-line rounded-xl bg-slate-50 p-4 leading-8 text-slate-800">
              {ops.map((o, i) =>
                o.t === "same" ? (
                  <span key={i}>{o.v}</span>
                ) : o.t === "add" ? (
                  <span key={i} className="rounded bg-emerald-100 text-emerald-800">{o.v}</span>
                ) : (
                  <span key={i} className="rounded bg-red-100 text-red-700 line-through">{o.v}</span>
                )
              )}
            </p>
          ) : (
            <p className="mt-2 text-sm text-slate-500">Text is too long to show a comparison.</p>
          )}
          <div className="mt-2 flex gap-3 text-xs text-slate-500">
            <span><span className="rounded bg-red-100 px-1 line-through">removed</span></span>
            <span><span className="rounded bg-emerald-100 px-1">added</span></span>
          </div>
        </section>
      )}

      {reviewed && s.status !== "ai_review" && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Findings ({findings.length})</h2>
          {findings.length === 0 && (
            <p className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              No issues found. This content matches the knowledge base.
            </p>
          )}
          <div className="mt-3 space-y-4">
            {findings.map((f, i) => {
              const d = DECISION[f.decision] || DECISION.open;
              return (
                <div
                  key={f.id}
                  id={`finding-${f.id}`}
                  className={`rounded-2xl border bg-white p-5 shadow-sm transition ${
                    activeId === f.id ? "border-indigo-500 ring-4 ring-indigo-100" : "border-slate-200"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-white">
                      {i + 1}
                    </span>
                    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${SEV[f.severity]}`}>
                      {f.severity}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium capitalize text-slate-700">
                      {f.category.replace("_", " ")}
                    </span>
                    <span className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium ${d.cls}`}>
                      {d.label}
                    </span>
                  </div>
                  <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-slate-800">“{f.flagged_text}”</p>
                  <p className="mt-3 text-sm text-slate-700"><span className="font-medium">Why:</span> {f.reason}</p>
                  <p className="mt-2 text-sm text-slate-700"><span className="font-medium">Source:</span> {f.source_ref}</p>
                  <p className="mt-2 text-sm text-emerald-800">
                    <span className="font-medium">Suggested fix:</span> {f.suggestion}
                  </p>
                  {f.decision === "dismissed" && f.decision_reason && (
                    <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                      <span className="font-medium">Dismissal reason:</span> {f.decision_reason}
                    </p>
                  )}

                  {canDecide && (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                      <div className="flex flex-wrap gap-2 text-sm">
                        <button
                          onClick={() => decide(f.id, "accepted")}
                          className="rounded-lg bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-700"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => decide(f.id, "edited")}
                          className="rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700"
                        >
                          Edit manually
                        </button>
                        <button
                          onClick={() => {
                            setDismissFor(dismissFor === f.id ? null : f.id);
                            setReasonText("");
                          }}
                          className="rounded-lg border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                        >
                          Dismiss
                        </button>
                        <button
                          onClick={() => navigator.clipboard?.writeText(f.suggestion || "")}
                          className="rounded-lg px-3 py-1.5 text-slate-500 hover:bg-slate-50"
                        >
                          Copy suggestion
                        </button>
                        {f.decision !== "open" && (
                          <button
                            onClick={() => decide(f.id, "open")}
                            className="rounded-lg px-3 py-1.5 text-slate-500 hover:bg-slate-50"
                          >
                            Undo
                          </button>
                        )}
                      </div>
                      {dismissFor === f.id && (
                        <div className="mt-3">
                          <input
                            className={inputClass}
                            placeholder="Why is this flag not a problem? (required)"
                            value={reasonText}
                            onChange={(e) => setReasonText(e.target.value)}
                          />
                          <button
                            onClick={() => decide(f.id, "dismissed", reasonText)}
                            className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
                          >
                            Confirm dismiss
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}
    </Layout>
  );
}