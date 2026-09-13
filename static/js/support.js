async function uploadFiles(inputId, kind) {
  const urls = [];
  const files = [...((document.getElementById(inputId)?.files) || [])].slice(0, 5);
  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/media/upload?kind=' + kind, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');
    urls.push(d.url);
  }
  return urls;
}
document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('ticketForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const btn = e.target.querySelector('button');
    btn.disabled = true;
    try {
      const attachments = await uploadFiles('ticketFiles', 'attachment');
      const d = await api('/api/support/tickets', { method: 'POST', body: JSON.stringify({ subject: f.get('subject'), category: f.get('category'), body: f.get('body'), attachments }) });
      toast('Ticket #' + d.id + ' created'); location.href = '/support/' + d.id;
    } catch (ex) { toast(ex.message); btn.disabled = false; }
  });
  const list = document.getElementById('ticketList');
  if (list) {
    try {
      const d = await api('/api/support/tickets');
      list.innerHTML = d.length ? d.map((t) => `<a class="card soft-in" href="/support/${t.id}"><b>#${t.id} ${escapeHtml(t.subject)}</b><span class="badge">${t.status}</span></a>`).join('') : '<div class="empty-state soft-in"><p>No tickets yet</p></div>';
    } catch (e) { list.innerHTML = '<p class="muted">Login to view tickets</p>'; }
  }
  if (window.TICKET_ID) {
    const box = document.getElementById('msgList');
    try {
      const d = await api('/api/support/tickets/' + window.TICKET_ID);
      box.innerHTML = d.messages.length ? d.messages.map((m) => `<div class="card ${m.is_admin ? 'soft-out' : 'soft-in'}"><b>${m.is_admin ? '🛠 Support' : '👤 You'}</b><p>${escapeHtml(m.body)}</p>${(m.attachments || []).map((a) => `<a href="${a}" target="_blank"><img src="${a}" style="max-width:140px;border-radius:10px"></a>`).join('')}</div>`).join('') : '<div class="empty-state soft-in"><p>No messages</p></div>';
    } catch (e) { box.innerHTML = '<div class="alert err">Cannot load ticket</div>'; }
    document.getElementById('replyForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      try {
        const attachments = await uploadFiles('replyFiles', 'attachment');
        await api(`/api/support/tickets/${window.TICKET_ID}/reply`, { method: 'POST', body: JSON.stringify({ body: f.get('body'), attachments }) });
        location.reload();
      } catch (ex) { toast(ex.message); }
    });
  }
});
