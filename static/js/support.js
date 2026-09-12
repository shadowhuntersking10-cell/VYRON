/* Support page: create tickets, open conversation modal, reply. */
import { get, post, qs, toast, t, escapeHtml, fmtDate, haptic } from "/static/js/core.js";

const modal = qs("#ticket-modal");
const chat = qs("#ticket-chat");
let openTicketId = null;

qs("#ticket-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.target.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await post("/api/support/tickets", {
      subject: qs("#ticket-subject").value.trim(),
      message: qs("#ticket-message").value.trim(),
      priority: qs("#ticket-priority").value,
    });
    toast(t("support.ticket_created"), "success");
    haptic("success");
    setTimeout(() => window.location.reload(), 800);
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
  }
});

function renderMessages(ticket) {
  qs("#ticket-modal-title").textContent = `${ticket.number} · ${ticket.subject}`;
  chat.innerHTML = (ticket.messages || []).map((m) => {
    const mine = m.author_role === "USER";
    return `<div class="chat-msg ${mine ? "me" : "them"} ${m.is_internal ? "internal" : ""}">
      <div class="who">${escapeHtml(m.author_name || "")} · ${escapeHtml(fmtDate(m.created_at))}</div>
      <div>${escapeHtml(m.body)}</div>
    </div>`;
  }).join("");
  chat.scrollTop = chat.scrollHeight;
}

async function openTicket(ticketId) {
  openTicketId = ticketId;
  modal.classList.add("open");
  chat.innerHTML = `<div class="loading-overlay"><span class="spinner"></span></div>`;
  try {
    const res = await get(`/api/support/tickets/${ticketId}`);
    renderMessages(res.data);
  } catch (error) {
    toast(error.message, "error");
    modal.classList.remove("open");
  }
}

modal?.addEventListener("click", (event) => {
  if (event.target === modal || event.target.dataset?.close !== undefined) modal.classList.remove("open");
});

document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href*="/support?ticket="]');
  if (link) {
    event.preventDefault();
    openTicket(new URL(link.href).searchParams.get("ticket"));
  }
});

qs("#ticket-reply-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!openTicketId) return;
  const body = qs("#ticket-reply").value.trim();
  if (!body) return;
  try {
    await post(`/api/support/tickets/${openTicketId}/messages`, { body });
    qs("#ticket-reply").value = "";
    haptic("light");
    const res = await get(`/api/support/tickets/${openTicketId}`);
    renderMessages(res.data);
  } catch (error) {
    toast(error.message, "error");
  }
});

const params = new URLSearchParams(window.location.search);
if (params.get("ticket")) openTicket(params.get("ticket"));
