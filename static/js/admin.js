/* VYRON admin panel — all sections rendered client-side from /api/admin/* (role-gated server-side). */
import { get, post, put, del, qs, toast, t, escapeHtml, fmtMoney, fmtDate, statusPill, emptyState, haptic, confirmDialog } from "/static/js/core.js";

const root = qs("#admin-root");
const section = root.dataset.section || "dashboard";
const card = (html, cls = "") => `<div class="card ${cls}">${html}</div>`;
const head = (title, extra = "") => `<div class="row spread mb-3 row-wrap"><h1 class="section-title">${escapeHtml(title)}</h1><div class="row gap-sm">${extra}</div></div>`;

function kpi(label, value, sub = "") {
  return card(`<div class="stat-card"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(String(value))}</span>${sub ? `<span class="delta">${escapeHtml(sub)}</span>` : ""}</div>`);
}

function table(headers, rows, responsive = true) {
  if (!rows.length) return `<div class="empty-state"><div class="icon">🗂</div><b>${escapeHtml(t("common.empty_title"))}</b><span>${escapeHtml(t("common.empty_text"))}</span></div>`;
  return `<div class="table-wrap card" style="padding:0.4rem 0.8rem"><table class="table ${responsive ? "table-responsive" : ""}">
    <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((cells) => `<tr>${cells.map((c, i) => `<td data-label="${escapeHtml(headers[i] || "")}">${c}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

function paginationEl(data, onGo) {
  const el = document.createElement("div");
  el.className = "pagination";
  if (!data || data.pages <= 1) return el;
  let html = `<button data-p="${data.page - 1}" ${data.page <= 1 ? "disabled" : ""}>←</button>`;
  const from = Math.max(1, data.page - 2), to = Math.min(data.pages, from + 4);
  for (let p = from; p <= to; p++) html += `<button data-p="${p}" class="${p === data.page ? "active" : ""}">${p}</button>`;
  html += `<button data-p="${data.page + 1}" ${data.page >= data.pages ? "disabled" : ""}>→</button>`;
  el.innerHTML = html;
  el.addEventListener("click", (e) => { const p = Number(e.target.dataset?.p); if (p) onGo(p); });
  return el;
}

function modal(html, { large = false } = {}) {
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop open";
  backdrop.innerHTML = `<div class="modal ${large ? "modal-lg" : ""}">${html}</div>`;
  document.body.appendChild(backdrop);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop || e.target.dataset?.close !== undefined) backdrop.remove(); });
  return backdrop;
}

/* ---------- tiny canvas charts (no libraries) ---------- */
function drawChart(canvas, series, { color = "#3b82f6", fill = true, money = false } = {}) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height, PAD = 34;
  const values = series.map((s) => Number(s.value) || 0);
  const max = Math.max(...values, 1);
  ctx.clearRect(0, 0, W, H);
  const style = getComputedStyle(document.documentElement);
  const grid = style.getPropertyValue("--border").trim() || "rgba(0,0,0,0.1)";
  const text = style.getPropertyValue("--text-mute").trim() || "#888";
  ctx.strokeStyle = grid; ctx.fillStyle = text; ctx.font = "10px sans-serif"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = PAD / 2 + ((H - PAD) / 4) * i;
    ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(W - 6, y); ctx.stroke();
    const v = max - (max / 4) * i;
    ctx.fillText(money ? v.toFixed(0) : String(Math.round(v)), 2, y + 3);
  }
  if (series.length < 2) return;
  const stepX = (W - PAD - 10) / (series.length - 1);
  const pointX = (i) => PAD + i * stepX;
  const pointY = (v) => PAD / 2 + (H - PAD) * (1 - v / max);
  if (fill) {
    ctx.beginPath();
    ctx.moveTo(pointX(0), pointY(values[0]));
    values.forEach((v, i) => ctx.lineTo(pointX(i), pointY(v)));
    ctx.lineTo(pointX(values.length - 1), H - PAD / 2);
    ctx.lineTo(pointX(0), H - PAD / 2);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, `${color}55`); grad.addColorStop(1, `${color}05`);
    ctx.fillStyle = grad; ctx.fill();
  }
  ctx.beginPath();
  values.forEach((v, i) => (i === 0 ? ctx.moveTo(pointX(i), pointY(v)) : ctx.lineTo(pointX(i), pointY(v))));
  ctx.strokeStyle = color; ctx.lineWidth = 2.4; ctx.lineJoin = "round"; ctx.stroke();
  values.forEach((v, i) => {
    ctx.beginPath(); ctx.arc(pointX(i), pointY(v), 2.6, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.fill();
  });
  const first = series[0]?.day || "", last = series[series.length - 1]?.day || "";
  ctx.fillStyle = text;
  ctx.fillText(first, PAD, H - 8);
  ctx.fillText(last, W - 60, H - 8);
}

function chartCard(title, id, money = false) {
  return card(`<h3 class="fw-800 fs-sm mb-1">${escapeHtml(title)}</h3><div class="chart-box"><canvas id="${id}"></canvas></div>`, "");
}

/* ================= DASHBOARD ================= */
async function renderDashboard() {
  const days = 30;
  const [stats, charts, queues] = await Promise.all([
    get(`/api/admin/stats?days=${days}`),
    get(`/api/admin/charts?days=${days}`),
    get("/api/admin/queue-health").catch(() => ({ data: { queues: [] } })),
  ]);
  const s = stats.data;
  root.innerHTML = `
    ${head(t("admin.dashboard"), `<span class="badge">${escapeHtml(t("admin.range_30"))}</span>`)}
    <div class="admin-kpis mb-3">
      ${kpi(t("admin.stat_revenue"), s.revenue?.gross || "0.00", `${t("admin.net_revenue")}: ${s.revenue?.net || "0.00"}`)}
      ${kpi(t("admin.stat_orders"), s.orders_total, `${s.orders_completed} ✓ · ${s.orders_review} ⚠️`)}
      ${kpi(t("admin.stat_users"), s.users_total, `+${s.users_new} /30d`)}
      ${kpi(t("admin.stat_sellers"), s.sellers_total, `${s.listings_pending} ⏳`)}
      ${kpi(t("admin.stat_donations"), s.donations_total, `${s.donations_count} donations`)}
      ${kpi(t("admin.stat_failed_payments"), s.payments_failed, `${s.payments_pending} pending`)}
      ${kpi(t("admin.stat_supplier_errors"), s.supplier_errors)}
      ${kpi(t("admin.stat_fraud_alerts"), s.fraud_alerts, `${s.payout_requests} payouts · ${s.tickets_open} tickets`)}
    </div>
    <div class="grid grid-2 mb-3">
      ${chartCard(t("admin.chart_daily_revenue"), "ch-revenue", true)}
      ${chartCard(t("admin.chart_orders"), "ch-orders")}
      ${chartCard(t("admin.chart_new_users"), "ch-users")}
      ${chartCard(t("admin.chart_donations"), "ch-donations", true)}
    </div>
    ${card(`<h3 class="fw-800 mb-2">${escapeHtml(t("admin.queue_health"))}</h3>
      ${table(["Queue", t("admin.queue_depth"), t("admin.dlq"), "Redis"],
        (queues.data?.queues || []).map((q) => [`<b class="mono">${escapeHtml(q.name)}</b>`, q.depth, q.dlq > 0 ? `<span class="text-danger">${q.dlq}</span>` : "0", ""]), false)}
      <div class="mt-1">${queues.data?.redis ? '<span class="badge badge-green">redis ✓</span>' : '<span class="badge badge-red">redis ✗</span>'}</div>`)}
    <div class="mt-3 row row-wrap">
      <a class="btn" href="/admin/orders?status=MANUAL_REVIEW">🛡️ ${escapeHtml(t("admin.order_force_review"))} (${s.orders_review})</a>
      <a class="btn" href="/admin/listings">🏷️ ${escapeHtml(t("admin.listings"))} (${s.listings_pending})</a>
      <a class="btn" href="/admin/payouts">🏦 ${escapeHtml(t("admin.payouts"))} (${s.payout_requests})</a>
    </div>`;
  requestAnimationFrame(() => {
    drawChart(qs("#ch-revenue"), charts.data.daily_revenue || [], { money: true });
    drawChart(qs("#ch-orders"), charts.data.daily_orders || [], { color: "#34d399" });
    drawChart(qs("#ch-users"), charts.data.daily_new_users || [], { color: "#a78bfa" });
    drawChart(qs("#ch-donations"), charts.data.daily_donations || [], { color: "#f5b942", money: true });
  });
}

/* ================= REVENUE ================= */
const revenueState = { days: 30, start: "", end: "" };
function revenueParams() {
  const p = new URLSearchParams();
  if (revenueState.start && revenueState.end) { p.set("start", revenueState.start); p.set("end", revenueState.end); }
  else p.set("days", String(revenueState.days));
  return p;
}
async function renderRevenue() {
  root.innerHTML = `
    ${head(t("admin.revenue"))}
    <div class="admin-toolbar">
      ${[[1, "admin.range_today"], [7, "admin.range_7"], [30, "admin.range_30"], [90, "admin.range_90"]].map(([d, key]) =>
        `<button class="chip ${revenueState.days === d && !revenueState.start ? "active" : ""}" data-days="${d}">${escapeHtml(t(key))}</button>`).join("")}
      <input type="date" id="rv-start" class="input" style="width:auto">
      <input type="date" id="rv-end" class="input" style="width:auto">
      <button class="btn btn-sm" id="rv-custom">${escapeHtml(t("admin.range_custom"))}</button>
    </div>
    <div id="rv-summary" class="admin-kpis mb-3"></div>
    <div class="grid grid-2 mb-3">
      ${chartCard(t("admin.chart_daily_revenue"), "rv-gross", true)}
      ${chartCard(t("admin.margin"), "rv-margin", true)}
    </div>
    <div id="rv-streams" class="mb-3"></div>
    <div class="grid grid-2">
      <div id="rv-games"></div>
      <div id="rv-products"></div>
    </div>`;

  async function load() {
    const params = revenueParams();
    const [summary, series, games, products] = await Promise.all([
      get(`/api/admin/revenue/summary?${params}`),
      get(`/api/admin/revenue/series?${params}`),
      get(`/api/admin/revenue/by-game?${params}`),
      get(`/api/admin/revenue/by-product?${params}`),
    ]);
    const s = summary.data.summary || {};
    const kpis = [
      ["admin.gross_revenue", s.gross || "0.00"],
      ["admin.platform_revenue", s.platform_revenue || s.commissions || "0.00"],
      ["admin.supplier_costs", s.supplier_costs || "0.00"],
      ["admin.payment_fees", s.payment_fees || "0.00"],
      ["admin.seller_payouts", s.payouts || "0.00"],
      ["admin.refunds_total", s.refunds || "0.00"],
      ["admin.net_revenue", s.net || "0.00"],
    ];
    qs("#rv-summary").innerHTML = kpis.map(([key, v]) => kpi(t(key) === key ? key : t(key), v)).join("");
    qs("#rv-streams").innerHTML = card(`<h3 class="fw-800 mb-2">${escapeHtml(t("admin.by_stream"))}</h3>` +
      table([t("admin.by_stream"), "USD"], (summary.data.streams || []).map((r) => [
        `<b>${escapeHtml(t(`admin.stream_${r.stream}`) !== `admin.stream_${r.stream}` ? t(`admin.stream_${r.stream}`) : r.stream)}</b>`,
        `<span class="${r.stream === "REFUND" ? "text-danger" : ""}">${escapeHtml(String(r.amount ?? r.total ?? ""))}</span>`,
      ]), false));
    qs("#rv-games").innerHTML = card(`<h3 class="fw-800 mb-2">🎮 ${escapeHtml(t("admin.by_game"))}</h3>` +
      table(["Game", t("admin.gross_revenue"), t("admin.margin")], (games.data || []).map((r) => [
        escapeHtml(r.game || r.name || "—"), escapeHtml(String(r.gross ?? "")), escapeHtml(String(r.margin ?? r.net ?? "")),
      ]), false));
    qs("#rv-products").innerHTML = card(`<h3 class="fw-800 mb-2">📦 ${escapeHtml(t("admin.by_product"))}</h3>` +
      table([t("admin.products"), t("admin.gross_revenue"), t("admin.supplier_costs"), t("admin.margin")], (products.data || []).map((r) => [
        escapeHtml(r.product || r.name || "—"), escapeHtml(String(r.gross ?? "")), escapeHtml(String(r.cost ?? r.supplier_cost ?? "")), escapeHtml(String(r.margin ?? "")),
      ]), false));
    requestAnimationFrame(() => {
      drawChart(qs("#rv-gross"), series.data.gross || [], { money: true });
      drawChart(qs("#rv-margin"), series.data.margin || [], { color: "#34d399", money: true });
    });
  }

  root.querySelectorAll("[data-days]").forEach((chip) => chip.addEventListener("click", () => {
    root.querySelectorAll("[data-days]").forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    revenueState.days = Number(chip.dataset.days);
    revenueState.start = revenueState.end = "";
    load();
  }));
  qs("#rv-custom").addEventListener("click", () => {
    revenueState.start = qs("#rv-start").value; revenueState.end = qs("#rv-end").value;
    if (!revenueState.start || !revenueState.end) { toast(t("common.from") + " / " + t("common.to"), "error"); return; }
    root.querySelectorAll("[data-days]").forEach((c) => c.classList.remove("active"));
    load();
  });
  await load();
}

/* ================= ORDERS ================= */
async function renderOrders() {
  const params = new URLSearchParams(window.location.search);
  let status = params.get("status") || "";
  let page = 1, query = "";
  root.innerHTML = `${head(t("admin.orders"))}
    <div class="admin-toolbar">
      <input id="od-q" class="input" placeholder="VYR-… / username">
      <select id="od-status" class="select">
        <option value="">${escapeHtml(t("common.all"))}</option>
        ${["CREATED", "PAYMENT_PENDING", "PAID", "PROCESSING", "DELIVERING", "COMPLETED", "MANUAL_REVIEW", "FAILED", "REFUND_PENDING", "REFUNDED", "CANCELLED"].map((s) =>
          `<option value="${s}" ${status === s ? "selected" : ""}>${s}</option>`).join("")}
      </select>
    </div>
    <div id="od-list"></div><div id="od-pages"></div>`;

  async function load() {
    const p = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) p.set("status", status);
    if (query) p.set("q", query);
    const res = await get(`/api/admin/orders?${p}`);
    const items = res.data?.items || [];
    qs("#od-list").innerHTML = table(
      ["#", t("common.status"), "User", t("orders.total"), t("admin.risk_score"), t("common.created_at"), ""],
      items.map((o) => [
        `<b class="mono">${escapeHtml(o.number)}</b>`,
        statusPill(o.status),
        escapeHtml(o.user?.username || "—"),
        `<b>${escapeHtml(o.total)} ${escapeHtml(o.currency)}</b>`,
        o.risk_score != null ? `<span class="${o.risk_score >= 70 ? "text-danger" : o.risk_score >= 40 ? "text-mute" : "text-success"}">${o.risk_score}</span>` : "—",
        escapeHtml(fmtDate(o.created_at)),
        `<button class="btn btn-sm" data-open="${escapeHtml(o.id)}">${escapeHtml(t("common.view"))}</button>`,
      ]));
    const pages = qs("#od-pages"); pages.innerHTML = ""; pages.appendChild(paginationEl(res.data, (p2) => { page = p2; load(); }));
    qs("#od-list").querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openOrderAdmin(b.dataset.open)));
  }
  qs("#od-status").addEventListener("change", (e) => { status = e.target.value; page = 1; load(); });
  let deb; qs("#od-q").addEventListener("input", (e) => { clearTimeout(deb); deb = setTimeout(() => { query = e.target.value.trim(); page = 1; load(); }, 350); });
  await load();
}

async function openOrderAdmin(orderId) {
  const m = modal(`<div class="loading-overlay"><span class="spinner"></span></div>`, { large: true });
  try {
    const res = await get(`/api/admin/orders/${orderId}`);
    const o = res.data;
    m.querySelector(".modal").innerHTML = `
      <div class="modal-head">
        <div><div class="modal-title mono">${escapeHtml(o.number)}</div><div class="mt-1">${statusPill(o.status)} <span class="badge badge-gray">${escapeHtml(o.risk_level || "")} ${o.risk_score ?? ""}</span></div></div>
        <button class="modal-close" data-close>✕</button>
      </div>
      <dl class="kv mb-2">
        <dt>User</dt><dd>${escapeHtml(o.user?.username || "—")} (${escapeHtml(o.user?.email || "")})</dd>
        <dt>${escapeHtml(t("orders.total"))}</dt><dd>${escapeHtml(fmtMoney(o.total, o.currency))}</dd>
        <dt>${escapeHtml(t("admin.supplier_costs"))}</dt><dd>${escapeHtml(String(o.supplier_cost_total || "0.00"))}</dd>
        <dt>${escapeHtml(t("orders.payment_provider"))}</dt><dd>${escapeHtml(o.payment_provider || "—")}</dd>
        <dt>IP</dt><dd class="mono">${escapeHtml(o.ip_address || "—")}</dd>
        ${o.failure_reason ? `<dt>⚠️</dt><dd class="text-danger">${escapeHtml(o.failure_reason)}</dd>` : ""}
      </dl>
      <h4 class="fw-800 fs-sm mb-1">${escapeHtml(t("orders.items"))}</h4>
      ${table(["Item", "Qty", "Total", "Delivery", ""], o.items.map((i) => [
        `<b>${escapeHtml(i.product_name)}</b><div class="fs-xs text-mute">${escapeHtml(i.variant_name || "")}</div>`,
        i.quantity, `${escapeHtml(i.total)} ${escapeHtml(i.currency)}`,
        `<span class="badge">${escapeHtml(i.delivery_state || "—")}</span>`,
        `<button class="btn btn-sm" data-retry="${escapeHtml(i.id)}">↻</button>`,
      ]), false)}
      ${o.supplier_orders?.length ? `<h4 class="fw-800 fs-sm mt-2 mb-1">${escapeHtml(t("admin.suppliers"))}</h4>
      ${table(["Supplier", "External", t("common.status"), "Cost", "Error"], o.supplier_orders.map((so) => [
        escapeHtml(so.supplier || "—"), `<span class="mono fs-xs">${escapeHtml(so.external_order_id || "—")}</span>`,
        statusPill(so.status, "seller"), escapeHtml(String(so.cost ?? "—")), `<span class="fs-xs text-danger">${escapeHtml((so.last_error || "").slice(0, 60))}</span>`,
      ]), false)}` : ""}
      ${o.payments?.length ? `<h4 class="fw-800 fs-sm mt-2 mb-1">${escapeHtml(t("admin.payments"))}</h4>
      ${table(["Provider", "Amount", t("common.status"), t("common.created_at")], o.payments.map((p) => [
        escapeHtml(p.provider), `${escapeHtml(p.amount)} ${escapeHtml(p.currency)}`, statusPill(p.status, "seller"), escapeHtml(fmtDate(p.created_at)),
      ]), false)}` : ""}
      <div class="row mt-3 row-wrap">
        ${o.status === "MANUAL_REVIEW" ? `<button class="btn btn-primary" id="oa-approve">✅ ${escapeHtml(t("admin.order_force_review"))}</button>` : ""}
        ${!["COMPLETED", "REFUNDED", "CANCELLED"].includes(o.status) ? `<button class="btn btn-danger" id="oa-cancel">${escapeHtml(t("admin.order_cancel"))}</button>` : ""}
        <a class="btn" href="/admin/revenue" id="oa-profit">💹 ${escapeHtml(t("admin.profitability"))}</a>
      </div>`;
    m.querySelectorAll("[data-retry]").forEach((b) => b.addEventListener("click", async () => {
      try { const r = await post(`/api/admin/orders/${o.id}/items/${b.dataset.retry}/retry`); toast(`→ ${r.data?.delivery_state}`, "success"); openOrderAdmin(o.id); m.remove(); }
      catch (e) { toast(e.message, "error"); }
    }));
    m.querySelector("#oa-approve")?.addEventListener("click", async () => {
      const note = window.prompt("Note") || "";
      try { await post(`/api/admin/orders/${o.id}/approve-review`, { note }); toast(t("toast.saved"), "success"); m.remove(); renderOrders(); }
      catch (e) { toast(e.message, "error"); }
    });
    m.querySelector("#oa-cancel")?.addEventListener("click", async () => {
      const reason = window.prompt(t("admin.order_cancel")) || "";
      if (!(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
      try { await post(`/api/admin/orders/${o.id}/cancel`, { reason }); toast(t("toast.saved"), "success"); m.remove(); renderOrders(); }
      catch (e) { toast(e.message, "error"); }
    });
    m.querySelector("#oa-profit")?.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const r = await get(`/api/admin/revenue/order/${o.id}`);
        const d = r.data || {};
        modal(`<div class="modal-head"><div class="modal-title">💹 ${escapeHtml(t("admin.profitability"))} · ${escapeHtml(o.number)}</div><button class="modal-close" data-close>✕</button></div>
          <dl class="kv">${Object.entries(d).map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(String(v))}</dd>`).join("")}</dl>`);
      } catch (err) { toast(err.message, "error"); }
    });
  } catch (error) {
    m.remove();
    toast(error.message, "error");
  }
}

