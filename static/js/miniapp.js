/* VYRON Telegram Mini App: mobile-first, WebApp SDK, haptics, theme */
(function () {
  const tg = window.Telegram?.WebApp;
  const main = document.getElementById('mMain');
  let me = null;
  let tab = new URLSearchParams(location.search).get('tab') || 'home';

  function haptic(kind) {
    try {
      if (kind === 'ok') tg?.HapticFeedback?.notificationOccurred('success');
      else tg?.HapticFeedback?.impactOccurred('light');
    } catch (e) {}
  }
  async function api(path, opts = {}) {
    const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || d.error || r.status);
    return d;
  }
  function esc(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  async function boot() {
    try { tg?.ready(); tg?.expand(); } catch (e) {}
    // theme from Telegram
    try {
      if (tg?.colorScheme === 'light') document.documentElement.dataset.theme = 'light';
      else document.documentElement.dataset.theme = 'dark';
    } catch (e) { document.documentElement.dataset.theme = 'dark'; }
    // auth via initData
    const initData = tg?.initData || '';
    if (initData) {
      try {
        me = await api('/api/telegram/auth', { method: 'POST', body: JSON.stringify({ init_data: initData }) });
      } catch (e) { /* fall through to cookie session */ }
    }
    if (!me) {
      try { me = await api('/api/auth/me'); } catch (e) { me = null; }
    }
    const u = tg?.initDataUnsafe?.user;
    document.getElementById('mUser').textContent = me ? ('@' + (me.username || me.email || '')) : (u ? ('@' + (u.username || u.first_name)) : '');
    // admin tab injection
    if (me?.role === 'ADMIN') {
      const nav = document.querySelector('.m-nav');
      const b = document.createElement('button');
      b.dataset.tab = 'admin';
      b.innerHTML = '🛠<span>Admin</span>';
      nav.appendChild(b);
      nav.style.gridTemplateColumns = 'repeat(6,1fr)';
    }
    document.querySelectorAll('.m-nav button').forEach((b) => b.addEventListener('click', () => { haptic(); setTab(b.dataset.tab); }));
    setTab(tab);
  }

  function setTab(t) {
    tab = t;
    document.querySelectorAll('.m-nav button').forEach((b) => b.classList.toggle('on', b.dataset.tab === t));
    ({ home: renderHome, games: renderGames, market: renderMarket, orders: renderOrders, profile: renderProfile, admin: renderAdmin }[t] || renderHome)();
  }

  async function renderHome() {
    main.innerHTML = '<div class="m-skel"></div><div class="m-skel"></div>';
    try {
      const d = await api('/api/miniapp/home');
      main.innerHTML = `<div class="m-card"><h3>🎮 Featured games</h3><div class="m-grid">` +
        d.featured_games.map((g) => `<button class="m-btn sec" data-game="${g.slug}">${esc(g.title)}</button>`).join('') +
        `</div></div><div class="m-card"><h3>🔥 Popular</h3>` +
        d.popular_products.map((p) => `<div class="m-row" style="justify-content:space-between;padding:8px 0"><span>${esc(p.name)}</span><b class="m-price">${p.selling_price}</b></div>`).join('') +
        `</div>` + (d.promotions.length ? `<div class="m-card"><h3>🏷 Promotions</h3>` + d.promotions.map((p) => `<div>🏷 ${esc(p.title)}</div>`).join('') + `</div>` : '');
      main.querySelectorAll('[data-game]').forEach((b) => b.onclick = () => { haptic(); openGame(b.dataset.game); });
    } catch (e) { main.innerHTML = `<div class="m-card">Failed to load. <button class="m-btn" onclick="location.reload()">Retry</button></div>`; }
  }

  async function openGame(slug) {
    const g = await api('/api/games/' + slug);
    const products = await api('/api/products/by-game/' + g.id);
    main.innerHTML = `<div class="m-card"><button class="m-btn sec" id="bk">← Back</button><h3>🎮 ${esc(g.title)}</h3></div>` +
      products.map((p) => `<div class="m-card"><h3>${esc(p.name)}</h3><div class="m-row" style="justify-content:space-between"><b class="m-price">${p.selling_price} ${p.currency}</b><button class="m-btn" style="width:auto" data-buy="${p.id}">Buy</button></div></div>`).join('');
    document.getElementById('bk').onclick = renderGames;
    main.querySelectorAll('[data-buy]').forEach((b) => b.onclick = () => buyProduct(+b.dataset.buy, g));
  }

  async function buyProduct(productId, game) {
    haptic();
    const fields = (game.fields_schema || []).map((f) => {
      const label = (f.label && (f.label.en || f.label.uz)) || f.key;
      return `<input class="m-in" data-f="${f.key}" placeholder="${esc(label)}">`;
    }).join('');
    main.innerHTML = `<div class="m-card"><h3>Checkout</h3>${fields}
      <input class="m-in" id="cCoupon" placeholder="Coupon (optional)">
      <div id="cQuote" class="muted">Calculating…</div>
      <button class="m-btn" id="cPay">💳 Pay</button><div style="height:8px"></div>
      <button class="m-btn sec" id="cBack">Cancel</button></div>`;
    document.getElementById('cBack').onclick = () => openGame(game.slug);
    const payload = () => {
      const cf = {};
      main.querySelectorAll('[data-f]').forEach((i) => (cf[i.dataset.f] = i.value));
      return { product_id: productId, quantity: 1, coupon_code: document.getElementById('cCoupon').value || null, customer_fields: cf };
    };
    try {
      const q = await api('/api/checkout/quote', { method: 'POST', body: JSON.stringify(payload()) });
      document.getElementById('cQuote').innerHTML = `Total: <b class="m-price">${q.total} ${q.currency}</b>`;
    } catch (e) { document.getElementById('cQuote').textContent = e.message; }
    document.getElementById('cPay').onclick = async () => {
      haptic();
      try {
        const res = await api('/api/checkout/orders', { method: 'POST', body: JSON.stringify({ ...payload(), provider: 'payme', idempotency_key: crypto.randomUUID() }) });
        if (res.error === 'payment_provider_not_configured') {
          tg?.showAlert?.('Payment provider not configured. Order ' + res.order.public_id + ' created.');
          main.innerHTML = `<div class="m-card"><h3>Order ${res.order.public_id}</h3><p>Payment provider not configured — the order is saved and can be paid once providers are enabled.</p></div>`;
          return;
        }
        haptic('ok');
        if (res.payment?.checkout_url) tg?.openLink?.(res.payment.checkout_url);
        else setTab('orders');
      } catch (e) { tg?.showAlert?.(e.message); }
    };
  }

  async function renderGames() {
    main.innerHTML = '<div class="m-skel"></div>';
    const games = await api('/api/games');
    main.innerHTML = games.map((g) => `<div class="m-card"><div class="m-row" style="justify-content:space-between"><b>🎮 ${esc(g.title)}</b><button class="m-btn" style="width:auto" data-game="${g.slug}">Open</button></div></div>`).join('') || '<div class="m-card">No games yet</div>';
    main.querySelectorAll('[data-game]').forEach((b) => b.onclick = () => { haptic(); openGame(b.dataset.game); });
  }

  async function renderMarket() {
    main.innerHTML = '<div class="m-skel"></div>';
    const items = await api('/api/marketplace/listings');
    main.innerHTML = items.map((l) => `<div class="m-card"><h3>${esc(l.title)}</h3><div class="m-row" style="justify-content:space-between"><b class="m-price">${l.price} ${l.currency}</b><span class="m-badge">${esc(l.category)}</span></div></div>`).join('') || '<div class="m-card">Market is empty</div>';
  }

  async function renderOrders() {
    if (!me) { main.innerHTML = '<div class="m-card">Open via Telegram to see orders.</div>'; return; }
    main.innerHTML = '<div class="m-skel"></div>';
    const orders = await api('/api/orders');
    main.innerHTML = orders.map((o) => `<div class="m-card"><div class="m-row" style="justify-content:space-between"><b>${o.public_id}</b><span class="m-badge">${o.status}</span></div><div class="m-price">${o.total} ${o.currency}</div></div>`).join('') || '<div class="m-card">No orders yet</div>';
  }

  async function renderProfile() {
    if (!me) { main.innerHTML = '<div class="m-card">Open via Telegram to see your profile.</div>'; return; }
    main.innerHTML = `<div class="m-card"><h3>👤 ${esc(me.username || me.email || '')}</h3><div class="muted">Role: ${me.role}</div></div>
      <div class="m-card"><h3>Language</h3><div class="m-row">
      ${['uz', 'en', 'ru'].map((l) => `<button class="m-btn sec" data-lang="${l}">${l.toUpperCase()}</button>`).join('')}</div></div>
      ${me.role === 'ADMIN' ? '<button class="m-btn" id="goAdmin">🛠 Admin Panel</button>' : ''}`;
    main.querySelectorAll('[data-lang]').forEach((b) => b.onclick = async () => {
      document.cookie = 'vyron_lang=' + b.dataset.lang + ';path=/;max-age=31536000';
      try { await api('/api/user/profile', { method: 'PATCH', body: JSON.stringify({ lang: b.dataset.lang }) }); } catch (e) {}
      haptic('ok');
    });
    const ga = document.getElementById('goAdmin');
    if (ga) ga.onclick = () => setTab('admin');
  }

  async function renderAdmin() {
    if (!me || me.role !== 'ADMIN') { main.innerHTML = '<div class="m-card">⛔ Admin only</div>'; return; }
    main.innerHTML = '<div class="m-skel"></div>';
    try {
      const d = await api('/api/admin/dashboard');
      const m = d.metrics;
      main.innerHTML = `<div class="m-card"><h3>🛠 Admin</h3>
        <div>Users: <b>${m.total_users}</b></div><div>Orders: <b>${m.orders}</b> (${m.pending_orders} pending)</div>
        <div>Net revenue: <b class="m-price">${m.net_revenue}</b></div></div>
        <a class="m-btn" href="/admin">Open full panel</a>`;
    } catch (e) { main.innerHTML = `<div class="m-card">⛔ ${esc(e.message)}</div>`; }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
