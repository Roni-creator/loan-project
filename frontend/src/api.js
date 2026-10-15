// Fetch helper for the Flask API.
//  * sends cookies (credentials: "include")
//  * attaches the per-session CSRF token to state-changing requests
//  * broadcasts 401s so the auth context can drop a dead session
const BASE = import.meta.env.VITE_API_BASE_URL || "";

let csrfToken = null;
export function setCsrfToken(token) { csrfToken = token || null; }
export function getCsrfToken() { return csrfToken; }

async function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;

  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Cannot reach the server. Is the Flask API running?");
  }

  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    window.dispatchEvent(new Event("auth:unauthorized"));
  }
  if (!res.ok) {
    const err = new Error(data.error || "Something went wrong. Please try again.");
    err.status = res.status;
    throw err;
  }
  return data;
}

export const apiGet = (path) => request("GET", path);
export const apiPost = (path, body = {}) => request("POST", path, body);