/* ================= USERS ================= */
async function renderUsers() {
  let page = 1, query = "", role = "", status = "";
  root.innerHTML = `${head(t("admin.users"))}
    <div class="admin-toolbar">
      <input id="us-q" class="input" placeholder="username / email / name">
      <select id="us-role" class="select"><option value="">${escapeHtml(t("common.all"))}</option>
        ${["USER", "SELLER", "SUPPORT", "MODERATOR", "FINANCE", "ADMIN", "SUPER_ADMIN"].map((r) => `<option>${r}</option>`).join("")}</select>
      <select id="us-status" class="select"><option value="">${escapeHtml(t("common.all"))}</option>
        ${["ACTIVE", "DISABLED", "SUSPENDED"].map((s) => `<option>${s}</option>`).join("")}</select>
    </div>
    <div id="us-list"></div><div id="us-pages"></div>`;
  async function load() {
    const p = new URLSearchParams({ page: String(page), page_size: "20" });
    if (query) p.set("q", query); if (role) p.set("role", role); if (status) p.set("status", status);
    const res = await get(`/api/admin/users?${p}`);
    qs("#us-list").innerHTML = table(
      ["User", "Email", t("admin.role_USER") && "Role", t("common.status"), "Risk", t("common.created_at"), ""],
      (res.data?.items || []).map((u) => [
        `<b>${escapeHtml(u.username)}</b><div class="fs-xs text-mute">${escapeHtml(u.name || "")}</div>`,
        escapeHtml(u.email),
        `<span class="badge">${escapeHtml(t(`admin.role_${u.role}`) !== `admin.role_${u.role}` ? t(`admin.role_${u.role}`) : u.role)}</span>`,
        statusPill(u.status, "seller"),
        u.fraud_risk_score ?? "—",
        escapeHtml(fmtDate(u.created_at, false)),
        `<button class="btn btn-sm" data-open="${escapeHtml(u.id)}">${escapeHtml(t("common.view"))}</button>`,
      ]));
    const pages = qs("#us-pages"); pages.innerHTML = ""; pages.appendChild(paginationEl(res.data, (p2) => { page = p2; load(); }));
    qs("#us-list").querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openUser(b.dataset.open, load)));
  }
  qs("#us-role").addEventListener("change", (e) => { role = e.target.value; page = 1; load(); });
  qs("#us-status").addEventListener("change", (e) => { status = e.target.value; page = 1; load(); });
  let deb; qs("#us-q").addEventListener("input", (e) => { clearTimeout(deb); deb = setTimeout(() => { query = e.target.value.trim(); page = 1; load(); }, 350); });
  await load();
}

