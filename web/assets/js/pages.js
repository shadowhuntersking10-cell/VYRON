/* VYRON public pages: home, catalog, game, cart, checkout, orders, account, support, auth. */
import { api, tgInitData } from "./api.js";
import { getLang, setLang, t, tStatus } from "./i18n.js";
import {
  el, emptyState, fmtDate, fmtMoney, modal, pager, skeletonGrid, statusPill,
  toast, withLoading,
} from "./ui.js";

/* ------------------------------------------------------------------ HOME */
export async function renderHome(view) {
  const lang = getLang();
  view.append(el("div", { class: "grid", style: "gap:14px" }, skeletonGrid(8)));
  view.innerHTML = "";

  const [gamesRes, productsRes, promoRes, supplierRes, infoRes] = await Promise.all([
    api.get(`/api/games?featured=true&lang=${lang}&page_size=8`).catch(() => ({ items: [] })),
    api.get(`/api/products?lang=${lang}&page_size=8`).catch(() => ({ items: [] })),
    api.get(`/api/promotions?lang=${lang}`).catch(() => ({ items: [] })),
    api.get("/api/supplier-status").catch(() => ({})),
    api.get(`/api/support/info?lang=${lang}`).catch(() => ({})),
  ]);

  // Hero
  view.append(
    el(
      "section",
      { class: "hero" },
      el("div", { class: "pill info", style: "margin-bottom:14px" }, t("hero_kicker")),
      el("h1", {}, `${t("hero_title_a")} `, el("span", { class: "accent" }, t("hero_title_b"))),
      el("p", {}, t("hero_sub")),
      el(
        "div",
        { class: "hero-cta" },
        el("a", { class: "btn btn-primary", href: "#/games" }, t("hero_cta_games")),
        el("a", { class: "btn btn-soft", href: "#/support" }, t("hero_cta_support")),
      ),
      el(
        "div",
        { class: "hero-stats" },
        el("div", { class: "hero-stat" }, el("b", {}, "40+"), el("span", {}, t("hero_stat_games"))),
        el("div", { class: "hero-stat" }, el("b", {}, "⚡ AUTO"), el("span", {}, t("hero_stat_auto"))),
        el("div", { class: "hero-stat" }, el("b", {}, "UZ · EN · RU"), el("span", {}, t("hero_stat_langs"))),
        el("div", { class: "hero-stat" }, el("b", {}, "24/7"), el("span", {}, t("hero_stat_support"))),
      ),
    ),
  );

  // Announcement
  if (infoRes.announcement) {
    view.append(el("div", { class: "announce" }, `📢 ${infoRes.announcement}`));
  }

  // Supplier honesty banner
  view.append(
    el(
      "div",
      { class: "announce" },
      supplierRes.automated_fulfillment ? `✅ ${t("supplier_banner_auto")}` : `ℹ️ ${t("supplier_banner_off")}`,
    ),
  );

  // Featured games
  if (gamesRes.items?.length) {
    view.append(
      el(
        "section",
        { class: "section" },
        el(
          "div",
          { class: "section-head" },
          el("h2", {}, t("featured_games")),
          el("a", { href: "#/games" }, t("view_all")),
        ),
        el("div", { class: "grid grid-auto" }, gamesRes.items.map(gameCard)),
      ),
    );
  }

  // Categories
  const cats = [
    ["mobile", "cat_mobile", "📱"],
    ["pc", "cat_pc", "💻"],
    ["console", "cat_console", "🎮"],
    ["gift-cards", "cat_gift", "🎁"],
    ["digital", "cat_digital", "💠"],
  ];
  view.append(
    el(
      "section",
      { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, t("categories"))),
      el(
        "div",
        { class: "grid grid-auto" },
        cats.map(([slug, key, ico]) =>
          el(
            "a",
            { class: "soft-card hoverable", href: `#/games?category=${slug}`, style: "padding:18px" },
            el("div", { style: "font-size:1.5rem" }, ico),
            el("h3", { style: "margin-top:8px;font-size:.98rem" }, t(key)),
          ),
        ),
      ),
    ),
  );

  // Popular products
  const sellable = (productsRes.items || []).filter((p) => p.available);
  const shown = sellable.length ? productsRes.items : productsRes.items || [];
  view.append(
    el(
      "section",
      { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, t("popular_products"))),
      sellable.length
        ? el("div", { class: "grid grid-auto" }, shown.map(productCard))
        : el("div", { class: "empty" }, el("div", { class: "big" }, "🛒"), t("no_products_yet"), el("p", { class: "muted small", style: "margin-top:8px" }, t("catalog_sync_note"))),
    ),
  );

  // Promotions
  if (promoRes.items?.length) {
    view.append(
      el(
        "section",
        { class: "section" },
        el("div", { class: "section-head" }, el("h2", {}, t("promotions"))),
        el(
          "div",
          { class: "grid grid-2" },
          promoRes.items.map((p) =>
            el(
              "div",
              { class: "soft-card hoverable promo-card" },
              p.image_url
                ? el("img", { src: p.image_url, alt: p.title })
                : el("div", { class: "art", style: "width:130px;height:88px;border-radius:18px;background:linear-gradient(135deg,#0D3B66,#4DA8DA)" }),
              el(
                "div",
                {},
                el("h3", { style: "font-size:1rem" }, p.title),
                p.description ? el("p", { class: "muted small", style: "margin:4px 0" }, p.description) : null,
                p.coupon_code
                  ? el("button", {
                      class: "chip active",
                      onclick: () => {
                        navigator.clipboard?.writeText(p.coupon_code);
                        toast(`${p.coupon_code} ✓`, "ok");
                      },
                    }, `🎫 ${p.coupon_code}`)
                  : null,
              ),
            ),
          ),
        ),
      ),
    );
  }

  // Trust
  view.append(
    el(
      "section",
      { class: "section" },
      el("div", { class: "section-head" }, el("h2", {}, t("trust_title"))),
      el(
        "div",
        { class: "trust-grid" },
        trustCard("🛡️", "trust_secure_t", "trust_secure_d"),
        trustCard("⚡", "trust_fast_t", "trust_fast_d"),
        trustCard("💬", "trust_support_t", "trust_support_d"),
        trustCard("✅", "trust_real_t", "trust_real_d"),
      ),
    ),
  );
}

