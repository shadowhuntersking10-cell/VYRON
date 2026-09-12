/* Product detail: variant selection, required-field validation, add-to-cart & buy-now. */
import { get, post, toast, t, qs, qsa, escapeHtml, haptic, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

const state = {
  variant: null,
  qty: 1,
};

function selectedVariantButton() {
  return qs(".variant-option.selected");
}

function refreshSummary() {
  const btn = selectedVariantButton();
  if (!btn) return;
  const price = Number(btn.dataset.price);
  const currency = btn.dataset.currency;
  qs("#sum-variant").textContent = btn.dataset.name;
  qs("#sum-price").textContent = `${price.toFixed(2)} ${currency}`;
  qs("#sum-qty").textContent = state.qty;
  qs("#sum-total").textContent = `${(price * state.qty).toFixed(2)} ${currency}`;
}

function collectRequiredFields() {
  const values = {};
  let valid = true;
  for (const input of qsa("#required-fields .input")) {
    const key = input.dataset.key;
    const required = input.dataset.required === "1";
    const value = input.value.trim();
    if (required && !value) {
      valid = false;
      input.style.boxShadow = "inset 3px 3px 8px var(--inset-dark), inset -3px -3px 8px var(--inset-light), 0 0 0 3px rgba(248,113,113,0.4)";
    } else {
      input.style.boxShadow = "";
    }
    if (input.pattern && value && !new RegExp(`^(?:${input.pattern})$`).test(value)) {
      valid = false;
      input.style.boxShadow = "inset 3px 3px 8px var(--inset-dark), inset -3px -3px 8px var(--inset-light), 0 0 0 3px rgba(245,185,66,0.5)";
    }
    if (value) values[key] = value;
  }
  if (!valid) {
    toast(t("checkout.required_field_missing"), "error");
    return null;
  }
  return values;
}

qsa(".variant-option").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.disabled) return;
    qsa(".variant-option").forEach((b) => { b.classList.remove("selected"); const r = b.querySelector("input"); if (r) r.checked = false; });
    btn.classList.add("selected");
    const radio = btn.querySelector("input");
    if (radio) radio.checked = true;
    state.variant = btn.dataset.variant;
    haptic("light");
    refreshSummary();
  });
});

qs("#qty-minus")?.addEventListener("click", () => { state.qty = Math.max(1, state.qty - 1); qs("#qty").value = state.qty; refreshSummary(); });
qs("#qty-plus")?.addEventListener("click", () => { state.qty = Math.min(99, state.qty + 1); qs("#qty").value = state.qty; refreshSummary(); });
qs("#qty")?.addEventListener("input", (event) => { state.qty = Math.max(1, Math.min(99, Number(event.target.value) || 1)); refreshSummary(); });

async function ensureLoggedIn() {
  if (document.body.dataset.user === "1") return true;
  toast(t("checkout.login_required"), "info");
  setTimeout(() => { window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`; }, 900);
  return false;
}

qs("#add-to-cart")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!(await ensureLoggedIn())) return;
  const values = collectRequiredFields();
  if (values === null) return;
  const btn = selectedVariantButton();
  if (!btn) return;
  button.disabled = true;
  try {
    await post("/api/cart/items", { variant_id: btn.dataset.variant, quantity: state.qty, required_field_values: values });
    toast(t("toast.added_to_cart"), "success");
    haptic("success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

qs("#buy-now")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!(await ensureLoggedIn())) return;
  const values = collectRequiredFields();
  if (values === null) return;
  const btn = selectedVariantButton();
  if (!btn) return;
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> ${t("checkout.placing")}`;
  try {
    const result = await post("/api/checkout/buy-now", {
      variant_id: btn.dataset.variant,
      quantity: state.qty,
      required_field_values: values,
      idempotency_key: idempotencyKey("buynow"),
    });
    clearIdempotencyKey("buynow");
    haptic("success");
    const payment = result.data?.payment;
    if (payment?.checkout_url) {
      toast(t("checkout.redirecting"), "info");
      window.location.href = payment.checkout_url;
    } else {
      window.location.href = `/dashboard/orders?highlight=${result.data?.order?.id || ""}`;
    }
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
    button.innerHTML = `⚡ ${t("products.buy_now")}`;
  }
});

state.variant = selectedVariantButton()?.dataset.variant || null;
refreshSummary();