async function openUser(userId, reload) {
  const m = modal(`<div class="loading-overlay"><span class="spinner"></span></div>`, { large: true });
  try {
    const res = await get(`/api/admin/users/${userId}`);
    const u = res.data.user;
    m.querySelector(".modal").innerHTML = `
      <div class="modal-head">
        <div><div class="modal-title">👤 ${escapeHtml(u.username)}</div><div class="fs-xs text-mute">${escapeHtml(u.email)} · ${escapeHtml(u.role)} · ${escapeHtml(u.status)}</div></div>
        <button class="modal-close" data-close>✕</button>
      </div>
      <div class="row gap-sm row-wrap mb-2">
        ${u.status === "ACTIVE"
          ? `<button class="btn btn-danger btn-sm" data-status="DISABLED">${escapeHtml(t("admin.disable_user"))}</button>
             <button class="btn btn-sm" data-status="SUSPENDED">SUSPEND</button>`
          : `<button class="btn btn-primary btn-sm" data-status="ACTIVE">${escapeHtml(t("admin.restore_user"))}</button>`}
        <select id="u-role" class="select" style="width:auto">
          ${["USER", "SELLER", "SUPPORT", "MODERATOR", "FINANCE", "ADMIN", "SUPER_ADMIN"].map((r) => `<option ${u.role === r ? "selected" : ""}>${r}</option>`).join("")}
        </select>
        <button class="btn btn-sm" id="u-role-save">${escapeHtml(t("admin.change_role"))}</button>
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="orders">${escapeHtml(t("admin.view_orders"))}</button>
        <button class="tab" data-tab="payments">${escapeHtml(t("admin.payment_history"))}</button>
        <button class="tab" data-tab="fraud">${escapeHtml(t("admin.fraud_events"))}</button>
        <button class="tab" data-tab="audit">${escapeHtml(t("admin.audit_trail"))}</button>
      </div>
      <div id="u-tab-body"></div>`;
    const body = m.querySelector("#u-tab-body");
    const tabs = {
      orders: () => table(["#", t("common.status"), t("orders.total"), t("common.created_at")], (res.data.orders || []).map((o) => [
        `<b class="mono">${escapeHtml(o.number)}</b>`, statusPill(o.status), `${escapeHtml(o.total)} ${escapeHtml(o.currency)}`, escapeHtml(fmtDate(o.created_at))])),
      payments: () => table(["Provider", "Amount", t("common.status"), t("common.created_at")], (res.data.payments || []).map((p) => [
        escapeHtml(p.provider), `${escapeHtml(p.amount)} ${escapeHtml(p.currency)}`, statusPill(p.status, "seller"), escapeHtml(fmtDate(p.created_at))])),
      fraud: () => table([t("admin.risk_score"), "Level", "Type", t("common.created_at")], (res.data.fraud_events || []).map((f) => [
        f.risk_score, `<span class="badge">${escapeHtml(t(`admin.level_${f.level}`) !== `admin.level_${f.level}` ? t(`admin.level_${f.level}`) : f.level)}</span>`, escapeHtml(f.type), escapeHtml(fmtDate(f.created_at))])),
      audit: () => table(["Action", "Entity", t("common.created_at")], (res.data.audit_logs || []).map((a) => [
        `<span class="mono fs-xs">${escapeHtml(a.action)}</span>`, escapeHtml(a.entity_type || "—"), escapeHtml(fmtDate(a.created_at))])),
    };
    const showTab = (name) => { body.innerHTML = tabs[name](); };
    m.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
      m.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active"); showTab(tab.dataset.tab);
    }));
    showTab("orders");
    m.querySelectorAll("[data-status]").forEach((b) => b.addEventListener("click", async () => {
      if (b.dataset.status !== "ACTIVE" && !(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
      try { await post(`/api/admin/users/${u.id}/status`, { status: b.dataset.status }); toast(t("toast.saved"), "success"); m.remove(); reload(); }
      catch (e) { toast(e.message, "error"); }
    }));
    m.querySelector("#u-role-save").addEventListener("click", async () => {
      try { await post(`/api/admin/users/${u.id}/role`, { role: m.querySelector("#u-role").value }); toast(t("admin.role_updated"), "success"); m.remove(); reload(); }
      catch (e) { toast(e.code === "FORBIDDEN" ? t("admin.cannot_escalate") : e.message, "error"); }
    });
  } catch (error) { m.remove(); toast(error.message, "error"); }
}

