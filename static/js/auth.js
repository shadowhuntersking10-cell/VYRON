/* Auth pages: login / register / forgot / reset / verify. */
import { post, qs, toast, t, haptic } from "/static/js/core.js";

function busy(form, on) {
  const button = form.querySelector('button[type="submit"]');
  if (!button) return;
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = on;
  if (on) button.innerHTML = `<span class="spinner"></span>`;
  else button.textContent = button.dataset.label;
}

/* --- login --- */
qs("#login-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  busy(form, true);
  try {
    await post("/api/auth/login", { email: qs("#email").value.trim(), password: qs("#password").value });
    haptic("success");
    toast(t("auth.welcome"), "success");
    const next = JSON.parse(qs("#auth-next")?.textContent || "{}").next || "/dashboard";
    window.location.href = next;
  } catch (error) {
    toast(error.message, "error");
    busy(form, false);
  }
});

/* --- register --- */
const registerForm = qs("#register-form");
registerForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = qs("#password").value;
  const confirm = qs("#confirm-password").value;
  if (password !== confirm) {
    qs("#match-error").textContent = t("auth.passwords_mismatch");
    return;
  }
  qs("#match-error").textContent = "";
  busy(registerForm, true);
  try {
    await post("/api/auth/register", {
      name: qs("#name").value.trim(),
      username: qs("#username").value.trim(),
      email: qs("#email").value.trim(),
      phone: qs("#phone").value.trim() || null,
      password,
      confirm_password: confirm,
    });
    haptic("success");
    toast(t("auth.verify_check"), "info", 5000);
    window.location.href = "/dashboard";
  } catch (error) {
    toast(error.message, "error");
    busy(registerForm, false);
  }
});

/* --- forgot --- */
qs("#forgot-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  busy(form, true);
  try {
    const result = await post("/api/auth/forgot-password", { email: qs("#email").value.trim() });
    toast(t("auth.reset_sent"), "success", 5000);
    if (result.dev_token) {
      /* development-only convenience; never present in production */
      window.location.href = `/reset-password?token=${encodeURIComponent(result.dev_token)}`;
      return;
    }
    busy(form, false);
  } catch (error) {
    toast(error.message, "error");
    busy(form, false);
  }
});

/* --- reset --- */
qs("#reset-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const token = JSON.parse(qs("#reset-token")?.textContent || "{}").token;
  if (!token) {
    toast(t("auth.verify_invalid"), "error");
    return;
  }
  busy(form, true);
  try {
    await post("/api/auth/reset-password", {
      token,
      new_password: qs("#new-password").value,
      confirm_password: qs("#confirm-password").value,
    });
    haptic("success");
    toast(t("auth.reset_password"), "success");
    setTimeout(() => { window.location.href = "/login"; }, 1000);
  } catch (error) {
    toast(error.message, "error");
    busy(form, false);
  }
});

/* --- verify --- */
const verifyToken = JSON.parse(qs("#verify-token")?.textContent || "{}").token;
const verifyStatus = qs("#verify-status");
if (verifyStatus) {
  (async () => {
    if (!verifyToken) {
      verifyStatus.innerHTML = `⚠️ ${t("auth.verify_invalid")}`;
      qs("#verify-actions").classList.remove("hidden");
      return;
    }
    try {
      await post("/api/auth/verify-email", { token: verifyToken });
      verifyStatus.innerHTML = `✅ ${t("auth.verify_success")}`;
      setTimeout(() => { window.location.href = "/dashboard"; }, 1200);
    } catch (error) {
      verifyStatus.innerHTML = `⛔ ${t("auth.verify_invalid")}`;
      qs("#verify-actions").classList.remove("hidden");
    }
  })();
}

qs("#resend-verify")?.addEventListener("click", async (event) => {
  event.target.disabled = true;
  try {
    await post("/api/auth/verify-email/resend");
    toast(t("auth.verify_check"), "success");
  } catch (error) {
    toast(error.message, "error");
    event.target.disabled = false;
  }
});
