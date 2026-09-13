document.addEventListener('DOMContentLoaded', async () => {
  const id = document.getElementById('listingBox')?.dataset.listing;
  if (!id) return;
  try {
    const d = await api('/api/reviews/listing/' + id);
    document.getElementById('reviews').innerHTML = d.length ? d.map((r) =>
      `<div class="card soft-in">⭐ ${r.rating}<p>${escapeHtml(r.comment || '')}</p></div>`).join('')
      : '<p class="muted">No reviews yet</p>';
  } catch (e) {}
  try { await api('/api/auth/me'); document.getElementById('reviewForm').hidden = false; } catch (e) {}
  document.getElementById('reviewForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api('/api/reviews', { method: 'POST', body: JSON.stringify({ order_id: +f.get('order_id'), rating: +f.get('rating'), comment: f.get('comment') }) });
      toast('Review posted'); location.reload();
    } catch (ex) { toast(ex.message); }
  });
});
