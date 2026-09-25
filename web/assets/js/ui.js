/* Shared UI helpers: toasts, modals, formatting, small components. */
import { t, tStatus } from "./i18n.js";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function toast(message, kind = "") {
  const root = document.getElementById("toasts");
  const node = el("div", { class: `toast ${kind}` }, message);
  root.append(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transition = "opacity .3s";
    setTimeout(() => node.remove(), 320);
  }, 3200);
}

export function modal(contentNodes, { onClose } = {}) {
  const root = document.getElementById("modal-root");
  const box = el("div", { class: "modal soft-card" }, contentNodes);
  const close = () => {
    backdrop.remove();
    if (onClose) onClose();
  };
  const backdrop = el(
    "div",
    {
      class: "modal-backdrop",
      onclick: (e) => {
        if (e.target === backdrop) close();
      },
    },
    box,
  );
  root.append(backdrop);
  return { close, box };
}

export function fmtMoney(amount, currency = "UZS") {
  if (amount === null || amount === undefined) return t("not_available");
  try {
    return `${new Intl.NumberFormat("ru-RU").format(amount)} ${currency}`;
  } catch {
    return `${amount} ${currency}`;
  }
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function statusPill(status) {
  const map = {
    COMPLETED: "ok",
    PAID: "ok",
    FAILED: "err",
    REFUNDED: "warn",
    CANCELLED: "",
    PENDING_PAYMENT: "info",
    FULFILLMENT_PENDING: "info",
    SUPPLIER_PROCESSING: "info",
    PENDING: "info",
    PROCESSING: "info",
    AWAITING_STATUS: "info",
  };
  return el("span", { class: `pill ${map[status] || ""}` }, tStatus(status));
}

export function spinner(label) {
  return el("div", { class: "empty" }, el("div", { class: "big" }, "⏳"), label || t("loading"));
}

export function skeletonGrid(n = 6) {
  return el(
    "div",
    { class: "grid grid-auto" },
    Array.from({ length: n }, () => el("div", { class: "skeleton", style: "height:190px" })),
  );
}

export function emptyState(icon, title, sub) {
  return el(
    "div",
    { class: "empty" },
    el("div", { class: "big" }, icon),
    el("h3", {}, title),
    sub ? el("p", { class: "muted", style: "margin-top:6px" }, sub) : null,
  );
}

export function pager(page, pageSize, total, onPage) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return el("div");
  return el(
    "div",
    { class: "pager" },
    el("button", {
      class: "btn btn-soft btn-sm",
      disabled: page <= 1,
      onclick: () => onPage(page - 1),
    }, t("prev")),
    el("span", { class: "muted small" }, `${page} / ${pages}`),
    el("button", {
      class: "btn btn-soft btn-sm",
      disabled: page >= pages,
      onclick: () => onPage(page + 1),
    }, t("next")),
  );
}

export function withLoading(button, fn) {
  return async (...args) => {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "…";
    try {
      return await fn(...args);
    } catch (err) {
      toast(err.message || t("error_generic"), "err");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  };
}
