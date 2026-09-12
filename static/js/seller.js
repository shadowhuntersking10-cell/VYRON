/* Seller area: overview, listings CRUD, orders, balance, payouts, promotions, premium, settings. */
import { get, post, put, del, qs, toast, t, escapeHtml, fmtMoney, fmtDate, statusPill, emptyState, haptic, confirmDialog, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

const root = qs("#seller-root");
const section = root.dataset.section || "overview";
const card = (html) => `<div class="card">${html}</div>`;
const head = (title) => `<h1 class="section-title mb-3">${escapeHtml(title)}</h1>`;

let profile = null;

async function loadProfile() {
  const res = await get("/api/seller/me");
  profile = res.data;
  return profile;
}

/* ---------- overview ---------- */
async function renderOverview() {
  const [me, orders, listings] = await Promise.all([
    loadProfile(),
    get("/api/seller/orders?page_size=5").catch(() => ({ data: { items: [] } })),
    get("/api/seller/listings?page_size=100").catch(() => ({ data: { items: [] } })),
  ]);
  const b = me.balance || {};
  const approved = (listings.data?.items || []).filter((l) => l.status === "APPROVED").length;
  const pending = (listings.data?.items || []).filter((l) => l.status === "PENDING_REVIEW").length;
  root.innerHTML = `
    ${head(t("seller.title"))}
    <div class="card balance-card mb-3">
      <span class="label">${escapeHtml(t("seller.available_balance"))}</span>
      <div class="value" style="font-size:2rem">${escapeHtml(b.available || "0.00")} USD</div>
      <div class="balance-rows">
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.pending_balance"))}</div><div class="value">${escapeHtml(b.pending || "0.00")}</div></div>
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.reserved_balance"))}</div><div class="value">${escapeHtml(b.reserved || "0.00")}</div></div>
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.lifetime_earnings"))}</div><div class="value">${escapeHtml(b.lifetime_earnings || "0.00")}</div></div>
      </div>
    </div>
    <div class="admin-kpis mb-3">
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("seller.listings"))}</span><span class="value">${listings.data?.total ?? 0}</span><span class="delta">${approved} ${escapeHtml(t("seller.status_APPROVED"))} · ${pending} ⏳</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("seller.orders"))}</span><span class="value">${orders.data?.total ?? 0}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">⭐ ${escapeHtml(t("marketplace.rating"))}</span><span class="value">${escapeHtml(me.rating || "0")}</span></div>`)}
      ${card(`<div class="stat-card"><span class="label">${escapeHtml(t("seller.earning"))}</span><span class="value fs-sm">${escapeHtml(t("seller.commission_note", { pct: me.commission_pct }))}</span></div>`)}
    </div>
    ${card(`<div class="row spread row-wrap"><h2 class="fw-800">${escapeHtml(t("seller.orders"))}</h2><a class="btn btn-sm" href="/seller/listings">+ ${escapeHtml(t("seller.new_listing"))}</a></div>
      <div class="stack mt-2" style="gap:0.5rem" id="recent-orders"></div>`)}
    <p class="field-hint mt-2">⏳ ${escapeHtml(t("seller.holding_notice", { hours: me.holding_hours }))}</p>`;

  const items = orders.data?.items || [];
  const recent = qs("#recent-orders");
  if (!items.length) emptyState(recent, "📦", t("seller.no_orders"), "");
  else recent.innerHTML = items.map(sellerOrderRow).join("");
}

function sellerOrderRow(order) {
  return `
  <div class="card-inset row spread" style="gap:0.8rem">
    <div style="min-width:0">
      <b class="mono fs-sm">${escapeHtml(order.number)}</b>
      <div class="text-mute fs-xs truncate">${escapeHtml(order.title)}</div>
      <div class="text-mute fs-xs">${escapeHtml(fmtDate(order.created_at))} · ${escapeHtml(order.buyer?.username || "")}</div>
    </div>
    <div class="text-right">
      <div class="price fs-sm">${escapeHtml(order.price)} ${escapeHtml(order.currency)}</div>
      <div class="fs-xs text-success">+${escapeHtml(order.seller_earning || "")}</div>
      <div class="mt-1">${statusPill(order.status, "seller")}</div>
      ${order.status === "PAID" && order.delivery_type === "MANUAL" ? `<button class="btn btn-sm btn-primary mt-1" data-deliver="${escapeHtml(order.id)}">${escapeHtml(t("orders.delivery"))}</button>` : ""}
    </div>
  </div>`;
}

/* ---------- listings ---------- */
async function renderListings() {
  await loadProfile();
  root.innerHTML = `${head(t("seller.listings"))}
    <div class="row spread mb-2"><span></span><button class="btn btn-primary btn-sm" id="new-listing">+ ${escapeHtml(t("seller.new_listing"))}</button></div>
    <div id="listings-list" class="stack" style="gap:0.6rem"></div>`;
  qs("#new-listing").addEventListener("click", () => listingModal(null));
  await loadListings();
}

async function loadListings() {
  const list = qs("#listings-list");
  list.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
  const res = await get("/api/seller/listings?page_size=100");
  const items = res.data?.items || [];
  if (!items.length) { list.innerHTML = ""; emptyState(list, "🏷️", t("seller.no_listings"), ""); return; }
  list.innerHTML = items.map((l) => `
    <div class="card-inset row spread" style="gap:0.8rem;flex-wrap:wrap">
      <div class="row gap-sm" style="min-width:0;flex:1">
        <div class="thumb" style="width:56px;height:44px;border-radius:10px;background:var(--surface-3);display:grid;place-items:center;overflow:hidden;flex-shrink:0">
          ${l.images?.length ? `<img src="${escapeHtml(l.images[0])}" alt="" style="width:100%;height:100%;object-fit:cover">` : "🏷️"}
        </div>
        <div style="min-width:0">
          <b class="fs-sm truncate" style="display:block">${escapeHtml(l.title)}</b>
          <div class="text-mute fs-xs">${escapeHtml(fmtMoney(l.price, l.currency))} · ${escapeHtml(t(`marketplace.delivery_type_${l.delivery_type}`))}</div>
          ${l.rejection_reason ? `<div class="fs-xs text-danger">${escapeHtml(l.rejection_reason)}</div>` : ""}
        </div>
      </div>
      <div class="row gap-sm">
        ${statusPill(l.status, "seller")}
        <button class="btn btn-sm" data-edit="${escapeHtml(l.id)}">${escapeHtml(t("common.edit"))}</button>
        ${["DRAFT", "REJECTED"].includes(l.status) ? `<button class="btn btn-sm btn-primary" data-submit="${escapeHtml(l.id)}">${escapeHtml(t("seller.submit_review"))}</button>` : ""}
        <button class="btn btn-sm btn-danger" data-del="${escapeHtml(l.id)}">✕</button>
      </div>
    </div>`).join("");

  list.addEventListener("click", async (event) => {
    const editId = event.target.dataset?.edit;
    const submitId = event.target.dataset?.submit;
    const delId = event.target.dataset?.del;
    try {
      if (editId) {
        const res = await get("/api/seller/listings?page_size=100");
        listingModal(res.data.items.find((l) => l.id === editId) || null);
      }
      if (submitId) { await post(`/api/seller/listings/${submitId}/submit`); toast(t("seller.listing_submitted"), "success"); loadListings(); }
      if (delId) {
        if (!(await confirmDialog(t("common.confirm_destructive"), { danger: true }))) return;
        await del(`/api/seller/listings/${delId}`); toast(t("toast.deleted"), "info"); loadListings();
      }
    } catch (error) { toast(error.message, "error"); }
  });
}

function listingModal(listing) {
  const isNew = !listing;
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop open";
  backdrop.innerHTML = `
    <div class="modal modal-lg">
      <div class="modal-head">
        <div class="modal-title">${escapeHtml(isNew ? t("seller.new_listing") : t("seller.edit_listing"))}</div>
        <button class="modal-close" data-close>✕</button>
      </div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.listing_title"))} *</label>
        <input id="l-title" class="input" maxlength="200" value="${escapeHtml(listing?.title || "")}"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.listing_description"))}</label>
        <textarea id="l-desc" class="textarea" maxlength="4000">${escapeHtml(listing?.description || "")}</textarea></div>
      <div class="row gap-sm" style="align-items:start">
        <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("seller.listing_price"))} *</label>
          <input id="l-price" class="input" type="number" min="0.01" step="0.01" value="${escapeHtml(listing?.price || "")}"></div>
        <div class="field" style="flex:1"><label class="field-label">${escapeHtml(t("seller.delivery_type"))}</label>
          <select id="l-delivery" class="select">
            ${["MANUAL", "INSTANT", "ACCOUNT", "GIFT_CARD", "GAME_KEY"].map((d) => `<option value="${d}" ${listing?.delivery_type === d ? "selected" : ""}>${escapeHtml(t(`marketplace.delivery_type_${d}`))}</option>`).join("")}
          </select></div>
      </div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.images"))} URL (1/line)</label>
        <textarea id="l-images" class="textarea" style="min-height:70px">${escapeHtml((listing?.images || []).join("\n"))}</textarea></div>
      <div class="field"><label class="field-label">🔐 ${escapeHtml(t("seller.sensitive_data"))}</label>
        <textarea id="l-sensitive" class="textarea" style="min-height:70px" placeholder="${listing?.has_delivery_data ? "••• (saved)" : ""}"></textarea>
        <span class="field-hint">${escapeHtml(t("seller.sensitive_note"))}</span></div>
      <div class="row mt-2">
        <button class="btn" id="l-draft">${escapeHtml(t("seller.save_draft"))}</button>
        <button class="btn btn-primary" id="l-submit">${escapeHtml(t("seller.submit_review"))}</button>
      </div>
    </div>`;
  document.body.appendChild(backdrop);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop || e.target.dataset?.close !== undefined) backdrop.remove(); });

  async function save(submit) {
    const payload = {
      title: qs("#l-title", backdrop).value.trim(),
      description: qs("#l-desc", backdrop).value.trim(),
      price: qs("#l-price", backdrop).value,
      delivery_type: qs("#l-delivery", backdrop).value,
      images: qs("#l-images", backdrop).value.split("\n").map((s) => s.trim()).filter(Boolean),
      submit_for_review: submit,
    };
    const sensitive = qs("#l-sensitive", backdrop).value.trim();
    if (sensitive) payload.sensitive_delivery_data = sensitive;
    try {
      if (isNew) await post("/api/seller/listings", payload);
      else await put(`/api/seller/listings/${listing.id}`, payload);
      toast(submit ? t("seller.listing_submitted") : t("seller.listing_created"), "success");
      haptic("success");
      backdrop.remove();
      loadListings();
    } catch (error) { toast(error.message, "error"); }
  }
  qs("#l-draft", backdrop).addEventListener("click", () => save(false));
  qs("#l-submit", backdrop).addEventListener("click", () => save(true));
}

/* ---------- orders ---------- */
async function renderOrders() {
  root.innerHTML = `${head(t("seller.orders"))}<div id="so-list" class="stack" style="gap:0.6rem"></div><div id="so-pagination" class="pagination"></div>`;
  const list = qs("#so-list");
  const res = await get("/api/seller/orders?page_size=20");
  const items = res.data?.items || [];
  if (!items.length) { emptyState(list, "📦", t("seller.no_orders"), ""); return; }
  list.innerHTML = items.map(sellerOrderRow).join("");
  list.addEventListener("click", async (event) => {
    const deliverId = event.target.dataset?.deliver;
    if (!deliverId) return;
    const note = window.prompt(t("orders.delivery")) || "";
    try {
      await post(`/api/seller/orders/${deliverId}/delivered`, { note });
      toast(t("orders.delivery"), "success");
      renderOrders();
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- balance ---------- */
async function renderBalance() {
  const me = await loadProfile();
  root.innerHTML = `${head(t("seller.balance"))}
    <div class="card balance-card mb-3">
      <span class="label">${escapeHtml(t("seller.available_balance"))}</span>
      <div class="value" style="font-size:2rem">${escapeHtml(me.balance?.available || "0.00")} USD</div>
      <div class="balance-rows">
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.pending_balance"))}</div><div class="value">${escapeHtml(me.balance?.pending || "0.00")}</div></div>
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.reserved_balance"))}</div><div class="value">${escapeHtml(me.balance?.reserved || "0.00")}</div></div>
        <div class="balance-row"><div class="label">${escapeHtml(t("seller.lifetime_paid"))}</div><div class="value">${escapeHtml(me.balance?.lifetime_paid || "0.00")}</div></div>
      </div>
    </div>
    <p class="field-hint mb-3">⏳ ${escapeHtml(t("seller.holding_notice", { hours: me.holding_hours }))}</p>
    ${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("seller.balance"))}</h2><div id="tx-list" class="stack" style="gap:0.4rem"></div>`)}`;
  const res = await get("/api/seller/balance/transactions?page_size=50");
  const txs = res.data?.items || [];
  const txList = qs("#tx-list");
  if (!txs.length) { emptyState(txList, "💰", t("common.empty_text"), ""); return; }
  txList.innerHTML = txs.map((tx) => `
    <div class="card-inset row spread fs-sm">
      <div><b>${escapeHtml(tx.type)}</b><div class="text-mute fs-xs">${escapeHtml(tx.note || "")} · ${escapeHtml(fmtDate(tx.created_at))}</div></div>
      <div class="text-right">
        ${Number(tx.pending_delta) !== 0 ? `<div class="${Number(tx.pending_delta) > 0 ? "text-success" : "text-danger"}">pending ${Number(tx.pending_delta) > 0 ? "+" : ""}${escapeHtml(tx.pending_delta)}</div>` : ""}
        ${Number(tx.available_delta) !== 0 ? `<div class="${Number(tx.available_delta) > 0 ? "text-success" : "text-danger"}">available ${Number(tx.available_delta) > 0 ? "+" : ""}${escapeHtml(tx.available_delta)}</div>` : ""}
        ${Number(tx.reserved_delta) !== 0 ? `<div class="text-mute">reserved ${Number(tx.reserved_delta) > 0 ? "+" : ""}${escapeHtml(tx.reserved_delta)}</div>` : ""}
      </div>
    </div>`).join("");
}

