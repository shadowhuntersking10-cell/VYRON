/* Theme (day / night) — persisted, integrates with Telegram WebApp theme. */

export function getTheme() {
  return localStorage.getItem("vyron_theme") || "night";
}

export function setTheme(theme, persist = true) {
  const value = theme === "day" ? "day" : "night";
  document.documentElement.dataset.theme = value;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = value === "day" ? "#E9F1FB" : "#0B2447";
  if (persist) localStorage.setItem("vyron_theme", value);
  const ico = document.querySelector(".theme-ico");
  if (ico) ico.textContent = value === "day" ? "☀️" : "🌙";
}

export function toggleTheme() {
  setTheme(getTheme() === "day" ? "night" : "day");
}

export function initTheme() {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      document.body.classList.add("tg-mode");
    } catch {
      /* not inside telegram */
    }
  }
  const saved = localStorage.getItem("vyron_theme");
  if (saved) {
    setTheme(saved, false);
  } else if (tg?.colorScheme === "light") {
    setTheme("day", false);
  } else {
    setTheme("night", false);
  }
}
