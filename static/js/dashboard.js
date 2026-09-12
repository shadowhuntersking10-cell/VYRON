/* User dashboard: overview, orders, notifications, donation page, telegram, profile, security. */
import { get, post, put, del, qs, toast, t, escapeHtml, fmtMoney, fmtDate, statusPill, emptyState, haptic, confirmDialog } from "/static/js/core.js";

const root = qs("#dash-root");
const section = root.dataset.section || "overview";

const card = (html) => `<div class="card">${html}</div>`;
const head = (title) => `<h1 class="section-title mb-3">${escapeHtml(title)}</h1>`;

/* ---------- overview ---------- */
async function renderOverview() {
  const [me, orders, donations] = await Promise.all([
    get("/api/auth/me"),
    get("/api/orders?page_size=5").catch(() => ({ data: { items: [] } })),
    get("/api/donations/me/page").catch(() => null),
  ]);
  const items = orders.data?.items || [];
  const stats = donations?.data?.stats || {};
  const completed = items.filter((o) => o.status === "COMPLETED").length;
  root.innerHTML = `
    ${head(t("dashboard.welcome", { name: me.data?.name || "" }))}
    <div class="admin-kpis mb-3">
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("dashboard.total_orders"))}</span><span class="value">${orders.data?.total ?? items.length}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("orders.status_COMPLETED"))}</span><span class="value">${completed}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("dashboard.donations_received"))}</span><span class="value">${escapeHtml(String(stats.received || "0.00"))}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">🔔 ${escapeHtml(t("dashboard.notifications"))}</span><span class="value" id="unread-count">…</span></div>`)}
    </div>
    ${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("dashboard.recent_orders"))}</h2>
      <div class="stack" style="gap:0.5rem" id="recent-orders"></div>
      <a class="btn btn-ghost btn-block mt-2" href="/dashboard/orders">${escapeHtml(t("common.see_all"))} →</a>`)}
    <div class="mt-3">${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("dashboard.quick_actions"))}</h2>
      <div class="row row-wrap">
        <a class="btn" href="/games">🎮 ${escapeHtml(t("nav.games"))}</a>
        <a class="btn" href="/marketplace">🛍️ ${escapeHtml(t("nav.marketplace"))}</a>
        <a class="btn" href="/donate/${escapeHtml(me.data?.username || "")}">💝 ${escapeHtml(t("donate.page_title"))}</a>
        <a class="btn" href="/support">✉️ ${escapeHtml(t("nav.support"))}</a>
      </div>`)}
    </div>`;

  const recent = qs("#recent-orders");
  if (!items.length) {
    emptyState(recent, "📦", t("orders.empty"), t("orders.empty_cta"));
  } else {
    recent.innerHTML = items.map(orderRow).join("");
    bindOrderRows(recent);
  }
  try {
    const unread = await get("/api/notifications?unread_only=true&page_size=1");
    qs("#unread-count").textContent = unread.unread ?? 0;
  } catch (_) { qs("#unread-count").textContent = "—"; }
}

function orderRow(order) {
  return `
  <div class="card-inset row spread" data-order="${escapeHtml(order.id)}" style="cursor:pointer;gap:0.8rem">
    <div style="min-width:0">
      <b class="mono fs-sm">${escapeHtml(order.number)}</b>
      <div class="text-mute fs-xs">${escapeHtml(fmtDate(order.created_at))} · ${order.items?.length || 0} ${escapeHtml(t("orders.items"))}</div>
    </div>
    <div class="row gap-sm">
      <span class="price">${escapeHtml(order.total)} ${escapeHtml(order.currency)}</span>
      ${statusPill(order.status)}
    </div>
  </div>`;
}

function bindOrderRows(container) {
  container.querySelectorAll("[data-order]").forEach((row) => {
    row.addEventListener("click", () => openOrder(row.dataset.order));
  });
}

/* ---------- orders ---------- */
let ordersPage = 1;
async function renderOrders() {
  root.innerHTML = `${head(t("orders.title"))}
    <div class="row row-wrap gap-sm mb-2" id="order-filters">
      <button class="chip active" data-status="">${escapeHtml(t("common.all"))}</button>
      ${["PAYMENT_PENDING", "PAID", "PROCESSING", "DELIVERING", "COMPLETED", "MANUAL_REVIEW", "REFUND_PENDING", "REFUNDED", "CANCELLED", "FAILED"]
        .map((s) => `<button class="chip" data-status="${s}">${escapeHtml(t(`orders.status_${s}`) !== `orders.status_${s}` ? t(`orders.status_${s}`) : s)}</button>`).join("")}
    </div>
    <div id="orders-list" class="stack" style="gap:0.6rem"></div>
    <div id="orders-pagination" class="pagination"></div>`;

  let status = "";
  const list = qs("#orders-list");

  async function load() {
    list.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
    const params = new URLSearchParams({ page: String(ordersPage), page_size: "10" });
    if (status) params.set("status", status);
    const res = await get(`/api/orders?${params}`);
    const items = res.data?.items || [];
    if (!items.length) {
      list.innerHTML = "";
      emptyState(list, "📦", t("orders.empty"), t("orders.empty_cta"));
      return;
    }
    list.innerHTML = items.map(orderRow).join("");
    bindOrderRows(list);
    renderPagination(res.data, (p) => { ordersPage = p; load(); });
  }

  qs("#order-filters").addEventListener("click", (event) => {
    const chip = event.target.closest(".chip");
    if (!chip) return;
    qs("#order-filters").querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    status = chip.dataset.status;
    ordersPage = 1;
    load();
  });
  await load();
}

function renderPagination(data, onGo) {
  const el = qs("#orders-pagination");
  if (!el || !data || data.pages <= 1) return;
  let html = `<button data-p="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>←</button>`;
  for (let p = 1; p <= data.pages; p++) html += `<button data-p="${p}" class="${p === data.page ? "active" : ""}">${p}</button>`;
  html += `<button data-p="${data.page + 1}" ${data.page >= data.pages ? "disabled" : ""}>→</button>`;
  el.innerHTML = html;
  el.addEventListener("click", (event) => { const p = Number(event.target.dataset?.p); if (p) onGo(p); });
}