function trustCard(icon, titleKey, descKey) {
  return el(
    "div",
    { class: "soft-card hoverable trust-card" },
    el("div", { class: "ico-lg" }, icon),
    el("h3", {}, t(titleKey)),
    el("p", {}, t(descKey)),
  );
}

export function gameCard(game) {
  return el(
    "a",
    { class: "soft-card hoverable game-card", href: `#/game/${game.slug}` },
    el(
      "div",
      { class: "art" },
      game.banner_url || game.icon_url ? el("img", { src: game.banner_url || game.icon_url, alt: game.name, loading: "lazy" }) : null,
      el("span", { class: `pill ${game.available ? "ok" : ""}` }, game.available ? t("available") : t("currently_unavailable")),
    ),
    el(
      "div",
      { class: "body" },
      el("h3", {}, game.name),
      el("div", { class: "meta" }, game.currency_label ? `🪙 ${game.currency_label}` : ""),
    ),
  );
}

export function productCard(product) {
  const minPrice = product.variants?.filter((v) => v.price != null).map((v) => v.price).sort((a, b) => a - b)[0];
  return el(
    "a",
    {
      class: "soft-card hoverable product-card",
      href: product.game ? `#/game/${product.game.slug}` : "#/games",
    },
    el(
      "div",
      { class: "art" },
      product.image_url ? el("img", { src: product.image_url, alt: product.name, loading: "lazy" }) : null,
    ),
    el(
      "div",
      { class: "body" },
      el("h3", {}, product.name),
      product.game ? el("div", { class: "muted small" }, product.game.name) : null,
      el(
        "div",
        { class: "price-row" },
        product.available && minPrice != null
          ? el("span", { class: "price" }, `${t("from_price")} ${fmtMoney(minPrice, product.variants[0]?.currency)}`)
          : el("span", { class: "price na" }, t("not_available")),
        el("span", { class: `pill ${product.available ? "ok" : ""}` }, product.available ? "🛒" : "—"),
      ),
    ),
  );
}

/* ------------------------------------------------------------ GAMES LIST */
export async function renderGames(view, params) {
  const lang = getLang();
  view.innerHTML = "";
  view.append(
    el(
      "div",
      { class: "page-head" },
      el("div", {}, el("h1", { class: "page-title" }, t("nav_games")), el("p", { class: "page-sub" }, t("catalog_sync_note"))),
    ),
  );
  const grid = el("div", { class: "grid grid-auto" }, skeletonGrid(8));
  const pagerSlot = el("div");
  view.append(grid, pagerSlot);

  const state = {
    page: Number(params.page) || 1,
    category: params.category || "",
    search: params.search || "",
  };

  const filters = el(
    "div",
    { class: "toolbar", style: "margin-bottom:18px" },
    ...["", "mobile", "pc", "console", "gift-cards", "digital"].map((cat) =>
      el("button", {
        class: `chip ${state.category === cat ? "active" : ""}`,
        onclick: (e) => {
          state.category = cat;
          state.page = 1;
          e.target.parentElement.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
          e.target.classList.add("active");
          load();
        },
      }, cat === "" ? t("all") : t(`cat_${cat.replace("-cards", "").replace("-", "")}`)),
    ),
  );
  view.insertBefore(filters, grid);

  async function load() {
    grid.innerHTML = "";
    grid.append(skeletonGrid(8));
    const q = new URLSearchParams({ lang, page: state.page, page_size: 24 });
    if (state.category) q.set("category", state.category);
    if (state.search) q.set("search", state.search);
    const res = await api.get(`/api/games?${q}`);
    grid.innerHTML = "";
    if (!res.items.length) {
      grid.append(emptyState("🎮", t("nav_games"), t("no_products_yet")));
    } else {
      grid.append(...res.items.map(gameCard));
    }
    pagerSlot.innerHTML = "";
    pagerSlot.append(pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }));
  }
  await load();
}

