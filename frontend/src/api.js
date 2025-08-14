const base =
  process.env.REACT_APP_API_BASE_URL ||
  process.env.VITE_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:10000/api";

const getToken = () => localStorage.getItem("access_token");

export async function apiFetch(path, opts = {}) {
  const res = await fetch(`${base}${path.startsWith("/") ? path : "/"+path}`, {
    method: opts.method || "GET",
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      ...(opts.headers || {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) throw new Error((isJson && (data.detail || data.message)) || res.statusText);
  return data;
}

export const api = {
  get: (p) => apiFetch(p),
  post: (p, b) => apiFetch(p, { method: "POST", body: b }),
  put: (p, b) => apiFetch(p, { method: "PUT", body: b }),
  del: (p) => apiFetch(p, { method: "DELETE" }),
};
