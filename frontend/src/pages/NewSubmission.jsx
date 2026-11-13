import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import { useAuth } from "../useAuth";
import { api } from "../api";
import { setDirty } from "../dirty";

const CHANNELS = [
  { value: "social", label: "Social post" },
  { value: "ad", label: "Ad" },
  { value: "email", label: "Email" },
  { value: "web", label: "Web page" },
];

const inputClass =
  "w-full rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100";

export default function NewSubmission() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [channel, setChannel] = useState("social");
  const [purpose, setPurpose] = useState("");
  const [content, setContent] = useState("");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isImage = file && /\.(png|jpe?g|webp)$/i.test(file.name);
  const isDoc = file && /\.(pdf|docx|txt)$/i.test(file.name);

  const hasDraft = Boolean(title.trim() || purpose.trim() || content.trim() || file);
  useEffect(() => {
    setDirty(hasDraft);
    const onUnload = (e) => {
      if (hasDraft) { e.preventDefault(); e.returnValue = ""; }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      setDirty(false);
    };
  }, [hasDraft]);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("title", title);
      form.append("channel", channel);
      form.append("purpose", purpose);
      form.append("content", content);
      if (file) form.append("file", file);
      const r = await api("/submissions", { method: "POST", token, body: form });
      setDirty(false);
      navigate(`/submissions/${r.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <h1 className="text-2xl font-bold text-slate-900">New submission</h1>
      <p className="mt-1 text-sm text-slate-500">
        Submit text, an image, or a document (PDF/DOCX/TXT). Nothing is published without human approval.
      </p>

      <form onSubmit={submit} className="mt-6 max-w-3xl space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Title</label>
            <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Channel</label>
            <select className={inputClass} value={channel} onChange={(e) => setChannel(e.target.value)}>
              {CHANNELS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Purpose (what is this content trying to achieve?)
          </label>
          <input className={inputClass} value={purpose} onChange={(e) => setPurpose(e.target.value)}
                 placeholder="e.g. Announce the new subscription price" />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            Attach an image or document (optional)
          </label>
          <input type="file" accept=".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt"
                 className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-4 file:py-2 file:font-medium file:text-indigo-700"
                 onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>

        {!isDoc && (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              {isImage ? "Caption / alt text (describe the image)" : "Content"}
            </label>
            <textarea className={`${inputClass} h-48`} value={content}
                      onChange={(e) => setContent(e.target.value)}
                      required={!file}
                      placeholder={isImage ? "Describe what the image shows..." : "Paste or write your content here..."} />
          </div>
        )}
        {isDoc && (
          <p className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-700">
            Text will be extracted from your document automatically.
          </p>
        )}

        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <button disabled={busy}
                className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
          {busy ? "Saving..." : "Save as draft"}
        </button>
      </form>
    </Layout>
  );
}