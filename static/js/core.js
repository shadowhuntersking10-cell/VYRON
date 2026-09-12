/* VYRON core frontend: theme, language, API client (CSRF), toasts, UI helpers.
   Loaded as an ES module on every page. No frameworks. */

const THEME_KEY = "vyron_theme";
const LANG_COOKIE = "vyron_lang";

/* ---------- i18n ---------- */
export const I18N = JSON.parse(document.getElementById("i18n-bundle")?.textContent || "{}");

export function t(key, params) {
  let value = key.split(".").reduce((node, part) => (node && typeof node === "object" ? node[part] : undefined), I18N);
  if (typeof value !== "string") value = key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      value = value.replaceAll(`{${k}}`, String(v));
    }
  }
  return value;
}

export function currentLang() {
  return document.documentElement.lang || "uz";
}

export function setLang(lang) {
  document.cookie = `${LANG_COOKIE}=${lang};path=/;max-age=${86400 * 365};samesite=lax`;
  window.location.reload();
}

/* ---------- theme ---------- */
function mediaDark() {
  return window.matchMedia("(prefers-color-scheme: dark)");
}

export function applyTheme(theme) {
  const resolved = theme === "system" ? (mediaDark().matches ? "dark" : "light") : theme;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePref = theme;
}

export function initTheme() {
  const serverTheme = document.documentElement.dataset.themePref || "system";
  let theme = serverTheme;
  try {
    theme = localStorage.getItem(THEME_KEY) || serverTheme;
  } catch (_) { /* private mode */ }
  applyTheme(theme);
  mediaDark().addEventListener("change", () => {
    const current = getTheme();
    if (current === "system") applyTheme("system");
  });
}

export function getTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || document.documentElement.dataset.themePref || "system";
  } catch (_) {
    return document.documentElement.dataset.themePref || "system";
  }
}

export function cycleTheme() {
  const order = ["light", "dark", "system"];
  const next = order[(order.indexOf(getTheme()) + 1) % order.length];
  try { localStorage.setItem(THEME_KEY, next); } catch (_) {}
  document.cookie = `${THEME_KEY}=${next};path=/;max-age=${86400 * 365};samesite=lax`;
  applyTheme(next);
  toast(`${t(`common.theme_${next}`)}`, "info", 1600);
  return next;
}

/* ---------- toasts ---------- */
export function toastZone() {
  let zone = document.querySelector(".toast-zone");
  if (!zone) {
    zone = document.createElement("div");
    zone.className = "toast-zone";
    document.body.appendChild(zone);
  }
  return zone;
}

export function toast(message, kind = "info", ms = 3200) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  const icon = kind === "success" ? "✅" : kind === "error" ? "⛔" : "ℹ️";
  el.innerHTML = `<span>${icon}</span><span></span>`;
  el.lastElementChild.textContent = message;
  toastZone().appendChild(el);
  setTimeout(() => {
    el.classList.add("hide");
    setTimeout(() => el.remove(), 350);
  }, ms);
}

/* ---------- CSRF + API ---------- */
export function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)vyron_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