async function openOrder(orderId) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop open";
  backdrop.innerHTML = `<div class="modal modal-lg"><div class="loading-overlay"><span class="spinner"></span></div></div>`;
  document.body.appendChild(backdrop);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });
  try {
    const res = await get(`/api/orders/${orderId}`);
    const order = res.data;
    const canCancel = ["CREATED", "PAYMENT_PENDING"].includes(order.status);
    const canRefund = ["COMPLETED", "PROCESSING", "DELIVERING", "PAID", "FAILED"].includes(order.status);
    const payment = order.timeline?.length ? order.timeline : [];
    backdrop.innerHTML = `
      <div class="modal modal-lg">
        <div class="modal-head">
          <div>
            <div class="modal-title mono">${escapeHtml(order.number)}</div>
            <div class="row gap-sm mt-1">${statusPill(order.status)}</div>
          </div>
          <button class="modal-close" data-close>✕</button>
        </div>
        ${order.status === "MANUAL_REVIEW" ? `<p class="card-inset fs-sm mb-2">🛡️ ${escapeHtml(t("orders.review_notice"))}</p>` : ""}
        ${order.status === "FAILED" ? `<p class="card-inset fs-sm mb-2">⚠️ ${escapeHtml(t("orders.failed_notice"))}</p>` : ""}
        <div class="stack" style="gap:0.5rem">
          ${order.items.map((item) => `
            <div class="card-inset row spread" style="gap:0.7rem">
              <div style="min-width:0">
                <b class="fs-sm">${escapeHtml(item.product_name)}</b>
                <div class="text-mute fs-xs">${escapeHtml(item.variant_name)} × ${item.quantity}</div>
                ${Object.entries(item.required_field_values || {}).map(([k, v]) => `<div class="fs-xs text-mute">${escapeHtml(k)}: <b>${escapeHtml(String(v))}</b></div>`).join("")}
              </div>
              <div class="text-right">
                <div class="price fs-sm">${escapeHtml(item.total)} ${escapeHtml(item.currency)}</div>
                <span class="badge badge-gray fs-xs">${escapeHtml(item.delivery_state || "")}</span>
              </div>
            </div>`).join("")}
        </div>
        <div class="soft-divider"></div>
        <div class="summary-line"><span>${escapeHtml(t("cart.subtotal"))}</span><span>${escapeHtml(order.subtotal)} ${escapeHtml(order.currency)}</span></div>
        ${Number(order.discount) > 0 ? `<div class="summary-line"><span>${escapeHtml(t("cart.discount"))}</span><span class="text-success">− ${escapeHtml(order.discount)}</span></div>` : ""}
        ${Number(order.service_fee) > 0 ? `<div class="summary-line"><span>${escapeHtml(t("cart.service_fee"))}</span><span>${escapeHtml(order.service_fee)}</span></div>` : ""}
        <div class="summary-line total"><span>${escapeHtml(t("cart.total"))}</span><span>${escapeHtml(order.total)} ${escapeHtml(order.currency)}</span></div>
        ${payment.length ? `
        <div class="soft-divider"></div>
        <h4 class="fw-800 fs-sm mb-1">${escapeHtml(t("orders.timeline"))}</h4>
        <div class="timeline">
          ${payment.map((step) => `
            <div class="timeline-item">
              <div class="rail"><span class="dot"></span><span class="line"></span></div>
              <div class="content"><b>${escapeHtml(step.to || "")}</b><span>${escapeHtml(fmtDate(step.at))}${step.reason ? ` · ${escapeHtml(step.reason)}` : ""}</span></div>
            </div>`).join("")}
        </div>` : ""}
        <div class="row mt-3 row-wrap">
          ${order.payment?.status === "PENDING" && order.payment?.checkout_url ? `<a class="btn btn-primary" href="${escapeHtml(order.payment.checkout_url)}">💳 ${escapeHtml(t("orders.pay_now"))}</a>` : ""}
          ${!order.payment?.checkout_url && ["CREATED", "PAYMENT_PENDING"].includes(order.status) ? `<button class="btn btn-primary" id="m-pay">💳 ${escapeHtml(t("orders.pay_now"))}</button>` : ""}
          ${canCancel ? `<button class="btn btn-danger" id="m-cancel">${escapeHtml(t("orders.cancel_order"))}</button>` : ""}
          ${canRefund ? `<button class="btn" id="m-refund">${escapeHtml(t("orders.request_refund"))}</button>` : ""}
        </div>
      </div>`;
    backdrop.querySelector("[data-close]").addEventListener("click", () => backdrop.remove());
    backdrop.querySelector("#m-pay")?.addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      btn.disabled = true;
      try {
        const providers = await get("/api/payment-providers");
        const provider = order.payment_provider || providers.data?.[0]?.name;
        if (!provider) throw new Error(t("errors.PAYMENT_PROVIDER_NOT_CONFIGURED"));
        const res = await post(`/api/orders/${order.id}/pay`, { provider });
        const url = res.data?.payment?.checkout_url;
        if (url) {
          toast(t("checkout.redirecting"), "info");
          window.location.href = url;
        } else {
          toast(t("orders.payment_pending"), "success");
          backdrop.remove();
          window.location.reload();
        }
      } catch (error) {
        toast(error.message, "error");
        btn.disabled = false;
      }
    });
    backdrop.querySelector("#m-cancel")?.addEventListener("click", async () => {
      if (!(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
      try {
        await post(`/api/orders/${order.id}/cancel`, { reason: "user" });
        toast(t("orders.cancel_order"), "success");
        backdrop.remove();
        window.location.reload();
      } catch (error) { toast(error.message, "error"); }
    });
    backdrop.querySelector("#m-refund")?.addEventListener("click", async () => {
      const reason = window.prompt(t("orders.refund_reason"));
      if (!reason) return;
      try {
        await post(`/api/orders/${order.id}/refund-request`, { reason });
        toast(t("orders.request_refund"), "success");
        backdrop.remove();
      } catch (error) { toast(error.message, "error"); }
    });
  } catch (error) {
    toast(error.message, "error");
    backdrop.remove();
  }
}