/* ---------- payouts ---------- */
async function renderPayouts() {
  const me = await loadProfile();
  root.innerHTML = `${head(t("seller.payouts"))}
    ${card(`<h2 class="fw-800 mb-2">${escapeHtml(t("seller.request_payout"))}</h2>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.payout_amount"))} (min ${escapeHtml(me.min_payout)} USD · available ${escapeHtml(me.balance?.available || "0.00")})</label>
        <input id="po-amount" class="input" type="number" min="0.01" step="0.01"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.payout_method"))}</label>
        <select id="po-method" class="select"><option>CARD</option><option>PAYME</option><option>CLICK</option><option>USDT_TRC20</option><option>OTHER</option></select></div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.payout_details"))} *</label>
        <textarea id="po-details" class="textarea" style="min-height:70px" maxlength="500" placeholder="Card number / wallet / …"></textarea></div>
      <button id="po-submit" class="btn btn-primary">${escapeHtml(t("seller.request_payout"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-2">${escapeHtml(t("seller.payouts"))}</h3><div id="po-list" class="stack" style="gap:0.5rem"></div>`)}</div>`;

  qs("#po-submit").addEventListener("click", async () => {
    try {
      await post("/api/seller/payouts", {
        amount: qs("#po-amount").value,
        method: qs("#po-method").value,
        details: qs("#po-details").value.trim(),
        idempotency_key: idempotencyKey("payout"),
      });
      clearIdempotencyKey("payout");
      toast(t("seller.payout_requested"), "success");
      haptic("success");
      renderPayouts();
    } catch (error) { toast(error.message, "error"); }
  });

  const res = await get("/api/seller/payouts?page_size=50");
  const items = res.data?.items || [];
  const list = qs("#po-list");
  if (!items.length) { emptyState(list, "🏦", t("seller.no_payouts"), ""); return; }
  list.innerHTML = items.map((p) => `
    <div class="card-inset row spread fs-sm">
      <div><b>${escapeHtml(fmtMoney(p.amount, p.currency))}</b>
        <div class="text-mute fs-xs">${escapeHtml(p.method)} · ${escapeHtml(fmtDate(p.created_at))}</div>
        ${p.review_note ? `<div class="fs-xs text-danger">${escapeHtml(p.review_note)}</div>` : ""}</div>
      <span class="status-pill st-${escapeHtml(p.status)}">${escapeHtml(t(`seller.payout_status_${p.status}`) !== `seller.payout_status_${p.status}` ? t(`seller.payout_status_${p.status}`) : p.status)}</span>
    </div>`).join("");
}

/* ---------- promote ---------- */
async function renderPromote() {
  root.innerHTML = `${head(t("seller.promote_title"))}
    ${card(`<p class="text-soft mb-2">${escapeHtml(t("seller.premium_text"))}</p>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.listings"))}</label>
        <select id="pr-listing" class="select"></select></div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.promote"))}</label>
        <select id="pr-kind" class="select">
          <option value="FEATURED">⭐ ${escapeHtml(t("seller.promote_featured"))}</option>
          <option value="HOMEPAGE">🏠 ${escapeHtml(t("seller.promote_homepage"))}</option>
          <option value="SEARCH">🔍 ${escapeHtml(t("seller.promote_search"))}</option>
        </select></div>
      <button id="pr-buy" class="btn btn-gold">${escapeHtml(t("seller.promote_activate"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-2">${escapeHtml(t("seller.promoted"))}</h3><div id="pr-list" class="stack" style="gap:0.5rem"></div>`)}</div>`;

  const res = await get("/api/seller/listings?page_size=100");
  const approved = (res.data?.items || []).filter((l) => l.status === "APPROVED");
  qs("#pr-listing").innerHTML = approved.map((l) => `<option value="${escapeHtml(l.id)}">${escapeHtml(l.title)}</option>`).join("") || `<option value="">${escapeHtml(t("seller.no_listings"))}</option>`;
  const promoted = (res.data?.items || []).filter((l) => l.is_promoted);
  const list = qs("#pr-list");
  if (!promoted.length) emptyState(list, "⭐", t("promotions.empty"), "");
  else list.innerHTML = promoted.map((l) => `<div class="card-inset row spread fs-sm"><b>⭐ ${escapeHtml(l.title)}</b><span class="price">${escapeHtml(l.price)} ${escapeHtml(l.currency)}</span></div>`).join("");

  qs("#pr-buy").addEventListener("click", async () => {
    const listingId = qs("#pr-listing").value;
    if (!listingId) return;
    try {
      const result = await post("/api/seller/promotions", { listing_id: listingId, kind: qs("#pr-kind").value });
      const payment = result.data?.payment;
      if (payment?.checkout_url) window.location.href = payment.checkout_url;
      else toast(t("seller.promote_activate"), "success");
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- premium ---------- */
async function renderPremium() {
  root.innerHTML = `${head(t("seller.premium_title"))}<div id="plans" class="grid grid-3"></div>`;
  const res = await get("/api/seller/subscription/plans").catch(() => ({ data: [] }));
  const plans = res.data || [];
  const el = qs("#plans");
  if (!plans.length) { el.innerHTML = card(`<div class="empty-state"><b>${escapeHtml(t("common.coming_soon"))}</b><span>${escapeHtml(t("seller.premium_text"))}</span></div>`); return; }
  el.innerHTML = plans.map((p) => `
    <div class="card text-center">
      <h3 class="fw-800">${escapeHtml(p.name)}</h3>
      <div class="price" style="font-size:1.6rem">${escapeHtml(p.price)} ${escapeHtml(p.currency)}</div>
      <div class="text-mute fs-xs mb-2">/ ${p.period_days}d</div>
      <p class="text-soft fs-sm">${escapeHtml(p.description || "")}</p>
      <ul class="fs-sm text-soft mt-1" style="list-style:none">${(p.features || []).map((f) => `<li>✓ ${escapeHtml(f)}</li>`).join("")}</ul>
      <button class="btn btn-primary btn-block mt-2" data-plan="${escapeHtml(p.code)}">${escapeHtml(t("seller.subscribe"))}</button>
    </div>`).join("");
  el.addEventListener("click", async (event) => {
    const code = event.target.dataset?.plan;
    if (!code) return;
    try {
      const result = await post("/api/seller/subscription", { plan_code: code });
      const payment = result.data?.payment;
      if (payment?.checkout_url) window.location.href = payment.checkout_url;
      else toast(t("seller.subscribe"), "success");
    } catch (error) { toast(error.message, "error"); }
  });
}

/* ---------- settings ---------- */
async function renderSettings() {
  const me = await loadProfile();
  root.innerHTML = `${head(t("seller.settings"))}
    ${card(`
      <div class="field"><label class="field-label">${escapeHtml(t("seller.title"))}</label>
        <input id="s-name" class="input" maxlength="120" value="${escapeHtml(me.display_name || "")}"></div>
      <div class="field"><label class="field-label">${escapeHtml(t("seller.listing_description"))}</label>
        <textarea id="s-desc" class="textarea">${escapeHtml(me.description || "")}</textarea></div>
      <div class="field"><label class="field-label">${escapeHtml(t("dashboard.avatar"))} URL</label>
        <input id="s-avatar" class="input" maxlength="500" value="${escapeHtml(me.avatar_url || "")}"></div>
      <p class="field-hint mb-2">💳 ${escapeHtml(t("seller.commission_note", { pct: me.commission_pct }))}</p>
      <button id="s-save" class="btn btn-primary">${escapeHtml(t("common.save"))}</button>`)}
    <div class="mt-3">${card(`<h3 class="fw-800 mb-1">🔗 @${escapeHtml(me.username)}</h3>
      <a class="btn btn-block mt-1" href="/sellers/${escapeHtml(me.username)}" target="_blank">${escapeHtml(t("common.open"))} →</a>`)}</div>`;

  qs("#s-save").addEventListener("click", async () => {
    try {
      await put("/api/seller/me", {
        display_name: qs("#s-name").value.trim(),
        description: qs("#s-desc").value.trim(),
        avatar_url: qs("#s-avatar").value.trim() || null,
      });
      toast(t("dashboard.settings_saved"), "success");
    } catch (error) { toast(error.message, "error"); }
  });
}

const routes = {
  overview: renderOverview,
  listings: renderListings,
  orders: renderOrders,
  balance: renderBalance,
  payouts: renderPayouts,
  promote: renderPromote,
  premium: renderPremium,
  settings: renderSettings,
};

(async () => {
  try {
    await (routes[section] || renderOverview)();
  } catch (error) {
    if (error.code === "NOT_A_SELLER") { window.location.href = "/seller"; return; }
    root.innerHTML = card(`<div class="empty-state"><div class="icon">⛔</div><b>${escapeHtml(t("common.error_title"))}</b><span>${escapeHtml(error.message)}</span></div>`);
  }
})();