/* ------------------------------------------------------------- GAME PAGE */
export async function renderGame(view, slug) {
  const lang = getLang();
  view.innerHTML = "";
  let game;
  try {
    ({ game } = await api.get(`/api/games/${encodeURIComponent(slug)}?lang=${lang}`));
  } catch {
    view.append(emptyState("🔍", t("game_not_found")));
    return;
  }

  view.append(
    el(
      "div",
      { class: "game-hero" },
      game.banner_url ? el("img", { src: game.banner_url, alt: game.name }) : el("div", { style: "height:240px;background:linear-gradient(135deg,#0B2447,#4DA8DA)" }),
      el(
        "div",
        { class: "overlay" },
        el("h1", {}, game.name),
        game.currency_label ? el("div", { class: "currency-tag" }, `🪙 ${game.currency_label}`) : null,
      ),
    ),
  );
  if (game.description) {
    view.append(el("p", { class: "muted", style: "max-width:760px;margin-bottom:22px" }, game.description));
  }

  const products = game.products || [];
  for (const product of products) {
    view.append(productBuyPanel(product, game));
  }
  if (!products.length) {
    view.append(emptyState("🛒", t("no_products_yet"), t("catalog_sync_note")));
  }

  // FAQ
  try {
    const { items } = await api.get(`/api/support/faq?lang=${lang}`);
    view.append(
      el(
        "section",
        { class: "section" },
        el("div", { class: "section-head" }, el("h2", {}, t("faq"))),
        el(
          "div",
          { class: "soft-card" },
          el("h4", { style: "margin-bottom:8px" }, t("how_to_buy")),
          el("p", { class: "muted small", style: "margin-bottom:14px" }, t("how_to_buy_text")),
          ...items.slice(0, 4).map((f) =>
            el("div", { class: "faq-item" }, el("h4", {}, f.question), el("p", {}, f.answer)),
          ),
        ),
      ),
    );
  } catch {
    /* faq optional */
  }
}

function productBuyPanel(product, game) {
  let selected = null;
  const fields = product.required_fields || [];
  const inputs = {};
  const priceNode = el("div", { class: "price" }, t("select_variant_first"));
  const errNode = el("div", { class: "form-error" });

  const variantList = el(
    "div",
    { class: "variant-list" },
    product.variants.map((v) => {
      const btn = el(
        "button",
        {
          class: "variant-chip",
          disabled: !v.available,
          onclick: () => {
            selected = v;
            variantList.querySelectorAll(".variant-chip").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            priceNode.textContent = fmtMoney(v.price, v.currency);
          },
        },
        el("span", {}, v.name),
        el("small", {}, v.available ? fmtMoney(v.price, v.currency) : t("unavailable")),
      );
      return btn;
    }),
  );

  const form = el(
    "div",
    {},
    fields.map((f) => {
      const input = el("input", {
        class: "input",
        id: `pf-${product.id}-${f.key}`,
        type: f.type === "number" ? "text" : "text",
        inputmode: f.type === "number" ? "numeric" : "text",
        required: !!f.required,
      });
      inputs[f.key] = input;
      return el(
        "div",
        { class: "field" },
        el("label", { for: input.id }, `${f.label || f.key}${f.required ? " *" : ""}`),
        input,
      );
    }),
    el("p", { class: "muted small" }, t("player_info_hint")),
  );

  const buyBtn = el("button", { class: "btn btn-primary btn-block" }, t("add_to_cart"));
  buyBtn.addEventListener(
    "click",
    withLoading(buyBtn, async () => {
      errNode.textContent = "";
      if (!selected) {
        errNode.textContent = t("select_variant_first");
        return;
      }
      const player_info = {};
      for (const f of fields) {
        const value = inputs[f.key].value.trim();
        if (f.required && !value) {
          errNode.textContent = `${t("missing_field")}: ${f.label || f.key}`;
          inputs[f.key].classList.add("invalid");
          return;
        }
        inputs[f.key].classList.remove("invalid");
        if (value) player_info[f.key] = value;
      }
      try {
        await api.post("/api/cart/items", {
          variant_id: selected.id,
          quantity: 1,
          player_info,
        });
        toast(t("added_to_cart"), "ok");
        document.dispatchEvent(new CustomEvent("cart:changed"));
      } catch (err) {
        errNode.textContent = err.message;
      }
    }),
  );

  return el(
    "section",
    { class: "section" },
    el(
      "div",
      { class: "grid grid-2", style: "align-items:start" },
      el(
        "div",
        { class: "soft-card" },
        el("h2", { style: "font-size:1.15rem;margin-bottom:6px" }, product.name),
        el("span", { class: `pill ${product.available ? "ok" : "warn"}` }, product.available ? t("available") : t("currently_unavailable")),
        product.description ? el("p", { class: "muted small", style: "margin:12px 0" }, product.description) : null,
        el("h4", { style: "margin:14px 0 10px" }, t("choose_variant")),
        variantList,
      ),
      el(
        "div",
        { class: "soft-card buy-panel" },
        el("h3", { style: "margin-bottom:6px" }, t("player_info")),
        form,
        el("div", { class: "summary-row total" }, t("price"), priceNode),
        errNode,
        el("div", { style: "margin-top:10px" }, buyBtn),
        product.available ? null : el("p", { class: "muted small", style: "margin-top:10px" }, t("no_products_yet")),
      ),
    ),
  );
}

