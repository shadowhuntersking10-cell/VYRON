/* VYRON Telegram Mini App — bottom nav, initData auth, mobile-first flows. */
import { get, post, qs, qsa, toast, t, escapeHtml, fmtMoney, fmtDate, statusPill, haptic, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

const tg = window.Telegram?.WebApp;
let me = null;
let isAdmin = false;

/* ---------- boot & auth ---------- */
function applyI18nStatic() {
  qsa("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  qsa("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}

async function boot() {
  try { tg?.ready(); tg?.expand(); } catch (_) {}
  applyI18nStatic();

  // Try existing session first (works in browsers & returning WebViews).
  try {
    const res = await get("/api/auth/me");
    if (res.data) { me = res.data; isAdmin = !!res.data.is_admin; onAuthed(); return; }
  } catch (_) {}

  // Otherwise authenticate with Telegram initData (HMAC-verified server-side).
  const initData = tg?.initData;
  if (!initData) {
    qs("#ma-boot").innerHTML = `<div class="empty-state"><div class="icon">📱</div><b>${escapeHtml(t("miniapp.guest"))}</b>
      <a class="btn btn-primary mt-2" href="/login">${escapeHtml(t("nav.login"))}</a></div>`;
    return;
  }
  try {
    const res = await post("/api/telegram/auth", { init_data: initData });
    me = res.data;
    isAdmin = !!me.is_admin;
    onAuthed();
  } catch (error) {
    qs("#ma-boot").innerHTML = `<div class="empty-state"><div class="icon">⛔</div><b>${escapeHtml(error.message)}</b></div>`;
  }
}

function onAuthed() {
  qs("#ma-boot").classList.add("hidden");
  qs("#ma-home").classList.remove("hidden");
  qs("#ma-user").textContent = `@${me.username}`;
  qs("#ma-greeting").textContent = t("miniapp.greeting", { name: me.name || me.username });
  if (isAdmin) qs("#ma-admin-zone").classList.remove("hidden");
  loadHome();
}

async function loadHome() {
  const [games, orders] = await Promise.all([
    get("/api/games?featured=true&page_size=6").catch(() => ({ data: { items: [] } })),
    me ? get("/api/orders?page_size=3").catch(() => ({ data: { items: [], total: 0 } })) : { data: { items: [], total: 0 } },
  ]);
  let items = games.data?.items || [];
  if (!items.length) {
    const all = await get("/api/games?page_size=6").catch(() => ({ data: { items: [] } }));
    items = all.data?.items || [];
  }
  qs("#ma-stat-games").textContent = games.data?.total ?? items.length;
  qs("#ma-stat-orders").textContent = orders.data?.total ?? 0;
  qs("#ma-featured").innerHTML = items.map(gameCard).join("") || `<div class="empty-state"><b>${escapeHtml(t("games.empty"))}</b></div>`;
  bindGameCards(qs("#ma-featured"));
}

function gameCard(game) {
  return `<div class="ma-game" data-game="${escapeHtml(game.slug)}">
    <div class="thumb">${game.logo_url ? `<img src="${escapeHtml(game.logo_url)}" alt="" loading="lazy">` : "🎮"}</div>
    <div class="body"><b class="fs-sm truncate" style="display:block">${escapeHtml(game.name)}</b></div>
  </div>`;
}

function bindGameCards(container) {
  container.querySelectorAll("[data-game]").forEach((el) => {
    el.addEventListener("click", () => { haptic("light"); openGame(el.dataset.game); });
  });
}

async function openGame(slug) {
  switchView("games");
  const list = qs("#ma-games-list");
  list.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
  const res = await get(`/api/games/${slug}`);
  const game = res.data;
  list.innerHTML = `<button class="btn btn-sm mb-2" id="ma-back-games">← ${escapeHtml(t("common.back"))}</button>
    <div class="card mb-2"><b>${escapeHtml(game.name)}</b>${game.description ? `<p class="fs-sm text-soft mt-1">${escapeHtml(game.description.slice(0, 160))}</p>` : ""}</div>
    ${(game.products || []).map((p) => `
      <div class="card mb-2" data-product="${escapeHtml(p.slug)}">
        <b class="fs-sm">${escapeHtml(p.name)}</b>
        <div class="text-mute fs-xs">${escapeHtml(t("products.type_" + p.type))}</div>
        <div class="ma-variants">
          ${(p.variants || []).slice(0, 6).map((v) => `<span class="chip ma-variant" data-buy="${escapeHtml(v.id)}" data-price="${escapeHtml(v.selling_price)}" data-name="${escapeHtml(v.name)}">${escapeHtml(v.name)} · ${escapeHtml(v.selling_price)}</span>`).join("")}
        </div>
      </div>`).join("") || `<div class="empty-state"><b>${escapeHtml(t("products.empty"))}</b></div>`}`;
  qs("#ma-back-games").addEventListener("click", () => loadGamesList());
  list.querySelectorAll("[data-buy]").forEach((chip) => chip.addEventListener("click", () => quickBuy(chip, game)));
}

async function quickBuy(chip, game) {
  if (!me) { toast(t("checkout.login_required"), "info"); return; }
  haptic("medium");
  const productEl = chip.closest("[data-product]");
  const productSlug = productEl?.dataset.product;
  let requiredFields = [];
  try {
    const prod = await get(`/api/products/${productSlug}`);
    requiredFields = prod.data?.required_fields || [];
  } catch (_) {}

  const values = {};
  for (const field of requiredFields.filter((f) => f.required)) {
    const value = window.prompt(`${field.label || field.key}${field.placeholder ? ` (${field.placeholder})` : ""}`);
    if (!value) { toast(t("checkout.required_field_missing"), "error"); return; }
    values[field.key] = value;
  }
  chip.classList.add("selected");
  try {
    const result = await post("/api/checkout/buy-now", {
      variant_id: chip.dataset.buy,
      quantity: 1,
      required_field_values: values,
      idempotency_key: idempotencyKey(`ma-${chip.dataset.buy}`),
    });
    clearIdempotencyKey(`ma-${chip.dataset.buy}`);
    haptic("success");
    let payment = result.data?.payment;
    const order = result.data?.order;
    if (!payment?.checkout_url && order?.id) {
      try {
        const providers = await get("/api/payment-providers");
        const provider = order.payment_provider || providers.data?.[0]?.name;
        if (!provider) throw new Error(t("errors.PAYMENT_PROVIDER_NOT_CONFIGURED"));
        const payRes = await post(`/api/orders/${order.id}/pay`, { provider });
        payment = payRes.data?.payment;
      } catch (payError) {
        toast(payError.message, "error");
        switchView("orders"); loadOrders();
        return;
      }
    }
    if (payment?.checkout_url) {
      toast(t("checkout.redirecting"), "info");
      if (tg?.openLink) tg.openLink(payment.checkout_url, { try_instant_view: false });
      else window.open(payment.checkout_url, "_blank");
    } else {
      toast(t("toast.order_created"), "success");
      switchView("orders"); loadOrders();
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    chip.classList.remove("selected");
  }
}

async function loadGamesList() {
  const list = qs("#ma-games-list");
  list.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
  const res = await get("/api/games?page_size=50");
  const items = res.data?.items || [];
  list.innerHTML = items.map((g) => `
    <div class="card row gap-sm" data-game="${escapeHtml(g.slug)}" style="cursor:pointer">
      <div style="width:52px;height:52px;border-radius:14px;background:var(--surface-3);display:grid;place-items:center;font-size:1.5rem;overflow:hidden;flex-shrink:0">
        ${g.logo_url ? `<img src="${escapeHtml(g.logo_url)}" alt="" style="width:100%;height:100%;object-fit:cover">` : "🎮"}
      </div>
      <div><b class="fs-sm">${escapeHtml(g.name)}</b><div class="text-mute fs-xs">${escapeHtml(t("games.top_up"))}</div></div>
    </div>`).join("") || `<div class="empty-state"><b>${escapeHtml(t("games.empty"))}</b></div>`;
  list.querySelectorAll("[data-game]").forEach((el) => el.addEventListener("click", () => { haptic("light"); openGame(el.dataset.game); }));
}

async function loadOrders() {
  const list = qs("#ma-orders");
  if (!me) { list.innerHTML = `<div class="empty-state"><b>${escapeHtml(t("checkout.login_required"))}</b></div>`; return; }
  list.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
  const res = await get("/api/orders?page_size=20");
  const items = res.data?.items || [];
  list.innerHTML = items.map((o) => `
    <div class="card">
      <div class="row spread">
        <b class="mono fs-sm">${escapeHtml(o.number)}</b>
        ${statusPill(o.status)}
      </div>
      <div class="text-mute fs-xs mt-1">${escapeHtml(fmtDate(o.created_at))} · ${o.items?.length || 0} ${escapeHtml(t("orders.items"))}</div>
      <div class="row spread mt-1">
        <span class="fs-xs text-soft truncate">${escapeHtml((o.items || []).map((i) => i.product_name).join(", ").slice(0, 60))}</span>
        <b class="price fs-sm">${escapeHtml(o.total)} ${escapeHtml(o.currency)}</b>
      </div>
    </div>`).join("") || `<div class="empty-state"><div class="icon">📦</div><b>${escapeHtml(t("miniapp.no_orders"))}</b></div>`;
}

async function loadProfile() {
  const el = qs("#ma-profile");
  if (!me) {
    el.innerHTML = `<div class="empty-state"><b>${escapeHtml(t("miniapp.guest"))}</b>
      <a class="btn btn-primary mt-2" href="/login">${escapeHtml(t("nav.login"))}</a></div>`;
    return;
  }
  el.innerHTML = `
    <div class="card text-center">
      <div class="creator-avatar">${me.avatar_url ? `<img src="${escapeHtml(me.avatar_url)}" alt="">` : escapeHtml((me.name || me.username)[0].toUpperCase())}</div>
      <b>${escapeHtml(me.name || me.username)}</b>
      <div class="text-mute fs-sm">@${escapeHtml(me.username)}</div>
      <div class="mt-1">${escapeHtml(me.email)}</div>
      <div class="mt-1"><span class="badge">${escapeHtml(me.role)}</span> ${me.email_verified ? '<span class="badge badge-green">✓ email</span>' : ""} ${me.telegram_connected ? '<span class="badge">✈️ telegram</span>' : ""}</div>
    </div>
    ${isAdmin ? `<a class="btn btn-block btn-gold mt-2" href="/admin" target="_blank">🛡️ ${escapeHtml(t("miniapp.admin_panel"))}</a>` : ""}
    <a class="btn btn-block mt-2" href="/dashboard" target="_blank">🌐 ${escapeHtml(t("nav.dashboard"))}</a>
    <a class="btn btn-block mt-2" href="/seller" target="_blank">🏪 ${escapeHtml(t("nav.seller_area"))}</a>
    <button class="btn btn-block btn-danger mt-2" id="ma-logout">🚪 ${escapeHtml(t("nav.logout"))}</button>`;
  qs("#ma-logout").addEventListener("click", async () => {
    try { await post("/api/auth/logout"); } catch (_) {}
    me = null; isAdmin = false;
    window.location.reload();
  });
}

function switchView(name) {
  qsa(".ma-view").forEach((v) => v.classList.remove("active"));
  qs(`#view-${name}`)?.classList.add("active");
  qsa(".bottom-nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  haptic("light");
  if (name === "games" && !qs("#ma-games-list").innerHTML.trim()) loadGamesList();
  if (name === "orders") loadOrders();
  if (name === "profile") loadProfile();
}

qsa(".bottom-nav button").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

qs("#ma-search")?.addEventListener("input", (event) => {
  const q = event.target.value.trim().toLowerCase();
  qsa("#ma-games-list [data-game]").forEach((el) => {
    el.style.display = !q || el.textContent.toLowerCase().includes(q) ? "" : "none";
  });
});

if (tg) {
  tg.setHeaderColor?.("#0b1220");
  tg.setBackgroundColor?.("#0b1220");
}

boot();