/* ================= GAMES ================= */
async function renderGames() {
  root.innerHTML = `${head(t("admin.games"), `<button class="btn btn-primary btn-sm" id="g-new">+ ${escapeHtml(t("admin.new_game"))}</button>`)}<div id="g-list"></div>`;
  async function load() {
    const res = await get("/api/admin/games");
    qs("#g-list").innerHTML = table(
      ["", "Name", "Slug", t("common.status"), "⭐", "Sort", ""],
      (res.data || []).map((g) => [
        g.logo_url ? `<img src="${escapeHtml(g.logo_url)}" style="width:42px;height:32px;object-fit:cover;border-radius:8px" alt="">` : "🎮",
        `<b>${escapeHtml(g.name)}</b>`, `<span class="mono fs-xs">${escapeHtml(g.slug)}</span>`,
        statusPill(g.status, "seller"), g.is_featured ? "⭐" : "", g.sort_order ?? 0,
        `<button class="btn btn-sm" data-edit='${escapeHtml(JSON.stringify(g))}'>${escapeHtml(t("common.edit"))}</button>`,
      ]));
    qs("#g-new").onclick = () => gameModal(null, load);
    qs("#g-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => gameModal(JSON.parse(b.dataset.edit), load)));
  }
  await load();
}

function gameModal(game, reload) {
  const m = modal(`
    <div class="modal-head"><div class="modal-title">${escapeHtml(game ? t("common.edit") : t("admin.new_game"))}</div><button class="modal-close" data-close>✕</button></div>
    <div class="field"><label class="field-label">Name *</label><input id="g-name" class="input" value="${escapeHtml(game?.name || "")}"></div>
    <div class="field"><label class="field-label">Slug</label><input id="g-slug" class="input" value="${escapeHtml(game?.slug || "")}" placeholder="auto"></div>
    <div class="field"><label class="field-label">${escapeHtml(t("products.description"))}</label><textarea id="g-desc" class="textarea">${escapeHtml(game?.description || "")}</textarea></div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Logo URL</label><input id="g-logo" class="input" value="${escapeHtml(game?.logo_url || "")}"></div>
      <div class="field" style="flex:1"><label class="field-label">Banner URL</label><input id="g-banner" class="input" value="${escapeHtml(game?.banner_url || "")}"></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("common.status"))}</label>
        <select id="g-status" class="select">${["ACTIVE", "INACTIVE", "COMING_SOON"].map((s) => `<option ${game?.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
      <div class="field" style="flex:1"><label class="field-label">Accent</label><input id="g-accent" class="input" value="${escapeHtml(game?.accent_color || "")}" placeholder="#3b82f6"></div>
      <div class="field" style="flex:1"><label class="field-label">Sort</label><input id="g-sort" class="input" type="number" value="${game?.sort_order ?? 0}"></div>
    </div>
    <label class="row mb-2" style="gap:0.6rem"><span class="switch"><input id="g-featured" type="checkbox" ${game?.is_featured ? "checked" : ""}><span class="track"></span></span>⭐ Featured</label>
    <button class="btn btn-primary btn-block" id="g-save">${escapeHtml(t("common.save"))}</button>`);
  m.querySelector("#g-save").addEventListener("click", async () => {
    const payload = {
      name: qs("#g-name", m).value.trim(), slug: qs("#g-slug", m).value.trim(),
      description: qs("#g-desc", m).value, logo_url: qs("#g-logo", m).value.trim(),
      banner_url: qs("#g-banner", m).value.trim(), status: qs("#g-status", m).value,
      accent_color: qs("#g-accent", m).value.trim(), sort_order: Number(qs("#g-sort", m).value || 0),
      is_featured: qs("#g-featured", m).checked,
    };
    try {
      if (game) await put(`/api/admin/games/${game.id}`, payload);
      else await post("/api/admin/games", payload);
      toast(t("toast.saved"), "success"); m.remove(); reload();
    } catch (e) { toast(e.message, "error"); }
  });
}

/* ================= PRODUCTS ================= */
async function renderProducts() {
  const games = (await get("/api/admin/games")).data || [];
  let page = 1;
  root.innerHTML = `${head(t("admin.products"), `<button class="btn btn-primary btn-sm" id="p-new">+ ${escapeHtml(t("admin.new_product"))}</button>`)}
    <div id="p-list"></div><div id="p-pages"></div>`;
  async function load() {
    const res = await get(`/api/admin/products?page=${page}&page_size=15`);
    qs("#p-list").innerHTML = table(
      ["", "Name", "Type", "Game", t("products.variants"), t("common.status"), ""],
      (res.data?.items || []).map((p) => [
        p.image_url ? `<img src="${escapeHtml(p.image_url)}" style="width:42px;height:32px;object-fit:cover;border-radius:8px" alt="">` : "🕹️",
        `<b>${escapeHtml(p.name)}</b><div class="fs-xs text-mute mono">${escapeHtml(p.slug)}</div>`,
        escapeHtml(p.type), escapeHtml(p.game_name || "—"),
        p.variants?.length ?? 0,
        p.active ? `<span class="badge badge-green">ACTIVE</span>` : `<span class="badge badge-gray">OFF</span>`,
        `<button class="btn btn-sm" data-edit="${escapeHtml(p.id)}">${escapeHtml(t("common.edit"))}</button>`,
      ]));
    const pages = qs("#p-pages"); pages.innerHTML = ""; pages.appendChild(paginationEl(res.data, (p2) => { page = p2; load(); }));
    const all = res.data?.items || [];
    qs("#p-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => productModal(all.find((x) => x.id === b.dataset.edit), games, load)));
  }
  qs("#p-new").onclick = () => productModal(null, games, load);
  await load();
}

function productModal(product, games, reload) {
  const variants = product?.variants?.length ? product.variants : [{ name: "", selling_price: "", cost_price: "", stock: 0, currency: "USD", active: true }];
  const m = modal(`
    <div class="modal-head"><div class="modal-title">${escapeHtml(product ? t("common.edit") : t("admin.new_product"))}</div><button class="modal-close" data-close>✕</button></div>
    <div class="row gap-sm">
      <div class="field" style="flex:2"><label class="field-label">Name *</label><input id="pr-name" class="input" value="${escapeHtml(product?.name || "")}"></div>
      <div class="field" style="flex:1"><label class="field-label">Type</label>
        <select id="pr-type" class="select">${["TOPUP", "GIFT_CARD", "GAME_KEY", "DIGITAL_ITEM", "SUBSCRIPTION", "OTHER"].map((ty) => `<option ${product?.type === ty ? "selected" : ""}>${ty}</option>`).join("")}</select></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Game</label>
        <select id="pr-game" class="select"><option value="">—</option>${games.map((g) => `<option value="${escapeHtml(g.id)}" ${product?.game_id === g.id ? "selected" : ""}>${escapeHtml(g.name)}</option>`).join("")}</select></div>
      <div class="field" style="flex:1"><label class="field-label">Image URL</label><input id="pr-image" class="input" value="${escapeHtml(product?.image_url || "")}"></div>
    </div>
    <div class="field"><label class="field-label">${escapeHtml(t("products.description"))}</label><textarea id="pr-desc" class="textarea">${escapeHtml(product?.description || "")}</textarea></div>
    <div id="pr-fields-editor" class="card-inset mb-2">
      <div class="row spread mb-1"><b class="fs-sm">🧩 ${escapeHtml(t("checkout.player_info"))}</b>
        <button class="btn btn-sm" id="pr-field-add">+</button></div>
      <div id="pr-fields" class="stack" style="gap:0.4rem"></div>
    </div>
    <div class="row spread mb-1"><b class="fs-sm">${escapeHtml(t("products.variants"))}</b><button class="btn btn-sm" id="pr-variant-add">+ ${escapeHtml(t("admin.new_variant"))}</button></div>
    <div id="pr-variants" class="stack" style="gap:0.5rem"></div>
    <label class="row mt-2 mb-2" style="gap:0.6rem"><span class="switch"><input id="pr-active" type="checkbox" ${product?.active !== false ? "checked" : ""}><span class="track"></span></span>Active</label>
    <label class="row mb-2" style="gap:0.6rem"><span class="switch"><input id="pr-featured" type="checkbox" ${product?.is_featured ? "checked" : ""}><span class="track"></span></span>⭐ Featured</label>
    <button class="btn btn-primary btn-block" id="pr-save">${escapeHtml(t("common.save"))}</button>`, { large: true });

  const fieldsWrap = m.querySelector("#pr-fields");
  function fieldRow(f = {}) {
    const row = document.createElement("div");
    row.className = "row gap-sm";
    row.innerHTML = `
      <input class="input f-key" placeholder="key (playerId)" value="${escapeHtml(f.key || "")}" style="flex:1">
      <input class="input f-label" placeholder="label" value="${escapeHtml(f.label || "")}" style="flex:1">
      <select class="select f-type" style="width:auto">
        ${["text", "number", "email", "select"].map((ty) => `<option ${(f.type || "text") === ty ? "selected" : ""}>${ty}</option>`).join("")}
      </select>
      <label class="row fs-xs" style="gap:0.3rem"><input type="checkbox" class="f-required" ${f.required !== false ? "checked" : ""}>*</label>
      <button class="btn btn-sm btn-danger f-del">✕</button>`;
    row.querySelector(".f-del").addEventListener("click", () => row.remove());
    fieldsWrap.appendChild(row);
  }
  (product?.required_fields || []).forEach(fieldRow);
  m.querySelector("#pr-field-add").addEventListener("click", () => fieldRow());

  const variantsWrap = m.querySelector("#pr-variants");
  function variantRow(v = {}) {
    const row = document.createElement("div");
    row.className = "card-inset";
    row.innerHTML = `
      <input type="hidden" class="v-id" value="${escapeHtml(v.id || "")}">
      <div class="row gap-sm" style="flex-wrap:wrap">
        <input class="input v-name" placeholder="Name *" value="${escapeHtml(v.name || "")}" style="flex:2;min-width:120px">
        <input class="input v-price" type="number" step="0.01" min="0.01" placeholder="Sell *" value="${escapeHtml(String(v.selling_price ?? ""))}" style="flex:1;min-width:90px">
        <input class="input v-cost" type="number" step="0.01" min="0" placeholder="Cost 🔒" value="${escapeHtml(String(v.cost_price ?? ""))}" style="flex:1;min-width:90px">
        <input class="input v-stock" type="number" min="0" placeholder="Stock" value="${v.stock ?? 0}" style="width:80px">
        <input class="input v-ext" placeholder="external_id" value="${escapeHtml(v.external_product_id || "")}" style="flex:1;min-width:100px">
        <label class="row fs-xs" style="gap:0.3rem"><input type="checkbox" class="v-active" ${v.active !== false ? "checked" : ""}>✓</label>
        <button class="btn btn-sm btn-danger v-del">✕</button>
      </div>
      ${v.margin ? `<div class="fs-xs text-success mt-1">margin: ${escapeHtml(v.margin)} (${escapeHtml(v.margin_pct)}%)</div>` : ""}`;
    row.querySelector(".v-del").addEventListener("click", () => row.remove());
    variantsWrap.appendChild(row);
  }
  variants.forEach(variantRow);
  m.querySelector("#pr-variant-add").addEventListener("click", () => variantRow());

  m.querySelector("#pr-save").addEventListener("click", async () => {
    const payload = {
      name: qs("#pr-name", m).value.trim(),
      type: qs("#pr-type", m).value,
      game_id: qs("#pr-game", m).value || null,
      image_url: qs("#pr-image", m).value.trim(),
      description: qs("#pr-desc", m).value,
      active: qs("#pr-active", m).checked,
      is_featured: qs("#pr-featured", m).checked,
      required_fields: [...m.querySelectorAll("#pr-fields .row")].map((row) => ({
        key: row.querySelector(".f-key").value.trim(),
        label: row.querySelector(".f-label").value.trim(),
        type: row.querySelector(".f-type").value,
        required: row.querySelector(".f-required").checked,
      })).filter((f) => f.key),
      variants: [...m.querySelectorAll("#pr-variants .card-inset")].map((row) => ({
        id: row.querySelector(".v-id").value || null,
        name: row.querySelector(".v-name").value.trim(),
        selling_price: row.querySelector(".v-price").value,
        cost_price: row.querySelector(".v-cost").value || null,
        stock: Number(row.querySelector(".v-stock").value || 0),
        external_product_id: row.querySelector(".v-ext").value.trim() || null,
        active: row.querySelector(".v-active").checked,
      })).filter((v) => v.name),
    };
    try {
      if (product) await put(`/api/admin/products/${product.id}`, payload);
      else await post("/api/admin/products", payload);
      toast(t("toast.saved"), "success"); m.remove(); reload();
    } catch (e) { toast(e.message, "error"); }
  });
}

/* ================= PAYMENTS / REFUNDS / WEBHOOKS ================= */
async function renderPayments() {
  let page = 1, status = "";
  root.innerHTML = `${head(t("admin.payments"))}
    <div class="admin-toolbar"><select id="py-status" class="select"><option value="">${escapeHtml(t("common.all"))}</option>
      ${["PENDING", "PROCESSING", "PAID", "FAILED", "CANCELLED", "EXPIRED", "REFUNDED", "PARTIALLY_REFUNDED"].map((s) => `<option>${s}</option>`).join("")}</select></div>
    <div id="py-list"></div><div id="py-pages"></div>`;
  async function load() {
    const p = new URLSearchParams({ page: String(page), page_size: "20" });
    if (status) p.set("status", status);
    const res = await get(`/api/admin/payments?${p}`);
    qs("#py-list").innerHTML = table(
      ["ID", "Provider", "Purpose", "Amount", t("common.status"), t("common.created_at")],
      (res.data?.items || []).map((pay) => [
        `<span class="mono fs-xs">${escapeHtml(pay.id.slice(0, 8))}…</span>`,
        escapeHtml(pay.provider), `<span class="badge">${escapeHtml(pay.purpose)}</span>`,
        `<b>${escapeHtml(pay.amount)} ${escapeHtml(pay.currency)}</b>`,
        statusPill(pay.status, "seller"), escapeHtml(fmtDate(pay.created_at)),
      ]));
    const pages = qs("#py-pages"); pages.innerHTML = ""; pages.appendChild(paginationEl(res.data, (p2) => { page = p2; load(); }));
  }
  qs("#py-status").addEventListener("change", (e) => { status = e.target.value; page = 1; load(); });
  await load();
}

async function renderRefunds() {
  const res = await get("/api/admin/refunds?page_size=50");
  const items = res.data?.items || [];
  root.innerHTML = `${head(t("admin.refunds"))}` + table(
    ["ID", "Amount", "Reason", t("common.status"), t("common.created_at"), ""],
    items.map((r) => [
      `<span class="mono fs-xs">${escapeHtml(r.id.slice(0, 8))}…</span>`,
      `<b>${escapeHtml(r.amount)} ${escapeHtml(r.currency)}</b>`,
      `<span class="fs-xs">${escapeHtml((r.reason || "").slice(0, 60))}</span>`,
      statusPill(r.status, "seller"), escapeHtml(fmtDate(r.created_at)),
      r.status === "PENDING" ? `<span class="row gap-sm"><button class="btn btn-sm btn-primary" data-ap="${escapeHtml(r.id)}">${escapeHtml(t("admin.refund_approve"))}</button><button class="btn btn-sm btn-danger" data-rj="${escapeHtml(r.id)}">${escapeHtml(t("admin.refund_reject"))}</button></span>` : "",
    ]));
  root.querySelectorAll("[data-ap]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmDialog(t("common.confirm_destructive")))) return;
    try { await post(`/api/admin/refunds/${b.dataset.ap}/approve`); toast(t("toast.saved"), "success"); renderRefunds(); }
    catch (e) { toast(e.message, "error"); }
  }));
  root.querySelectorAll("[data-rj]").forEach((b) => b.addEventListener("click", async () => {
    const reason = window.prompt(t("admin.refund_reject")) || "";
    try { await post(`/api/admin/refunds/${b.dataset.rj}/reject`, { reason }); toast(t("toast.saved"), "success"); renderRefunds(); }
    catch (e) { toast(e.message, "error"); }
  }));
}

async function renderWebhooks() {
  const res = await get("/api/admin/webhook-events?page_size=50");
  root.innerHTML = `${head(t("admin.webhook_log"))}` + table(
    ["Provider", "Event", "Type", "✓ Sig", "Processed", "Error", t("common.created_at")],
    (res.data?.items || []).map((e) => [
      escapeHtml(e.provider), `<span class="mono fs-xs">${escapeHtml((e.event_id || "").slice(0, 18))}</span>`,
      `<span class="badge">${escapeHtml(e.event_type || "")}</span>`,
      e.signature_valid ? "✅" : "❌",
      e.processed ? "✅" : "⏳",
      `<span class="fs-xs text-danger">${escapeHtml((e.processing_error || "").slice(0, 50))}</span>`,
      escapeHtml(fmtDate(e.received_at)),
    ]));
}

/* ================= SUPPLIERS ================= */
async function renderSuppliers() {
  root.innerHTML = `${head(t("admin.suppliers"), `<button class="btn btn-primary btn-sm" id="sp-new">+ ${escapeHtml(t("common.create"))}</button>`)}<div id="sp-list"></div>`;
  async function load() {
    const res = await get("/api/admin/suppliers");
    qs("#sp-list").innerHTML = table(
      ["Name", "Kind", "Priority", t("common.status"), t("admin.supplier_balance"), t("admin.supplier_last_sync"), t("admin.supplier_last_error"), ""],
      (res.data || []).map((s) => [
        `<b>${escapeHtml(s.name)}</b><div class="fs-xs text-mute mono">${escapeHtml(s.slug)}</div>`,
        escapeHtml(s.provider_kind), s.priority,
        `<span class="row gap-sm">${statusPill(s.status, "seller")}${s.active ? "" : '<span class="badge badge-gray">OFF</span>'}</span>`,
        s.balance != null ? `${escapeHtml(s.balance)} ${escapeHtml(s.balance_currency || "")}` : "—",
        escapeHtml(fmtDate(s.last_sync_at)),
        `<span class="fs-xs text-danger">${escapeHtml((s.last_error || "").slice(0, 40))}</span>`,
        `<span class="row gap-sm">
          <button class="btn btn-sm" data-edit="${escapeHtml(s.id)}">${escapeHtml(t("common.edit"))}</button>
          <button class="btn btn-sm" data-test="${escapeHtml(s.id)}">${escapeHtml(t("admin.supplier_test"))}</button>
          <button class="btn btn-sm" data-sync="${escapeHtml(s.id)}">↻</button>
          <button class="btn btn-sm" data-toggle="${escapeHtml(s.id)}">${s.active ? "⏸" : "▶"}</button>
        </span>`,
      ]));
    const all = res.data || [];
    qs("#sp-new").onclick = () => supplierModal(null, load);
    qs("#sp-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => supplierModal(all.find((x) => x.id === b.dataset.edit), load)));
    qs("#sp-list").querySelectorAll("[data-test]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true; b.innerHTML = `<span class="spinner"></span>`;
      try { const r = await post(`/api/admin/suppliers/${b.dataset.test}/test`); toast(JSON.stringify(r.data).slice(0, 120), r.data?.ok === false ? "error" : "success"); load(); }
      catch (e) { toast(e.message, "error"); load(); }
    }));
    qs("#sp-list").querySelectorAll("[data-sync]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try { const r = await post(`/api/admin/suppliers/${b.dataset.sync}/sync-catalog`, {}); toast(JSON.stringify(r.data).slice(0, 120), "success"); load(); }
      catch (e) { toast(e.message, "error"); load(); }
    }));
    qs("#sp-list").querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", async () => {
      try { await post(`/api/admin/suppliers/${b.dataset.toggle}/toggle`); load(); }
      catch (e) { toast(e.message, "error"); }
    }));
  }
  await load();
}

function supplierModal(supplier, reload) {
  const m = modal(`
    <div class="modal-head"><div class="modal-title">🚚 ${escapeHtml(supplier?.name || t("common.create"))}</div><button class="modal-close" data-close>✕</button></div>
    <div class="row gap-sm">
      <div class="field" style="flex:2"><label class="field-label">Name *</label><input id="sp-name" class="input" value="${escapeHtml(supplier?.name || "")}"></div>
      <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("admin.supplier_priority"))}</label><input id="sp-priority" class="input" type="number" value="${supplier?.priority ?? 100}"></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Kind</label>
        <select id="sp-kind" class="select"><option value="http_json" ${supplier?.provider_kind === "http_json" ? "selected" : ""}>http_json</option></select></div>
      <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("common.status"))}</label>
        <select id="sp-status" class="select">${["ACTIVE", "INACTIVE", "ERROR", "SYNCING"].map((s) => `<option ${supplier?.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></div>
    </div>
    <div class="field"><label class="field-label">Base URL 🔒</label><input id="sp-url" class="input" placeholder="${supplier ? "••• (saved — enter to replace)" : "https://api.supplier.com"}"></div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">API key 🔒</label><input id="sp-key" class="input" type="password" placeholder="${supplier ? "••••••" : ""}"></div>
      <div class="field" style="flex:1"><label class="field-label">API secret 🔒</label><input id="sp-secret" class="input" type="password" placeholder="${supplier ? "••••••" : ""}"></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Timeout (s)</label><input id="sp-timeout" class="input" type="number" value="30"></div>
      <div class="field" style="flex:1"><label class="field-label">Max retries</label><input id="sp-retries" class="input" type="number" value="2"></div>
    </div>
    <label class="row mb-2" style="gap:0.6rem"><span class="switch"><input id="sp-active" type="checkbox" ${supplier?.active ? "checked" : ""}><span class="track"></span></span>Active</label>
    <button class="btn btn-primary btn-block" id="sp-save">${escapeHtml(t("common.save"))}</button>`);
  m.querySelector("#sp-save").addEventListener("click", async () => {
    const payload = {
      name: qs("#sp-name", m).value.trim(),
      priority: Number(qs("#sp-priority", m).value || 100),
      provider_kind: qs("#sp-kind", m).value,
      status: qs("#sp-status", m).value,
      active: qs("#sp-active", m).checked,
      timeout_seconds: Number(qs("#sp-timeout", m).value || 30),
      max_retries: Number(qs("#sp-retries", m).value || 2),
    };
    const url = qs("#sp-url", m).value.trim();
    const key = qs("#sp-key", m).value.trim();
    const secret = qs("#sp-secret", m).value.trim();
    if (url) payload.base_url = url;
    if (key) payload.api_key = key;
    if (secret) payload.api_secret = secret;
    try {
      if (supplier) await put(`/api/admin/suppliers/${supplier.id}`, payload);
      else await post("/api/admin/suppliers", payload);
      toast(t("toast.saved"), "success"); m.remove(); reload();
    } catch (e) { toast(e.message, "error"); }
  });
}

