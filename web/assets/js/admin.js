/* VYRON admin panel — all sections. Server-side RBAC protects every endpoint. */
import { api } from "./api.js";
import { t } from "./i18n.js";
import {
  el, emptyState, fmtDate, fmtMoney, modal, pager, statusPill, toast, withLoading,
} from "./ui.js";

const SECTIONS = [
  ["dashboard", "a_dashboard"],
  ["users", "a_users"],
  ["games", "a_games"],
  ["products", "a_products"],
  ["variants", "a_variants"],
  ["orders", "a_orders"],
  ["payments", "a_payments"],
  ["fulfillments", "a_fulfillments"],
  ["payerpin", "a_payerpin"],
  ["pricing", "a_pricing"],
  ["coupons", "a_coupons"],
  ["promotions", "a_promotions"],
  ["analytics", "a_analytics"],
  ["notifications", "a_notifications"],
  ["telegram", "a_telegram"],
  ["security", "a_security"],
  ["audit", "a_audit"],
  ["health", "a_health"],
  ["settings", "a_settings"],
];

export async function renderAdmin(view) {
  view.innerHTML = "";
  let me = null;
  try {
    me = (await api.get("/api/auth/me")).user;
  } catch {
    /* ignore */
  }
  if (!me || !me.is_admin) {
    view.append(emptyState("⛔️", t("admin_denied"), t("admin_denied_sub")));
    view.append(el("div", { style: "text-align:center;margin-top:14px" }, el("a", { class: "btn btn-primary", href: "#/login" }, t("login"))));
    return;
  }

  view.append(
    el(
      "div",
      { class: "page-head" },
      el("div", {}, el("h1", { class: "page-title" }, `⚙️ ${t("admin_title")}`), el("p", { class: "page-sub" }, "VYRON · Payerpin · Payments")),
    ),
  );

  const content = el("div", {});
  const nav = el(
    "div",
    { class: "soft-card admin-nav" },
    ...SECTIONS.map(([key, labelKey], i) =>
      el("button", {
        class: i === 0 ? "active" : "",
        onclick: (e) => {
          nav.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
          e.target.classList.add("active");
          loadSection(key);
        },
      }, t(labelKey)),
    ),
  );

  async function loadSection(key) {
    content.innerHTML = "";
    content.append(el("div", { class: "skeleton", style: "height:160px" }));
    try {
      content.innerHTML = "";
      await SECTIONS_FN[key]?.(content);
    } catch (err) {
      content.innerHTML = "";
      content.append(emptyState("⚠️", err.message || t("error_generic")));
    }
  }

  view.append(el("div", { class: "admin-layout" }, nav, content));
  await loadSection("dashboard");
}

function statCard(labelKey, value, cls = "") {
  return el(
    "div",
    { class: "soft-card stat-card" },
    el("div", { class: "label" }, t(labelKey)),
    el("div", { class: `value ${cls}` }, value),
  );
}

function table(headers, rows) {
  return el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      { class: "soft-table" },
      el("thead", {}, el("tr", {}, headers.map((h) => el("th", {}, h)))),
      el("tbody", {}, rows.length ? rows : [el("tr", {}, el("td", { colspan: headers.length, class: "muted" }, "—"))]),
    ),
  );
}

function toolbar(...nodes) {
  return el("div", { class: "toolbar" }, ...nodes);
}

function searchInput(placeholder, onSearch) {
  const input = el("input", { class: "input", placeholder });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") onSearch(input.value.trim());
  });
  return input;
}

