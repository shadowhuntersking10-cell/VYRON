/* VYRON admin panel */
(function () {
  "use strict";
  const root = $("#admin-root");
  if (!root) return;
  const view = $("#admin-view");

  function money(v) { return Number(v || 0).toLocaleString("en-US"); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function tbl(heads, rows) {
    return '<div class="table-wrap"><table class="tbl"><thead><tr>' +
      heads.map((h) => "<th>" + esc(h) + "</th>").join("") + "</tr></thead><tbody>" +
      rows.map((r) => "<tr>" + r.map((c, i) => '<td data-l="' + esc(heads[i]) + '">' + c + "</td>").join("") + "</tr>").join("") +
      "</tbody></table></div>";
  }

  const sections = {
    dashboard: async () => {
      const d = await api("/api/admin/dashboard?days=30");
      const r = d.range_30d || {};
      const stats = [["gross", r.gross_revenue], ["supplier", r.supplier_costs], ["pay_fees", r.payment_fees],
        ["platform", r.platform_revenue], ["market_com", r.marketplace_commission], ["don_fees", r.donation_fees],
        ["payouts", r.seller_payouts], ["refunds", r.refunds], ["net", r.net_profit],
        ["orders", r.orders], ["aov", r.aov]];
      view.innerHTML = '<div class="stat-grid">' + stats.map(([l, v]) =>
        '<div class="stat"><div class="v">' + money(v) + '</div><div class="l">' + esc(l) + "</div></div>").join("") + "</div>" +
        "<h3>Top products</h3>" + tbl(["title", "total"],
          (d.top_products || []).map((p) => [esc(p.title), money(p.total)])) +
        "<h3>Order statuses</h3>" + tbl(["status", "count"],
          Object.entries(d.statuses || {}).map(([k, v]) => [esc(k), v]));
    },
    users: async (q) => {
      q = q || "";
      const d = await api("/api/admin/users?search=" + encodeURIComponent(q));
      view.innerHTML = '<div class="toolbar"><input class="input" id="q" placeholder="search" value="' + esc(q) + '">' +
        '<button class="btn btn-soft btn-sm" onclick="AdminGo.users(document.getElementById(' + "'q'" + ').value)">Search</button></div>' +
        tbl(["id", "username", "email", "roles", "banned", "actions"], d.items.map((u) =>
          [u.id, esc(u.username), esc(u.email), u.roles.join(","), u.banned ? "YES" : "no",
           '<button class="btn btn-sm ' + (u.banned ? "btn-success" : "btn-danger") + '" data-ban="' + u.id + '" data-v="' + (u.banned ? "0" : "1") + '">' +
           (u.banned ? "unban" : "ban") + "</button>"]));
      view.querySelectorAll("[data-ban]").forEach((b) => b.onclick = async () => {
        await api("/api/admin/users/" + b.dataset.ban + "/ban", { method: "POST", body: JSON.stringify({ banned: b.dataset.v === "1" }) });
        sections.users(q);
      });
    },
    products: async () => {
      const d = await api("/api/admin/products?per_page=100");
      view.innerHTML = tbl(["id", "name", "cost", "price", "min_safe", "suggested", "profit", "margin", "actions"],
        d.items.map((p) => [p.id, esc(p.name), money(p.supplier_cost), money(p.price), money(p.min_safe),
          money(p.suggested), money(p.profit), p.margin + "%",
          '<button class="btn btn-sm btn-soft" data-price="' + p.id + '">pricing</button>']));
      view.querySelectorAll("[data-price]").forEach((b) => b.onclick = () => priceEditor(+b.dataset.price));
    },
    games: async () => {
      const d = await api("/api/admin/games?per_page=100");
      view.innerHTML = tbl(["id", "name", "slug", "status", "featured", "products"],
        d.items.map((g) => [g.id, esc(g.name), esc(g.slug), g.status, g.featured ? "★" : "", g.products])) +
        '<h3>Create game</h3><div class="toolbar"><input class="input" id="g-name" placeholder="Name">' +
        '<input class="input" id="g-desc" placeholder="Description"><button class="btn btn-primary btn-sm" id="g-create">Create</button></div>';
      document.getElementById("g-create").onclick = async () => {
        await api("/api/admin/games", { method: "POST", body: JSON.stringify({ name: document.getElementById("g-name").value, description: document.getElementById("g-desc").value }) });
        toast("OK", "ok"); sections.games();
      };
    },
    orders: async () => {
      const d = await api("/api/admin/orders?per_page=50");
      view.innerHTML = tbl(["id", "public", "user", "kind", "status", "total", "actions"], d.items.map((o) =>
        [o.id, esc(o.public_id), o.user, o.kind, "<b>" + esc(o.status) + "</b>", money(o.total),
         '<button class="btn btn-sm btn-soft" data-ost="' + o.id + '">status</button> ' +
         '<button class="btn btn-sm btn-soft" data-ref="' + o.id + '">refund</button>']));
      view.querySelectorAll("[data-ost]").forEach((b) => b.onclick = async () => {
        const st = prompt("New status (COMPLETED/FAILED/CANCELLED/MANUAL_REVIEW/PROCESSING):");
        if (!st) return;
        try {
          await api("/api/admin/orders/" + b.dataset.ost + "/status", { method: "POST", body: JSON.stringify({ status: st }) });
          toast("OK", "ok"); sections.orders();
        } catch (e) { toast(errText(e), "err"); }
      });
      view.querySelectorAll("[data-ref]").forEach((b) => b.onclick = async () => {
        if (!confirm("Refund to wallet?")) return;
        await api("/api/admin/refunds/" + b.dataset.ref + "?reason=admin", { method: "POST" });
        toast("OK", "ok"); sections.orders();
      });
    },
    payments: async () => {
      const d = await api("/api/admin/payments?per_page=50");
      const st = await api("/api/payments/providers");
      view.innerHTML = "<h3>Providers</h3>" + tbl(["provider", "status"],
        Object.entries(st.providers || {}).map(([k, v]) => [k, v])) +
        "<h3>Payments</h3>" + tbl(["id", "order", "provider", "status", "amount"],
          d.items.map((p) => [p.id, p.order, p.provider, p.status, money(p.amount)]));
    },
    suppliers: async () => {
      const d = await api("/api/admin/suppliers");
      view.innerHTML = tbl(["id", "name", "code", "adapter", "configured", "active", "balance", "error"],
        d.items.map((s) => [s.id, esc(s.name), esc(s.code), s.adapter, s.configured ? "YES" : "NO",
          s.active ? "yes" : "no", money(s.balance), esc(s.last_error || "")])) +
        '<h3>Add / update supplier</h3><div class="toolbar"><input class="input" id="s-name" placeholder="Name">' +
        '<input class="input" id="s-code" placeholder="code"><input class="input" id="s-url" placeholder="API URL">' +
        '<input class="input" id="s-key" placeholder="API key"><button class="btn btn-primary btn-sm" id="s-save">Save</button></div>';
      document.getElementById("s-save").onclick = async () => {
        await api("/api/admin/suppliers", { method: "POST", body: JSON.stringify({
          name: document.getElementById("s-name").value, code: document.getElementById("s-code").value,
          api_url: document.getElementById("s-url").value, api_key: document.getElementById("s-key").value }) });
        toast("OK", "ok"); sections.suppliers();
      };
    },
    sellers: async () => {
      const d = await api("/api/admin/sellers");
      view.innerHTML = tbl(["id", "shop", "slug", "status", "sales", "actions"], d.items.map((s) =>
        [s.id, esc(s.shop), esc(s.slug), s.status, s.sales,
         '<button class="btn btn-sm btn-success" data-ap="1" data-id="' + s.id + '">approve</button> ' +
         '<button class="btn btn-sm btn-danger" data-ap="0" data-id="' + s.id + '">reject</button>']));
      view.querySelectorAll("[data-ap]").forEach((b) => b.onclick = async () => {
        await api("/api/admin/sellers/" + b.dataset.id + "/verify?approved=" + (b.dataset.ap === "1"), { method: "POST" });
        sections.sellers();
      });
      const p = await api("/api/admin/payouts");
      view.innerHTML += "<h3>Payouts</h3>" + tbl(["id", "seller", "amount", "method", "status", "actions"],
        p.items.map((x) => [x.id, x.seller, money(x.amount), esc(x.method), x.status,
          x.status === "pending" ? '<button class="btn btn-sm btn-success" data-po="1" data-id="' + x.id + '">approve</button> ' +
          '<button class="btn btn-sm btn-danger" data-po="0" data-id="' + x.id + '">reject</button>' : ""]));
      view.querySelectorAll("[data-po]").forEach((b) => b.onclick = async () => {
        await api("/api/admin/payouts/" + b.dataset.id + "?approve=" + (b.dataset.po === "1"), { method: "POST" });
        sections.sellers();
      });
    },
    coupons: async () => {
      const d = await api("/api/admin/coupons");
      view.innerHTML = tbl(["id", "code", "kind", "value", "used", "active"], d.items.map((c) =>
        [c.id, c.code, c.kind, c.value, c.used, c.active ? "yes" : "no"])) +
        '<h3>Create coupon</h3><div class="toolbar"><input class="input" id="c-code" placeholder="CODE">' +
        '<input class="input" id="c-val" placeholder="value" type="number"><button class="btn btn-primary btn-sm" id="c-save">Save</button></div>';
      document.getElementById("c-save").onclick = async () => {
        await api("/api/admin/coupons", { method: "POST", body: JSON.stringify({ code: document.getElementById("c-code").value, value: +document.getElementById("c-val").value }) });
        toast("OK", "ok"); sections.coupons();
      };
    },
    promotions: async () => {
      const d = await api("/api/admin/promotions");
      view.innerHTML = tbl(["id", "title", "slug", "banner", "active"], d.items.map((p) =>
        [p.id, esc(p.title), esc(p.slug), esc(p.banner), p.active ? "yes" : "no"])) +
        '<h3>Create promotion</h3><div class="toolbar"><input class="input" id="p-title" placeholder="Title">' +
        '<input class="input" id="p-url" placeholder="target url"><button class="btn btn-primary btn-sm" id="p-save">Save</button></div>';
      document.getElementById("p-save").onclick = async () => {
        await api("/api/admin/promotions", { method: "POST", body: JSON.stringify({ title: document.getElementById("p-title").value, target_url: document.getElementById("p-url").value }) });
        toast("OK", "ok"); sections.promotions();
      };
      const pr = await api("/api/admin/donation-presets");
      view.innerHTML += "<h3>Donation presets</h3>" + tbl(["id", "amount", "active"],
        pr.items.map((x) => [x.id, money(x.amount), x.active ? "yes" : "no"])) +
        '<div class="toolbar"><input class="input" id="d-amt" type="number" placeholder="amount">' +
        '<button class="btn btn-primary btn-sm" id="d-save">Add preset</button></div>';
      document.getElementById("d-save").onclick = async () => {
        await api("/api/admin/donation-presets", { method: "POST", body: JSON.stringify({ amount: +document.getElementById("d-amt").value }) });
        sections.promotions();
      };
    },
    media: async () => {
      const d = await api("/api/admin/media?per_page=60");
      view.innerHTML = '<div class="toolbar"><input class="input" id="m-file" type="file" accept="image/*">' +
        '<select class="input" id="m-type"><option>GAME_LOGO</option><option>GAME_COVER</option><option>GAME_BANNER</option>' +
        '<option>PRODUCT_IMAGE</option><option>MARKETPLACE_IMAGE</option><option>AVATAR</option><option>DONATION_COVER</option>' +
        '<option>PROMOTION_BANNER</option></select><button class="btn btn-primary btn-sm" id="m-up">Upload</button></div>' +
        tbl(["id", "file", "path", "type", "size", "preview", "actions"], d.items.map((m) =>
          [m.id, esc(m.file), esc(m.path), m.type, m.size,
           '<img src="' + esc(m.path) + '" style="height:40px;border-radius:8px" loading="lazy" onerror="this.style.display=' + "'none'" + '">',
           '<button class="btn btn-sm btn-danger" data-del="' + m.id + '">del</button>']));
      document.getElementById("m-up").onclick = async () => {
        const f = document.getElementById("m-file").files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append("file", f);
        fd.append("type", document.getElementById("m-type").value);
        const res = await fetch("/api/admin/media-upload", { method: "POST", body: fd });
        if (!res.ok) { toast("upload failed", "err"); return; }
        toast("OK", "ok"); sections.media();
      };
      view.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
        if (!confirm("delete?")) return;
        await fetch("/api/admin/media/" + b.dataset.del, { method: "DELETE" });
        sections.media();
      });
    },
    support: async () => {
      const d = await api("/api/admin/tickets");
      view.innerHTML = tbl(["id", "user", "subject", "category", "status", "actions"], d.items.map((t) =>
        [t.id, t.user, esc(t.subject), t.category, t.status,
         '<button class="btn btn-sm btn-soft" data-tk="' + t.id + '">open</button>']));
      view.querySelectorAll("[data-tk]").forEach((b) => b.onclick = async () => {
        const t = await api("/api/support/tickets/" + b.dataset.tk);
        const body = prompt("Reply (messages: " + t.messages.length + "):");
        if (body) {
          await api("/api/support/tickets/" + b.dataset.tk + "/messages", { method: "POST", body: JSON.stringify({ body }) });
          toast("OK", "ok");
        }
      });
    },
    audit: async () => {
      const d = await api("/api/admin/audit?per_page=50");
      view.innerHTML = tbl(["id", "admin", "action", "entity", "entity_id", "ip", "time"],
        d.items.map((a) => [a.id, a.admin, esc(a.action), esc(a.entity), esc(a.entity_id), esc(a.ip), esc(a.created_at)]));
    },
    settings: async () => {
      const d = await api("/api/admin/settings");
      view.innerHTML = tbl(["key", "value", "description"], d.items.map((s) =>
        [esc(s.key), esc(s.value), esc(s.description || "")])) +
        '<h3>Set setting</h3><div class="toolbar"><input class="input" id="k" placeholder="key">' +
        '<input class="input" id="v" placeholder="value"><button class="btn btn-primary btn-sm" id="s-save">Save</button></div>' +
        "<p>ENV: " + esc(JSON.stringify(d.env)) + "</p>";
      document.getElementById("s-save").onclick = async () => {
        await api("/api/admin/settings", { method: "POST", body: JSON.stringify({ key: document.getElementById("k").value, value: document.getElementById("v").value }) });
        toast("OK", "ok"); sections.settings();
      };
    },
  };

  async function priceEditor(id) {
    const q = await api("/api/admin/products/" + id + "/pricing");
    view.innerHTML = '<button class="btn btn-soft btn-sm" id="bk">← back</button><h3>Pricing #' + id + "</h3>" +
      '<div class="kv"><span>Supplier cost</span><b>' + money(q.supplier_cost) + '</b></div>' +
      '<div class="kv"><span>Payment fee</span><b>' + money(q.payment_fee) + '</b></div>' +
      '<div class="kv"><span>Platform fee</span><b>' + money(q.platform_fee) + '</b></div>' +
      '<div class="kv"><span>Minimum safe</span><b>' + money(q.minimum_safe_price) + '</b></div>' +
      '<div class="kv"><span>Suggested</span><b>' + money(q.suggested_price) + '</b></div>' +
      '<div class="kv"><span>Current</span><b>' + money(q.current_price) + '</b></div>' +
      '<div class="kv"><span>Profit</span><b>' + money(q.expected_profit) + " (" + q.expected_margin_percent + '%)</b></div>' +
      '<div class="kv"><span>Max safe discount</span><b>' + money(q.max_safe_discount) + '</b></div>' +
      '<div class="toolbar" style="margin-top:16px"><input class="input" id="np" type="number" value="' + q.current_price + '">' +
      '<label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="ov"> override</label>' +
      '<button class="btn btn-primary btn-sm" id="pv">Preview</button>' +
      '<button class="btn btn-success btn-sm" id="sv">Save</button></div><div id="pwarn"></div>';
    document.getElementById("bk").onclick = () => sections.products();
    document.getElementById("pv").onclick = async () => {
      const r = await api("/api/admin/products/" + id + "/pricing?new_price=" + document.getElementById("np").value);
      document.getElementById("pwarn").innerHTML = "<p>Profit: <b>" + money(r.expected_profit) + "</b> (" + r.expected_margin_percent + "%) " +
        (r.blocked ? '<span class="badge err">BLOCKED: ' + esc(r.warning) + "</span>" : '<span class="badge ok">OK</span>') + "</p>";
    };
    document.getElementById("sv").onclick = async () => {
      try {
        await api("/api/admin/products/" + id + "/price", { method: "POST", body: JSON.stringify({
          customer_price: +document.getElementById("np").value,
          override_loss_protection: document.getElementById("ov").checked }) });
        toast("saved", "ok"); sections.products();
      } catch (e) { toast(errText(e), "err"); }
    };
  }

  window.AdminGo = sections;
  document.querySelectorAll("[data-section]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-section]").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    view.innerHTML = '<div class="skeleton" style="height:200px"></div>';
    sections[b.dataset.section]().catch((e) => { view.innerHTML = "<p>Error: " + esc(e.detail || e) + "</p>"; });
  }));
  sections.dashboard().catch((e) => { view.innerHTML = "<p>Error: " + esc(e.detail || e) + "</p>"; });
})();
