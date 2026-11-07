export const STATUS = {
  draft: { label: "Draft", cls: "bg-slate-100 text-slate-700" },
  ai_review: { label: "AI Review", cls: "bg-blue-100 text-blue-700" },
  needs_changes: { label: "Needs Changes", cls: "bg-amber-100 text-amber-800" },
  in_human_review: { label: "In Human Review", cls: "bg-violet-100 text-violet-700" },
  approved: { label: "Approved", cls: "bg-emerald-100 text-emerald-700" },
  published: { label: "Published", cls: "bg-green-600 text-white" },
  rejected: { label: "Rejected", cls: "bg-red-100 text-red-700" },
};

export const PIPELINE = ["draft", "ai_review", "needs_changes", "in_human_review", "approved", "published"];

export default function StatusBadge({ status }) {
  const s = STATUS[status] || { label: status, cls: "bg-slate-100 text-slate-700" };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>{s.label}</span>
  );
}