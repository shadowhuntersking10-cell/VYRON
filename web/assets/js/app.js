/* VYRON SPA bootstrap + hash router. */
import { api } from "./api.js";
import { applyStaticTranslations, getLang, setLang, t } from "./i18n.js";
import { getTheme, initTheme, toggleTheme } from "./theme.js";
import {
  renderAccount, renderAuth, renderCart, renderCheckout, renderGame, renderGames,
  renderHome, renderOrder, renderOrders, renderSandboxCheckout, renderSupport,
} from "./pages.js";
import { renderAdmin } from "./admin.js";

const view = document.getElementById("view");

/* ---------------------------------------------------------- chrome state */
let currentUser = null;

async function refreshUser() {
  try {
    currentUser = (await api.get("/api/auth/me")).user;
  } catch {
    currentUser = null;
  }
  updateChrome();
}

function updateChrome() {
  const adminLink = document.getElementById("mobile-admin-link");
  if (adminLink) adminLink.hidden = !(currentUser && currentUser.is_admin);
  updateCartBadge();
}

async function updateCartBadge() {
  const badge = document.getElementById("cart-count");
  if (!badge) return;
  if (!currentUser) {
    badge.hidden = true;
    return;
  }
  try {
    const { cart } = await api.get("/api/cart");
    badge.textContent = String(cart.count);
    badge.hidden = cart.count === 0;
  } catch {
    badge.hidden = true;
  }
}

document.addEventListener("cart:changed", updateCartBadge);
document.addEventListener("auth:changed", refreshUser);
document.addEventListener("lang:changed", () => {
  applyStaticTranslations();
  route();
});

/* --------------------------------------------------------------- router */
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [pathPart, queryPart] = raw.split("?");
  const segments = pathPart.split("/").filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(queryPart || ""));
  return { segments, params };
}

async function route() {
  const { segments, params } = parseHash();
  const [head, arg] = segments;
  view.innerHTML = "";
  window.scrollTo({ top: 0 });
  document.querySelectorAll(".nav-links a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === `#/${head || ""}` || (!head && a.getAttribute("href") === "#/"));
  });
  try {
    if (!head) await renderHome(view);
    else if (head === "games") await renderGames(view, params);
    else if (head === "game" && arg) await renderGame(view, arg);
    else if (head === "cart") await renderCart(view);
    else if (head === "checkout") await renderCheckout(view);
    else if (head === "orders") await renderOrders(view, params);
    else if (head === "order" && arg) await renderOrder(view, arg);
    else if (head === "account") await renderAccount(view);
    else if (head === "support") await renderSupport(view);
    else if (head === "login") renderAuth(view, "login");
    else if (head === "register") renderAuth(view, "register");
    else if (head === "admin") await renderAdmin(view);
    else if (head === "sandbox" && arg === "checkout") renderSandboxCheckout(view, params);
    else await renderHome(view);
  } catch (err) {
    view.innerHTML = "";
    const box = document.createElement("div");
    box.className = "empty";
    box.textContent = err.message || t("error_generic");
    view.append(box);
  }
}

window.addEventListener("hashchange", route);

/* ------------------------------------------------------------- chrome UI */
function initChrome() {
  document.getElementById("year").textContent = String(new Date().getFullYear());

  // language
  document.querySelectorAll("#lang-switch .chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.lang === getLang());
    chip.addEventListener("click", async () => {
      setLang(chip.dataset.lang);
      document.querySelectorAll("#lang-switch .chip").forEach((c) => c.classList.toggle("active", c === chip));
      if (currentUser) await api.patch("/api/account/profile", { language: chip.dataset.lang }).catch(() => {});
      applyStaticTranslations();
      route();
    });
  });

  // theme
  const themeBtn = document.getElementById("theme-toggle");
  themeBtn.addEventListener("click", async () => {
    toggleTheme();
    if (currentUser) {
      await api.patch("/api/account/profile", { theme: getTheme() }).catch(() => {});
    }
  });

  // search
  const searchForm = document.getElementById("search-form");
  searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = document.getElementById("search-input").value.trim();
    if (q) location.hash = `#/games?search=${encodeURIComponent(q)}`;
  });

  // mobile menu
  const menuBtn = document.getElementById("menu-btn");
  const menu = document.getElementById("mobile-menu");
  menuBtn.addEventListener("click", () => {
    menu.hidden = !menu.hidden;
  });
  menu.addEventListener("click", (e) => {
    if (e.target.tagName === "A") menu.hidden = true;
  });
}

/* ----------------------------------------------------------- telegram bg */
function applyTelegramTheme() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;
  // Match Telegram header if possible
  try {
    if (tg.setHeaderColor) tg.setHeaderColor("bg_color");
    if (tg.setBackgroundColor) tg.setBackgroundColor("bg_color");
  } catch {
    /* ignore */
  }
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  initTheme();
  initChrome();
  applyStaticTranslations();
  applyTelegramTheme();
  await refreshUser();

  // Telegram WebApp auto-login (verified server-side initData)
  const tg = window.Telegram?.WebApp;
  if (!currentUser && tg?.initData) {
    try {
      await api.post("/api/auth/telegram", { init_data: tg.initData });
      await refreshUser();
    } catch {
      /* telegram not configured or invalid */
    }
  }

  await route();
}

boot();
