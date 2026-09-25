/* VYRON API client — cookies are HttpOnly sessions; errors mapped to i18n keys. */
import { tError } from "./i18n.js";

async function request(path, options = {}) {
  const opts = {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("error_network");
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const detail = data?.detail;
    const err = new Error(tError(detail));
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body: body ?? {} }),
  patch: (path, body) => request(path, { method: "PATCH", body: body ?? {} }),
  put: (path, body) => request(path, { method: "PUT", body: body ?? {} }),
  del: (path) => request(path, { method: "DELETE" }),
};

export function tgInitData() {
  return window.Telegram?.WebApp?.initData || "";
}