/* ----------------------------------------------------------------- CART */
export async function renderCart(view) {
  view.innerHTML = "";
  view.append(el("div", { class: "page-head" }, el("h1", { class: "page-title" }, t("cart_title"))));
  let data;
  try {
    data = await api.get("/api/cart");
  } catch {
    view.append(emptyState("🔒", t("unauthorized")));
    view.append(el("div", { style: "text-align:center;margin-top:14px" }, el("a", { class: "btn btn-primary", href: "#/login" }, t("login"))));
    return;
  }
  const cart = data.cart;
  if (!cart.items.length) {
    view.append(emptyState("🛒", t("cart_empty"), t("cart_empty_sub")));
    view.append(el("div", { style: "text-align:center;margin-top:14px" }, el("a", { class: "btn btn-primary", href: "#/games" }, t("hero_cta_games"))));
    return;
  }

  const list = el("div", {});
  for (const item of cart.items) {
    list.append(
      el(
        "div",
        { class: "soft-card cart-item" },
        item.product?.image_url ? el("img", { src: item.product.image_url, alt: "" }) : el("div", {}),
        el(
          "div",
          {},
          el("h3", { style: "font-size:.95rem" }, `${item.product?.name || ""} — ${item.variant?.name || ""}`),
          el("div", { class: "muted small" }, item.game?.name || ""),
          !item.available ? el("span", { class: "pill err", style: "margin-top:6px" }, t("unavailable")) : null,
          el(
            "div",
            { class: "qty-controls", style: "margin-top:8px" },
            el("button", {
              onclick: async () => {
                if (item.quantity <= 1) return;
                await api.patch(`/api/cart/items/${item.id}`, { quantity: item.quantity - 1 });
                renderCart(view);
                document.dispatchEvent(new CustomEvent("cart:changed"));
              },
            }, "−"),
            el("span", {}, item.quantity),
            el("button", {
              onclick: async () => {
                await api.patch(`/api/cart/items/${item.id}`, { quantity: Math.min(50, item.quantity + 1) });
                renderCart(view);
                document.dispatchEvent(new CustomEvent("cart:changed"));
              },
            }, "+"),
          ),
        ),
        el(
          "div",
          { class: "line-side", style: "text-align:right" },
          el("div", { class: "price" }, item.unit_price != null ? fmtMoney(item.line_total) : t("not_available")),
          el("button", {
            class: "btn btn-soft btn-sm",
            style: "margin-top:8px",
            onclick: async () => {
              await api.del(`/api/cart/items/${item.id}`);
              renderCart(view);
              document.dispatchEvent(new CustomEvent("cart:changed"));
            },
          }, t("remove")),
        ),
      ),
    );
  }

  const couponInput = el("input", { class: "input", placeholder: t("coupon_placeholder"), value: cart.coupon_code || "" });
  const couponBtn = el("button", { class: "btn btn-soft" }, t("apply_coupon"));
  couponBtn.addEventListener(
    "click",
    withLoading(couponBtn, async () => {
      try {
        await api.post("/api/cart/coupon", { code: couponInput.value.trim() });
        toast(t("coupon_applied"), "ok");
        renderCart(view);
      } catch (err) {
        toast(err.message, "err");
      }
    }),
  );

  const summary = el(
    "div",
    { class: "soft-card buy-panel" },
    el("h3", { style: "margin-bottom:12px" }, t("order_summary")),
    el("div", { class: "summary-row" }, t("subtotal"), el("b", {}, fmtMoney(cart.subtotal))),
    cart.coupon_code ? el("div", { class: "summary-row" }, t("discount"), el("b", {}, cart.coupon_code)) : null,
    el("div", { class: "summary-row total" }, t("total"), el("span", { class: "price" }, fmtMoney(cart.subtotal))),
    el("div", { class: "toolbar", style: "margin-top:12px" }, couponInput, couponBtn),
    !cart.valid ? el("p", { class: "form-error" }, t("cart_invalid")) : null,
    el(
      "button",
      {
        class: "btn btn-primary btn-block",
        style: "margin-top:12px",
        disabled: !cart.valid,
        onclick: () => { location.hash = "#/checkout"; },
      },
      t("checkout"),
    ),
    el(
      "button",
      {
        class: "btn btn-soft btn-block",
        style: "margin-top:8px",
        onclick: async () => {
          await api.post("/api/cart/clear");
          renderCart(view);
          document.dispatchEvent(new CustomEvent("cart:changed"));
        },
      },
      t("clear_cart"),
    ),
  );

  view.append(el("div", { class: "split-layout" }, list, summary));
}

