/* Theme: light / dark / system */
(function () {
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('vyron_theme', theme); } catch (e) {}
  }
  function current() {
    try { return localStorage.getItem('vyron_theme') || 'system'; } catch (e) { return 'system'; }
  }
  function cycle() {
    const order = ['system', 'light', 'dark'];
    apply(order[(order.indexOf(current()) + 1) % 3]);
  }
  document.addEventListener('DOMContentLoaded', () => {
    apply(current());
    document.getElementById('themeBtn')?.addEventListener('click', cycle);
  });
  window.VYRON_THEME = { apply, current, cycle };
})();
