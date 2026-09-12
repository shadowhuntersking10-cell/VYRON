/* Marketplace browsing: search/sort/game filters via the public API (progressive enhancement over SSR). */
import { get, qs, escapeHtml, t, skeletonCards, emptyState, haptic } from "/static/js/core.js";

const grid = qs("#listing-grid");
const pagination = qs("#mq-pagination");
let currentPage = 1;

function listingCard(listing) {
  const image = listing.images?.length
    ? `<img src="${escapeHtml(listing.images[0])}" alt="${escapeHtml(listing.title)}" loading="lazy">`
    : "🛍️";
  return `
  <a class="card card-hover listing-card" href="/marketplace/listing/${escapeHtml(listing.id)}">
    ${listing.is_promoted ? `<span class="promoted-flag">⭐ ${escapeHtml(t("seller.promoted"))}</span>` : ""}
    <div class="thumb">${image}</div>
    <div class="name truncate mt-1 fw-800">${escapeHtml(listing.title)}</div>
    <div class="text-mute fs-xs truncate">${escapeHtml(t("marketplace.seller"))}: ${escapeHtml(listing.seller?.display_name || "")}</div>
    <div class="meta row spread mt-1">
      <span class="price">${escapeHtml(listing.price)} ${escapeHtml(listing.currency)}</span>
      <span class="badge badge-gold">${escapeHtml(t(`marketplace.delivery_type_${listing.delivery_type}`))}</span>
    </div>
  </a>`;
}

function renderPagination(page, pages) {
  if (pages <= 1) { pagination.innerHTML = ""; return; }
  let html = "";
  html += `<button data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>←</button>`;
  const from = Math.max(1, page - 2);
  const to = Math.min(pages, from + 4);
  for (let p = from; p <= to; p++) {
    html += `<button data-page="${p}" class="${p === page ? "active" : ""}">${p}</button>`;
  }
  html += `<button data-page="${page + 1}" ${page >= pages ? "disabled" : ""}>→</button>`;
  pagination.innerHTML = html;
}

pagination.addEventListener("click", (event) => {
  const page = Number(event.target.dataset?.page);
  if (page) { currentPage = page; load(); haptic("light"); }
});

async function load() {
  const params = new URLSearchParams({ page: String(currentPage), page_size: "24" });
  const q = qs("#mq-search").value.trim();
  const sort = qs("#mq-sort").value;
  const game = qs("#mq-game").value;
  if (q) params.set("q", q);
  if (sort) params.set("sort", sort);
  if (game) params.set("game_id", game);
  skeletonCards(grid, 8, "");
  grid.classList.add("grid-4");
  try {
    const result = await get(`/api/marketplace/listings?${params}`);
    const items = result.data.items || [];
    if (!items.length) {
      grid.innerHTML = "";
      emptyState(grid, "🛍️", t("marketplace.empty"), t("common.no_results"));
    } else {
      grid.innerHTML = items.map(listingCard).join("");
    }
    renderPagination(result.data.page, result.data.pages);
  } catch (error) {
    grid.innerHTML = "";
    emptyState(grid, "⛔", t("common.error_title"), error.message);
  }
}

let debounce;
qs("#mq-search").addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => { currentPage = 1; load(); }, 350); });
qs("#mq-sort").addEventListener("change", () => { currentPage = 1; load(); });
qs("#mq-game").addEventListener("change", () => { currentPage = 1; load(); });
