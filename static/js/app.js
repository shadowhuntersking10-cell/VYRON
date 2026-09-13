/* Global: auth area, burger, search w/ debounce, toasts, favorites */
function toast(msg) {
  const box = document.getElementById('toasts');
  if (!box) return alert(msg);
  const el = document.createElement('div');
  el.className = 'toast'; el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || ('HTTP ' + r.status));
  return data;
}
document.addEventListener('DOMContentLoaded', async () => {
  // burger
  document.getElementById('burger')?.addEventListener('click', () => document.getElementById('mainNav')?.classList.toggle('open'));
  // lang selector
  const sel = document.getElementById('langSel');
  if (sel) {
    sel.value = window.VYRON_LANG || 'uz';
    sel.addEventListener('change', () => window.VYRON_I18N.setLang(sel.value).then(() => location.reload()));
  }
  // auth area
  const area = document.getElementById('authArea');
  try {
    const me = await api('/api/auth/me');
    area.innerHTML = `<a class="btn btn-sm" href="/app">👤 ${escapeHtml(me.username || me.email || 'Cabinet')}</a> <button class="iconbtn" id="logoutBtn" title="logout">⏻</button>`;
    document.getElementById('logoutBtn')?.addEventListener('click', async () => {
      await fetch('/api/auth/logout', { method: 'POST' });
      location.href = '/';
    });
  } catch (e) {
    area.innerHTML = `<a class="btn btn-sm" href="/auth/login">Login</a> <a class="btn btn-sm btn-primary" href="/auth/register">Sign up</a>`;
  }
  // global search (debounced)
  const input = document.getElementById('globalSearch');
  const results = document.getElementById('searchResults');
  let timer = null;
  input?.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = input.value.trim();
      if (q.length < 2) { results.hidden = true; return; }
      try {
        const d = await api('/api/search?q=' + encodeURIComponent(q));
        let html = '';
        d.games.forEach((g) => (html += `<a href="/games/${g.slug}">🎮 ${escapeHtml(g.title)}</a>`));
        d.products.forEach((p) => (html += `<a href="/products/${p.id}">📦 ${escapeHtml(p.name)}</a>`));
        d.listings.forEach((l) => (html += `<a href="/marketplace/${l.id}">🛍 ${escapeHtml(l.title)}</a>`));
        d.sellers.forEach((s) => (html += `<a href="/marketplace">🏪 ${escapeHtml(s.shop_name)}</a>`));
        results.innerHTML = html || '<div class="muted" style="padding:8px">Nothing found</div>';
        results.hidden = false;
      } catch (e) { results.hidden = true; }
    }, 300);
  });
  document.addEventListener('click', (e) => { if (results && !results.contains(e.target) && e.target !== input) results.hidden = true; });
  // favorite buttons
  document.getElementById('favBtn')?.addEventListener('click', async (e) => {
    const b = e.currentTarget;
    try {
      const d = await api('/api/favorites/toggle', { method: 'POST', body: JSON.stringify({ kind: b.dataset.kind, ref_id: +b.dataset.id }) });
      b.textContent = d.favorited ? '♥' : '♡';
      toast(d.favorited ? 'Added to favorites' : 'Removed');
    } catch (err) { toast('Login required'); location.href = '/auth/login'; }
  });
});
function escapeHtml(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