/* ================= SELLERS / LISTINGS / PAYOUTS ================= */
async function renderSellers() {
  const res = await get("/api/admin/sellers?page_size=50");
  root.innerHTML = `${head(t("admin.sellers"))}` + table(
    ["Seller", "User", t("common.status"), "⭐", t("seller.orders"), "Commission", t("seller.available_balance"), ""],
    (res.data?.items || []).map((s) => [
      `<b>${escapeHtml(s.display_name)}</b>`, `@${escapeHtml(s.username)}`,
      statusPill(s.status, "seller"), escapeHtml(s.rating), s.completed_orders,
      s.commission_override_pct ? `<b>${escapeHtml(s.commission_override_pct)}%</b>` : `<span class="text-mute">default</span>`,
      `<b>${escapeHtml(s.balance?.available || "0.00")}</b>`,
      `<button class="btn btn-sm" data-comm="${escapeHtml(s.id)}" data-pct="${escapeHtml(s.commission_override_pct || "")}">%</button>`,
    ]));
  root.querySelectorAll("[data-comm]").forEach((b) => b.addEventListener("click", async () => {
    const value = window.prompt(`${t("seller.commission_note", { pct: "" })} (0-50, empty = default)`, b.dataset.pct);
    if (value === null) return;
    try { await post(`/api/admin/sellers/${b.dataset.comm}/commission`, { commission_pct: value || null }); toast(t("toast.saved"), "success"); renderSellers(); }
    catch (e) { toast(e.message, "error"); }
  }));
}