const SECTIONS_FN = {
  /* ---------------------------------------------------------- dashboard */
  async dashboard(root) {
    const data = await api.get("/api/admin/dashboard");
    const s = data.stats;
    root.append(
      el(
        "div",
        { class: "stat-grid" },
        statCard("a_users_total", s.users),
        statCard("a_orders_total", s.orders_total),
        statCard("a_orders_24h", s.orders_24h, "accent"),
        statCard("a_revenue", fmtMoney(s.revenue_total), "ok"),
        statCard("a_profit", fmtMoney(s.profit_total), "accent"),
        statCard("a_pending", s.orders_pending, s.orders_pending ? "err" : ""),
        statCard("a_processing", s.orders_processing, "accent"),
        statCard("a_completed", s.orders_completed, "ok"),
        statCard("a_failed", s.orders_failed, s.orders_failed ? "err" : ""),
        statCard("a_active_products", s.products_active),
      ),
    );
    root.append(
      el("h3", { style: "margin:22px 0 12px" }, t("a_recent_orders")),
      table(
        [t("order_number"), t("a_user"), t("total"), t("status"), t("date")],
        data.recent_orders.map((o) =>
          el(
            "tr",
            {},
            el("td", {}, el("a", { href: `#/order/${o.order_number}`, style: "color:var(--accent)" }, o.order_number)),
            el("td", {}, o.user || o.user_id),
            el("td", {}, fmtMoney(o.total, o.currency)),
            el("td", {}, statusPill(o.status)),
            el("td", { class: "muted small" }, fmtDate(o.created_at)),
          ),
        ),
      ),
    );
  },

  /* -------------------------------------------------------------- users */
  async users(root) {
    const state = { page: 1, search: "" };
    const slot = el("div");
    root.append(
      toolbar(searchInput(`${t("search")}…`, (q) => { state.search = q; state.page = 1; load(); })),
      slot,
    );
    async function load() {
      slot.innerHTML = "";
      const q = new URLSearchParams({ page: state.page, page_size: 15 });
      if (state.search) q.set("search", state.search);
      const res = await api.get(`/api/admin/users?${q}`);
      slot.append(
        table(
          ["ID", t("username"), t("email"), t("a_role"), t("status"), t("actions")],
          res.items.map((u) =>
            el(
              "tr",
              {},
              el("td", {}, u.id),
              el("td", {}, u.username, u.telegram_linked ? " ✈️" : ""),
              el("td", {}, u.email || "—"),
              el("td", {}, el("span", { class: "pill info" }, u.role)),
              el("td", {}, el("span", { class: `pill ${u.is_active ? "ok" : "err"}` }, u.is_active ? t("a_active") : "OFF")),
              el(
                "td",
                {},
                el("button", {
                  class: "btn btn-soft btn-sm",
                  onclick: async () => {
                    await api.patch(`/api/admin/users/${u.id}`, { is_active: !u.is_active });
                    toast(t("a_save_ok"), "ok");
                    load();
                  },
                }, u.is_active ? "OFF" : "ON"),
                " ",
                el("button", {
                  class: "btn btn-soft btn-sm",
                  onclick: async () => {
                    await api.patch(`/api/admin/users/${u.id}`, { role: u.role === "ADMIN" ? "CUSTOMER" : "ADMIN" });
                    toast(t("a_save_ok"), "ok");
                    load();
                  },
                }, u.role === "ADMIN" ? "USER" : "ADMIN"),
              ),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* -------------------------------------------------------------- games */
  async games(root) {
    const state = { page: 1 };
    const slot = el("div");
    const newBtn = el("button", { class: "btn btn-primary btn-sm" }, `+ ${t("create")}`);
    newBtn.addEventListener("click", () => gameForm(null, () => load()));
    root.append(toolbar(newBtn, searchInput(`${t("search")}…`, () => { state.page = 1; load(); })), slot);

    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/games?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", t("a_game"), "Slug", t("a_type"), "🪙", t("a_active"), t("actions")],
          res.items.map((g) =>
            el(
              "tr",
              {},
              el("td", {}, g.id),
              el("td", {}, g.name, g.featured ? " ⭐" : ""),
              el("td", { class: "muted small" }, g.slug),
              el("td", {}, g.category),
              el("td", {}, g.currency_label),
              el("td", {}, el("span", { class: `pill ${g.active ? "ok" : "err"}` }, g.active ? "ON" : "OFF")),
              el("td", {}, el("button", { class: "btn btn-soft btn-sm", onclick: () => gameForm(g, () => load()) }, t("edit"))),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* ------------------------------------------------------------ products */
  async products(root) {
    const state = { page: 1 };
    const slot = el("div");
    const newBtn = el("button", { class: "btn btn-primary btn-sm" }, `+ ${t("create")}`);
    newBtn.addEventListener("click", () => productForm(null, () => load()));
    root.append(toolbar(newBtn), slot);

    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/products?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", t("a_product_name"), t("a_game"), t("a_type"), t("a_variants"), t("a_active"), t("actions")],
          res.items.map((p) =>
            el(
              "tr",
              {},
              el("td", {}, p.id),
              el("td", {}, p.name),
              el("td", {}, p.game || "—"),
              el("td", {}, p.product_type),
              el("td", {}, p.variants),
              el("td", {}, el("span", { class: `pill ${p.active ? "ok" : "err"}` }, p.active ? "ON" : "OFF")),
              el("td", {}, el("button", { class: "btn btn-soft btn-sm", onclick: () => productForm(p, () => load()) }, t("edit"))),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* ------------------------------------------------------------ variants */
  async variants(root) {
    const state = { page: 1 };
    const slot = el("div");
    const newBtn = el("button", { class: "btn btn-primary btn-sm" }, `+ ${t("create")}`);
    newBtn.addEventListener("click", () => variantForm(null, () => load()));
    root.append(
      toolbar(newBtn, searchInput(`${t("search")}…`, () => { state.page = 1; load(); })),
      el("p", { class: "muted small", style: "margin-bottom:10px" }, t("a_pricing_note")),
      slot,
    );

    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/variants?page=${state.page}&page_size=15`);
      slot.append(
        table(
          [t("a_product_name"), t("price"), t("a_supplier_cost"), t("a_profit_line"), t("a_supplier_mapping"), t("a_active"), t("actions")],
          res.items.map((v) =>
            el(
              "tr",
              {},
              el("td", {}, v.name, el("div", { class: "muted small" }, v.product)),
              el("td", {}, v.price != null ? fmtMoney(v.price, v.currency) : t("not_available")),
              el("td", { class: "muted" }, v.supplier_cost != null ? fmtMoney(v.supplier_cost, v.currency) : "—"),
              el("td", { class: "muted" }, v.profit != null ? fmtMoney(v.profit, v.currency) : "—"),
              el(
                "td",
                {},
                el("span", { class: `pill ${v.mapped ? "ok" : "warn"}` }, v.mapped ? t("a_mapped") : t("a_unmapped")),
                v.supplier_product_id ? el("div", { class: "muted small" }, `${v.supplier_product_id}${v.supplier_variation_id ? "/" + v.supplier_variation_id : ""}`) : null,
              ),
              el("td", {}, el("span", { class: `pill ${v.active ? "ok" : "err"}` }, v.active ? "ON" : "OFF")),
              el("td", {}, el("button", { class: "btn btn-soft btn-sm", onclick: () => variantForm(v, () => load()) }, t("edit"))),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* -------------------------------------------------------------- orders */
  async orders(root) {
    const state = { page: 1, search: "", status: "" };
    const slot = el("div");
    root.append(
      toolbar(
        searchInput(`${t("order_number")}…`, (q) => { state.search = q; state.page = 1; load(); }),
        el(
          "select",
          {
            class: "select", style: "width:220px",
            onchange: (e) => { state.status = e.target.value; state.page = 1; load(); },
          },
          el("option", { value: "" }, t("all")),
          ...["PENDING_PAYMENT", "PAID", "FULFILLMENT_PENDING", "SUPPLIER_PROCESSING", "COMPLETED", "FAILED", "REFUNDED", "CANCELLED"].map((s) =>
            el("option", { value: s }, s)),
        ),
      ),
      slot,
    );
    async function load() {
      slot.innerHTML = "";
      const q = new URLSearchParams({ page: state.page, page_size: 15 });
      if (state.search) q.set("search", state.search);
      if (state.status) q.set("status", state.status);
      const res = await api.get(`/api/admin/orders?${q}`);
      slot.append(
        table(
          [t("order_number"), t("a_user"), t("price"), t("a_profit_line"), t("status"), t("actions")],
          res.items.map((o) =>
            el(
              "tr",
              {},
              el("td", {}, el("a", { href: `#/order/${o.order_number}`, style: "color:var(--accent)" }, o.order_number)),
              el("td", {}, o.user),
              el("td", {}, fmtMoney(o.total, o.currency)),
              el("td", { class: "muted" }, fmtMoney(o.profit, o.currency)),
              el("td", {}, statusPill(o.status)),
              el(
                "td",
                {},
                ["PENDING_PAYMENT", "FAILED"].includes(o.status)
                  ? el("button", {
                      class: "btn btn-soft btn-sm",
                      onclick: async () => {
                        await api.post(`/api/admin/orders/${o.id}/cancel`, {});
                        toast(t("a_cancelled"), "ok");
                        load();
                      },
                    }, "✕")
                  : null,
                " ",
                ["COMPLETED", "FAILED", "SUPPLIER_PROCESSING"].includes(o.status)
                  ? el("button", {
                      class: "btn btn-soft btn-sm",
                      onclick: async () => {
                        try {
                          await api.post(`/api/admin/orders/${o.id}/refund`, {});
                          toast(t("a_refunded"), "ok");
                        } catch (err) {
                          toast(err.message, "err");
                        }
                        load();
                      },
                    }, "↩")
                  : null,
                " ",
                ["FAILED", "SUPPLIER_PROCESSING"].includes(o.status)
                  ? el("button", {
                      class: "btn btn-soft btn-sm",
                      onclick: async () => {
                        try {
                          await api.post(`/api/admin/orders/${o.id}/retry-fulfillment`, {});
                          toast(t("a_retried"), "ok");
                        } catch (err) {
                          toast(err.message, "err");
                        }
                        load();
                      },
                    }, "↻")
                  : null,
              ),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* ------------------------------------------------------------ payments */
  async payments(root) {
    const state = { page: 1 };
    const slot = el("div");
    root.append(slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/payments?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", t("order_number"), t("a_type"), "Provider ID", t("total"), t("status"), t("date")],
          res.items.map((p) =>
            el(
              "tr",
              {},
              el("td", {}, p.id),
              el("td", {}, p.order_number),
              el("td", {}, p.provider),
              el("td", { class: "muted small" }, p.provider_payment_id || "—"),
              el("td", {}, fmtMoney(p.amount, p.currency)),
              el("td", {}, statusPill(p.status)),
              el("td", { class: "muted small" }, fmtDate(p.created_at)),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /*                                                        fulfillments */
  async fulfillments(root) {
    const state = { page: 1 };
    const slot = el("div");
    root.append(slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/fulfillments?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", t("order_number"), t("status"), "Attempts", t("status"), t("date")],
          res.items.map((f) =>
            el(
              "tr",
              {},
              el("td", {}, f.id),
              el("td", {}, f.order_number),
              el("td", {}, statusPill(f.status)),
              el("td", {}, `${f.attempts}/${f.max_attempts}`),
              el("td", { class: "muted small" }, f.last_error || "—"),
              el("td", { class: "muted small" }, fmtDate(f.created_at)),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* ------------------------------------------------------------ payerpin */
  async payerpin(root) {
    const data = await api.get("/api/admin/suppliers/payerpin");

    const connPill = el(
      "span",
      { class: `pill ${data.api_configured ? "ok" : "warn"}` },
      data.connection_status,
    );

    const testBtn = el("button", { class: "btn btn-primary btn-sm" }, t("test_connection"));
    const syncBtn = el("button", { class: "btn btn-soft btn-sm" }, t("sync_catalog"));
    const balBtn = el("button", { class: "btn btn-soft btn-sm" }, t("check_balance"));

    testBtn.addEventListener("click", async () => {
      testBtn.disabled = true;
      try {
        await api.post("/api/admin/suppliers/payerpin/test-connection");
        toast(t("connection_successful"), "ok");
        renderAdmin(document.getElementById("view"));
      } catch (err) {
        toast(`${t("connection_failed")}: ${err.message}`, "err");
      } finally {
        testBtn.disabled = false;
      }
    });
    syncBtn.addEventListener("click", async () => {
      syncBtn.disabled = true;
      syncBtn.textContent = "…";
      try {
        const stats = await api.post("/api/admin/suppliers/payerpin/sync-catalog");
        toast(t("sync_done"), "ok");
        toast(t("sync_report", stats), "ok");
        renderAdmin(document.getElementById("view"));
      } catch (err) {
        toast(err.message, "err");
      } finally {
        syncBtn.disabled = false;
        syncBtn.textContent = t("sync_catalog");
      }
    });
    balBtn.addEventListener("click", async () => {
      balBtn.disabled = true;
      try {
        const res = await api.post("/api/admin/suppliers/payerpin/check-balance");
        toast(`${t("balance")}: ${fmtMoney(res.balance, res.currency || "UZS")}`, "ok");
        renderAdmin(document.getElementById("view"));
      } catch (err) {
        toast(err.message, "err");
      } finally {
        balBtn.disabled = false;
      }
    });

    root.append(
      el(
        "div",
        { class: "soft-card", style: "margin-bottom:16px" },
        el(
          "div",
          { class: "section-head" },
          el("h3", {}, `🔌 Payerpin · ${data.base_url}`),
          connPill,
        ),
        el("p", { class: "muted small", style: "margin-bottom:14px" }, t("never_shows_key")),
        toolbar(testBtn, syncBtn, balBtn),
      ),
      el(
        "div",
        { class: "stat-grid", style: "margin-bottom:16px" },
        statCard("api_key_configured", data.api_key_configured ? "✅ " + t("configured") : "❌ " + t("not_configured"), data.api_key_configured ? "ok" : "err"),
        statCard("balance", data.balance != null ? fmtMoney(data.balance, data.balance_currency || "UZS") : t("not_available"), data.low_balance_warning ? "err" : ""),
        statCard("a_active_products", data.active_supplier_products),
        statCard("pending_fulfillments", data.pending_fulfillments, data.pending_fulfillments ? "accent" : ""),
        statCard("failed_fulfillments", data.failed_fulfillments, data.failed_fulfillments ? "err" : ""),
        statCard("completed_supplier_orders", data.completed_supplier_orders, "ok"),
      ),
      el(
        "div",
        { class: "soft-card", style: "margin-bottom:16px" },
        el("h3", { style: "margin-bottom:10px" }, t("status")),
        el("div", { class: "kv" }, t("last_success_request"), el("b", {}, fmtDate(data.last_success_request))),
        el("div", { class: "kv" }, t("last_failed_request"), el("b", {}, fmtDate(data.last_failed_request))),
        el("div", { class: "kv" }, t("last_sync"), el("b", {}, fmtDate(data.last_catalog_sync))),
        data.balance_checked_at ? el("div", { class: "kv" }, t("check_balance"), el("b", {}, fmtDate(data.balance_checked_at))) : null,
      ),
      el("h3", { style: "margin-bottom:10px" }, t("last_sync")),
      table(
        ["ID", t("status"), "🎮", "🛒", "📦", t("date")],
        data.sync_history.map((s) =>
          el(
            "tr",
            {},
            el("td", {}, s.id),
            el("td", {}, el("span", { class: `pill ${s.status === "SUCCESS" ? "ok" : s.status === "NOT_CONFIGURED" ? "warn" : "err"}` }, s.status)),
            el("td", {}, s.games),
            el("td", {}, s.products),
            el("td", {}, s.variants),
            el("td", { class: "muted small" }, fmtDate(s.started_at)),
          ),
        ),
      ),
    );
  },

  /* ------------------------------------------------------------- pricing */
  async pricing(root) {
    const { pricing } = await api.get("/api/admin/pricing");
    const fields = [
      ["margin_percent", "a_margin_percent"],
      ["margin_fixed", "a_margin_fixed"],
      ["payment_fee_percent", "a_fee_percent"],
      ["payment_fee_fixed", "a_fee_fixed"],
      ["min_margin_percent", "a_min_margin"],
    ];
    const inputs = {};
    const saveBtn = el("button", { class: "btn btn-primary" }, t("save_changes"));
    saveBtn.addEventListener(
      "click",
      withLoading(saveBtn, async () => {
        const body = {};
        for (const [key] of fields) body[key] = Number(inputs[key].value) || 0;
        await api.put("/api/admin/pricing", body);
        toast(`${t("a_save_ok")} ${t("a_recalc_note")}`, "ok");
      }),
    );
    root.append(
      el(
        "div",
        { class: "soft-card", style: "max-width:520px" },
        el("h3", { style: "margin-bottom:6px" }, t("a_pricing")),
        el("p", { class: "muted small", style: "margin-bottom:14px" }, t("a_pricing_note")),
        fields.map(([key, label]) => {
          const input = el("input", { class: "input", type: "number", min: "0", value: String(pricing[key] ?? 0) });
          inputs[key] = input;
          return el("div", { class: "field" }, el("label", {}, t(label)), input);
        }),
        saveBtn,
      ),
    );
  },

  /* ------------------------------------------------------------- coupons */
  async coupons(root) {
    const slot = el("div");
    const newBtn = el("button", { class: "btn btn-primary btn-sm" }, `+ ${t("create")}`);
    newBtn.addEventListener("click", () => couponForm(null, () => load()));
    root.append(toolbar(newBtn), slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get("/api/admin/coupons");
      slot.append(
        table(
          [t("a_code"), t("a_type"), t("a_value"), t("a_used"), t("a_expires"), t("a_active"), t("actions")],
          res.items.map((c) =>
            el(
              "tr",
              {},
              el("td", {}, el("b", {}, c.code)),
              el("td", {}, t(c.coupon_type === "PERCENT" ? "a_percent" : "a_fixed")),
              el("td", {}, c.coupon_type === "PERCENT" ? `${c.value}%` : fmtMoney(c.value)),
              el("td", {}, `${c.used_count}${c.max_uses ? " / " + c.max_uses : ""}`),
              el("td", { class: "muted small" }, c.expires_at ? fmtDate(c.expires_at) : "—"),
              el("td", {}, el("span", { class: `pill ${c.active ? "ok" : "err"}` }, c.active ? "ON" : "OFF")),
              el("td", {}, el("button", { class: "btn btn-soft btn-sm", onclick: () => couponForm(c, () => load()) }, t("edit"))),
            ),
          ),
        ),
      );
    }
    await load();
  },

  /* ---------------------------------------------------------- promotions */
  async promotions(root) {
    const slot = el("div");
    const newBtn = el("button", { class: "btn btn-primary btn-sm" }, `+ ${t("create")}`);
    newBtn.addEventListener("click", () => promotionForm(null, () => load()));
    root.append(toolbar(newBtn), slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get("/api/admin/promotions");
      slot.append(
        table(
          [t("a_product_name"), "Coupon", t("a_image_url"), t("a_active"), t("actions")],
          res.items.map((p) =>
            el(
              "tr",
              {},
              el("td", {}, p.title),
              el("td", {}, p.coupon_code || "—"),
              el("td", { class: "muted small", style: "max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, p.image_url || "—"),
              el("td", {}, el("span", { class: `pill ${p.active ? "ok" : "err"}` }, p.active ? "ON" : "OFF")),
              el("td", {}, el("button", { class: "btn btn-soft btn-sm", onclick: () => promotionForm(p, () => load()) }, t("edit"))),
            ),
          ),
        ),
      );
    }
    await load();
  },

  /* ----------------------------------------------------------- analytics */
  async analytics(root) {
    const data = await api.get("/api/admin/analytics?days=14");
    const maxRev = Math.max(...data.daily.map((d) => d.revenue), 1);
    root.append(
      el("h3", { style: "margin-bottom:12px" }, t("a_revenue_chart")),
      el(
        "div",
        { class: "soft-card", style: "display:flex;align-items:flex-end;gap:6px;height:180px;padding:18px" },
        data.daily.map((d) =>
          el(
            "div",
            {
              title: `${d.date}: ${fmtMoney(d.revenue)}`,
              style: `flex:1;background:linear-gradient(180deg,var(--blue-400),var(--navy-600));border-radius:8px 8px 0 0;height:${Math.max(4, (d.revenue / maxRev) * 100)}%`,
            },
          ),
        ),
      ),
      el("h3", { style: "margin:22px 0 12px" }, t("a_top_products")),
      table(
        [t("a_product_name"), t("quantity"), t("a_revenue")],
        data.top_products.map((p) =>
          el("tr", {}, el("td", {}, p.variant), el("td", {}, p.quantity), el("td", {}, fmtMoney(p.revenue))),
        ),
      ),
    );
  },

  /*                                                        notifications */
  async notifications(root) {
    const state = { page: 1 };
    const slot = el("div");
    const bcBtn = el("button", { class: "btn btn-primary btn-sm" }, `📢 ${t("a_broadcast")}`);
    bcBtn.addEventListener("click", () => broadcastForm());
    root.append(toolbar(bcBtn), slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/notifications?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", "#", t("a_type"), "Title", t("date")],
          res.items.map((n) =>
            el(
              "tr",
              {},
              el("td", {}, n.id),
              el("td", {}, n.user_id),
              el("td", {}, el("span", { class: "pill info" }, n.kind)),
              el("td", {}, t(n.title_key)),
              el("td", { class: "muted small" }, fmtDate(n.created_at)),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* ------------------------------------------------------------ telegram */
  async telegram(root) {
    const data = await api.get("/api/admin/telegram");
    root.append(
      el(
        "div",
        { class: "stat-grid", style: "margin-bottom:16px" },
        statCard("a_check_telegram", data.configured ? "✅ " + t("configured") : "❌ " + t("not_configured"), data.configured ? "ok" : "err"),
        statCard("a_users", data.users.length),
      ),
      table(
        ["Telegram ID", t("username"), t("language"), t("status")],
        data.users.map((u) =>
          el(
            "tr",
            {},
            el("td", {}, u.telegram_id),
            el("td", {}, u.username || u.first_name || "—"),
            el("td", {}, u.language),
            el("td", {}, el("span", { class: `pill ${u.linked ? "ok" : ""}` }, u.linked ? t("a_mapped") : "—")),
          ),
        ),
      ),
    );
  },

  /* ------------------------------------------------------------ security */
  async security(root) {
    const data = await api.get("/api/admin/security");
    root.append(
      el(
        "div",
        { class: "stat-grid", style: "margin-bottom:16px" },
        statCard("password", data.password_hashing, "ok"),
        statCard("a_locked_accounts", data.locked_accounts, data.locked_accounts ? "warn" : ""),
        statCard("a_failed_webhooks", data.failed_webhooks, data.failed_webhooks ? "err" : "ok"),
      ),
      el("h3", { style: "margin-bottom:10px" }, t("a_admin_actions")),
      table(
        [t("a_type"), "Target", t("status"), "Admin", t("date")],
        data.recent_admin_actions.map((a) =>
          el(
            "tr",
            {},
            el("td", {}, a.action),
            el("td", { class: "muted small" }, a.target || "—"),
            el("td", {}, el("span", { class: `pill ${a.result === "SUCCESS" ? "ok" : "err"}` }, a.result)),
            el("td", {}, a.admin),
            el("td", { class: "muted small" }, fmtDate(a.created_at)),
          ),
        ),
      ),
    );
  },

  /* ---------------------------------------------------------- audit logs */
  async audit(root) {
    const state = { page: 1 };
    const slot = el("div");
    root.append(toolbar(searchInput(`${t("search")}…`, () => { state.page = 1; load(); })), slot);
    async function load() {
      slot.innerHTML = "";
      const res = await api.get(`/api/admin/audit-logs?page=${state.page}&page_size=15`);
      slot.append(
        table(
          ["ID", t("a_type"), "Target", t("status"), t("date")],
          res.items.map((a) =>
            el(
              "tr",
              {},
              el("td", {}, a.id),
              el("td", {}, a.action),
              el("td", { class: "muted small" }, a.target_type ? `${a.target_type}:${a.target_id}` : "—"),
              el("td", {}, el("span", { class: `pill ${a.result === "SUCCESS" ? "ok" : "err"}` }, a.result)),
              el("td", { class: "muted small" }, fmtDate(a.created_at)),
            ),
          ),
        ),
        pager(state.page, res.page_size, res.total, (p) => { state.page = p; load(); }),
      );
    }
    await load();
  },

  /* --------------------------------------------------------------- health */
  async health(root) {
    const data = await api.get("/api/admin/health");
    const rows = Object.entries(data.checks).map(([name, info]) =>
      el(
        "tr",
        {},
        el("td", {}, t(`a_check_${name.toLowerCase()}`) !== `a_check_${name.toLowerCase()}` ? t(`a_check_${name.toLowerCase()}`) : name),
        el("td", {}, el("span", {
          class: `pill ${["Connected", "Configured"].includes(info.status) ? "ok" : info.status === "Error" ? "err" : "warn"}`,
        }, info.status)),
        el("td", { class: "muted small" }, info.detail),
      ),
    );
    root.append(table(["Component", t("status"), "Detail"], rows));
  },

  /* ------------------------------------------------------------ settings */
  async settings(root) {
    const data = await api.get("/api/admin/settings");
    const general = data.settings.general || {};
    const supportLink = el("input", { class: "input", value: general.support_link || "" });
    const annUz = el("input", { class: "input", value: general.announcement_uz || "" });
    const annEn = el("input", { class: "input", value: general.announcement_en || "" });
    const annRu = el("input", { class: "input", value: general.announcement_ru || "" });
    const saveBtn = el("button", { class: "btn btn-primary" }, t("save_changes"));
    saveBtn.addEventListener(
      "click",
      withLoading(saveBtn, async () => {
        await api.put("/api/admin/settings/general", {
          value: {
            ...general,
            support_link: supportLink.value.trim(),
            announcement_uz: annUz.value.trim(),
            announcement_en: annEn.value.trim(),
            announcement_ru: annRu.value.trim(),
          },
        });
        toast(t("a_save_ok"), "ok");
      }),
    );
    root.append(
      el(
        "div",
        { class: "soft-card", style: "max-width:560px" },
        el("h3", { style: "margin-bottom:12px" }, t("a_setting_general")),
        el("div", { class: "field" }, el("label", {}, t("a_support_link")), supportLink),
        el("div", { class: "field" }, el("label", {}, `${t("a_announcement")} (UZ)`), annUz),
        el("div", { class: "field" }, el("label", {}, `${t("a_announcement")} (EN)`), annEn),
        el("div", { class: "field" }, el("label", {}, `${t("a_announcement")} (RU)`), annRu),
        saveBtn,
      ),
      el(
        "div",
        { class: "soft-card", style: "margin-top:16px;max-width:560px" },
        el("h3", { style: "margin-bottom:10px" }, "Environment"),
        ...Object.entries(data.env).map(([k, v]) =>
          el("div", { class: "kv" }, el("span", { class: "muted" }, k), el("b", {}, String(v))),
        ),
      ),
    );
  },
};

/* ------------------------------------------------------------ modals */
function field(labelText, input) {
  const id = `f-${Math.random().toString(36).slice(2, 8)}`;
  input.id = id;
  return el("div", { class: "field" }, el("label", { for: id }, labelText), input);
}

function gameForm(game, onDone) {
  const name = el("input", { class: "input", value: game?.name || "" });
  const nameUz = el("input", { class: "input", value: game?.name || "" });
  const nameRu = el("input", { class: "input", value: game?.name || "" });
  const category = el("input", { class: "input", value: game?.category || "mobile" });
  const currency = el("input", { class: "input", value: game?.currency_label || "" });
  const icon = el("input", { class: "input", value: game?.icon_url || "" });
  const banner = el("input", { class: "input", value: game?.banner_url || "" });
  const active = el("input", { type: "checkbox", checked: game?.active !== false });
  const featured = el("input", { type: "checkbox", checked: !!game?.featured });

  const save = el("button", { class: "btn btn-primary btn-block" }, t("save"));
  save.addEventListener(
    "click",
    withLoading(save, async () => {
      const body = {
        name: name.value.trim(),
        name_uz: nameUz.value.trim() || null,
        name_ru: nameRu.value.trim() || null,
        category: category.value.trim(),
        currency_label: currency.value.trim(),
        icon_url: icon.value.trim() || null,
        banner_url: banner.value.trim() || null,
        active: active.checked,
        featured: featured.checked,
      };
      if (game) await api.patch(`/api/admin/games/${game.id}`, body);
      else await api.post("/api/admin/games", body);
      toast(t("a_save_ok"), "ok");
      m.close();
      onDone();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:14px" }, `${game ? t("edit") : t("create")} — ${t("a_games")}`),
    field(t("a_product_name"), name),
    field("Name UZ", nameUz),
    field("Name RU", nameRu),
    field("Category", category),
    field("🪙", currency),
    field(t("a_image_url") + " (icon)", icon),
    field(t("a_image_url") + " (banner)", banner),
    el("div", { class: "check-row" }, "Active", active),
    el("div", { class: "check-row", style: "margin-bottom:14px" }, "⭐ Featured", featured),
    save,
  ]);
}

function productForm(product, onDone) {
  const name = el("input", { class: "input", value: product?.name || "" });
  const gameId = el("input", { class: "input", type: "number", value: product?.game_id || "" });
  const image = el("input", { class: "input", value: product?.image_url || "" });
  const required = el("textarea", { class: "textarea" }, JSON.stringify({ fields: [] }));
  const marginP = el("input", { class: "input", type: "number", value: product?.margin_percent ?? "" });
  const marginF = el("input", { class: "input", type: "number", value: product?.margin_fixed ?? "" });
  const active = el("input", { type: "checkbox", checked: !!product?.active });

  const save = el("button", { class: "btn btn-primary btn-block" }, t("save"));
  save.addEventListener(
    "click",
    withLoading(save, async () => {
      let required_fields;
      try {
        required_fields = JSON.parse(required.value || '{"fields":[]}');
      } catch {
        toast("JSON error", "err");
        return;
      }
      const body = {
        name: name.value.trim(),
        game_id: Number(gameId.value) || null,
        image_url: image.value.trim() || null,
        required_fields,
        margin_percent: marginP.value === "" ? null : Number(marginP.value),
        margin_fixed: marginF.value === "" ? null : Number(marginF.value),
        active: active.checked,
      };
      if (product) await api.patch(`/api/admin/products/${product.id}`, body);
      else await api.post("/api/admin/products", body);
      toast(t("a_save_ok"), "ok");
      m.close();
      onDone();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:14px" }, `${product ? t("edit") : t("create")} — ${t("a_products")}`),
    field(t("a_product_name"), name),
    field("Game ID", gameId),
    field(t("a_image_url"), image),
    field(t("a_required_fields"), required),
    field(t("a_margin_percent"), marginP),
    field(t("a_margin_fixed"), marginF),
    el("div", { class: "check-row", style: "margin-bottom:14px" }, t("a_active"), active),
    save,
  ]);
}

function variantForm(variant, onDone) {
  const productId = el("input", { class: "input", type: "number", value: variant?.product_id || "" });
  const name = el("input", { class: "input", value: variant?.name || "" });
  const supProd = el("input", { class: "input", value: variant?.supplier_product_id || "" });
  const supVar = el("input", { class: "input", value: variant?.supplier_variation_id || "" });
  const supCost = el("input", { class: "input", type: "number", value: variant?.supplier_cost ?? "" });
  const marginP = el("input", { class: "input", type: "number", value: variant?.margin_percent ?? "" });
  const inStock = el("input", { type: "checkbox", checked: !!variant?.in_stock });
  const active = el("input", { type: "checkbox", checked: !!variant?.active });

  const save = el("button", { class: "btn btn-primary btn-block" }, t("save"));
  save.addEventListener(
    "click",
    withLoading(save, async () => {
      const body = {
        product_id: Number(productId.value) || 0,
        name: name.value.trim(),
        amount_label: name.value.trim(),
        supplier_product_id: supProd.value.trim() || null,
        supplier_variation_id: supVar.value.trim() || null,
        supplier_cost: supCost.value === "" ? null : Number(supCost.value),
        margin_percent: marginP.value === "" ? null : Number(marginP.value),
        in_stock: inStock.checked,
        active: active.checked,
      };
      if (variant) await api.patch(`/api/admin/variants/${variant.id}`, body);
      else await api.post("/api/admin/variants", body);
      toast(t("a_save_ok"), "ok");
      m.close();
      onDone();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:14px" }, `${variant ? t("edit") : t("create")} — ${t("a_variants")}`),
    field("Product ID", productId),
    field(t("a_product_name"), name),
    el("p", { class: "muted small", style: "margin-bottom:10px" }, t("a_supplier_mapping")),
    field("Supplier product ID", supProd),
    field("Supplier variation ID", supVar),
    field(t("a_supplier_cost"), supCost),
    field(t("a_margin_percent"), marginP),
    el("div", { class: "check-row" }, "In stock", inStock),
    el("div", { class: "check-row", style: "margin-bottom:14px" }, t("a_active"), active),
    save,
  ]);
}

function couponForm(coupon, onDone) {
  const code = el("input", { class: "input", value: coupon?.code || "" });
  const type = el(
    "select",
    { class: "select" },
    el("option", { value: "PERCENT", selected: coupon?.coupon_type === "PERCENT" }, t("a_percent")),
    el("option", { value: "FIXED", selected: coupon?.coupon_type === "FIXED" }, t("a_fixed")),
  );
  const value = el("input", { class: "input", type: "number", value: coupon?.value ?? "" });
  const minOrder = el("input", { class: "input", type: "number", value: coupon?.min_order_amount ?? 0 });
  const maxUses = el("input", { class: "input", type: "number", value: coupon?.max_uses ?? "" });
  const perUser = el("input", { class: "input", type: "number", value: coupon?.per_user_limit ?? 1 });
  const expires = el("input", { class: "input", type: "datetime-local" });
  const active = el("input", { type: "checkbox", checked: coupon?.active !== false });

  const save = el("button", { class: "btn btn-primary btn-block" }, t("save"));
  save.addEventListener(
    "click",
    withLoading(save, async () => {
      const body = {
        code: code.value.trim(),
        coupon_type: type.value,
        value: Number(value.value) || 0,
        min_order_amount: Number(minOrder.value) || 0,
        max_uses: maxUses.value === "" ? null : Number(maxUses.value),
        per_user_limit: Number(perUser.value) || 1,
        expires_at: expires.value ? new Date(expires.value).toISOString() : null,
        active: active.checked,
      };
      if (coupon) await api.patch(`/api/admin/coupons/${coupon.id}`, body);
      else await api.post("/api/admin/coupons", body);
      toast(t("a_save_ok"), "ok");
      m.close();
      onDone();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:14px" }, `${coupon ? t("edit") : t("create")} — ${t("a_coupons")}`),
    field(t("a_code"), code),
    field(t("a_type"), type),
    field(t("a_value"), value),
    field(t("a_min_order"), minOrder),
    field(t("a_max_uses"), maxUses),
    field(t("a_per_user"), perUser),
    field(t("a_expires"), expires),
    el("div", { class: "check-row", style: "margin-bottom:14px" }, t("a_active"), active),
    save,
  ]);
}

function promotionForm(promo, onDone) {
  const title = el("input", { class: "input", value: promo?.title || "" });
  const titleUz = el("input", { class: "input", value: promo?.title_uz || "" });
  const titleRu = el("input", { class: "input", value: promo?.title_ru || "" });
  const descEn = el("textarea", { class: "textarea" }, promo?.description_en || "");
  const image = el("input", { class: "input", value: promo?.image_url || "" });
  const coupon = el("input", { class: "input", value: promo?.coupon_code || "" });
  const active = el("input", { type: "checkbox", checked: promo?.active !== false });

  const save = el("button", { class: "btn btn-primary btn-block" }, t("save"));
  save.addEventListener(
    "click",
    withLoading(save, async () => {
      const body = {
        title: title.value.trim(),
        title_uz: titleUz.value.trim() || null,
        title_ru: titleRu.value.trim() || null,
        description_en: descEn.value.trim() || null,
        image_url: image.value.trim() || null,
        coupon_code: coupon.value.trim() || null,
        active: active.checked,
      };
      if (promo) await api.patch(`/api/admin/promotions/${promo.id}`, body);
      else await api.post("/api/admin/promotions", body);
      toast(t("a_save_ok"), "ok");
      m.close();
      onDone();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:14px" }, `${promo ? t("edit") : t("create")} — ${t("a_promotions")}`),
    field(t("a_product_name"), title),
    field("Title UZ", titleUz),
    field("Title RU", titleRu),
    field("Description EN", descEn),
    field(t("a_image_url"), image),
    field("Coupon", coupon),
    el("div", { class: "check-row", style: "margin-bottom:14px" }, t("a_active"), active),
    save,
  ]);
}

function broadcastForm() {
  const titleKey = el("input", { class: "input", value: "order_completed" });
  const bodyKey = el("input", { class: "input", value: "order_completed" });
  const send = el("button", { class: "btn btn-primary btn-block" }, t("a_broadcast"));
  send.addEventListener(
    "click",
    withLoading(send, async () => {
      const res = await api.post("/api/admin/notifications/broadcast", {
        title_key: titleKey.value.trim(),
        body_key: bodyKey.value.trim(),
      });
      toast(t("a_sent", { n: res.sent }), "ok");
      m.close();
    }),
  );
  const m = modal([
    el("h3", { style: "margin-bottom:6px" }, t("a_broadcast_title")),
    el("p", { class: "muted small", style: "margin-bottom:14px" }, t("a_broadcast_hint")),
    field("Title key", titleKey),
    field("Body key", bodyKey),
    send,
  ]);
}
