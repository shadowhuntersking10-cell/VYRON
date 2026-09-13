document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('ticketForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const d = await api('/api/support/tickets', { method: 'POST', body: JSON.stringify({ subject: f.get('subject'), category: f.get('category'), body: f.get('body') }) });
      toast('Ticket #' + d.id + ' created'); location.href = '/support/' + d.id;
    } catch (ex) { toast(ex.message); }
  });
  const list = document.getElementById('ticketList');
  if (list) {
    try {
      const d = await api('/api/support/tickets');
      list.innerHTML = d.length ? d.map((t) => `<a class="card soft-in" href="/support/${t.id}"><b>#${t.id} ${escapeHtml(t.subject)}</b><span class="badge">${t.status}</span></a>`).join('') : '<p class="muted">No tickets yet</p>';
    } catch (e) { list.innerHTML = '<p class="muted">Login to view tickets</p>'; }
  }
  if (window.TICKET_ID) {
    const box = document.getElementById('msgList');
    try {
      const d = await api('/api/support/tickets/' + window.TICKET_ID);
      box.innerHTML = d.messages.map((m) => `<div class="card ${m.is_admin ? 'soft-out' : 'soft-in'}"><b>${m.is_admin ? '🛠 Support' : '👤 You'}</b><p>${escapeHtml(m.body)}</p></div>`).join('');
    } catch (e) { box.innerHTML = '<div class="alert err">Cannot load ticket</div>'; }
    document.getElementById('replyForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      try { await api(`/api/support/tickets/${window.TICKET_ID}/reply`, { method: 'POST', body: JSON.stringify({ body: f.get('body') }) }); location.reload(); }
      catch (ex) { toast(ex.message); }
    });
  }
});