async function renderListings() {
  const res = await get("/api/admin/listings/pending");
  const items = res.data || [];
  root.innerHTML = `${head(t("admin.listings"), `<span class="badge">${items.length} ⏳</span>`)}
    ${items.length ? items.map((l) => card(`
      <div class="row gap-sm" style="align-items:start;flex-wrap:wrap">
        <div style="width:110px;height:80px;border-radius:12px;overflow:hidden;background:var(--surface-3);display:grid;place-items:center;flex-shrink:0">
          ${l.images?.length ? `<img src="${escapeHtml(l.images[0])}" alt="" style="width:100%;height:100%;object-fit:cover">` : "🏷️"}
        </div>
        <div style="flex:1;min-width:200px">
          <b>${escapeHtml(l.title)}</b>
          <div class="text-mute fs-xs">${escapeHtml(l.seller?.display_name || "")} · ${escapeHtml(fmtMoney(l.price, l.currency))} · ${escapeHtml(l.delivery_type)}</div>
          <p class="fs-sm text-soft mt-1" style="max-height:60px;overflow:hidden">${escapeHtml((l.description || "").slice(0, 240))}</p>
        </div>
        <div class="row gap-sm">
          <button class="btn btn-sm btn-primary" data-ap="${escapeHtml(l.id)}">✅ ${escapeHtml(t("admin.listing_approve"))}</button>
          <button class="btn btn-sm btn-danger" data-rj="${escapeHtml(l.id)}">⛔ ${escapeHtml(t("admin.listing_reject"))}</button>
        </div>
      </div>`)).join("") : `<div class="card empty-state"><div class="icon">✅</div><b>${escapeHtml(t("common.empty_title"))}</b></div>`}`;
  root.querySelectorAll("[data-ap]").forEach((b) => b.addEventListener("click", async () => {
    try { await post(`/api/admin/listings/${b.dataset.ap}/review`, { approve: true }); toast(t("toast.saved"), "success"); renderListings(); }
    catch (e) { toast(e.message, "error"); }
  }));
  root.querySelectorAll("[data-rj]").forEach((b) => b.addEventListener("click", async () => {
    const reason = window.prompt(t("admin.listing_reject")) || "";
    try { await post(`/api/admin/listings/${b.dataset.rj}/review`, { approve: false, reason }); toast(t("toast.saved"), "success"); renderListings(); }
    catch (e) { toast(e.message, "error"); }
  }));
}

async function renderPayouts() {
  const res = await get("/api/admin/payouts?page_size=50");
  root.innerHTML = `${head(t("admin.payouts"))}` + table(
    ["Seller", "Amount", "Method", "Details 🔒", t("common.status"), t("common.created_at"), ""],
    (res.data?.items || []).map((p) => [
      `<b>${escapeHtml(p.seller?.display_name || "")}</b><div class="fs-xs text-mute">@${escapeHtml(p.seller?.username || "")}</div>`,
      `<b>${escapeHtml(p.amount)} ${escapeHtml(p.currency)}</b>`,
      escapeHtml(p.method),
      `<span class="mono fs-xs">${escapeHtml((p.details || "").slice(0, 28))}…</span>`,
      statusPill(p.status, "seller"), escapeHtml(fmtDate(p.created_at)),
      p.status === "PENDING" ? `<span class="row gap-sm">
          <button class="btn btn-sm btn-primary" data-ap="${escapeHtml(p.id)}">${escapeHtml(t("admin.payout_approve"))}</button>
          <button class="btn btn-sm btn-danger" data-rj="${escapeHtml(p.id)}">${escapeHtml(t("admin.payout_reject"))}</button></span>`
        : p.status === "APPROVED" ? `<button class="btn btn-sm" data-pr="${escapeHtml(p.id)}">▶ ${escapeHtml(t("admin.payout_status_PROCESSING") !== "admin.payout_status_PROCESSING" ? "" : "PROCESS")}</button>`
        : p.status === "PROCESSING" ? `<button class="btn btn-sm btn-primary" data-cp="${escapeHtml(p.id)}">✅ ${escapeHtml(t("admin.payout_mark_completed"))}</button>`
        : p.status === "APPROVED" ? "" : "",
    ]));
  const act = async (id, action, extra = {}) => {
    try { await post(`/api/admin/payouts/${id}/${action}`, extra); toast(t("toast.saved"), "success"); renderPayouts(); }
    catch (e) { toast(e.message, "error"); }
  };
  root.querySelectorAll("[data-ap]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmDialog(t("admin.payout_approve") + "?"))) return;
    act(b.dataset.ap, "approve");
  }));
  root.querySelectorAll("[data-rj]").forEach((b) => b.addEventListener("click", async () => {
    const note = window.prompt(t("admin.payout_reject")) || "";
    act(b.dataset.rj, "reject", { note });
  }));
  root.querySelectorAll("[data-pr]").forEach((b) => b.addEventListener("click", () => act(b.dataset.pr, "process")));
  root.querySelectorAll("[data-cp]").forEach((b) => b.addEventListener("click", async () => {
    const reference = window.prompt("Reference / txn id") || "";
    if (!(await confirmDialog(t("admin.payout_mark_completed") + "?"))) return;
    act(b.dataset.cp, "complete", { reference });
  }));
}

