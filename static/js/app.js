/* VYRON frontend: theme, lang, api, auth, checkout, donations, miniapp bridge */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ---------- toast ---------- */
  window.toast = function (msg, type) {
    const box = $("#toasts") || (() => { const d = document.createElement("div"); d.id = "toasts"; document.body.appendChild(d); return d; })();
    const el = document.createElement("div");
    el.className = "toast " + (type || "");
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  };

  /* ---------- theme ---------- */
  function applyTheme(mode) {
    let t = mode;
    if (mode === "system" || !mode) t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    document.documentElement.dataset.theme = t;
  }
  window.setTheme = function (mode) {
    localStorage.setItem("vyron_theme", mode);
    document.cookie = "vyron_theme=" + mode + ";path=/;max-age=31536000;SameSite=Lax";
    applyTheme(mode);
    fetch("/api/users/me", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ theme: mode }) }).catch(() => {});
  };
  applyTheme(localStorage.getItem("vyron_theme") || document.documentElement.dataset.theme || "system");

  /* ---------- language ---------- */
  window.setLang = function (lang) {
    document.cookie = "vyron_lang=" + lang + ";path=/;max-age=31536000;SameSite=Lax";
    fetch("/api/users/me", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang }) }).finally(() => location.reload());
  };

  /* ---------- api ---------- */
  window.api = async function (url, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    const res = await fetch(url, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { data = {}; }
    if (!res.ok) throw { status: res.status, detail: (data && data.detail) || "error" };
    return data;
  };
  window.errText = function (e) {
    const map = (window.I18N_ERRORS || {});
    return map[e.detail] || String(e.detail || "error");
  };

  function formHandler(formId, url, onOk) {
    const f = document.getElementById(formId);
    if (!f) return;
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const err = $(".form-err", f), ok = $(".form-ok", f);
      if (err) err.classList.remove("show");
      const btn = $("button[type=submit]", f);
      if (btn) btn.disabled = true;
      const body = {};
      new FormData(f).forEach((v, k) => body[k] = v);
      try {
        const data = await api(url, { method: "POST", body: JSON.stringify(body) });
        if (onOk) onOk(data, f);
      } catch (e) {
        if (err) { err.textContent = errText(e); err.classList.add("show"); }
        else toast(errText(e), "err");
      } finally { if (btn) btn.disabled = false; }
    });
  }

  /* ---------- auth forms ---------- */
  formHandler("login-form", "/api/auth/login", () => {
    const next = new URLSearchParams(location.search).get("next") || "/";
    location.href = next;
  });
  formHandler("register-form", "/api/auth/register", () => { location.href = "/"; });
  formHandler("forgot-form", "/api/auth/forgot", (d, f) => {
    const ok = $(".form-ok", f);
    if (ok) { ok.textContent = "OK"; ok.classList.add("show"); }
    else toast("OK", "ok");
    if (d.dev_reset_token) {
      const a = document.createElement("a");
      a.href = "/reset-password?token=" + d.dev_reset_token;
      a.textContent = "→ dev reset link";
      a.className = "btn btn-soft btn-sm";
      f.appendChild(a);
    }
  });
  formHandler("reset-form", "/api/auth/reset", () => { location.href = "/login"; });
  formHandler("password-form", "/api/users/me/password", () => toast("OK", "ok"));

  const verifyToken = $("#verify-email-token");
  if (verifyToken && verifyToken.value) {
    api("/api/auth/verify-email?token=" + encodeURIComponent(verifyToken.value))
      .then(() => { const el = $("#verify-result"); if (el) el.textContent = "OK ✓"; })
      .catch((e) => { const el = $("#verify-result"); if (el) el.textContent = errText(e); });
  }

  /* ---------- favorites ---------- */
  $$("[data-fav]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const [type, id] = btn.dataset.fav.split(":");
      try {
        const d = await api("/api/favorites", { method: "POST", body: JSON.stringify({ target_type: type, target_id: +id }) });
        btn.classList.toggle("faved", d.favorited);
        toast(d.favorited ? "♥" : "♡", "ok");
      } catch (e) { toast(errText(e), "err"); }
    });
  });

  /* ---------- checkout ---------- */
  const coRoot = $("#checkout-root");
  if (coRoot) {
    const state = {
      items: JSON.parse(coRoot.dataset.items || "[]"),
      provider: "payme",
      idempotency: (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
    };
    $$(".provider", coRoot).forEach((p) => p.addEventListener("click", () => {
      if (p.classList.contains("disabled")) return;
      $$(".provider", coRoot).forEach((x) => x.classList.remove("selected"));
      p.classList.add("selected");
      state.provider = p.dataset.provider;
    }));
    // load provider statuses
    api("/api/payments/providers").then((d) => {
      Object.entries(d.providers || {}).forEach(([name, st]) => {
        const el = $('.provider[data-provider="' + name + '"]', coRoot);
        if (el && st !== "CONFIGURED" && name !== "wallet") {
          el.classList.add("disabled");
          el.title = "NOT CONFIGURED";
        }
      });
    }).catch(() => {});
    const placeBtn = $("#place-order");
    if (placeBtn) placeBtn.addEventListener("click", async () => {
      const fields = {};
      $$("[data-cfield]", coRoot).forEach((i) => fields[i.dataset.cfield] = i.value);
      const coupon = ($("#coupon-input", coRoot) || {}).value || "";
      placeBtn.disabled = true;
      try {
        const d = await api("/api/checkout", { method: "POST", body: JSON.stringify({
          items: state.items, coupon_code: coupon, provider: state.provider,
          customer_fields: fields, idempotency_key: state.idempotency }) });
        handlePayAction(d.action, d.order.public_id);
      } catch (e) { toast(errText(e), "err"); placeBtn.disabled = false; }
    });
  }

  window.handlePayAction = function (action, publicId) {
    if (!action) { location.href = "/orders/" + publicId; return; }
    if (action.action === "redirect" && action.url) { location.href = action.url; return; }
    if (action.action === "paid") { location.href = "/orders/" + publicId; return; }
    if (action.action === "stars_invoice") {
      const tg = window.Telegram && window.Telegram.WebApp;
      if (tg && tg.openInvoice) {
        toast("Opening Stars invoice…");
        location.href = "/orders/" + publicId;
      } else location.href = "/orders/" + publicId;
      return;
    }
    if (action.action === "error") { toast(action.error || "error", "err"); return; }
    location.href = "/orders/" + publicId;
  };

  /* ---------- donation page ---------- */
  const dnRoot = $("#donate-root");
  if (dnRoot) {
    let amount = dnRoot.dataset.preset || "";
    $$(".preset", dnRoot).forEach((p) => p.addEventListener("click", () => {
      $$(".preset", dnRoot).forEach((x) => x.classList.remove("selected"));
      p.classList.add("selected");
      amount = p.dataset.amount;
      const c = $("#custom-amount"); if (c) c.value = "";
    }));
    const btn = $("#donate-btn");
    if (btn) btn.addEventListener("click", async () => {
      const c = $("#custom-amount");
      const val = (c && c.value) ? c.value : amount;
      if (!val || +val <= 0) { toast("amount?", "err"); return; }
      btn.disabled = true;
      try {
        const d = await api("/api/donations/profiles/" + dnRoot.dataset.username + "/donate", {
          method: "POST",
          body: JSON.stringify({ amount: +val, message: ($("#donate-msg") || {}).value || "",
            is_anonymous: ($("#donate-anon") || {}).checked || false, provider: "payme" }),
        });
        const b = d.breakdown || {};
        if (confirm("Total: " + (b.amount || val) + " | Fee: " + (b.fee || 0) + " | Recipient: " + (b.net || val))) {
          handlePayAction(d.action, d.order);
        } else btn.disabled = false;
      } catch (e) { toast(errText(e), "err"); btn.disabled = false; }
    });
  }

  /* ---------- support ---------- */
  const tForm = $("#ticket-form");
  if (tForm) tForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(tForm);
    try {
      const d = await api("/api/support/tickets", { method: "POST",
        body: JSON.stringify({ subject: fd.get("subject"), category: fd.get("category") || "general", body: fd.get("body") }) });
      location.href = "/support?ticket=" + d.id;
    } catch (e) { toast(errText(e), "err"); }
  });
  const ticketId = new URLSearchParams(location.search).get("ticket");
  if (ticketId && $("#ticket-thread")) {
    api("/api/support/tickets/" + ticketId).then((d) => {
      const box = $("#ticket-thread");
      box.innerHTML = (d.messages || []).map((m) =>
        '<div class="msg' + (m.staff ? " staff" : "") + '"><div>' + escapeHtml(m.body) +
        '</div><small>' + (m.staff ? "staff" : "you") + " · " + m.created_at + "</small></div>").join("");
    }).catch((e) => toast(errText(e), "err"));
    const rf = $("#reply-form");
    if (rf) rf.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const body = $("#reply-body").value;
      try {
        await api("/api/support/tickets/" + ticketId + "/messages", { method: "POST", body: JSON.stringify({ body }) });
        location.reload();
      } catch (e) { toast(errText(e), "err"); }
    });
  }
  function escapeHtml(s) { return String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

  /* ---------- profile settings ---------- */
  const pForm = $("#profile-form");
  if (pForm) pForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(pForm);
    try {
      await api("/api/users/me", { method: "PATCH",
        body: JSON.stringify({ display_name: fd.get("display_name"), lang: fd.get("lang"), theme: fd.get("theme") }) });
      toast("OK", "ok");
      setTimeout(() => location.reload(), 600);
    } catch (e) { toast(errText(e), "err"); }
  });
  const logoutBtn = $("#logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    location.href = "/";
  });

  /* ---------- wallet deposit ---------- */
  const depBtn = $("#deposit-btn");
  if (depBtn) depBtn.addEventListener("click", async () => {
    const amt = ($("#deposit-amount") || {}).value;
    if (!amt || +amt <= 0) { toast("amount?", "err"); return; }
    try {
      const d = await api("/api/wallet/deposit", { method: "POST", body: JSON.stringify({ amount: +amt, provider: "payme" }) });
      handlePayAction(d.action, d.order);
    } catch (e) { toast(errText(e), "err"); }
  });

  /* ---------- seller ---------- */
  const sForm = $("#seller-register-form");
  if (sForm) sForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(sForm);
    try {
      await api("/api/marketplace/sellers/register", { method: "POST",
        body: JSON.stringify({ shop_name: fd.get("shop_name"), bio: fd.get("bio") }) });
      location.reload();
    } catch (e) { toast(errText(e), "err"); }
  });
  const lForm = $("#listing-form");
  if (lForm) lForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(lForm);
    try {
      await api("/api/marketplace/sellers/listings", { method: "POST", body: JSON.stringify({
        title: fd.get("title"), description: fd.get("description") || "",
        price: +fd.get("price"), stock: +(fd.get("stock") || 1),
        category_id: fd.get("category_id") ? +fd.get("category_id") : null }) });
      location.reload();
    } catch (e) { toast(errText(e), "err"); }
  });

  /* ---------- review ---------- */
  const rForm = $("#review-form");
  if (rForm) rForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(rForm);
    try {
      await api("/api/listings/" + rForm.dataset.listing + "/reviews", { method: "POST",
        body: JSON.stringify({ order_id: +fd.get("order_id"), rating: +fd.get("rating"), comment: fd.get("comment") || "" }) });
      location.reload();
    } catch (e) { toast(errText(e), "err"); }
  });

  /* ---------- Telegram Mini App bridge ---------- */
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.colorScheme === "light") { document.documentElement.dataset.theme = "light"; }
      if (tg.BackButton && history.length > 1) {
        tg.BackButton.show();
        tg.BackButton.onClick(() => history.back());
      }
      if (tg.HapticFeedback) {
        document.addEventListener("click", (e) => {
          if (e.target.closest(".btn,.preset,.provider")) tg.HapticFeedback.impactOccurred("light");
        });
      }
      // server-side initData login
      if (tg.initData) {
        api("/api/auth/telegram", { method: "POST", body: JSON.stringify({ init_data: tg.initData }) })
          .then(() => { if (!window.__tg_authed) { window.__tg_authed = 1; location.reload(); } })
          .catch(() => {});
      }
      document.body.classList.add("in-tg");
    } catch (e) { /* no-op */ }
  }
})();
