document.addEventListener('DOMContentLoaded', () => {
  const list = document.getElementById('mktList');
  const q = document.getElementById('mktQ');
  const sort = document.getElementById('mktSort');
  let timer = null;
  async function load() {
    list.innerHTML = '<div class="skeleton soft-in"></div><div class="skeleton soft-in"></div>';
    try {
      const d = await api(`/api/marketplace/listings?q=${encodeURIComponent(q.value)}&sort=${sort.value}`);
      list.innerHTML = d.length ? d.map((l) =>
        `<a class="card soft-out" href="/marketplace/${l.id}"><b>${escapeHtml(l.title)}</b><span class="price">${l.price} ${l.currency}</span></a>`
      ).join('') : '<div class="empty-state soft-in"><div class="empty-ico">🛍</div><p>Nothing here yet</p></div>';
    } catch (e) { list.innerHTML = '<div class="alert err">Failed to load</div>'; }
  }
  q?.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 350); });
  sort?.addEventListener('change', load);
  load();
});