export async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (!["GET", "HEAD"].includes(method)) {
    headers["X-CSRF-Token"] = csrfToken();
  }
  let body = options.body;
  if (body !== undefined && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  const response = await fetch(path, { method, headers, body, credentials: "same-origin" });
  let data = null;
  try { data = await response.json(); } catch (_) { /* non-JSON */ }
  if (!response.ok || (data && data.success === false)) {
    const err = (data && data.error) || {};
    const error = new Error(err.message || `Request failed (${response.status})`);
    error.code = err.code || `HTTP_${response.status}`;
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

export const get = (path) => api(path);
export const post = (path, body) => api(path, { method: "POST", body });
export const put = (path, body) => api(path, { method: "PUT", body });
export const patch = (path, body) => api(path, { method: "PATCH", body });
export const del = (path) => api(path, { method: "DELETE" });

/* idempotency key helper — protects double-click buys */
export function idempotencyKey(prefix = "op") {
  const stored = sessionStorage.getItem(`idem:${prefix}`);
  if (stored) return stored;
  const key = `${prefix}-${crypto.randomUUID()}`;
  sessionStorage.setItem(`idem:${prefix}`, key);
  return key;
}
export function clearIdempotencyKey(prefix = "op") {
  sessionStorage.removeItem(`idem:${prefix}`);
}

/* ---------- UI helpers ---------- */
export function haptic(style = "light") {
  try {
    if (window.Telegram?.WebApp?.HapticFeedback) {
      const hf = window.Telegram.WebApp.HapticFeedback;
      if (style === "success" || style === "error" || style === "warning") {
        hf.notificationOccurred(style);
      } else {
        hf.impactOccurred(style);
      }
    }
  } catch (_) {}
}

export function qs(sel, root = document) { return root.querySelector(sel); }
export function qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; }

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function fmtMoney(value, currency = "USD") {
  const num = Number(value ?? 0);
  return `${num.toFixed(2)} ${currency}`;
}

export function fmtDate(iso, withTime = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const opts = { year: "numeric", month: "short", day: "numeric" };
  if (withTime) { opts.hour = "2-digit"; opts.minute = "2-digit"; }
  return d.toLocaleString(currentLang() === "uz" ? "uz-UZ" : currentLang() === "ru" ? "ru-RU" : "en-US", opts);
}

export function statusPill(status, ns = "orders") {
  const key = `${ns}.status_${status}`;
  const translated = t(key);
  const label = translated === key ? String(status).replaceAll("_", " ").toLowerCase() : translated;
  return `<span class="status-pill st-${escapeHtml(status)}">${escapeHtml(label)}</span>`;
}

export function skeletonCards(container, count = 4, cls = "") {
  container.innerHTML = Array.from({ length: count }, () =>
    `<div class="card ${cls}"><div class="skeleton" style="height:120px"></div><div class="skeleton mt-2" style="height:16px;width:70%"></div><div class="skeleton mt-1" style="height:14px;width:45%"></div></div>`
  ).join("");
}

export function emptyState(container, icon, title, subtitle = "") {
  container.innerHTML = `<div class="empty-state"><div class="icon">${icon}</div><b>${escapeHtml(title)}</b><span>${escapeHtml(subtitle)}</span></div>`;
}

export async function confirmDialog(message, { title = "", confirmLabel = "", danger = false } = {}) {
  return new Promise((resolve) => {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop open";
    backdrop.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head"><div class="modal-title">${escapeHtml(title || t("common.confirm"))}</div></div>
        <p class="text-soft mb-3">${escapeHtml(message)}</p>
        <div class="row" style="justify-content:flex-end">
          <button class="btn" data-act="cancel">${escapeHtml(t("common.cancel"))}</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-act="ok">${escapeHtml(confirmLabel || t("common.confirm"))}</button>
        </div>
      </div>`;
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", (event) => {
      const act = event.target.dataset?.act;
      if (act === "ok") { resolve(true); backdrop.remove(); }
      else if (act === "cancel" || event.target === backdrop) { resolve(false); backdrop.remove(); }
    });
  });
}

/* ---------- header wiring (theme/lang/menu/cart badge) ---------- */
export async function initHeader() {
  initTheme();

  qs("#theme-toggle")?.addEventListener("click", () => {
    cycleTheme();
    haptic("light");
  });

  const langSelect = qs("#lang-select");
  if (langSelect) {
    langSelect.value = currentLang();
    langSelect.addEventListener("change", () => setLang(langSelect.value));
  }

  qs("#burger")?.addEventListener("click", () => {
    qs("#main-nav")?.classList.toggle("open");
    haptic("light");
  });

  const menuBtn = qs("#user-menu-btn");
  const menu = qs("#user-menu");
  if (menuBtn && menu) {
    menuBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      menu.classList.toggle("open");
    });
    document.addEventListener("click", () => menu.classList.remove("open"));
  }

  if (document.body.dataset.user === "1") {
    refreshBadges();
    setInterval(refreshBadges, 45000);
  }
}

async function refreshBadges() {
  try {
    const [cart, notifications] = await Promise.all([
      get("/api/cart").catch(() => null),
      get("/api/notifications?unread_only=true&page_size=1").catch(() => null),
    ]);
    const cartDot = qs("#cart-dot");
    if (cartDot) {
      const count = cart?.data?.items?.length || 0;
      cartDot.textContent = count;
      cartDot.classList.toggle("hidden", count === 0);
    }
    const bellDot = qs("#bell-dot");
    if (bellDot) {
      const unread = notifications?.unread || 0;
      bellDot.textContent = unread > 99 ? "99+" : unread;
      bellDot.classList.toggle("hidden", unread === 0);
    }
  } catch (_) { /* silent */ }
}

export function bindSearch() {
  const input = qs("#site-search");
  if (!input) return;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const q = input.value.trim();
      window.location.href = q ? `/search?q=${encodeURIComponent(q)}` : "/search";
    }
  });
}

/* auto-init on every page */
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { initHeader(); bindSearch(); });
} else {
  initHeader(); bindSearch();
}