/* ------------------------------------------------------------- CHECKOUT */
export async function renderCheckout(view) {
  view.innerHTML = "";
  view.append(el("div", { class: "page-head" }, el("h1", { class: "page-title" }, t("checkout_title"))));

  let config = {};
  try {
    config = await api.get("/api/config");
  } catch {
    /* ignore */
  }

  let data;
  try {
    data = await api.get("/api/cart");
  } catch {
    view.append(emptyState("🔒", t("unauthorized")));
    return;
  }
  const cart = data.cart;
  if (!cart.items.length) {
    view.append(emptyState("🛒", t("cart_empty")));
    return;
  }

  // dynamic player fields from the first item's product
  const first = cart.items[0];
  const fields = first.product?.required_fields || [];
  const inputs = {};
  const errNode = el("div", { class: "form-error" });

  const form = el(
    "div",
    { class: "soft-card" },
    el("h3", { style: "margin-bottom:12px" }, t("player_info")),
    fields.map((f) => {
      const input = el("input", {
        class: "input",
        id: `ck-${f.key}`,
        inputmode: f.type === "number" ? "numeric" : "text",
        value: (first.player_info && first.player_info[f.key]) || "",
      });
      inputs[f.key] = input;
      return el("div", { class: "field" }, el("label", { for: input.id }, `${f.label || f.key}${f.required ? " *" : ""}`), input);
    }),
    el("p", { class: "muted small" }, t("player_info_hint")),
  );

  const payBtn = el("button", { class: "btn btn-primary btn-block" }, t("confirm_pay"));
  payBtn.addEventListener(
    "click",
    withLoading(payBtn, async () => {
      errNode.textContent = "";
      const player_info = {};
      for (const f of fields) {
        const value = inputs[f.key].value.trim();
        if (f.required && !value) {
          errNode.textContent = `${t("missing_field")}: ${f.label || f.key}`;
          return;
        }
        if (value) player_info[f.key] = value;
      }
      try {
        const result = await api.post("/api/checkout", {
          player_info,
          coupon_code: cart.coupon_code || null,
        });
        if (result.error === "payment_not_configured") {
          toast(t("payment_not_configured_msg"), "err");
          location.hash = `#/order/${result.order.order_number}`;
          return;
        }
        if (result.checkout_url) {
          location.href = result.checkout_url;
        } else {
          location.hash = `#/order/${result.order.order_number}`;
        }
      } catch (err) {
        errNode.textContent = err.message;
      }
    }),
  );

  const items = cart.items.map((item) =>
    el(
      "div",
      { class: "kv" },
      el("span", {}, `${item.product?.name} — ${item.variant?.name} × ${item.quantity}`),
      el("b", {}, fmtMoney(item.line_total)),
    ),
  );

  view.append(
    el(
      "div",
      { class: "split-layout" },
      form,
      el(
        "div",
        { class: "soft-card buy-panel" },
        el("h3", { style: "margin-bottom:10px" }, t("order_summary")),
        ...items,
        el("div", { class: "summary-row" }, t("subtotal"), el("b", {}, fmtMoney(cart.subtotal))),
        el("div", { class: "summary-row total" }, t("total"), el("span", { class: "price" }, fmtMoney(cart.subtotal))),
        !config.payment_configured ? el("p", { class: "form-error" }, t("payment_not_configured_msg")) : null,
        errNode,
        el("div", { style: "margin-top:10px" }, payBtn),
      ),
    ),
  );
}

/* ---------------------------------------------------------------- ORDERS */
export async function renderOrders(view, params) {
  view.innerHTML = "";
  view.append(el("div", { class: "page-head" }, el("h1", { class: "page-title" }, t("orders_title"))));
  const state = { page: Number(params.page) || 1, status: params.status || "" };
  const list = el("div", {}, el("div", { class: "skeleton", style: "height:120px" }));
  const pagerSlot = el("div");

  const filters = el(
    "div",
    { class: "toolbar" },
    ...["", "PENDING_PAYMENT", "PAID", "SUPPLIER_PROCESSING", "COMPLETED", "FAILED"].map((st) =>
      el("button", {
        class: `chip ${state.status === st ? "active" : ""}`,
        onclick: (e) => {
          state.status = st;
          state.page = 1;
          e.target.parentElement.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
          e.target.classList.add("active");
          load();
        },
      }, st === "" ? t("all") : tStatus(st)),
    ),
  );
  view.append(filters, list, pagerSlot);

  async function load() {
    list.innerHTML = "";
    list.append(el("div", { class: "skeleton", style: "height:120px" }));
    const q = new URLSearchParams({ page: state.page, page_size: 10 });
    if (state.status) q.set("status", state.status);
    let res;
    try {
      res = await api.get(`/api/orders?${q}`);
    } catch {
      list.innerHTML = "";
      list.append(emptyState("🔒", t("unauthorized")));
      list.append(el("div", { style: "text-align:center;margin-top:14px" }, el("a", { class: "btn btn-primary", href: "#/login" }, t("login"))));
      return;
    }
    list.innerHTML = "";
    if (!res.items.length) {
      list.append(emptyState("📦", t("no_orders"), t("no_orders_sub")));
    } else {
      for (const order of res.items) {
        list.append(
          el(
            "a",
            { class: "soft-card hoverable", href: `#/order/${order.order_number}`, style: "display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap" },
            el(
              "div",
              {},
              el("b", { style: "font-family:var(--font-head)" }, order.order_number),
              el("div", { class: "muted small" }, order.items.map((i) => `${i.variant_name}`).join(", ")),
              el("div", { class: "muted small" }, fmtDate(order.created_at)),
            ),
            el(
              "div",
              { style: "text-align:right" },
              el("div", { class: "price" }, fmtMoney(order.total, order.currency)),
              el("div", { style: "margin-top:6px" }, statusPill(order.status)),
            ),
          ),
        );
      }
    }
    pagerSlot.innerHTML = "";
    pagerSlot.append(pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }));
  }
  await load();
}

