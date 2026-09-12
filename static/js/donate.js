/* Public donation page: amount presets, transparent server-fee preview, submit. */
import { post, qs, qsa, toast, t, haptic, idempotencyKey, clearIdempotencyKey } from "/static/js/core.js";

const data = JSON.parse(qs("#donate-data")?.textContent || "{}");
const amountInput = qs("#amount");
const feeBox = qs("#fee-box");
const donateBtn = qs("#donate-btn");
const feePct = Number(data.fee_pct || 0);
const feeFixed = Number(data.fee_fixed || 0);

function refreshFeePreview() {
  const gross = Number(amountInput.value || 0);
  if (!(gross >= 1)) {
    feeBox.style.display = "none";
    donateBtn.disabled = true;
    return;
  }
  const fee = Math.min(gross, Math.round((gross * feePct / 100 + feeFixed) * 100) / 100);
  const net = Math.round((gross - fee) * 100) / 100;
  qs("#fee-gross").textContent = `${gross.toFixed(2)} ${data.currency}`;
  qs("#fee-amount").textContent = `− ${fee.toFixed(2)} ${data.currency}`;
  qs("#fee-net").textContent = `${net.toFixed(2)} ${data.currency}`;
  feeBox.style.display = "block";
  donateBtn.disabled = false;
}

qsa(".amount-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    qsa(".amount-btn").forEach((b) => b.classList.remove("selected"));
    btn.classList.add("selected");
    if (btn.dataset.amount !== "custom") {
      amountInput.value = btn.dataset.amount;
    } else {
      amountInput.value = "";
      amountInput.focus();
    }
    haptic("light");
    refreshFeePreview();
  });
});

amountInput.addEventListener("input", () => {
  qsa(".amount-btn").forEach((b) => b.classList.remove("selected"));
  refreshFeePreview();
});

donateBtn.addEventListener("click", async () => {
  const gross = Number(amountInput.value || 0);
  if (!(gross >= 1)) {
    toast(t("donate.min_amount", { min: `1.00 ${data.currency}` }), "error");
    return;
  }
  donateBtn.disabled = true;
  donateBtn.innerHTML = `<span class="spinner"></span> ${t("common.loading")}`;
  try {
    const result = await post("/api/donations", {
      username: data.username,
      amount: String(gross),
      donor_name: qs("#donor-name").value.trim(),
      message: qs("#donor-message").value.trim(),
      anonymous: qs("#anonymous").checked,
      idempotency_key: idempotencyKey(`donate-${data.username}`),
    });
    clearIdempotencyKey(`donate-${data.username}`);
    haptic("success");
    const payment = result.data?.payment;
    if (payment?.checkout_url) {
      toast(t("checkout.redirecting"), "info");
      window.location.href = payment.checkout_url;
    } else {
      toast(t("donate.pending"), "info", 5000);
      donateBtn.innerHTML = `💝 ${t("donate.donate_now")}`;
      donateBtn.disabled = false;
    }
  } catch (error) {
    toast(error.message, "error");
    donateBtn.innerHTML = `💝 ${t("donate.donate_now")}`;
    donateBtn.disabled = false;
  }
});

refreshFeePreview();