/* ---------- notifications ---------- */
async function renderNotifications() {
  root.innerHTML = `${head(t("dashboard.notifications"))}
    <div class="row spread mb-2">
      <span class="text-mute fs-sm" id="notif-unread"></span>
      <button class="btn btn-sm" id="mark-all">${escapeHtml(t("dashboard.mark_all_read"))}</button>
    </div>
    <div id="notif-list" class="stack" style="gap:0.6rem"></div>`;
  const list = qs("#notif-list");
  const res = await get("/api/notifications?page_size=50");
  const items = res.data?.items || [];
  qs("#notif-unread").textContent = `${res.unread ?? 0} unread`;
  if (!items.length) {
    emptyState(list, "🔔", t("dashboard.notifications_empty"), "");
  } else {
    list.innerHTML = items.map((n) => `
      <div class="card-inset row spread" data-notif="${escapeHtml(n.id)}" style="gap:0.8rem;${n.read ? "opacity:0.65" : ""}">
        <div style="min-width:0;flex:1">
          <b class="fs-sm">${escapeHtml(n.title)}</b>
          <div class="text-soft fs-xs">${escapeHtml(n.body || "")}</div>
          <div class="text-mute fs-xs">${escapeHtml(fmtDate(n.created_at))}</div>
        </div>
        <div class="row gap-sm">
          ${n.link ? `<a class="btn btn-sm" href="${escapeHtml(n.link)}">${escapeHtml(t("common.open"))}</a>` : ""}
          ${!n.read ? `<button class="btn btn-sm btn-ghost" data-read="${escapeHtml(n.id)}">✓</button>` : ""}
          <button class="btn btn-sm btn-ghost btn-danger" data-del="${escapeHtml(n.id)}">✕</button>
        </div>
      </div>`).join("");
    list.addEventListener("click", async (event) => {
      const readId = event.target.dataset?.read;
      const delId = event.target.dataset?.del;
      try {
        if (readId) { await post(`/api/notifications/${readId}/read`); renderNotifications(); }
        if (delId) { await del(`/api/notifications/${delId}`); renderNotifications(); }
      } catch (error) { toast(error.message, "error"); }
    });
  }
  qs("#mark-all").addEventListener("click", async () => {
    await post("/api/notifications/read-all");
    toast(t("toast.saved"), "success");
    renderNotifications();
  });
}

