/* Cart & checkout: server-priced totals, coupon, provider select, place order. */
import { get, post, patch, del, qs, toast, t, escapeHtml, fmtMoney, haptic, emptyState, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

const linesEl = qs("#cart-lines");
const providersEl = qs("#providers");
const placeBtn = qs("#place-order");
let selectedProvider = null;
let cartData = null;

function renderLines() {
  const items = cartData?.items || [];
  if (!items.length) {
    emptyState(linesEl, "🛒", t("cart.empty"), "");
    linesEl.insertAdjacentHTML("beforeend", `<div class="text-center mt-2"><a class="btn btn-primary" href="/products">${t("cart.empty_cta")}</a></div>`);
    placeBtn.disabled = true;
    return;
  }
  placeBtn.disabled = false;
  linesEl.innerHTML = items.map((item) => `
    <div class="cart-line" data-item="${escapeHtml(item.item_id)}">
      <div class="thumb">${item.product_image ? `<img src="${escapeHtml(item.product_image)}" alt="">` : "🕹️"}</div>
      <div style="flex:1;min-width:0">
        <div class="fw-800 truncate">${escapeHtml(item.product_name)}</div>
        <div class="text-mute fs-xs truncate">${escapeHtml(item.variant_name)}${item.game_name ? ` · ${escapeHtml(item.game_name)}` : ""}</div>
        ${Object.entries(item.required_field_values || {}).map(([k, v]) => `<div class="fs-xs text-mute">${escapeHtml(k)}: <b>${escapeHtml(String(v))}</b></div>`).join("")}
        ${!item.in_stock ? `<div class="fs-xs text-danger">${t("products.out_of_stock")}</div>` : ""}
      </div>
      <div class="qty-stepper">
        <button data-act="dec" aria-label="−">−</button>
        <input class="input" type="number" min="1" max="99" value="${item.quantity}" data-act="qty" aria-label="${escapeHtml(t("cart.quantity"))}">
        <button data-act="inc" aria-label="+">+</button>
      </div>
      <div class="text-right" style="min-width:92px">
        <div class="price">${escapeHtml(item.line_total)} ${escapeHtml(item.currency)}</div>
        <button class="btn btn-sm btn-ghost btn-danger mt-1" data-act="rm">${t("cart.remove")}</button>
      </div>
    </div>`).join("");
}

function renderTotals() {
  const totals = cartData?.totals;
  if (!totals) return;
  qs("#sum-subtotal").textContent = fmtMoney(totals.subtotal, totals.currency);
  qs("#sum-fee").textContent = fmtMoney(totals.service_fee, totals.currency);
  qs("#sum-total").textContent = fmtMoney(totals.total, totals.currency);
  const discountRow = qs("#row-discount");
  if (Number(totals.discount) > 0) {
    discountRow.style.display = "flex";
    qs("#sum-discount").textContent = `− ${fmtMoney(totals.discount, totals.currency)}`;
  } else {
    discountRow.style.display = "none";
  }
  const couponState = qs("#coupon-state");
  if (totals.coupon_error) {
    couponState.innerHTML = `<span class="text-danger">${escapeHtml(totals.coupon_error)}</span>`;
  } else if (totals.coupon_code) {
    couponState.innerHTML = `✅ <b>${escapeHtml(totals.coupon_code)}</b> · <a href="#" id="coupon-remove">${escapeHtml(t("cart.coupon_removed"))}</a>`;
    qs("#coupon-remove")?.addEventListener("click", async (event) => {
      event.preventDefault();
      await del("/api/cart/coupon");
      await refresh();
      toast(t("cart.coupon_removed"), "info");
    });
  } else {
    couponState.textContent = "";
  }
}

async function refresh() {
  try {
    const res = await get("/api/cart");
    cartData = res.data;
    renderLines();
    renderTotals();
  } catch (error) {
    toast(error.message, "error");
  }
}

linesEl.addEventListener("click", async (event) => {
  const line = event.target.closest(".cart-line");
  if (!line) return;
  const itemId = line.dataset.item;
  const act = event.target.dataset?.act;
  if (!act) return;
  const input = line.querySelector('input[data-act="qty"]');
  try {
    if (act === "rm") {
      await del(`/api/cart/items/${itemId}`);
      toast(t("toast.deleted"), "info");
    } else if (act === "inc") {
      await patch(`/api/cart/items/${itemId}`, { quantity: Number(input.value) + 1 });
    } else if (act === "dec") {
      const next = Number(input.value) - 1;
      if (next < 1) { await del(`/api/cart/items/${itemId}`); }
      else { await patch(`/api/cart/items/${itemId}`, { quantity: next }); }
    }
    haptic("light");
    await refresh();
  } catch (error) {
    toast(error.message, "error");
  }
});

linesEl.addEventListener("change", async (event) => {
  if (event.target.dataset?.act !== "qty") return;
  const line = event.target.closest(".cart-line");
  try {
    await patch(`/api/cart/items/${line.dataset.item}`, { quantity: Math.max(1, Number(event.target.value) || 1) });
    await refresh();
  } catch (error) {
    toast(error.message, "error");
  }
});

qs("#coupon-apply").addEventListener("click", async () => {
  const code = qs("#coupon-input").value.trim();
  if (!code) return;
  try {
    await post("/api/cart/coupon", { code });
    qs("#coupon-input").value = "";
    toast(t("cart.coupon_applied"), "success");
    await refresh();
  } catch (error) {
    toast(error.message, "error");
  }
});

async function loadProviders() {
  try {
    const res = await get("/api/payment-providers");
    const providers = res.data || [];
    if (!providers.length) {
      providersEl.innerHTML = `<div class="empty-state"><div class="icon">💳</div><b>${escapeHtml(t("errors.PAYMENT_PROVIDER_NOT_CONFIGURED"))}</b></div>`;
      return;
    }
    providersEl.innerHTML = providers.map((p, index) => `
      <label class="provider-option ${index === 0 ? "selected" : ""}" data-provider="${escapeHtml(p.name)}">
        <input type="radio" name="provider" value="${escapeHtml(p.name)}" ${index === 0 ? "checked" : ""}>
        <b>${escapeHtml(p.display_name || p.name)}</b>
      </label>`).join("");
    selectedProvider = providers[0].name;
    providersEl.querySelectorAll(".provider-option").forEach((option) => {
      option.addEventListener("click", () => {
        providersEl.querySelectorAll(".provider-option").forEach((o) => o.classList.remove("selected"));
        option.classList.add("selected");
        option.querySelector("input").checked = true;
        selectedProvider = option.dataset.provider;
        haptic("light");
      });
    });
  } catch (error) {
    providersEl.innerHTML = `<div class="empty-state"><b>${escapeHtml(error.message)}</b></div>`;
  }
}

placeBtn.addEventListener("click", async () => {
  placeBtn.disabled = true;
  placeBtn.innerHTML = `<span class="spinner"></span> ${t("checkout.placing")}`;
  try {
    const result = await post("/api/checkout", {
      provider: selectedProvider,
      notes: qs("#order-notes").value.trim() || null,
      idempotency_key: idempotencyKey("checkout"),
    });
    clearIdempotencyKey("checkout");
    haptic("success");
    let payment = result.data?.payment;
    const order = result.data?.order;
    if (!payment?.checkout_url && order?.id) {
      // Order created but no payment yet — initiate it now (server returns a clear
      // PAYMENT_PROVIDER_NOT_CONFIGURED error if the provider lacks credentials).
      try {
        const payRes = await post(`/api/orders/${order.id}/pay`, { provider: selectedProvider });
        payment = payRes.data?.payment;
      } catch (payError) {
        toast(payError.message, "error");
        window.location.href = "/dashboard/orders";
        return;
      }
    }
    if (payment?.checkout_url) {
      toast(t("checkout.redirecting"), "info");
      window.location.href = payment.checkout_url;
    } else {
      toast(t("toast.order_created"), "success");
      window.location.href = "/dashboard/orders";
    }
  } catch (error) {
    toast(error.message, "error");
    placeBtn.disabled = false;
    placeBtn.textContent = t("checkout.place_order");
  }
});

await Promise.all([refresh(), loadProviders()]);
