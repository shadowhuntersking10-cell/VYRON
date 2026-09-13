/* Checkout: quote -> order -> payment. Backend is the price authority. */
document.addEventListener('DOMContentLoaded', async () => {
  const qs = new URLSearchParams(location.search);
  const payload = {
    product_id: qs.get('product_id') ? +qs.get('product_id') : null,
    variant_id: qs.get('variant_id') ? +qs.get('variant_id') : null,
    listing_id: qs.get('listing_id') ? +qs.get('listing_id') : null,
    quantity: 1, coupon_code: null, customer_fields: {},
  };
  const sumBody = document.getElementById('sumBody');
  const coQuote = document.getElementById('coQuote');
  const coError = document.getElementById('coError');
  const providersBox = document.getElementById('providers');
  let provider = 'payme';

  async function loadProviders() {
    try {
      const d = await api('/api/payments/providers');
      providersBox.innerHTML = '';
      d.providers.forEach((p) => {
        const b = document.createElement('button');
        b.className = 'btn btn-sm' + (p.name === provider ? ' btn-primary' : '');
        b.textContent = (p.configured ? '● ' : '○ ') + p.name;
        b.title = p.configured ? p.name : 'Payment provider not configured';
        b.onclick = () => { provider = p.name; loadProviders(); };
        providersBox.appendChild(b);
      });
    } catch (e) { providersBox.innerHTML = '<span class="muted">Failed to load providers</span>'; }
  }
  async function refreshQuote() {
    coError.hidden = true;
    try {
      const q = await api('/api/checkout/quote', { method: 'POST', body: JSON.stringify(payload) });
      sumBody.innerHTML = `<p><b>${escapeHtml(q.title)}</b></p>
        <p>Subtotal: ${q.subtotal} ${q.currency}</p>
        <p>Discount: −${q.discount}</p><p>Service fee: ${q.service_fee}</p>
        <p class="price big">Total: ${q.total} ${q.currency}</p>`;
      coQuote.innerHTML = `<p><b>${escapeHtml(q.title)}</b> × ${q.quantity}</p>`;
      // dynamic player fields (fetched from game schema when top-up product)
      if (payload.product_id) {
        try {
          const p = await api('/api/products/' + payload.product_id);
          const games = await api('/api/games');
          const g = games.find((x) => x.id === p.game_id);
          if (g && g.fields_schema?.length) {
            document.getElementById('coFields').innerHTML = '<h3>Game details</h3>' + g.fields_schema.map((f) =>
              `<label>${escapeHtml((f.label && (f.label[VYRON_LANG] || f.label.en)) || f.key)}<input class="input soft-in" data-field="${f.key}" required></label>`
            ).join('');
          }
        } catch (e) { /* ignore */ }
      }
    } catch (e) {
      coError.hidden = false; coError.textContent = e.message;
      sumBody.innerHTML = '<p class="muted">Unable to calculate total.</p>';
    }
  }
  document.getElementById('couponBtn')?.addEventListener('click', () => {
    payload.coupon_code = document.getElementById('couponIn').value.trim() || null;
    refreshQuote();
  });
  document.getElementById('payBtn')?.addEventListener('click', async () => {
    coError.hidden = true;
    document.querySelectorAll('[data-field]').forEach((i) => (payload.customer_fields[i.dataset.field] = i.value.trim()));
    const btn = document.getElementById('payBtn');
    btn.disabled = true; btn.textContent = '…';
    try {
      const res = await api('/api/checkout/orders', { method: 'POST', body: JSON.stringify({ ...payload, provider, idempotency_key: crypto.randomUUID() }) });
      if (res.error === 'payment_provider_not_configured') {
        coError.hidden = false;
        coError.textContent = 'Payment provider not configured. Order ' + res.order.public_id + ' created — pay when providers are enabled.';
        toast('Order created: ' + res.order.public_id);
        return;
      }
      if (res.payment?.checkout_url) location.href = res.payment.checkout_url;
      else location.href = '/app/orders/' + res.order.public_id;
    } catch (e) { coError.hidden = false; coError.textContent = e.message; }
    finally { btn.disabled = false; btn.textContent = '💳 Pay'; }
  });
  await loadProviders();
  await refreshQuote();
});