/* ================= DONATIONS ================= */
async function renderDonations() {
  const res = await get("/api/admin/donations?page_size=50");
  root.innerHTML = `${head(t("nav.donate"))}` + table(
    ["Recipient", "Donor", "Gross", "Fee", "Net", t("common.status"), t("common.created_at")],
    (res.data?.items || []).map((d) => [
      `@${escapeHtml(d.recipient || "—")}`,
      d.anonymous ? `<i>${escapeHtml(t("donate.anonymous_label"))}</i>` : escapeHtml(d.donor_name || "—"),
      escapeHtml(d.gross_amount), escapeHtml(d.platform_fee), `<b>${escapeHtml(d.amount)}</b>`,
      statusPill(d.status, "seller"), escapeHtml(fmtDate(d.created_at)),
    ]));
}

/* ================= COUPONS ================= */
async function renderCoupons() {
  root.innerHTML = `${head(t("admin.coupons"), `<button class="btn btn-primary btn-sm" id="cp-new">+ ${escapeHtml(t("admin.new_coupon"))}</button>`)}<div id="cp-list"></div>`;
  async function load() {
    const res = await get("/api/admin/coupons");
    qs("#cp-list").innerHTML = table(
      ["Code", "Type", "Value", "Min", "Max ₼", "Uses", "Expires", t("common.status"), ""],
      (res.data || []).map((c) => [
        `<b class="mono">${escapeHtml(c.code)}</b>`,
        c.type === "PERCENTAGE" ? "%" : c.type,
        `<b>${escapeHtml(c.value)}</b>`,
        escapeHtml(String(c.min_order_amount ?? "—")),
        escapeHtml(String(c.max_discount ?? "—")),
        `${c.used_count}/${c.max_uses ?? "∞"}`,
        escapeHtml(c.expires_at ? fmtDate(c.expires_at, false) : "—"),
        c.active ? `<span class="badge badge-green">ON</span>` : `<span class="badge badge-gray">OFF</span>`,
        `<button class="btn btn-sm" data-edit='${escapeHtml(JSON.stringify(c))}'>${escapeHtml(t("common.edit"))}</button>`,
      ]));
    qs("#cp-new").onclick = () => couponModal(null, load);
    qs("#cp-list").querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => couponModal(JSON.parse(b.dataset.edit), load)));
  }
  await load();
}

function couponModal(coupon, reload) {
  const m = modal(`
    <div class="modal-head"><div class="modal-title">🎟️ ${escapeHtml(coupon?.code || t("admin.new_coupon"))}</div><button class="modal-close" data-close>✕</button></div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Code *</label><input id="cp-code" class="input mono" style="text-transform:uppercase" value="${escapeHtml(coupon?.code || "")}"></div>
      <div class="field" style="flex:1"><label class="field-label">Type</label>
        <select id="cp-type" class="select"><option ${coupon?.type === "PERCENTAGE" ? "selected" : ""}>PERCENTAGE</option><option ${coupon?.type === "FIXED" ? "selected" : ""}>FIXED</option></select></div>
      <div class="field" style="flex:1"><label class="field-label">Value *</label><input id="cp-value" class="input" type="number" step="0.01" value="${escapeHtml(String(coupon?.value ?? ""))}"></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Min order</label><input id="cp-min" class="input" type="number" step="0.01" value="${escapeHtml(String(coupon?.min_order_amount ?? ""))}"></div>
      <div class="field" style="flex:1"><label class="field-label">Max discount</label><input id="cp-max" class="input" type="number" step="0.01" value="${escapeHtml(String(coupon?.max_discount ?? ""))}"></div>
      <div class="field" style="flex:1"><label class="field-label">Max uses</label><input id="cp-uses" class="input" type="number" value="${escapeHtml(String(coupon?.max_uses ?? ""))}"></div>
    </div>
    <div class="row gap-sm">
      <div class="field" style="flex:1"><label class="field-label">Per user</label><input id="cp-per" class="input" type="number" value="${escapeHtml(String(coupon?.per_user_limit ?? ""))}"></div>
      <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("common.from"))}</label><input id="cp-start" class="input" type="date" value="${coupon?.starts_at ? coupon.starts_at.slice(0, 10) : ""}"></div>
      <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("common.to"))}</label><input id="cp-end" class="input" type="date" value="${coupon?.expires_at ? coupon.expires_at.slice(0, 10) : ""}"></div>
    </div>
    <label class="row mb-2" style="gap:0.6rem"><span class="switch"><input id="cp-active" type="checkbox" ${coupon?.active !== false ? "checked" : ""}><span class="track"></span></span>Active</label>
    <button class="btn btn-primary btn-block" id="cp-save">${escapeHtml(t("common.save"))}</button>`);
  m.querySelector("#cp-save").addEventListener("click", async () => {
    const payload = {
      code: qs("#cp-code", m).value.trim(), type: qs("#cp-type", m).value, value: qs("#cp-value", m).value,
      min_order_amount: qs("#cp-min", m).value || null, max_discount: qs("#cp-max", m).value || null,
      max_uses: qs("#cp-uses", m).value || null, per_user_limit: qs("#cp-per", m).value || null,
      starts_at: qs("#cp-start", m).value || null, expires_at: qs("#cp-end", m).value || null,
      active: qs("#cp-active", m).checked,
    };
    try {
      if (coupon) await put(`/api/admin/coupons/${coupon.id}`, payload);
      else await post("/api/admin/coupons", payload);
      toast(t("toast.saved"), "success"); m.remove(); reload();
    } catch (e) { toast(e.message, "error"); }
  });
}

/* ================= PROMOTIONS ================= */
async function renderPromotions() {
  const res = await get("/api/admin/promotions");
  root.innerHTML = `${head(t("admin.promotions"))}` + table(
    ["Listing", "Seller", "Kind", "Price", t("common.status"), t("promotions.starts"), t("promotions.ends")],
    (res.data || []).map((p) => [
      escapeHtml(p.listing_title || "—"), escapeHtml(p.seller_name || "—"),
      `<span class="badge badge-gold">${escapeHtml(p.kind)}</span>`,
      escapeHtml(`${p.price} ${p.currency || ""}`),
      statusPill(p.status, "seller"),
      escapeHtml(fmtDate(p.starts_at, false)), escapeHtml(fmtDate(p.ends_at, false)),
    ]));
}

/* ================= SUPPORT ================= */
async function renderSupport() {
  const res = await get("/api/admin/tickets?page_size=50");
  root.innerHTML = `${head(t("admin.support"))}` + table(
    ["#", "Subject", "User", t("common.status"), "Priority", t("common.updated_at"), ""],
    (res.data?.items || []).map((tk) => [
      `<b class="mono fs-xs">${escapeHtml(tk.number)}</b>`,
      escapeHtml(tk.subject), `@${escapeHtml(tk.user || "—")}`,
      `<span class="status-pill st-${escapeHtml(tk.status)}">${escapeHtml(t(`support.status_${tk.status}`) !== `support.status_${tk.status}` ? t(`support.status_${tk.status}`) : tk.status)}</span>`,
      escapeHtml(tk.priority), escapeHtml(fmtDate(tk.last_message_at)),
      `<button class="btn btn-sm" data-open="${escapeHtml(tk.id)}">${escapeHtml(t("common.open"))}</button>`,
    ]));
  root.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openTicketAdmin(b.dataset.open)));
}

