import { useEffect, useState } from "react";
import Layout from "../components/Layout";
import { useAuth } from "../AuthContext";
import { api } from "../api";

const KINDS = [
  { value: "guideline", label: "Guidelines" },
  { value: "tone", label: "Tone rules" },
  { value: "term", label: "Terminology" },
  { value: "fact", label: "Approved facts" },
  { value: "asset", label: "Assets (colours, fonts, logo)" },
];

const inputClass =
  "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

export default function KnowledgeBase() {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState("paste");
  const [kind, setKind] = useState("guideline");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null);
  const [history, setHistory] = useState(null);

  async function load() {
    try {
      setItems(await api("/kb", { token }));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function flash(msg) {
    setMessage(msg);
    setTimeout(() => setMessage(""), 3000);
  }

  async function add(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "paste") {
        await api("/kb", { method: "POST", token, body: { kind, title, content } });
      } else {
        if (!file) throw new Error("Choose a file first");
        const form = new FormData();
        form.append("kind", kind);
        form.append("title", title);
        form.append("file", file);
        await api("/kb/upload", { method: "POST", token, body: form });
      }
      setTitle("");
      setContent("");
      setFile(null);
      setFileKey((k) => k + 1);
      flash("Saved to knowledge base");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    setError("");
    setBusy(true);
    try {
      const r = await api(`/kb/${editing.id}`, {
        method: "PUT",
        token,
        body: { content: editing.content },
      });
      setEditing(null);
      flash(`Saved as version ${r.version}`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function archive(id) {
    if (!confirm("Remove this item from the active knowledge base? Past versions are kept.")) return;
    try {
      await api(`/kb/${id}`, { method: "DELETE", token });
      flash("Item archived");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function showHistory(item) {
    try {
      const rows = await api(`/kb/${item.id}/history`, { token });
      setHistory({ title: item.title, rows });
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <Layout>
      <h1 className="text-2xl font-bold text-slate-900">Brand knowledge base</h1>
      <p className="mt-1 text-sm text-slate-500">
        Everything the AI checks content against. Edits create a new version; old versions are kept.
      </p>

      {message && <p className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}
      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <form onSubmit={add} className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex gap-2 text-sm">
          {["paste", "upload"].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`rounded-lg px-3 py-1.5 font-medium ${
                mode === m ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {m === "paste" ? "Paste text" : "Upload file"}
            </button>
          ))}
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
          <input className={inputClass} placeholder="Title (e.g. Brand Voice 2026)"
                 value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>

        {mode === "paste" ? (
          <textarea className={`${inputClass} mt-3 h-32`} placeholder="Paste the guideline, facts or terms here..."
                    value={content} onChange={(e) => setContent(e.target.value)} required />
        ) : (
          <input key={fileKey} type="file" accept=".pdf,.docx,.txt,.md"
                 className="mt-3 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:font-medium file:text-indigo-700"
                 onChange={(e) => setFile(e.target.files[0])} />
        )}

        <button disabled={busy}
                className="mt-4 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {busy ? "Saving..." : "Add to knowledge base"}
        </button>
      </form>

      {KINDS.map((k) => {
        const group = items.filter((i) => i.kind === k.value);
        return (
          <section key={k.value} className="mt-8">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{k.label}</h2>
            {group.length === 0 && <p className="mt-2 text-sm text-slate-400">Nothing here yet.</p>}
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              {group.map((i) => (
                <div key={i.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold text-slate-900">{i.title}</h3>
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      v{i.version}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-5 whitespace-pre-line text-sm text-slate-600">{i.content}</p>
                  <div className="mt-4 flex gap-4 text-sm">
                    <button onClick={() => setEditing({ id: i.id, title: i.title, content: i.content })}
                            className="text-indigo-600 hover:underline">Edit</button>
                    <button onClick={() => showHistory(i)} className="text-slate-600 hover:underline">History</button>
                    <button onClick={() => archive(i.id)} className="text-red-600 hover:underline">Archive</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}

      {editing && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="font-semibold text-slate-900">Edit: {editing.title}</h3>
            <p className="text-xs text-slate-500">Saving creates a new version.</p>
            <textarea className={`${inputClass} mt-3 h-64`} value={editing.content}
                      onChange={(e) => setEditing({ ...editing, content: e.target.value })} />
            <div className="mt-4 flex justify-end gap-3">
              <button onClick={() => setEditing(null)}
                      className="rounded-xl border border-slate-300 px-4 py-2 text-sm">Cancel</button>
              <button onClick={saveEdit} disabled={busy}
                      className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                Save new version
              </button>
            </div>
          </div>
        </div>
      )}

      {history && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
            <h3 className="font-semibold text-slate-900">Version history: {history.title}</h3>
            <div className="mt-4 space-y-3">
              {history.rows.map((r) => (
                <div key={r.id} className="rounded-xl border border-slate-200 p-3">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="font-semibold text-slate-800">
                      v{r.version} {r.is_active ? "(current)" : ""}
                    </span>
                    <span>{r.author || "System"} · {r.created_at}</span>
                  </div>
                  <p className="mt-2 whitespace-pre-line text-sm text-slate-600">{r.content}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 text-right">
              <button onClick={() => setHistory(null)}
                      className="rounded-xl border border-slate-300 px-4 py-2 text-sm">Close</button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}