/* ------------------------------------------------------------ ORDER PAGE */
export async function renderOrder(view, orderNumber) {
  view.innerHTML = "";
  let order;
  try {
    ({ order } = await api.get(`/api/orders/${encodeURIComponent(orderNumber)}`));
  } catch {
    view.append(emptyState("🔍", t("order_not_found")));
    return;
  }

  const steps = ["PENDING_PAYMENT", "PAID", "SUPPLIER_PROCESSING", "COMPLETED"];
  const idx = steps.indexOf(order.status);
  const failed = ["FAILED", "REFUNDED", "CANCELLED"].includes(order.status);

  const timeline = el(
    "div",
    { class: "timeline" },
    steps.map((st, i) =>
      el(
        "div",
        {
          class: `tl-step ${idx >= 0 && i <= idx ? "done" : ""} ${i === idx ? "current" : ""}`,
        },
        tStatus(st),
      ),
    ),
  );

  const header = el(
    "div",
    { class: "page-head" },
    el(
      "div",
      {},
      el("h1", { class: "page-title" }, order.order_number),
      el("p", { class: "page-sub" }, fmtDate(order.created_at)),
    ),
    el("div", { style: "text-align:right" }, statusPill(order.status), el("div", { class: "price", style: "margin-top:8px" }, fmtMoney(order.total, order.currency))),
  );

  const items = order.items.map((i) =>
    el(
      "div",
      { class: "kv" },
      el("span", {}, `${i.product_name} — ${i.variant_name} × ${i.quantity}`),
      el("b", {}, fmtMoney(i.line_total, order.currency)),
    ),
  );

  const playerRows = Object.entries(order.player_info || {}).map(([k, v]) =>
    el("div", { class: "kv" }, el("span", {}, k), el("b", {}, String(v))),
  );

  view.append(
    header,
    failed ? el("div", { class: "announce" }, `⚠️ ${tStatus(order.status)}`) : timeline,
    el(
      "div",
      { class: "grid grid-2", style: "align-items:start" },
      el(
        "div",
        { class: "soft-card" },
        el("h3", { style: "margin-bottom:8px" }, t("order_summary")),
        ...items,
        el("div", { class: "summary-row" }, t("subtotal"), el("b", {}, fmtMoney(order.subtotal, order.currency))),
        order.discount ? el("div", { class: "summary-row" }, t("discount"), el("b", {}, `-${fmtMoney(order.discount, order.currency)}`)) : null,
        el("div", { class: "summary-row total" }, t("total"), el("span", { class: "price" }, fmtMoney(order.total, order.currency))),
      ),
      el(
        "div",
        { class: "soft-card" },
        el("h3", { style: "margin-bottom:8px" }, t("player_info")),
        playerRows.length ? playerRows : el("p", { class: "muted small" }, "—"),
        el("p", { class: "muted small", style: "margin-top:10px" }, `🔒 ${t("masked_note")}`),
        el("div", { class: "kv", style: "margin-top:12px" }, t("payment_status"), statusPill(order.payment_status || "PENDING")),
        el("div", { class: "kv" }, t("fulfillment_status"), statusPill(order.fulfillment_status || "PENDING")),
        el("p", { class: "muted small", style: "margin-top:10px" }, `🔄 ${t("order_refresh_note")}`),
      ),
    ),
  );

  // auto-refresh while not final
  if (!["COMPLETED", "FAILED", "REFUNDED", "CANCELLED"].includes(order.status)) {
    setTimeout(async () => {
      if (location.hash.includes(orderNumber)) {
        try {
          const fresh = await api.get(`/api/orders/${encodeURIComponent(orderNumber)}`);
          if (fresh.order.status !== order.status) {
            renderOrder(view, orderNumber);
          } else {
            renderOrder(view, orderNumber);
          }
        } catch {
          /* ignore */
        }
      }
    }, 6000);
  }
}

/* ------------------------------------------------------------- SUPPORT */
export async function renderSupport(view) {
  const lang = getLang();
  view.innerHTML = "";
  view.append(el("div", { class: "page-head" }, el("h1", { class: "page-title" }, t("support_title"))));
  const [faqRes, infoRes] = await Promise.all([
    api.get(`/api/support/faq?lang=${lang}`).catch(() => ({ items: [] })),
    api.get(`/api/support/info?lang=${lang}`).catch(() => ({})),
  ]);
  view.append(
    el(
      "div",
      { class: "grid", style: "align-items:start" },
      el(
        "div",
        { class: "soft-card" },
        el("h3", { style: "margin-bottom:8px" }, t("faq")),
        ...faqRes.items.map((f) =>
          el("div", { class: "faq-item" }, el("h4", {}, f.question), el("p", {}, f.answer)),
        ),
      ),
      el(
        "div",
        { class: "soft-card" },
        el("h3", {}, t("nav_support")),
        el("p", { class: "muted small", style: "margin:10px 0" }, t("player_info_hint")),
        infoRes.support_link
          ? el("a", { class: "btn btn-primary btn-block", href: infoRes.support_link, target: "_blank", rel: "noopener" }, "💬 Telegram")
          : el("p", { class: "form-error" }, t("not_configured")),
      ),
    ),
  );
}