/* ---------- donation page ---------- */
async function renderDonations() {
  const res = await get("/api/donations/me/page").catch(() => null);
  const page = res?.data?.page || {};
  const stats = res?.data?.stats || {};
  root.innerHTML = `${head(t("donate.your_page"))}
    <div class="admin-kpis mb-3">
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("donate.raised_total"))}</span><span class="value">${escapeHtml(String(stats.received || "0.00"))}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">❤️</span><span class="value">${stats.count ?? 0}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("donate.goal"))}</span><span class="value">${escapeHtml(String(page.goal_amount || "—"))}</span></div>`)}
    </div>
    ${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("donate.page_settings"))}</h2>
      <div class="field"><label class="field-label">${escapeHtml(t("donate.page_title"))}</label>
        <input id="dp-title" class="input" maxlength="160" value="${escapeHtml(page.title || "")}"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("products.description"))}</label>
        <textarea id="dp-desc" class="textarea" maxlength="2000">${escapeHtml(page.description || "")}</textarea></div>
      <div class="field"><label class="field-label">${escapeHtml(t("donate.goal"))} (USD)</label>
        <input id="dp-goal" class="input" type="number" min="0" step="0.01" value="${escapeHtml(page.goal_amount || "")}"></div>
      <label class="row mb-2" style="gap:0.7rem;cursor:pointer">
        <span class="switch"><input id="dp-active" type="checkbox" ${page.active === false ? "" : "checked"}><span class="track"></span></span>
        <span class="fs-sm">${escapeHtml(t("common.status"))}: ACTIVE</span>
      </label>
      <button id="dp-save" class="btn btn-primary">${escapeHtml(t("common.save"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-1">🔗 /donate/${""}</h3>
      <a class="btn btn-block" id="dp-open" href="/donations" target="_blank">${escapeHtml(t("common.open"))} →</a>`)}
    </div>`;

  get("/api/auth/me").then((me) => {
    const link = qs("#dp-open");
    link.href = `/donate/${me.data.username}`;
    link.previousElementSibling.innerHTML = `🔗 /donate/${escapeHtml(me.data.username)}`;
  });

  qs("#dp-save").addEventListener("click", async () => {
    try {
      await put("/api/donations/me/page", {
        title: qs("#dp-title").value,
        description: qs("#dp-desc").value,
        goal_amount: qs("#dp-goal").value || null,
        active: qs("#dp-active").checked,
      });
      toast(t("donate.goal_updated"), "success");
      haptic("success");
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- telegram ---------- */
async function renderTelegram() {
  const me = await get("/api/auth/me");
  const connected = me.data?.telegram_connected;
  root.innerHTML = `${head(t("telegram_page.title"))}
    ${card(connected ? `
      <div class="row spread">
        <div><b>✈️ @${escapeHtml(me.data.telegram_username || "")}</b>
        <div class="text-mute fs-xs">${escapeHtml(t("telegram_page.connected"))}</div></div>
        <button class="btn btn-danger btn-sm" id="tg-unlink">${escapeHtml(t("telegram_page.disconnect"))}</button>
      </div>
      <p class="field-hint mt-2">${escapeHtml(t("telegram_page.notifications_note"))}</p>` : `
      <p class="text-soft mb-2">${escapeHtml(t("telegram_page.connect"))}</p>
      <button class="btn btn-primary" id="tg-generate">${escapeHtml(t("telegram_page.generate_link"))}</button>
      <div id="tg-token" class="mt-2"></div>`)}
    ${card(`<a class="btn btn-block" href="/miniapp">📱 ${escapeHtml(t("telegram_page.open_miniapp"))}</a>`)}
    <div class="stack mt-3"></div>`;

  qs("#tg-unlink")?.addEventListener("click", async () => {
    if (!(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
    try { await post("/api/auth/telegram/unlink"); toast(t("toast.saved"), "success"); renderTelegram(); }
    catch (error) { toast(error.message, "error"); }
  });

  qs("#tg-generate")?.addEventListener("click", async () => {
    try {
      const res = await get("/api/auth/telegram/link-token");
      qs("#tg-token").innerHTML = `
        <p class="fs-sm text-soft">${escapeHtml(t("telegram_page.link_instructions"))}</p>
        <div class="card-inset mono mt-1 row spread">/start ${escapeHtml(res.data.token)}
          <button class="btn btn-sm" id="tg-copy">${escapeHtml(t("common.copied").split(" ")[0] || "Copy")}</button></div>
        <p class="field-hint mt-1">${escapeHtml(t("telegram_page.token_expires"))}</p>`;
      qs("#tg-copy").addEventListener("click", () => {
        navigator.clipboard.writeText(`/start ${res.data.token}`);
        toast(t("toast.copied"), "success");
      });
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- profile ---------- */
async function renderProfile() {
  const me = await get("/api/auth/me");
  const u = me.data;
  root.innerHTML = `${head(t("dashboard.profile"))}
    ${card(`
      <div class="field"><label class="field-label">${escapeHtml(t("auth.name"))}</label>
        <input id="p-name" class="input" maxlength="120" value="${escapeHtml(u.name || "")}"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("auth.phone"))}</label>
        <input id="p-phone" class="input" maxlength="32" value="${escapeHtml(u.phone || "")}"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("auth.email"))}</label>
        <input class="input" value="${escapeHtml(u.email)}" disabled>
        ${u.email_verified ? "" : `<span class="field-hint text-danger">${escapeHtml(t("auth.verify_check"))}</span>`}</div>
      <div class="field"><label class="field-label">${escapeHtml(t("common.language"))}</label>
        <select id="p-locale" class="select">
          ${["uz", "en", "ru"].map((l) => `<option value="${l}" ${u.locale === l ? "selected" : ""}>${l.toUpperCase()}</option>`).join("")}
        </select></div>
      <div class="field"><label class="field-label">${escapeHtml(t("dashboard.avatar"))} URL</label>
        <div class="row gap-sm">
          <input id="p-avatar" class="input" maxlength="500" value="${escapeHtml(u.avatar_url || "")}">
          <label class="btn btn-sm" style="flex-shrink:0">⬆️
            <input id="p-avatar-file" type="file" accept="image/*" hidden>
          </label>
        </div></div>
      <button id="p-save" class="btn btn-primary">${escapeHtml(t("common.save"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-2">${escapeHtml(t("dashboard.preferences"))}</h3>
      <div class="field"><label class="field-label">${escapeHtml(t("common.theme"))}</label>
        <select id="p-theme" class="select">
          <option value="system" ${u.theme === "system" || !u.theme ? "selected" : ""}>${escapeHtml(t("common.theme_system"))}</option>
          <option value="light" ${u.theme === "light" ? "selected" : ""}>${escapeHtml(t("common.theme_light"))}</option>
          <option value="dark" ${u.theme === "dark" ? "selected" : ""}>${escapeHtml(t("common.theme_dark"))}</option>
        </select></div>`)}
    </div>`;

  qs("#p-avatar-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/uploads/image", { method: "POST", body: form, headers: { "X-CSRF-Token": (document.cookie.match(/vyron_csrf=([^;]+)/) || [])[1] || "" }, credentials: "same-origin" });
      const data = await res.json();
      if (!res.ok || data.success === false) throw new Error(data?.error?.message || "Upload failed");
      qs("#p-avatar").value = data.data.url;
      toast(t("toast.saved"), "success");
    } catch (error) { toast(error.message, "error"); }
  });

  qs("#p-save").addEventListener("click", async () => {
    try {
      await put("/api/users/me", {
        name: qs("#p-name").value,
        phone: qs("#p-phone").value,
        locale: qs("#p-locale").value,
        theme: qs("#p-theme").value,
        avatar_url: qs("#p-avatar").value || null,
      });
      toast(t("dashboard.profile_updated"), "success");
      haptic("success");
      setTimeout(() => window.location.reload(), 700);
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- security ---------- */
async function renderSecurity() {
  root.innerHTML = `${head(t("dashboard.security"))}
    ${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("dashboard.change_password"))}</h2>
      <div class="field"><label class="field-label">${escapeHtml(t("dashboard.current_password"))}</label>
        <input id="s-current" class="input" type="password" autocomplete="current-password"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("auth.new_password"))}</label>
        <input id="s-new" class="input" type="password" minlength="8" autocomplete="new-password">
        <span class="field-hint">${escapeHtml(t("auth.password_rules"))}</span></div>
      <div class="field"><label class="field-label">${escapeHtml(t("auth.confirm_password"))}</label>
        <input id="s-confirm" class="input" type="password" minlength="8" autocomplete="new-password"></div>
      <button id="s-save" class="btn btn-primary">${escapeHtml(t("common.save"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-1">${escapeHtml(t("dashboard.sessions"))}</h3>
      <p class="field-hint mb-2">HTTP-only · SameSite · Secure</p>
      <button id="s-revoke" class="btn btn-danger">${escapeHtml(t("dashboard.revoke_all"))}</button>`)}
    </div>`;

  qs("#s-save").addEventListener("click", async () => {
    try {
      await post("/api/auth/change-password", {
        current_password: qs("#s-current").value,
        new_password: qs("#s-new").value,
        confirm_password: qs("#s-confirm").value,
      });
      toast(t("dashboard.password_changed"), "success");
      qs("#s-current").value = qs("#s-new").value = qs("#s-confirm").value = "";
    } catch (error) { toast(error.message, "error"); }
  });

  qs("#s-revoke").addEventListener("click", async () => {
    if (!(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
    try {
      await post("/api/auth/logout-all");
      window.location.href = "/login";
    } catch (error) { toast(error.message, "error"); }
  });
}

const routes = {
  overview: renderOverview,
  orders: renderOrders,
  notifications: renderNotifications,
  donations: renderDonations,
  telegram: renderTelegram,
  profile: renderProfile,
  security: renderSecurity,
};

(async () => {
  try {
    await (routes[section] || renderOverview)();
  } catch (error) {
    root.innerHTML = card(`<div class="empty-state"><div class="icon">⛔</div><b>${escapeHtml(t("common.error_title"))}</b><span>${escapeHtml(error.message)}</span></div>`);
  }
})();
