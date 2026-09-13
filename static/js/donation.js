document.addEventListener('DOMContentLoaded', async () => {
  const box = document.getElementById('donBox');
  if (!box) return;
  const username = box.dataset.username;
  const form = document.getElementById('donForm');
  try {
    const d = await api('/api/donations/profiles/' + username);
    document.getElementById('donFee').textContent = `Platform fee: ${d.fee_percent}% (transparent) · Currency: ${d.currency}`;
    const chips = document.getElementById('presetChips');
    chips.innerHTML = (d.presets || []).map((a) => `<button type="button" class="chip soft-out" data-amt="${a}">${Number(a).toLocaleString()} ${d.currency}</button>`).join('');
    chips.querySelectorAll('[data-amt]').forEach((b) => b.onclick = () => {
      form.amount.value = b.dataset.amt;
      chips.querySelectorAll('.chip').forEach((c) => c.classList.remove('on'));
      b.classList.add('on');
    });
    document.getElementById('donRecent').innerHTML = d.recent.map((x) =>
      `<div class="card soft-in"><b>${x.anonymous ? '🕶 Anonymous' : '💙 Supporter'}</b> — ${x.amount}<p>${escapeHtml(x.message || '')}</p><span class="muted">${x.created_at}</span></div>`).join('') || '<p class="muted">No donations yet — be the first!</p>';
    document.getElementById('donTop').innerHTML = d.top.map((x) =>
      `<div class="card soft-in"><b>${x.anonymous ? '🕶 Anonymous' : '🏆 Supporter'}</b> — ${x.amount}</div>`).join('') || '<p class="muted">—</p>';
    try {
      const pv = await api('/api/payments/providers');
      const sel = document.getElementById('donProvider');
      sel.innerHTML = pv.providers.map((p) => `<option value="${p.name}" ${p.configured ? '' : 'disabled'}>${p.name}${p.configured ? '' : ' (not configured)'}</option>`).join('');
    } catch (e) {}
  } catch (e) {}
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const res = await api(`/api/donations/profiles/${username}/donate`, { method: 'POST',
        body: JSON.stringify({ amount: +f.get('amount'), message: f.get('message') || null, anonymous: !!f.get('anonymous'), provider: f.get('provider') }) });
      const out = document.getElementById('donResult');
      if (res.error === 'payment_provider_not_configured') { out.innerHTML = '<div class="alert err">Payment provider is not configured. Your donation intent was saved as order ' + res.order_id + '.</div>'; return; }
      if (res.payment?.checkout_url) location.href = res.payment.checkout_url;
      else { out.innerHTML = '<div class="alert ok">Donation order: ' + res.order_id + '</div>'; }
    } catch (ex) { toast(ex.message); }
  });
});