/* ----------------------------------------------------------------- AUTH */
export function renderAuth(view, mode) {
  view.innerHTML = "";
  const isLogin = mode !== "register";
  const errNode = el("div", { class: "form-error" });
  const username = el("input", { class: "input", id: "auth-username", autocomplete: "username" });
  const email = el("input", { class: "input", id: "auth-email", type: "email", autocomplete: "email" });
  const password = el("input", { class: "input", id: "auth-password", type: "password", autocomplete: isLogin ? "current-password" : "new-password" });

  const submitBtn = el("button", { class: "btn btn-primary btn-block" }, isLogin ? t("login") : t("register"));
  submitBtn.addEventListener("click", async () => {
    errNode.textContent = "";
    submitBtn.disabled = true;
    try {
      const body = isLogin
        ? { username: username.value.trim(), password: password.value }
        : { username: username.value.trim(), email: email.value.trim(), password: password.value, language: getLang() };
      await api.post(isLogin ? "/api/auth/login" : "/api/auth/register", body);
      toast(isLogin ? t("login_ok") : t("register_ok"), "ok");
      location.hash = "#/";
      document.dispatchEvent(new CustomEvent("auth:changed"));
    } catch (err) {
      errNode.textContent = err.message;
    } finally {
      submitBtn.disabled = false;
    }
  });

  const tgBtn = el("button", { class: "btn btn-soft btn-block", style: "margin-top:10px" }, `✈️ ${t("telegram_login")}`);
  tgBtn.addEventListener("click", async () => {
    errNode.textContent = "";
    const initData = tgInitData();
    if (!initData) {
      errNode.textContent = t("telegram_only_webapp");
      return;
    }
    tgBtn.disabled = true;
    try {
      await api.post("/api/auth/telegram", { init_data: initData });
      toast(t("login_ok"), "ok");
      location.hash = "#/";
      document.dispatchEvent(new CustomEvent("auth:changed"));
    } catch (err) {
      errNode.textContent = err.message;
    } finally {
      tgBtn.disabled = false;
    }
  });

  view.append(
    el(
      "div",
      { class: "auth-wrap" },
      el(
        "div",
        { class: "auth-tabs" },
        el("a", { class: `chip ${isLogin ? "active" : ""}`, href: "#/login" }, t("login")),
        el("a", { class: `chip ${!isLogin ? "active" : ""}`, href: "#/register" }, t("register")),
      ),
      el(
        "div",
        { class: "soft-card" },
        el("h2", { style: "margin-bottom:16px" }, isLogin ? t("login_title") : t("register_title")),
        el("div", { class: "field" }, el("label", { for: "auth-username" }, t("username")), username),
        isLogin ? null : el("div", { class: "field" }, el("label", { for: "auth-email" }, t("email")), email),
        el("div", { class: "field" }, el("label", { for: "auth-password" }, t("password")), password),
        errNode,
        el("div", { style: "margin-top:12px" }, submitBtn, tgBtn),
        el(
          "p",
          { class: "muted small", style: "margin-top:14px;text-align:center" },
          isLogin ? t("no_account") : t("have_account"),
          " ",
          el("a", { href: isLogin ? "#/register" : "#/login", style: "color:var(--accent)" }, isLogin ? t("register") : t("login")),
        ),
      ),
    ),
  );
}

