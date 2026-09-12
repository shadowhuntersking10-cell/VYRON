/* Listing detail: gallery + purchase flow. */
import { post, qs, qsa, toast, t, haptic, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

qsa(".thumb-pick").forEach((img) => {
  img.addEventListener("click", () => {
    const main = qs("#main-image");
    if (main) main.src = img.dataset.src;
    qsa(".thumb-pick").forEach((other) => { other.style.borderColor = "transparent"; });
    img.style.borderColor = "var(--vyron-blue)";
  });
});

const data = JSON.parse(qs("#listing-data")?.textContent || "{}");

qs("#buy-listing")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (document.body.dataset.user !== "1") {
    toast(t("checkout.login_required"), "info");
    setTimeout(() => { window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`; }, 900);
    return;
  }
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> ${t("checkout.placing")}`;
  try {
    const result = await post(`/api/marketplace/listings/${data.id}/purchase`, {
      idempotency_key: idempotencyKey(`listing-${data.id}`),
    });
    clearIdempotencyKey(`listing-${data.id}`);
    haptic("success");
    const payment = result.data?.payment;
    if (payment?.checkout_url) {
      toast(t("checkout.redirecting"), "info");
      window.location.href = payment.checkout_url;
    } else {
      toast(t("marketplace.purchase_complete"), "success");
      setTimeout(() => { window.location.href = "/dashboard/orders"; }, 1200);
    }
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
    button.innerHTML = `⚡ ${t("marketplace.buy_now")}`;
  }
});
