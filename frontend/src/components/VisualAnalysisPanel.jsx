import { useEffect, useState } from "react";
import { useAuth } from "../useAuth";
import { api } from "../api";

const SEVERITY = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-sky-100 text-sky-700",
};

const CHECK_LABELS = {
  logos: "Approved logo",
  colors: "Brand colours",
  text_contrast: "Text contrast & accessibility",
  visual_guidelines: "Visual guidelines",
};

const CHECK_STATUS = {
  complete: "Checked",
  partial: "Partial",
  not_configured: "Not configured",
  failed: "Not completed",
  running: "Running",
};

export default function VisualAnalysisPanel({ submissionId, version, reviewStatus, imageUrl, textFindingCount }) {
  const { token } = useAuth();
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await api(`/submissions/${submissionId}/visual-analysis`, { token });
        if (active) {
          setAnalysis(result);
          setError("");
        }
      } catch (err) {
        if (active) setError(err.message);
      }
    }

    load();
    const timer = reviewStatus === "ai_review" ? setInterval(load, 2000) : null;
    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
  }, [submissionId, version, reviewStatus, token]);

  const report = analysis?.result;
  const findings = report?.findings || [];
  const located = findings.filter((finding) => finding.bbox);

  return (
    <section className="mt-6 rounded-2xl border border-indigo-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Visual analysis & compliance report</h2>
          <p className="mt-1 text-sm text-slate-500">
            Separate from the text score. Automated findings are advisory; a human reviewer makes the final decision.
          </p>
        </div>
        {report && (
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
            report.status === "complete" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"
          }`}>
            {report.status === "complete" ? "Checks completed" : "Partial analysis"}
          </span>
        )}
      </div>

      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      {analysis?.status === "running" || (analysis?.status === "not_run" && reviewStatus === "ai_review") ? (
        <p className="mt-4 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
          Visual checks are running. Results will appear here when available.
        </p>
      ) : null}
      {analysis?.status === "failed" && (
        <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          Visual analysis did not complete{analysis.error ? `: ${analysis.error}` : "."}
        </p>
      )}
      {analysis?.status === "not_run" && reviewStatus !== "ai_review" && (
        <p className="mt-4 text-sm text-slate-500">Visual checks have not been run for this image version.</p>
      )}

      {report && (
        <>
          <p className="mt-4 rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
            Overall review: <b>{textFindingCount} text finding{textFindingCount === 1 ? "" : "s"}</b> ·{" "}
            <b>{report.summary.total_findings} visual finding{report.summary.total_findings === 1 ? "" : "s"}</b>
            <span className="ml-1 text-xs text-indigo-700">Visual results supplement and do not change the existing text score.</span>
          </p>
          {report.note && <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">{report.note}</p>}
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {Object.entries(report.checks).map(([key, check]) => (
              <div key={key} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                <span className="text-slate-700">{CHECK_LABELS[key] || key}</span>
                <span className={`text-xs font-medium ${
                  check.status === "complete" ? "text-emerald-700" : "text-amber-700"
                }`}>
                  {CHECK_STATUS[check.status] || check.status}
                </span>
              </div>
            ))}
          </div>

          {imageUrl && located.length > 0 && (
            <div className="mt-5">
              <p className="mb-2 text-xs font-medium text-slate-600">Highlighted regions (approximate for AI observations)</p>
              <div className="relative inline-block max-w-full">
                <img src={imageUrl} alt="Submitted creative with visual findings highlighted" className="block max-h-96 max-w-full rounded-xl border border-slate-200" />
                <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
                  {located.map((finding, index) => (
                    <rect
                      key={`${finding.category}-${index}`}
                      x={finding.bbox.x * 1000}
                      y={finding.bbox.y * 1000}
                      width={finding.bbox.width * 1000}
                      height={finding.bbox.height * 1000}
                      fill="rgba(239,68,68,0.12)"
                      stroke="#ef4444"
                      strokeWidth="4"
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}
                </svg>
              </div>
            </div>
          )}

          <div className="mt-5 space-y-3">
            <h3 className="text-sm font-semibold text-slate-800">
              Findings ({findings.length})
            </h3>
            {findings.length === 0 && (
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                No issues were returned by the checks that completed. Unconfigured checks are not treated as passing.
              </p>
            )}
            {findings.map((finding, index) => (
              <article key={`${finding.category}-${index}`} className="rounded-xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${SEVERITY[finding.severity] || SEVERITY.low}`}>
                    {finding.severity}
                  </span>
                  <span className="text-sm font-semibold capitalize text-slate-800">{finding.category.replace(/_/g, " ")}</span>
                  <span className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    finding.source === "ai_estimate" ? "bg-violet-100 text-violet-800" : "bg-blue-100 text-blue-800"
                  }`}>
                    {finding.source === "ai_estimate" ? "AI estimate — verify" : "Image measurement"}
                  </span>
                </div>
                <p className="mt-3 text-sm font-medium text-slate-800">{finding.description}</p>
                <p className="mt-1 text-sm text-slate-600"><b>Why:</b> {finding.reason}</p>
                <p className="mt-1 text-sm text-slate-600"><b>Guideline:</b> {finding.guideline || "No matching guideline cited"}</p>
                <p className="mt-1 text-sm text-slate-600"><b>Suggested correction:</b> {finding.suggestion}</p>
                {finding.detected_color && (
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
                    {[["Detected", finding.detected_color], ["Nearest approved", finding.expected_color]].map(([label, color]) => (
                      <span key={label} className="inline-flex items-center gap-1.5">
                        <span className="h-4 w-4 rounded border border-slate-300" style={{ backgroundColor: color }} />
                        {label}: {color}
                      </span>
                    ))}
                  </div>
                )}
                {finding.estimated_contrast_ratio !== undefined && (
                  <p className="mt-2 text-sm text-slate-700">
                    <b>Estimated contrast:</b> {finding.estimated_contrast_ratio}:1
                    <span className="ml-1 text-xs text-slate-500">({finding.contrast_basis})</span>
                  </p>
                )}
                {finding.bbox ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Region: x {Math.round(finding.bbox.x * 100)}%, y {Math.round(finding.bbox.y * 100)}%, width {Math.round(finding.bbox.width * 100)}%, height {Math.round(finding.bbox.height * 100)}%
                  </p>
                ) : (
                  <p className="mt-2 text-xs text-slate-500">Location could not be pinpointed by this check.</p>
                )}
                {finding.source === "ai_estimate" && typeof finding.confidence === "number" && (
                  <p className="mt-1 text-xs text-violet-700">AI confidence estimate: {Math.round(finding.confidence * 100)}% — not a calibrated probability.</p>
                )}
              </article>
            ))}
          </div>
          <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
            The submitted image is never modified. The visual report is supplemental and does not replace required human approval.
          </p>
        </>
      )}
    </section>
  );
}
