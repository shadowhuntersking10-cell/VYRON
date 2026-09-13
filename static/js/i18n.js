/* VYRON i18n: loads /api/locale/{lang}, applies data-i18n keys */
(function () {
  let strings = {};
  function get(key) {
    return key.split('.').reduce((o, k) => (o && o[k] !== undefined ? o[k] : null), strings) || key;
  }
  async function load(lang) {
    try {
      const r = await fetch('/api/locale/' + lang);
      const d = await r.json();
      strings = d.strings || {};
    } catch (e) { /* keep defaults */ }
  }
  function apply() {
    document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = get(el.dataset.i18n); });
    document.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.placeholder = get(el.dataset.i18nPh); });
  }
  async function setLang(lang) {
    document.cookie = 'vyron_lang=' + lang + ';path=/;max-age=31536000';
    try { localStorage.setItem('vyron_lang', lang); } catch (e) {}
    await load(lang);
    apply();
  }
  window.VYRON_I18N = { load, apply, setLang, get };
  const initial = window.VYRON_LANG || localStorage.getItem('vyron_lang') || 'uz';
  load(initial).then(apply);
})();