/* -------------------------------------------------------------- ACCOUNT */
export async function renderAccount(view) {
  view.innerHTML = "";
  let me;
  try {
    me = (await api.get("/api/auth/me")).user;
  } catch {
    me = null;
  }
  if (!me) {
    view.append(emptyState("🔒", t("unauthorized")));
    view.append(el("div", { style: "text-align:center;margin-top:14px" }, el("a", { class: "btn btn-primary", href: "#/login" }, t("login"))));
    return;
  }

  if (me.is_admin) {
    const adminLink = el("div", { style: "margin-bottom:16px" }, el("a", { class: "btn btn-soft", href: "#/admin" }, `⚙️ ${t("nav_admin")}`));
    view.append(adminLink);
  }

  view.append(el("div", { class: "page-head" }, el("h1", { class: "page-title" }, t("nav_account"))));

  const content = el("div", {});
  const nav = el(
    "div",
    { class: "soft-card side-nav" },
    ...[
      ["profile", t("profile")],
      ["orders", t("order_history")],
      ["notifications", t("notifications")],
      ["preferences", t("language") + " · " + t("theme")],
      ["logout", t("logout")],
    ].map(([key, label]) =>
      el("button", {
        class: key === "profile" ? "active" : "",
        onclick: (e) => {
          nav.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
          e.target.classList.add("active");
          if (key === "logout") {
            api.post("/api/auth/logout").then(() => {
              document.dispatchEvent(new CustomEvent("auth:changed"));
              location.hash = "#/";
            });
            return;
          }
          renderPanel(key);
        },
      }, label),
    ),
  );

  async function renderPanel(key) {
    content.innerHTML = "";
    if (key === "profile") {
      const { profile } = await api.get("/api/account/profile");
      const emailIn = el("input", { class: "input", id: "pf-email", type: "email", value: profile.email || "" });
      const saveBtn = el("button", { class: "btn btn-primary" }, t("save_changes"));
      saveBtn.addEventListener(
        "click",
        withLoading(saveBtn, async () => {
          await api.patch("/api/account/profile", { email: emailIn.value.trim() || null });
          toast(t("saved"), "ok");
        }),
      );
      content.append(
        el(
          "div",
          { class: "soft-card" },
          el("h3", { style: "margin-bottom:14px" }, t("personal_info")),
          el("div", { class: "kv" }, t("username"), el("b", {}, profile.username)),
          el("div", { class: "kv" }, t("member_since"), el("b", {}, fmtDate(profile.created_at))),
          el(
            "div",
            { class: "kv" },
            "Telegram",
            el("b", {}, profile.telegram_linked ? `✅ ${t("telegram_linked")}` : `— ${t("telegram_not_linked")}`),
          ),
          el("div", { class: "field", style: "margin-top:14px" }, el("label", { for: "pf-email" }, t("email")), emailIn),
          saveBtn,
        ),
      );
    } else if (key === "orders") {
      const res = await api.get("/api/orders?page_size=20");
      content.append(
        res.items.length
          ? el(
              "div",
              {},
              res.items.map((o) =>
                el(
                  "a",
                  { class: "soft-card hoverable", href: `#/order/${o.order_number}`, style: "display:flex;justify-content:space-between;margin-bottom:10px;align-items:center" },
                  el("div", {}, el("b", {}, o.order_number), el("div", { class: "muted small" }, fmtDate(o.created_at))),
                  el("div", { style: "text-align:right" }, el("div", { class: "price" }, fmtMoney(o.total, o.currency)), el("div", {}, statusPill(o.status))),
                ),
              ),
            )
          : emptyState("📦", t("no_orders"), t("no_orders_sub")),
      );
    } else if (key === "notifications") {
      const res = await api.get("/api/account/notifications");
      const markBtn = el("button", { class: "btn btn-soft btn-sm" }, t("mark_all_read"));
      markBtn.addEventListener("click", async () => {
        await api.post("/api/account/notifications/read");
        renderPanel("notifications");
      });
      content.append(
        el(
          "div",
          { class: "soft-card" },
          el("div", { class: "section-head" }, el("h3", {}, t("notifications")), markBtn),
          res.items.length
            ? res.items.map((n) =>
                el(
                  "div",
                  { class: `notif-row ${n.is_read ? "" : "unread"}` },
                  el("div", {}, el("div", { class: "notif-title" }, t(n.title_key)), el("div", { class: "muted small" }, t(n.body_key, n.params))),
                  el("div", { class: "muted small", style: "margin-left:auto;white-space:nowrap" }, fmtDate(n.created_at)),
                ),
              )
            : emptyState("🔔", t("no_notifications")),
        ),
      );
    } else if (key === "preferences") {
      const langRow = el(
        "div",
        { class: "field" },
        el("label", {}, t("language")),
        el(
          "select",
          {
            class: "select",
            onchange: async (e) => {
              setLang(e.target.value);
              await api.patch("/api/account/profile", { language: e.target.value }).catch(() => {});
              document.dispatchEvent(new CustomEvent("lang:changed"));
            },
          },
          ...["uz", "en", "ru"].map((l) => el("option", { value: l, selected: getLang() === l }, l.toUpperCase())),
        ),
      );
      const themeRow = el(
        "div",
        { class: "field" },
        el("label", {}, t("theme")),
        el(
          "select",
          {
            class: "select",
            onchange: async (e) => {
              const { setTheme } = await import("./theme.js");
              setTheme(e.target.value);
              await api.patch("/api/account/profile", { theme: e.target.value }).catch(() => {});
            },
          },
          el("option", { value: "night", selected: document.documentElement.dataset.theme === "night" }, t("theme_night")),
          el("option", { value: "day", selected: document.documentElement.dataset.theme === "day" }, t("theme_day")),
        ),
      );
      content.append(el("div", { class: "soft-card" }, el("h3", { style: "margin-bottom:14px" }, t("language") + " · " + t("theme")), langRow, themeRow));
    }
  }

  await renderPanel("profile");
  view.append(el("div", { class: "account-layout" }, nav, content));
}

/* ---------------------------------------------------------- SANDBOX PAY */
export function renderSandboxCheckout(view, params) {
  view.innerHTML = "";
  const amount = Number(params.amount || 0);
  const currency = params.currency || "UZS";
  const notice = el(
    "div",
    { class: "announce" },
    "🧪 SANDBOX payment provider (test mode) — explicit PAYMENT_PROVIDER=sandbox only. It signs a REAL HMAC webhook to VYRON.",
  );
  const payBtn = el("button", { class: "btn btn-primary btn-block" }, `Pay ${fmtMoney(amount, currency)} (SANDBOX)`);
  payBtn.addEventListener("click", async () => {
    payBtn.disabled = true;
    payBtn.textContent = "…";
    try {
      await fetch("/sandbox/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payment_id: params.payment_id,
          order_number: params.order_number,
          amount,
          currency,
          status: "succeeded",
        }),
      });
      location.hash = `#/order/${params.order_number}`;
    } catch {
      payBtn.disabled = false;
      payBtn.textContent = `Pay ${fmtMoney(amount, currency)} (SANDBOX)`;
    }
  });
  view.append(
    el(
      "div",
      { class: "auth-wrap" },
      el(
        "div",
        { class: "soft-card" },
        notice,
        el("h2", { style: "margin:10px 0" }, "Sandbox Checkout"),
        el("div", { class: "kv" }, t("order_number"), el("b", {}, params.order_number || "—")),
        el("div", { class: "kv" }, t("total"), el("b", {}, fmtMoney(amount, currency))),
        el("div", { style: "margin-top:16px" }, payBtn),
      ),
    ),
  );
}
