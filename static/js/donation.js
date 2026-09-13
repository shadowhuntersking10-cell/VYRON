document.addEventListener('DOMContentLoaded', async () => {
  const box = document.getElementById('donBox');
  if (!box) return;
  const username = box.dataset.username;
  try {
    const d = await api('/api/donations/profiles/' + username);
    document.getElementById('donFee').textContent = `Platform fee: ${d.fee_percent}% (transparent)`;
    document.getElementById('donRecent').innerHTML = d.recent.map((x) =>
      `<div class="card soft-in"><b>${x.anonymous ? '🕶 Anonymous' : '💙 Supporter'}</b> — ${x.amount}<p>${escapeHtml(x.message || '')}</p></div>`).join('') || '<p class="muted">No donations yet</p>';
    document.getElementById('donTop').innerHTML = d.top.map((x) =>
      `<div class="card soft-in"><b>${x.anonymous ? '🕶 Anonymous' : '🏆 Supporter'}</b> — ${x.amount}</div>`).join('') || '<p class="muted">—</p>';
  } catch (e) {}
  document.getElementById('donForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const res = await api(`/api/donations/profiles/${username}/donate`, { method: 'POST',
        body: JSON.stringify({ amount: +f.get('amount'), message: f.get('message') || null, anonymous: !!f.get('anonymous') }) });
      if (res.error === 'payment_provider_not_configured') { toast('Payment provider not configured'); return; }
      if (res.payment?.checkout_url) location.href = res.payment.checkout_url;
      else toast('Donation order: ' + res.order_id);
    } catch (ex) { toast(ex.message); }
  });
});