async function openTicketAdmin(ticketId) {
  const m = modal(`<div class="loading-overlay"><span class="spinner"></span></div>`, { large: true });
  async function loadThread() {
    const res = await get(`/api/admin/tickets/${ticketId}`);
    const tk = res.data;
    m.querySelector(".modal").innerHTML = `
      <div class="modal-head">
        <div><div class="modal-title">${escapeHtml(tk.number)} · ${escapeHtml(tk.subject)}</div>
          <div class="fs-xs text-mute">@${escapeHtml(tk.user?.username || "")} · <span class="status-pill st-${escapeHtml(tk.status)}">${escapeHtml(tk.status)}</span></div></div>
        <button class="modal-close" data-close>✕</button>
      </div>
      <div class="chat-box" id="tk-chat"></div>
      <div class="row gap-sm mt-2">
        <select id="tk-status" class="select" style="width:auto">
          ${["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"].map((s) => `<option ${tk.status === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <button class="btn btn-sm" id="tk-status-save">${escapeHtml(t("common.save"))}</button>
      </div>
      <form id="tk-reply" class="row mt-2" style="align-items:end">
        <div class="field" style="flex:1;margin:0"><textarea id="tk-body" class="textarea" style="min-height:60px" maxlength="5000"></textarea></div>
        <div class="stack gap-sm">
          <label class="row fs-xs" style="gap:0.4rem"><input id="tk-internal" type="checkbox">🔒 internal</label>
          <button class="btn btn-primary" type="submit">${escapeHtml(t("support.send"))}</button>
        </div>
      </form>`;
    const chat = m.querySelector("#tk-chat");
    chat.innerHTML = (tk.messages || []).map((msg) => {
      const mine = msg.author_role !== "USER";
      return `<div class="chat-msg ${mine ? "me" : "them"} ${msg.is_internal ? "internal" : ""}">
        <div class="who">${escapeHtml(msg.author_name || msg.author_role)}${msg.is_internal ? " 🔒" : ""} · ${escapeHtml(fmtDate(msg.created_at))}</div>
        <div>${escapeHtml(msg.body)}</div></div>`;
    }).join("");
    chat.scrollTop = chat.scrollHeight;
    m.querySelector("#tk-status-save").addEventListener("click", async () => {
      try { await post(`/api/admin/tickets/${ticketId}/status`, { status: m.querySelector("#tk-status").value }); toast(t("toast.saved"), "success"); loadThread(); }
      catch (e) { toast(e.message, "error"); }
    });
    m.querySelector("#tk-reply").addEventListener("submit", async (event) => {
      event.preventDefault();
      const body = m.querySelector("#tk-body").value.trim();
      if (!body) return;
      try {
        await post(`/api/admin/tickets/${ticketId}/messages`, { body, internal: m.querySelector("#tk-internal").checked });
        loadThread();
      } catch (e) { toast(e.message, "error"); }
    });
  }
  await loadThread();
}

/* ================= FRAUD ================= */
async function renderFraud() {
  const res = await get("/api/admin/fraud?resolved=false&page_size=50");
  root.innerHTML = `${head(t("admin.fraud"), `<span class="badge badge-red">${res.data?.total ?? 0} open</span>`)}
    <div id="fr-list"></div>`;
  const items = res.data?.items || [];
  qs("#fr-list").innerHTML = items.length ? table(
    [t("admin.risk_score"), "Level", "Type", "User", "Order", "Signals", t("common.created_at"), ""],
    items.map((f) => [
      `<b class="${f.risk_score >= 70 ? "text-danger" : ""}">${f.risk_score}</b>`,
      `<span class="badge ${f.level === "CRITICAL" || f.level === "HIGH" ? "badge-red" : "badge-gold"}">${escapeHtml(t(`admin.level_${f.level}`) !== `admin.level_${f.level}` ? t(`admin.level_${f.level}`) : f.level)}</span>`,
      escapeHtml(f.type), `@${escapeHtml(f.user || "—")}`, escapeHtml(f.order_number || "—"),
      `<span class="fs-xs text-mute">${escapeHtml(JSON.stringify(f.signals || []).slice(0, 70))}</span>`,
      escapeHtml(fmtDate(f.created_at)),
      `<button class="btn btn-sm btn-primary" data-res="${escapeHtml(f.id)}">${escapeHtml(t("admin.resolve"))}</button>`,
    ])) : `<div class="card empty-state"><div class="icon">🛡️</div><b>${escapeHtml(t("admin.no_fraud"))}</b></div>`;
  root.querySelectorAll("[data-res]").forEach((b) => b.addEventListener("click", async () => {
    const note = window.prompt(t("admin.resolve")) || "";
    try { await post(`/api/admin/fraud/${b.dataset.res}/resolve`, { note }); toast(t("admin.resolved"), "success"); renderFraud(); }
    catch (e) { toast(e.message, "error"); }
  }));
}

/* ================= NOTIFICATIONS / TELEGRAM / AUDIT ================= */
async function renderNotificationsAdmin() {
  root.innerHTML = `${head(t("admin.notifications"))}
    ${card(`<h2 class="fw-800 mb-2">📣 Broadcast</h2>
      <div class="field"><label class="field-label">Title *</label><input id="nb-title" class="input" maxlength="200"></div>
      <div class="field"><label class="field-label">Body *</label><textarea id="nb-body" class="textarea" maxlength="2000"></textarea></div>
      <p class="field-hint mb-2">Sent to ALL users as an in-app notification.</p>
      <button id="nb-send" class="btn btn-primary">${escapeHtml(t("support.send"))}</button>`)}
    <div id="nb-result" class="mt-2"></div>`;
  qs("#nb-send").addEventListener("click", async () => {
    if (!(await confirmDialog("Broadcast to all users?"))) return;
    try {
      const res = await post("/api/admin/notifications/broadcast", { title: qs("#nb-title").value.trim(), body: qs("#nb-body").value.trim() });
      qs("#nb-result").innerHTML = card(`✅ recipients: <b>${res.data?.recipients ?? 0}</b>`);
      toast(t("toast.saved"), "success");
    } catch (e) { toast(e.message, "error"); }
  });
}

async function renderTelegramAdmin() {
  const res = await get("/api/admin/telegram/stats");
  const d = res.data || {};
  root.innerHTML = `${head(t("admin.telegram"))}
    <div class="admin-kpis">
      ${kpi(t("admin.connections"), d.total_connections ?? 0)}
      ${kpi("+7d", d.linked_last_7_days ?? 0)}
      ${kpi("Bot", d.bot_configured ? "✅ configured" : "⛔ TELEGRAM_BOT_TOKEN missing")}
      ${kpi(t("admin.admins_by_telegram"), d.admin_ids_configured ?? 0)}
    </div>
    <div class="mt-3">${card(`<h3 class="fw-800 mb-1">📱 Mini App</h3>
      <p class="text-soft fs-sm">/miniapp · initData HMAC · ADMIN_TELEGRAM_IDS (server-side)</p>`)}</div>`;
}

async function renderAudit() {
  let page = 1, action = "";
  root.innerHTML = `${head(t("admin.audit_logs"))}
    <div class="admin-toolbar"><input id="au-q" class="input" placeholder="action prefix (user., order., …)"></div>
    <div id="au-list"></div><div id="au-pages"></div>`;
  async function load() {
    const p = new URLSearchParams({ page: String(page), page_size: "50" });
    if (action) p.set("action", action);
    const res = await get(`/api/admin/audit-logs?${p}`);
    qs("#au-list").innerHTML = table(
      ["Action", "Actor", "Entity", "IP", t("common.created_at")],
      (res.data?.items || []).map((a) => [
        `<span class="mono fs-xs">${escapeHtml(a.action)}</span>`,
        `${escapeHtml(a.actor_type || "")}${a.actor_role ? ` · ${escapeHtml(a.actor_role)}` : ""}<div class="fs-xs text-mute mono">${escapeHtml((a.actor_id || "").slice(0, 8))}</div>`,
        `${escapeHtml(a.entity_type || "—")} <span class="fs-xs text-mute mono">${escapeHtml((a.entity_id || "").slice(0, 8))}</span>`,
        `<span class="mono fs-xs">${escapeHtml(a.ip_address || "—")}</span>`,
        escapeHtml(fmtDate(a.created_at)),
      ]));
    const pages = qs("#au-pages"); pages.innerHTML = ""; pages.appendChild(paginationEl(res.data, (p2) => { page = p2; load(); }));
  }
  let deb; qs("#au-q").addEventListener("input", (e) => { clearTimeout(deb); deb = setTimeout(() => { action = e.target.value.trim(); page = 1; load(); }, 350); });
  await load();
}

/* ================= SETTINGS ================= */
async function renderSettings() {
  const res = await get("/api/admin/settings");
  const values = res.data?.settings || {};
  const groups = {
    "admin.settings_fees": ["marketplace_commission_pct", "donation_fee_pct", "donation_fee_fixed", "service_fee_pct", "promoted_listing_price", "featured_listing_price", "homepage_promotion_price", "search_promotion_price"],
    "admin.settings_limits": ["seller_holding_period_hours", "min_payout_amount", "promotion_default_days", "max_open_tickets_per_user"],
    "common.actions": ["maintenance_mode", "support_telegram", "support_email"],
  };
  root.innerHTML = `${head(t("admin.settings"))}` + Object.entries(groups).map(([group, keys]) => card(`
    <h2 class="fw-800 mb-2">${escapeHtml(t(group) !== group ? t(group) : group)}</h2>
    ${keys.map((key) => `
      <div class="field">
        <label class="field-label mono" for="set-${escapeHtml(key)}">${escapeHtml(key)}</label>
        <input id="set-${escapeHtml(key)}" class="input" data-key="${escapeHtml(key)}" value="${escapeHtml(String(values[key] ?? ""))}">
      </div>`).join("")}
  `)).join("") + `<button class="btn btn-primary btn-block mt-2" id="st-save">${escapeHtml(t("common.save"))}</button>`;

  qs("#st-save").addEventListener("click", async () => {
    const settingsPayload = {};
    root.querySelectorAll("[data-key]").forEach((input) => { settingsPayload[input.dataset.key] = input.value; });
    try {
      await put("/api/admin/settings", { settings: settingsPayload });
      toast(t("admin.settings_saved"), "success");
      haptic("success");
    } catch (e) { toast(e.message, "error"); }
  });
}

/* ================= router ================= */
const routes = {
  dashboard: renderDashboard,
  revenue: renderRevenue,
  orders: renderOrders,
  users: renderUsers,
  games: renderGames,
  products: renderProducts,
  payments: renderPayments,
  refunds: renderRefunds,
  suppliers: renderSuppliers,
  sellers: renderSellers,
  listings: renderListings,
  payouts: renderPayouts,
  donations: renderDonations,
  coupons: renderCoupons,
  promotions: renderPromotions,
  support: renderSupport,
  fraud: renderFraud,
  webhooks: renderWebhooks,
  notifications: renderNotificationsAdmin,
  telegram: renderTelegramAdmin,
  audit: renderAudit,
  settings: renderSettings,
};

(async () => {
  try {
    await (routes[section] || renderDashboard)();
  } catch (error) {
    root.innerHTML = card(`<div class="empty-state"><div class="icon">⛔</div><b>${escapeHtml(t("common.error_title"))}</b><span>${escapeHtml(error.message)}</span></div>`);
  }
})();
