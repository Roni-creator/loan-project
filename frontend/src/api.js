// Small fetch helper. Same error behaviour as the old static/app.js:
// show the server's "error" message if there is one.
const BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function apiGet(path) {
  const res = await fetch(BASE + path);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}

export async function apiPost(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong. Please try again.");
  return data;
}
