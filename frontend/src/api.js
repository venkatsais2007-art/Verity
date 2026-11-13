export async function api(path, { method = "GET", body, token } = {}) {
  const isForm = body instanceof FormData;
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && path !== "/login") {
      window.dispatchEvent(new Event("verity:unauthorized"));
    }
    const error = new Error(data.detail || "Request failed");
    error.status = res.status;
    throw error;
  }
  return data;
}