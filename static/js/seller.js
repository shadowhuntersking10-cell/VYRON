document.addEventListener('DOMContentLoaded', async () => {
  const box = document.getElementById('sellerBox');
  if (box) {
    try {
      const d = await api('/api/seller/me');
      document.getElementById('becomeBox').style.display = 'none';
      box.innerHTML = `<div class="grid cards">
        <div class="card soft-out"><span class="muted">Shop</span><b>${escapeHtml(d.seller.shop_name)}</b><span>⭐ ${d.seller.rating_avg} · ${d.seller.sales_count} sales</span></div>
        <div class="card soft-out"><span class="muted">Available</span><b>${d.balance.available} ${d.balance.currency}</b></div>
        <div class="card soft-out"><span class="muted">Pending</span><b>${d.balance.pending}</b></div>
        <div class="card soft-out"><span class="muted">Lifetime</span><b>${d.balance.lifetime_earned}</b></div></div>`;
    } catch (e) { box.innerHTML = '<p class="muted">You are not a seller yet — create your shop below.</p>'; }
  }
  document.getElementById('becomeForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api('/api/marketplace/become-seller?shop_name=' + encodeURIComponent(f.get('shop_name')) + '&description=' + encodeURIComponent(f.get('description') || ''), { method: 'POST' });
      toast('Welcome, seller!'); location.reload();
    } catch (ex) { toast(ex.message); }
  });
  try {
    const cats = await api('/api/marketplace/categories');
    const sel = document.getElementById('listingCat');
    if (sel && cats.categories?.length) sel.innerHTML = cats.categories.map((c) => `<option value="${c}">${c}</option>`).join('');
  } catch (e) {}
  document.getElementById('listingFiles')?.addEventListener('change', (e) => {
    const prev = document.getElementById('listingPreview');
    prev.innerHTML = '';
    [...e.target.files].slice(0, 8).forEach((f) => {
      const img = document.createElement('img');
      img.style.cssText = 'width:64px;height:64px;object-fit:cover;border-radius:10px';
      img.src = URL.createObjectURL(f);
      prev.appendChild(img);
    });
  });
  document.getElementById('listingForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector('button');
    btn.disabled = true; btn.textContent = 'Publishing…';
    try {
      const images = [];
      const files = [...(document.getElementById('listingFiles').files || [])].slice(0, 8);
      for (const file of files) {
        const fd = new FormData();
        fd.append('file', file);
        const r = await fetch('/api/media/upload?kind=listing', { method: 'POST', body: fd });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || 'Upload failed');
        images.push(d.url);
      }
      await api('/api/marketplace/listings', { method: 'POST', body: JSON.stringify({ title: f.get('title'), description: f.get('description'), price: +f.get('price'), category: f.get('category'), stock: +f.get('stock'), delivery_type: f.get('delivery_type'), images }) });
      toast('Listing published'); e.target.reset();
      document.getElementById('listingPreview').innerHTML = '';
    } catch (ex) { toast(ex.message); }
    finally { btn.disabled = false; btn.textContent = 'Publish'; }
  });
  if (document.getElementById('payoutList')) {
    const load = async () => {
      const d = await api('/api/seller/payouts').catch(() => []);
      document.getElementById('payoutList').innerHTML = d.map((p) => `<div class="card soft-in"><b>${p.amount} ${p.currency}</b><span class="badge">${p.status}</span></div>`).join('') || '<p class="muted">No payouts</p>';
    };
    load();
    document.getElementById('payoutForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      try { await api('/api/seller/payouts', { method: 'POST', body: JSON.stringify({ amount: +f.get('amount'), method: f.get('method') }) }); toast('Payout requested'); load(); }
      catch (ex) { toast(ex.message); }
    });
  }
  if (document.getElementById('sellerOrders')) {
    try {
      const orders = await api('/api/seller/orders');
      document.getElementById('sellerOrders').innerHTML = orders.map((o) =>
        `<div class="card soft-out"><b>${escapeHtml(o.title)}</b> × ${o.quantity}<span class="badge">${o.status}</span><span>${o.total} ${escapeHtml(o.currency)}</span><span class="muted">${o.public_id} · ${o.created_at}</span></div>`
      ).join('') || '<div class="empty-state soft-in"><p>No sales yet. Buyers pay → you get notified → balance updates.</p></div>';
    } catch (e) { document.getElementById('sellerOrders').innerHTML = '<div class="alert err">Failed to load</div>'; }
  }
});
