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
  document.getElementById('listingForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api('/api/marketplace/listings', { method: 'POST', body: JSON.stringify({ title: f.get('title'), description: f.get('description'), price: +f.get('price'), category: f.get('category') }) });
      toast('Listing published'); e.target.reset();
    } catch (ex) { toast(ex.message); }
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
    document.getElementById('sellerOrders').innerHTML = '<p class="muted">Sales appear here after your first order. Buyers pay → you get notified → balance updates.</p>';
  }
});
