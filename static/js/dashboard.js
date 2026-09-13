/* User dashboard pages */
document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('.side a').forEach((a) => { if (a.getAttribute('href') === location.pathname) a.classList.add('on'); });
  let me = null;
  try { me = await api('/api/auth/me'); } catch (e) { if (location.pathname.startsWith('/app')) location.href = '/auth/login'; return; }

  if (document.getElementById('dashCards')) {
    const [orders, notes, wallet] = await Promise.all([
      api('/api/orders').catch(() => []), api('/api/notifications').catch(() => ({ unread: 0, items: [] })), api('/api/wallet').catch(() => null),
    ]);
    document.getElementById('dashCards').innerHTML = `
      <div class="card soft-out"><span class="muted">Orders</span><b>${orders.length}</b></div>
      <div class="card soft-out"><span class="muted">Unread</span><b>${notes.unread}</b></div>
      <div class="card soft-out"><span class="muted">Wallet</span><b>${wallet ? wallet.balance + ' ' + wallet.currency : '—'}</b></div>`;
    document.getElementById('dashOrders').innerHTML = orders.slice(0, 5).map((o) =>
      `<a class="card soft-in" href="/app/orders/${o.public_id}"><b>${o.public_id}</b><span class="badge">${o.status}</span><span>${o.total} ${o.currency}</span></a>`).join('') || '<p class="muted">No orders yet</p>';
  }
  if (document.getElementById('ordersList')) {
    const orders = await api('/api/orders').catch(() => []);
    document.getElementById('ordersList').innerHTML = orders.map((o) =>
      `<a class="card soft-out" href="/app/orders/${o.public_id}"><b>${o.public_id}</b><span class="badge">${o.status}</span><span>${o.total} ${o.currency}</span></a>`).join('') || '<div class="empty-state soft-in"><p>No orders yet</p></div>';
  }
  const od = document.getElementById('orderDetail');
  if (od) {
    try {
      const o = await api('/api/orders/' + od.dataset.id);
      od.innerHTML = `<div class="card soft-out"><p>Status: <span class="badge">${o.status}</span></p>
        <p>Total: <b>${o.total} ${o.currency}</b></p>
        <h3>Timeline</h3><ul class="timeline">${(o.timeline || []).map((t) => `<li class="soft-in">${escapeHtml(t.event)} — ${escapeHtml(t.at || '')}</li>`).join('')}</ul></div>`;
    } catch (e) { od.innerHTML = '<div class="alert err">Order not found</div>'; }
  }
  if (document.getElementById('walletBal')) {
    try {
      const w = await api('/api/wallet');
      document.getElementById('walletBal').textContent = w.balance + ' ' + w.currency;
      document.getElementById('walletTx').innerHTML = w.transactions.map((t) =>
        `<div class="card soft-in"><b>${t.kind}</b> ${t.amount}<span class="muted">${t.reference || ''} · ${t.created_at}</span></div>`).join('') || '<p class="muted">No transactions</p>';
    } catch (e) {}
    try {
      const pv = await api('/api/payments/providers');
      document.getElementById('topupProvider').innerHTML = pv.providers.map((p) => `<option value="${p.name}" ${p.configured ? '' : 'disabled'}>${p.name}${p.configured ? '' : ' (not configured)'}</option>`).join('');
    } catch (e) {}
    document.getElementById('topupForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      const msg = document.getElementById('topupMsg');
      try {
        const res = await api('/api/wallet/topup', { method: 'POST', body: JSON.stringify({ amount: +f.get('amount'), provider: f.get('provider') }) });
        if (res.error === 'payment_provider_not_configured') { msg.innerHTML = '<div class="alert err">Payment provider is not configured.</div>'; return; }
        if (res.payment?.checkout_url) location.href = res.payment.checkout_url;
        else { msg.innerHTML = '<div class="alert ok">Top-up initiated.</div>'; }
      } catch (ex) { msg.innerHTML = `<div class="alert err">${escapeHtml(ex.message)}</div>`; }
    });
  }
  if (document.getElementById('noteList')) {
    const n = await api('/api/notifications').catch(() => ({ items: [] }));
    const render = (items) => (document.getElementById('noteList').innerHTML = items.map((x) =>
      `<div class="card ${x.is_read ? 'soft-in' : 'soft-out'}"><b>${escapeHtml(x.title)}</b><p>${escapeHtml(x.body || '')}</p>
       ${x.is_read ? '' : `<button class="btn btn-sm" data-read="${x.id}">Mark read</button>`}</div>`).join('') || '<p class="muted">No notifications</p>');
    render(n.items);
    document.getElementById('noteList').addEventListener('click', async (e) => {
      const b = e.target.closest('[data-read]');
      if (b) { await api(`/api/notifications/${b.dataset.read}/read`, { method: 'POST' }); location.reload(); }
    });
    document.getElementById('readAll')?.addEventListener('click', async () => { await api('/api/notifications/read-all', { method: 'POST' }); location.reload(); });
  }
  if (document.getElementById('favList')) {
    const f = await api('/api/favorites').catch(() => []);
    document.getElementById('favList').innerHTML = f.map((x) => `<div class="card soft-out"><b>${x.kind} #${x.ref_id}</b></div>`).join('') || '<p class="muted">No favorites yet</p>';
  }
  document.getElementById('profileForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try { await api('/api/user/profile', { method: 'PATCH', body: JSON.stringify({ full_name: f.get('full_name') || null, username: f.get('username') || null }) }); toast('Saved'); }
    catch (ex) { toast(ex.message); }
  });
  document.getElementById('pwForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try { await api('/api/user/password', { method: 'POST', body: JSON.stringify({ old_password: f.get('old_password'), new_password: f.get('new_password') }) }); toast('Password changed'); }
    catch (ex) { toast(ex.message); }
  });
  const setSave = document.getElementById('setSave');
  if (setSave) {
    document.getElementById('setLang').value = me.lang || 'uz';
    document.getElementById('setTheme').value = window.VYRON_THEME.current();
    setSave.addEventListener('click', async () => {
      const lang = document.getElementById('setLang').value;
      window.VYRON_THEME.apply(document.getElementById('setTheme').value);
      try { await api('/api/user/profile', { method: 'PATCH', body: JSON.stringify({ lang }) }); } catch (e) {}
      await window.VYRON_I18N.setLang(lang);
      toast('Saved');
    });
  }
});
