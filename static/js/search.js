/* Global search page. */
import { get, qs, toast, t, escapeHtml, emptyState } from "/static/js/core.js";

const input = qs("#search-input");
const results = qs("#search-results");

function section(title, rows) {
  if (!rows.length) return "";
  return `<div class="card"><h3 class="fw-800 mb-2">${escapeHtml(title)}</h3><div class="stack" style="gap:0.5rem">${rows.join("")}</div></div>`;
}

async function run() {
  const q = input.value.trim();
  if (q.length < 2) {
    results.innerHTML = `<div class="card empty-state"><div class="icon">🔍</div><b>${escapeHtml(t("search.hint"))}</b></div>`;
    return;
  }
  results.innerHTML = `<div class="loading-overlay"><span class="spinner"></span>${escapeHtml(t("common.loading"))}</div>`;
  try {
    const res = await get(`/api/search?q=${encodeURIComponent(q)}`);
    const data = res.data || {};
    const games = (data.games || []).map((g) =>
      `<a class="card-inset row spread" href="/games/${escapeHtml(g.slug)}" style="text-decoration:none;color:inherit"><b>🎮 ${escapeHtml(g.name)}</b><span class="text-mute fs-xs">→</span></a>`);
    const products = (data.products || []).map((p) =>
      `<a class="card-inset row spread" href="/products/${escapeHtml(p.slug)}" style="text-decoration:none;color:inherit"><b>🕹️ ${escapeHtml(p.name)}</b><span class="price">${p.from_price ? `${escapeHtml(p.from_price)} ${escapeHtml(p.currency)}` : ""}</span></a>`);
    const listings = (data.listings || []).map((l) =>
      `<a class="card-inset row spread" href="/marketplace/listing/${escapeHtml(l.id)}" style="text-decoration:none;color:inherit"><b>🛍️ ${escapeHtml(l.title)}</b><span class="price">${escapeHtml(l.price)} ${escapeHtml(l.currency)}</span></a>`);
    const sellers = (data.sellers || []).map((s) =>
      `<a class="card-inset row spread" href="/sellers/${escapeHtml(s.username)}" style="text-decoration:none;color:inherit"><b>🏪 ${escapeHtml(s.display_name)}</b><span class="text-mute fs-xs">⭐ ${escapeHtml(s.rating)}</span></a>`);

    const html = [
      section(t("search.games"), games),
      section(t("search.products"), products),
      section(t("search.listings"), listings),
      section(t("search.sellers"), sellers),
    ].join("");
    results.innerHTML = html || `<div class="card empty-state"><div class="icon">🔍</div><b>${escapeHtml(t("search.no_results"))}</b><span>${escapeHtml(t("search.hint"))}</span></div>`;
  } catch (error) {
    emptyState(results, "⛔", t("common.error_title"), error.message);
  }
}

let debounce;
input.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(run, 300); });
run();
