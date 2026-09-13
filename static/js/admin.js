/* VYRON Admin panel: all sections driven by /api/admin/* */
document.addEventListener('DOMContentLoaded', async () => {
  const section = window.ADMIN_SECTION || 'dashboard';
  document.querySelectorAll('#adminNav a').forEach((a) => { if (a.dataset.s === section) a.classList.add('on'); });
  const content = document.getElementById('adminContent');
  const toolbar = document.getElementById('adminToolbar');

  const pill = (s) => {
    const v = String(s);
    const cls = /COMPLETE|PAID|ACTIVE|RESOLVED|success/i.test(v) ? 'green' : /FAIL|BAN|CANCEL|REFUND/i.test(v) ? 'red' : /PEND|REVIEW|OPEN|PROCESS|REQUEST/i.test(v) ? 'amber' : '';
    return `<span class="pill ${cls}">${escapeHtml(v)}</span>`;
  };
  const tbl = (heads, rows) => `<div style="overflow-x:auto"><table class="tbl"><thead><tr>${heads.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  const modal = (html) => {
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = `<div class="modal-box soft-out">${html}</div>`;
    m.addEventListener('click', (e) => { if (e.target === m) m.remove(); });
    document.body.appendChild(m);
    return m;
  };
  const confirmDlg = (msg) => new Promise((resolve) => {
    const m = modal(`<h3>Confirm</h3><p>${escapeHtml(msg)}</p><div class="row gap"><button class="btn btn-primary" id="cfY">Yes</button><button class="btn" id="cfN">No</button></div>`);
    m.querySelector('#cfY').onclick = () => { m.remove(); resolve(true); };
    m.querySelector('#cfN').onclick = () => { m.remove(); resolve(false); };
  });

  try {
    if (section === 'dashboard') {
      const d = await api('/api/admin/dashboard');
      const m = d.metrics;
      const cards = [['Total Users', m.total_users], ['Active Users', m.active_users], ['Orders', m.orders],
        ['Completed', m.completed_orders], ['Pending', m.pending_orders], ['Gross Revenue', m.gross_revenue],
        ['Platform Revenue', m.platform_revenue], ['Supplier Costs', m.supplier_costs],
        ['Seller Payouts', m.seller_payouts], ['Net Revenue', m.net_revenue]];
      document.getElementById('metrics').innerHTML = cards.map(([k, v]) => `<div class="metric soft-out"><span>${k}</span><b>${v}</b></div>`).join('');
      // tiny canvas chart
      const c = document.getElementById('revChart');
      if (c && d.timeseries?.length) {
        const ctx = c.getContext('2d');
        const vals = d.timeseries.map((t) => t.net);
        const max = Math.max(...vals, 1);
        ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 3; ctx.beginPath();
        vals.forEach((v, i) => {
          const x = (i / Math.max(vals.length - 1, 1)) * (c.width - 20) + 10;
          const y = c.height - 10 - (v / max) * (c.height - 20);
          i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.stroke();
      }
      return;
    }

    if (section === 'users') {
      toolbar.innerHTML = `<input id="uq" class="input soft-in" placeholder="Search email/username"><select id="urole" class="select soft-in"><option value="">All roles</option><option>USER</option><option>SELLER</option><option>ADMIN</option></select><button class="btn btn-sm" id="uGo">Search</button>`;
      const load = async () => {
        const d = await api(`/api/admin/users?q=${encodeURIComponent(document.getElementById('uq').value)}&role=${document.getElementById('urole').value}`);
        content.innerHTML = tbl(['ID', 'Email', 'Username', 'Role', 'State', 'Actions'],
          d.items.map((u) => `<tr><td>${u.id}</td><td>${escapeHtml(u.email || '—')}</td><td>${escapeHtml(u.username || '—')}</td><td>${pill(u.role)}</td><td>${u.is_banned ? pill('BANNED') : u.is_active ? pill('ACTIVE') : pill('INACTIVE')}</td>
          <td><button class="btn btn-sm" data-edit="${u.id}">Edit</button></td></tr>`).join(''));
        content.querySelectorAll('[data-edit]').forEach((b) => b.onclick = () => {
          const u = d.items.find((x) => x.id === +b.dataset.edit);
          const m = modal(`<h3>User #${u.id}</h3>
            <label>Role<select id="mRole" class="select soft-in"><option ${u.role === 'USER' ? 'selected' : ''}>USER</option><option ${u.role === 'SELLER' ? 'selected' : ''}>SELLER</option><option ${u.role === 'ADMIN' ? 'selected' : ''}>ADMIN</option></select></label>
            <label class="chk"><input type="checkbox" id="mBan" ${u.is_banned ? 'checked' : ''}> Banned</label>
            <input id="mReason" class="input soft-in" placeholder="Ban reason">
            <div class="row gap"><button class="btn btn-primary" id="mSave">Save</button></div>`);
          m.querySelector('#mSave').onclick = async () => {
            await api(`/api/admin/users/${u.id}`, { method: 'PATCH', body: JSON.stringify({ role: m.querySelector('#mRole').value, is_banned: m.querySelector('#mBan').checked, ban_reason: m.querySelector('#mReason').value }) });
            m.remove(); toast('Saved'); load();
          };
        });
      };
      document.getElementById('uGo').onclick = load;
      await load();
      return;
    }

    if (section === 'games') {
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="gAdd">+ Add game</button>`;
      const load = async () => {
        const d = await api('/api/admin/games');
        content.innerHTML = tbl(['ID', 'Slug', 'Title', 'Active', 'Featured', 'Actions'],
          d.map((g) => `<tr><td>${g.id}</td><td>${escapeHtml(g.slug)}</td><td>${escapeHtml(g.title)}</td><td>${pill(g.is_active ? 'ACTIVE' : 'OFF')}</td><td>${g.is_featured ? '⭐' : ''}</td>
          <td><button class="btn btn-sm" data-dis="${g.id}">Disable</button></td></tr>`).join('') || '<tr><td>No games</td></tr>');
        content.querySelectorAll('[data-dis]').forEach((b) => b.onclick = async () => {
          if (await confirmDlg('Disable this game?')) { await api('/api/admin/games/' + b.dataset.dis, { method: 'DELETE' }); load(); }
        });
      };
      document.getElementById('gAdd').onclick = () => {
        const m = modal(`<h3>New game</h3><div class="stack">
          <input id="gSlug" class="input soft-in" placeholder="slug"><input id="gTitle" class="input soft-in" placeholder="Title">
          <textarea id="gFields" class="input soft-in" placeholder='Fields JSON: [{"key":"player_id","label":{"en":"Player ID"},"required":true}]'></textarea>
          <div class="row gap"><button class="btn btn-primary" id="gSave">Create</button></div></div>`);
        m.querySelector('#gSave').onclick = async () => {
          let fields = [];
          try { fields = JSON.parse(m.querySelector('#gFields').value || '[]'); } catch (e) { toast('Bad fields JSON'); return; }
          await api('/api/admin/games', { method: 'POST', body: JSON.stringify({ slug: m.querySelector('#gSlug').value, title: m.querySelector('#gTitle').value, fields_schema: fields }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'products') {
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="pAdd">+ Add product</button>`;
      const load = async () => {
        const d = await api('/api/admin/products');
        content.innerHTML = tbl(['ID', 'Name', 'Cost (secret)', 'Price', 'Stock', 'Active', 'Actions'],
          d.map((p) => `<tr><td>${p.id}</td><td>${escapeHtml(p.name)}</td><td>${p.supplier_cost}</td><td><b>${p.selling_price} ${p.currency}</b></td><td>${p.stock}</td><td>${pill(p.is_active ? 'ACTIVE' : 'OFF')}</td>
          <td><button class="btn btn-sm" data-pe="${p.id}">Price</button></td></tr>`).join('') || '<tr><td>No products</td></tr>');
        content.querySelectorAll('[data-pe]').forEach((b) => b.onclick = async () => {
          const p = d.find((x) => x.id === +b.dataset.pe);
          let q = null;
          try { q = await api('/api/admin/pricing/' + p.id); } catch (e) {}
          const m = modal(`<h3>${escapeHtml(p.name)}</h3><div class="stack">
            ${q ? `<p class="muted">Cost ${q.supplier_cost} · Pay ${q.payment_cost} · <b>Min safe ${q.minimum_safe_price}</b> · Suggested ${q.suggested_price} · Profit ${q.estimated_profit} (${q.profit_margin_percent}%)</p>` : ''}
            <label>Supplier cost<input id="pCost" class="input soft-in" type="number" step="100" value="${p.supplier_cost}"></label>
            <label>Selling price<input id="pPrice" class="input soft-in" type="number" step="100" value="${p.selling_price}"></label>
            <label class="chk"><input type="checkbox" id="pLoss"> Loss-leader (explicit, logged)</label>
            <div class="row gap"><button class="btn btn-primary" id="pSave">Save</button></div></div>`);
          m.querySelector('#pSave').onclick = async () => {
            const body = { game_id: p.game_id, name: p.name, supplier_cost: +m.querySelector('#pCost').value, selling_price: +m.querySelector('#pPrice').value, currency: p.currency, loss_leader_allowed: m.querySelector('#pLoss').checked };
            try {
              await api(`/api/admin/products/${p.id}`, { method: 'PATCH', body: JSON.stringify(body) });
            } catch (e) {
              if (String(e.message).includes('loss') && await confirmDlg(e.message + ' Save anyway as confirmed loss-leader?')) {
                body.confirm_unsafe = true; body.loss_leader_allowed = true;
                await api(`/api/admin/products/${p.id}`, { method: 'PATCH', body: JSON.stringify(body) });
              } else { toast(e.message); return; }
            }
            m.remove(); toast('Price updated'); load();
          };
        });
      };
      document.getElementById('pAdd').onclick = async () => {
        const games = await api('/api/games');
        const m = modal(`<h3>New product</h3><div class="stack">
          <select id="pGame" class="select soft-in">${games.map((g) => `<option value="${g.id}">${escapeHtml(g.title)}</option>`).join('')}</select>
          <input id="pName" class="input soft-in" placeholder="Name"><input id="pSell" class="input soft-in" type="number" placeholder="Selling price">
          <div class="row gap"><button class="btn btn-primary" id="pCreate">Create</button></div></div>`);
        m.querySelector('#pCreate').onclick = async () => {
          await api('/api/admin/products', { method: 'POST', body: JSON.stringify({ game_id: +m.querySelector('#pGame').value, name: m.querySelector('#pName').value, selling_price: +m.querySelector('#pSell').value }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'orders') {
      toolbar.innerHTML = `<select id="oStatus" class="select soft-in"><option value="">All statuses</option>${['PENDING_PAYMENT', 'PAID', 'PROCESSING', 'SUPPLIER_PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', 'REFUND_PENDING', 'REFUNDED', 'MANUAL_REVIEW', 'SUPPLIER_NOT_CONFIGURED'].map((s) => `<option>${s}</option>`).join('')}</select><button class="btn btn-sm" id="oGo">Filter</button>`;
      const load = async () => {
        const d = await api('/api/admin/orders?status=' + document.getElementById('oStatus').value);
        content.innerHTML = tbl(['ID', 'Public ID', 'Status', 'Total', 'Actions'],
          d.items.map((o) => `<tr><td>${o.id}</td><td>${o.public_id}</td><td>${pill(o.status)}</td><td>${o.total} ${o.currency}</td>
          <td><button class="btn btn-sm" data-ov="${o.id}">View</button></td></tr>`).join(''));
        content.querySelectorAll('[data-ov]').forEach((b) => b.onclick = async () => {
          const o = await api('/api/admin/orders/' + b.dataset.ov);
          const m = modal(`<h3>${o.public_id}</h3><p>${pill(o.status)} <b>${o.total} ${o.currency}</b></p>
            <p class="muted">${escapeHtml(JSON.stringify(o.customer_fields))}</p>
            <ul class="timeline">${(o.timeline || []).map((t) => `<li class="soft-in">${escapeHtml(t.event)}</li>`).join('')}</ul>
            <div class="row gap wrap"><button class="btn btn-sm" data-st="COMPLETED">Complete</button><button class="btn btn-sm" data-st="MANUAL_REVIEW">Manual review</button><button class="btn btn-sm" data-st="FAILED">Fail</button><button class="btn btn-sm" data-st="REFUNDED">Refund</button></div>`);
          m.querySelectorAll('[data-st]').forEach((sb) => sb.onclick = async () => {
            if (sb.dataset.st === 'REFUNDED') {
              if (await confirmDlg('Refund this order? The amount will be credited to the customer wallet.')) {
                await api(`/api/admin/orders/${o.id}/refund`, { method: 'POST', body: JSON.stringify({}) });
                toast('Refunded'); m.remove(); load();
              }
              return;
            }
            if (await confirmDlg('Set status ' + sb.dataset.st + '?')) {
              await api(`/api/admin/orders/${o.id}/status`, { method: 'POST', body: JSON.stringify({ status: sb.dataset.st }) });
              m.remove(); load();
            }
          });
        });
      };
      document.getElementById('oGo').onclick = load;
      await load();
      return;
    }

    if (section === 'payments') {
      const d = await api('/api/admin/payments');
      toolbar.innerHTML = `<span class="muted">Total: ${d.total}</span>`;
      content.innerHTML = tbl(['ID', 'Order', 'Provider', 'Status', 'Amount'],
        d.items.map((p) => `<tr><td>${p.id}</td><td>${p.order_id}</td><td>${p.provider}</td><td>${pill(p.status)}</td><td>${p.amount} ${p.currency}</td></tr>`).join(''));
      return;
    }

    if (section === 'suppliers') {
      const d = await api('/api/admin/suppliers');
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="sAdd">+ Add supplier</button>`;
      content.innerHTML = `<h3>Live provider status</h3>` + tbl(['Code', 'Configured'],
        d.providers.map((p) => `<tr><td>${p.code}</td><td>${pill(p.configured ? 'CONFIGURED' : 'NOT CONFIGURED')}</td></tr>`).join('')) +
        `<h3>Database</h3>` + tbl(['ID', 'Code', 'Name', 'Status', 'Balance'],
        (d.db || []).map((s) => `<tr><td>${s.id}</td><td>${s.code}</td><td>${escapeHtml(s.name)}</td><td>${pill(s.status)}</td><td>${s.balance}</td></tr>`).join(''));
      document.getElementById('sAdd').onclick = () => {
        const m = modal(`<h3>New supplier</h3><div class="stack"><input id="sCode" class="input soft-in" placeholder="code (manual/generic/...)"><input id="sName" class="input soft-in" placeholder="Name"><button class="btn btn-primary" id="sSave">Create</button></div>`);
        m.querySelector('#sSave').onclick = async () => {
          await api('/api/admin/suppliers', { method: 'POST', body: JSON.stringify({ code: m.querySelector('#sCode').value, name: m.querySelector('#sName').value }) });
          location.reload();
        };
      };
      return;
    }

    if (section === 'marketplace') {
      const load = async () => {
        const d = await api('/api/admin/listings');
        content.innerHTML = tbl(['ID', 'Title', 'Price', 'Status', 'Promoted', 'Actions'],
          d.map((l) => `<tr><td>${l.id}</td><td>${escapeHtml(l.title)}</td><td>${l.price}</td><td>${pill(l.status)}</td><td>${l.is_promoted ? '⭐' : ''}</td>
          <td><button class="btn btn-sm" data-pr="${l.id}" data-on="${l.is_promoted ? '0' : '1'}">${l.is_promoted ? 'Unpromote' : 'Promote ⭐'}</button></td></tr>`).join('') || '<tr><td>No listings</td></tr>');
        content.querySelectorAll('[data-pr]').forEach((b) => b.onclick = async () => {
          await api(`/api/admin/listings/${b.dataset.pr}/promote?promoted=${b.dataset.on === '1'}`, { method: 'POST' });
          load();
        });
      };
      await load();
      return;
    }

    if (section === 'sellers') {
      const load = async () => {
        const d = await api('/api/admin/sellers');
        content.innerHTML = tbl(['ID', 'Shop', 'Verified', 'Active', 'Sales', 'Actions'],
          d.map((s) => `<tr><td>${s.id}</td><td>${escapeHtml(s.shop_name)}</td><td>${s.is_verified ? '✔' : ''}</td><td>${pill(s.is_active ? 'ACTIVE' : 'OFF')}</td><td>${s.sales_count}</td>
          <td><button class="btn btn-sm" data-sv="${s.id}">Verify</button> <button class="btn btn-sm" data-se="${s.id}">Edit</button></td></tr>`).join('') || '<tr><td>No sellers</td></tr>');
        content.querySelectorAll('[data-sv]').forEach((b) => b.onclick = async () => {
          await api(`/api/admin/sellers/${b.dataset.sv}/verify?verified=true`, { method: 'POST' });
          toast('Verified'); load();
        });
        content.querySelectorAll('[data-se]').forEach((b) => b.onclick = () => {
          const m = modal(`<h3>Seller #${b.dataset.se}</h3><div class="stack">
            <label>Commission % override (empty = global)<input id="sComm" class="input soft-in" type="number" step="0.1" placeholder="e.g. 7.5"></label>
            <label class="chk"><input type="checkbox" id="sPrem"> Premium seller</label>
            <button class="btn btn-primary" id="sSave">Save</button></div>`);
          m.querySelector('#sSave').onclick = async () => {
            const body = { is_premium: m.querySelector('#sPrem').checked };
            const c = m.querySelector('#sComm').value;
            if (c !== '') body.commission_percent = +c;
            await api(`/api/admin/sellers/${b.dataset.se}`, { method: 'PATCH', body: JSON.stringify(body) });
            m.remove(); toast('Saved');
          };
        });
      };
      await load();
      return;
    }

    if (section === 'donations') {
      const d = await api('/api/admin/donations');
      content.innerHTML = tbl(['ID', 'Profile', 'Amount', 'Fee', 'Status'],
        d.map((x) => `<tr><td>${x.id}</td><td>@${escapeHtml(x.profile || '?')}</td><td>${x.amount}</td><td>${x.fee}</td><td>${pill(x.status)}</td></tr>`).join('') || '<tr><td>No donations</td></tr>');
      return;
    }

    if (section === 'coupons') {
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="cAdd">+ Add coupon</button>`;
      const load = async () => {
        const d = await api('/api/admin/coupons');
        content.innerHTML = tbl(['Code', 'Kind', 'Value', 'Used', 'Active', 'Actions'],
          d.map((c) => `<tr><td><b>${c.code}</b></td><td>${c.kind}</td><td>${c.value}</td><td>${c.used_count}</td><td>${pill(c.is_active ? 'ACTIVE' : 'OFF')}</td>
          <td><button class="btn btn-sm" data-ct="${c.id}">Toggle</button></td></tr>`).join('') || '<tr><td>No coupons</td></tr>');
        content.querySelectorAll('[data-ct]').forEach((b) => b.onclick = async () => {
          await api(`/api/admin/coupons/${b.dataset.ct}/toggle`, { method: 'POST' }); load();
        });
      };
      document.getElementById('cAdd').onclick = () => {
        const m = modal(`<h3>New coupon</h3><div class="stack">
          <input id="cCode" class="input soft-in" placeholder="CODE"><select id="cKind" class="select soft-in"><option value="percent">Percent %</option><option value="fixed">Fixed</option></select>
          <input id="cVal" class="input soft-in" type="number" placeholder="Value"><button class="btn btn-primary" id="cSave">Create</button></div>`);
        m.querySelector('#cSave').onclick = async () => {
          await api('/api/admin/coupons', { method: 'POST', body: JSON.stringify({ code: m.querySelector('#cCode').value, kind: m.querySelector('#cKind').value, value: +m.querySelector('#cVal').value }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'promotions') {
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="prAdd">+ Add promotion</button>`;
      const load = async () => {
        const d = await api('/api/admin/promotions');
        content.innerHTML = tbl(['Slug', 'Title', 'Active'],
          d.map((p) => `<tr><td>${p.slug}</td><td>${escapeHtml(p.title)}</td><td>${pill(p.is_active ? 'ACTIVE' : 'OFF')}</td></tr>`).join('') || '<tr><td>No promotions</td></tr>');
      };
      document.getElementById('prAdd').onclick = () => {
        const m = modal(`<h3>New promotion</h3><div class="stack"><input id="prSlug" class="input soft-in" placeholder="slug"><input id="prTitle" class="input soft-in" placeholder="Title"><button class="btn btn-primary" id="prSave">Create</button></div>`);
        m.querySelector('#prSave').onclick = async () => {
          await api('/api/admin/promotions', { method: 'POST', body: JSON.stringify({ slug: m.querySelector('#prSlug').value, title: m.querySelector('#prTitle').value }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'payouts') {
      toolbar.innerHTML = `<select id="poS" class="select soft-in"><option value="">All</option><option>REQUESTED</option><option>PROCESSING</option><option>COMPLETED</option><option>FAILED</option><option>CANCELLED</option></select><button class="btn btn-sm" id="poGo">Filter</button>`;
      const load = async () => {
        const d = await api('/api/admin/payouts?status=' + document.getElementById('poS').value);
        content.innerHTML = tbl(['ID', 'Shop', 'Amount', 'Status', 'Actions'],
          d.map((p) => `<tr><td>${p.id}</td><td>${escapeHtml(p.shop)}</td><td>${p.amount}</td><td>${pill(p.status)}</td>
          <td><button class="btn btn-sm" data-po="${p.id}">Review</button></td></tr>`).join('') || '<tr><td>No payouts</td></tr>');
        content.querySelectorAll('[data-po]').forEach((b) => b.onclick = () => {
          const m = modal(`<h3>Payout #${b.dataset.po}</h3><div class="row gap wrap">
            ${['PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED'].map((s) => `<button class="btn btn-sm" data-ps="${s}">${s}</button>`).join('')}</div>`);
          m.querySelectorAll('[data-ps]').forEach((sb) => sb.onclick = async () => {
            if (await confirmDlg('Set payout ' + sb.dataset.ps + '?')) {
              await api(`/api/admin/payouts/${b.dataset.po}/status`, { method: 'POST', body: JSON.stringify({ status: sb.dataset.ps }) });
              m.remove(); load();
            }
          });
        });
      };
      document.getElementById('poGo').onclick = load;
      await load();
      return;
    }

    if (section === 'revenue') {
      let range = '30d';
      const render = async () => {
        const d = await api('/api/admin/revenue?range=' + range);
        const tops = await api('/api/admin/revenue/tops?range=' + range);
        toolbar.innerHTML = `<div class="row gap">${['today', '7d', '30d', 'all'].map((r) => `<button class="btn btn-sm ${r === range ? 'btn-primary' : ''}" data-range="${r}">${r === 'today' ? 'Today' : r === 'all' ? 'All time' : 'Last ' + r}</button>`).join('')}</div><span class="muted">Gross: <b>${d.total_gross}</b> · Net: <b>${d.total_net}</b></span>`;
        const topTbl = (rows, cols) => tbl(cols, rows.map((r) => `<tr><td>${escapeHtml(String(r.name ?? r.id))}</td><td>${r.gross}</td><td>${r.orders}</td></tr>`).join('') || '<tr><td>—</td></tr>');
        content.innerHTML = `<div class="stack"><h3>By stream</h3>` + tbl(['Stream', 'Gross', 'Supplier cost', 'Net', 'Count'],
          d.by_stream.map((r) => `<tr><td>${r.stream}</td><td>${r.gross}</td><td>${r.supplier_cost}</td><td><b>${r.net}</b></td><td>${r.count}</td></tr>`).join('') || '<tr><td>No revenue yet — only verified transactions appear here.</td></tr>') +
          `<h3>🏆 Top games</h3>` + topTbl(tops.top_games, ['Game', 'Gross', 'Orders']) +
          `<h3>📦 Top products</h3>` + topTbl(tops.top_products, ['Product', 'Gross', 'Orders']) +
          `<h3>🏪 Top sellers</h3>` + topTbl(tops.top_sellers, ['Seller', 'Gross', 'Orders']) + `</div>`;
        toolbar.querySelectorAll('[data-range]').forEach((b) => b.onclick = () => { range = b.dataset.range; render(); });
      };
      await render();
      return;
    }

    if (section === 'support') {
      toolbar.innerHTML = `<select id="tS" class="select soft-in"><option value="">All</option><option>OPEN</option><option>IN_PROGRESS</option><option>WAITING_USER</option><option>RESOLVED</option><option>CLOSED</option></select><button class="btn btn-sm" id="tGo">Filter</button>`;
      const load = async () => {
        const d = await api('/api/admin/support?status=' + document.getElementById('tS').value);
        content.innerHTML = tbl(['ID', 'Subject', 'Category', 'Status', 'Actions'],
          d.map((t) => `<tr><td>${t.id}</td><td>${escapeHtml(t.subject)}</td><td>${t.category}</td><td>${pill(t.status)}</td>
          <td><button class="btn btn-sm" data-tr="${t.id}">Reply</button> <button class="btn btn-sm" data-tc="${t.id}">Close</button></td></tr>`).join('') || '<tr><td>No tickets</td></tr>');
        content.querySelectorAll('[data-tr]').forEach((b) => b.onclick = () => {
          const m = modal(`<h3>Reply #${b.dataset.tr}</h3><div class="stack"><textarea id="tBody" class="input soft-in"></textarea><button class="btn btn-primary" id="tSend">Send</button></div>`);
          m.querySelector('#tSend').onclick = async () => {
            await api(`/api/admin/support/${b.dataset.tr}/reply`, { method: 'POST', body: JSON.stringify({ body: m.querySelector('#tBody').value }) });
            m.remove(); toast('Sent');
          };
        });
        content.querySelectorAll('[data-tc]').forEach((b) => b.onclick = async () => {
          await api(`/api/admin/support/${b.dataset.tc}/status?status=CLOSED`, { method: 'POST' }); load();
        });
      };
      document.getElementById('tGo').onclick = load;
      await load();
      return;
    }

    if (section === 'fraud') {
      const d = await api('/api/admin/fraud');
      content.innerHTML = `<p class="muted">${escapeHtml(d.note)}</p>` + tbl(['User ID', 'Orders (1h)'],
        d.suspicious_users_last_hour.map((u) => `<tr><td>${u.user_id}</td><td>${u.orders}</td></tr>`).join('') || '<tr><td>No suspicious activity</td></tr>');
      return;
    }

    if (section === 'notifications') {
      toolbar.innerHTML = '';
      content.innerHTML = `<div class="card soft-out stack"><h3>Broadcast</h3>
        <input id="bTitle" class="input soft-in" placeholder="Title"><textarea id="bBody" class="input soft-in" placeholder="Body"></textarea>
        <input id="bLink" class="input soft-in" placeholder="Link (optional)"><button class="btn btn-primary" id="bSend">Send to all users</button></div>`;
      document.getElementById('bSend').onclick = async () => {
        if (await confirmDlg('Broadcast to ALL users?')) {
          const d = await api('/api/admin/notifications/broadcast', { method: 'POST', body: JSON.stringify({ title: document.getElementById('bTitle').value, body: document.getElementById('bBody').value, link: document.getElementById('bLink').value || null }) });
          toast('Sent to ' + d.count);
        }
      };
      return;
    }

    if (section === 'telegram') {
      const d = await api('/api/admin/telegram');
      content.innerHTML = `<div class="grid cards">
        <div class="card soft-out"><span class="muted">Bot</span><b>${pill(d.bot_configured ? 'CONFIGURED' : 'NOT CONFIGURED')}</b></div>
        <div class="card soft-out"><span class="muted">WebApp URL</span><b>${escapeHtml(d.webapp_url || '—')}</b></div>
        <div class="card soft-out"><span class="muted">Admin IDs</span><b>${(d.admin_ids || []).join(', ') || '—'}</b></div>
        <div class="card soft-out"><span class="muted">Linked users</span><b>${d.linked_users}</b></div></div>`;
      return;
    }

    if (section === 'audit') {
      const d = await api('/api/admin/audit');
      toolbar.innerHTML = `<span class="muted">Total: ${d.total}</span>`;
      content.innerHTML = tbl(['ID', 'Actor', 'Action', 'Entity', 'ID', 'IP', 'Time'],
        d.items.map((a) => `<tr><td>${a.id}</td><td>${a.actor_id ?? '—'}</td><td>${escapeHtml(a.action)}</td><td>${a.entity || ''}</td><td>${a.entity_id || ''}</td><td>${a.ip || ''}</td><td>${a.created_at}</td></tr>`).join(''));
      return;
    }

    if (section === 'settings') {
      const d = await api('/api/admin/settings');
      content.innerHTML = tbl(['Key', 'Value', 'Actions'],
        Object.entries(d).map(([k, v]) => `<tr><td><b>${k}</b></td><td><input class="input soft-in" data-k="${k}" value="${escapeHtml(v)}"></td><td><button class="btn btn-sm" data-save="${k}">Save</button></td></tr>`).join(''));
      content.querySelectorAll('[data-save]').forEach((b) => b.onclick = async () => {
        const v = content.querySelector(`[data-k="${b.dataset.save}"]`).value;
        await api('/api/admin/settings/' + b.dataset.save, { method: 'PUT', body: JSON.stringify({ value: v }) });
        toast('Saved');
      });
      return;
    }

    if (section === 'categories') {
      toolbar.innerHTML = `<button class="btn btn-sm btn-primary" id="catAdd">+ Add category</button>`;
      const load = async () => {
        const d = await api('/api/admin/categories');
        content.innerHTML = tbl(['Slug', 'UZ', 'EN', 'RU', 'Order', 'Active'],
          d.map((c) => `<tr><td><b>${c.slug}</b></td><td>${escapeHtml(c.name_uz)}</td><td>${escapeHtml(c.name_en)}</td><td>${escapeHtml(c.name_ru)}</td><td>${c.sort_order}</td><td>${pill(c.is_active ? 'ACTIVE' : 'OFF')}</td></tr>`).join('') || '<tr><td>No categories</td></tr>');
      };
      document.getElementById('catAdd').onclick = () => {
        const m = modal(`<h3>New category</h3><div class="stack"><input id="cSlug" class="input soft-in" placeholder="slug"><input id="cUz" class="input soft-in" placeholder="Name UZ"><input id="cEn" class="input soft-in" placeholder="Name EN"><input id="cRu" class="input soft-in" placeholder="Name RU"><button class="btn btn-primary" id="cSave">Create</button></div>`);
        m.querySelector('#cSave').onclick = async () => {
          await api('/api/admin/categories', { method: 'POST', body: JSON.stringify({ slug: m.querySelector('#cSlug').value, name_uz: m.querySelector('#cUz').value, name_en: m.querySelector('#cEn').value, name_ru: m.querySelector('#cRu').value }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'pricing') {
      toolbar.innerHTML = `<span class="muted">Loss radar — every product with live cost breakdown. Red rows sell below the safe floor.</span>`;
      const d = await api('/api/admin/pricing/overview');
      content.innerHTML = tbl(['Product', 'Cost', 'Pay cost', 'Min safe', 'Suggested', 'Current', 'Profit', 'Margin', 'Actions'],
        d.map((p) => `<tr style="${p.below_safe ? 'background:rgba(220,38,38,.08)' : ''}"><td>${escapeHtml(p.name)}</td><td>${p.supplier_cost}</td><td>${p.payment_cost}</td><td><b>${p.minimum_safe_price}</b></td><td>${p.suggested_price}</td><td><b>${p.current_price}</b> ${p.below_safe ? '⚠️' : ''}</td><td>${p.estimated_profit}</td><td>${p.profit_margin_percent}%</td>
        <td><button class="btn btn-sm" data-sug="${p.id}">Apply suggested</button></td></tr>`).join('') || '<tr><td>No products</td></tr>');
      content.querySelectorAll('[data-sug]').forEach((b) => b.onclick = async () => {
        if (await confirmDlg('Set price to the suggested price?')) {
          const r = await api(`/api/admin/pricing/${b.dataset.sug}/apply-suggested`, { method: 'POST', body: JSON.stringify({}) });
          toast('New price: ' + r.price); location.reload();
        }
      });
      return;
    }

    if (section === 'variants') {
      toolbar.innerHTML = `<input id="vPid" class="input soft-in" placeholder="Product ID filter" style="max-width:160px"><button class="btn btn-sm" id="vGo">Filter</button><button class="btn btn-sm btn-primary" id="vAdd">+ Add variant</button>`;
      const load = async () => {
        const pid = document.getElementById('vPid').value;
        const d = await api('/api/admin/variants' + (pid ? '?product_id=' + pid : ''));
        content.innerHTML = tbl(['ID', 'Product', 'Name', 'Cost', 'Price', 'Stock', 'Active'],
          d.map((v) => `<tr><td>${v.id}</td><td>${v.product_id}</td><td>${escapeHtml(v.name)}</td><td>${v.supplier_cost}</td><td><b>${v.selling_price}</b></td><td>${v.stock}</td><td>${pill(v.is_active ? 'ACTIVE' : 'OFF')}</td></tr>`).join('') || '<tr><td>No variants</td></tr>');
      };
      document.getElementById('vGo').onclick = load;
      document.getElementById('vAdd').onclick = () => {
        const m = modal(`<h3>New variant</h3><div class="stack"><input id="vP" class="input soft-in" type="number" placeholder="Product ID"><input id="vN" class="input soft-in" placeholder="Name"><input id="vC" class="input soft-in" type="number" placeholder="Supplier cost"><input id="vS" class="input soft-in" type="number" placeholder="Selling price"><button class="btn btn-primary" id="vSave">Create</button></div>`);
        m.querySelector('#vSave').onclick = async () => {
          await api('/api/admin/variants', { method: 'POST', body: JSON.stringify({ product_id: +m.querySelector('#vP').value, name: m.querySelector('#vN').value, supplier_cost: +m.querySelector('#vC').value || 0, selling_price: +m.querySelector('#vS').value || 0 }) });
          m.remove(); load();
        };
      };
      await load();
      return;
    }

    if (section === 'wallets') {
      const d = await api('/api/admin/wallets');
      toolbar.innerHTML = `<span class="muted">Total: ${d.total}</span>`;
      content.innerHTML = tbl(['ID', 'User', 'Balance', 'Currency', 'Actions'],
        d.items.map((w) => `<tr><td>${w.id}</td><td>${w.user_id}</td><td><b>${w.balance}</b></td><td>${w.currency}</td><td><button class="btn btn-sm" data-wx="${w.id}">Transactions</button></td></tr>`).join('') || '<tr><td>No wallets</td></tr>');
      content.querySelectorAll('[data-wx]').forEach((b) => b.onclick = async () => {
        const tx = await api(`/api/admin/wallets/${b.dataset.wx}/transactions`);
        modal(`<h3>Wallet #${b.dataset.wx}</h3>` + tbl(['Kind', 'Amount', 'After', 'Ref'],
          tx.map((t) => `<tr><td>${t.kind}</td><td>${t.amount}</td><td>${t.balance_after}</td><td>${escapeHtml(t.reference || '')}</td></tr>`).join('') || '<tr><td>No transactions</td></tr>'));
      });
      return;
    }

    if (section === 'media') {
      toolbar.innerHTML = `<select id="medK" class="select soft-in"><option value="">All kinds</option>${['game_logo', 'product', 'avatar', 'listing', 'banner', 'attachment'].map((k) => `<option>${k}</option>`).join('')}</select><button class="btn btn-sm" id="medGo">Filter</button><input type="file" id="medFile" accept="image/*" style="max-width:200px"><select id="medKind" class="select soft-in"><option value="game_logo">game_logo</option><option value="product">product</option><option value="banner">banner</option><option value="avatar">avatar</option><option value="listing">listing</option></select><button class="btn btn-sm btn-primary" id="medUp">Upload</button>`;
      const load = async () => {
        const k = document.getElementById('medK').value;
        const d = await api('/api/admin/media' + (k ? '?kind=' + k : ''));
        content.innerHTML = `<div class="grid cards">` + d.items.map((m) =>
          `<div class="card soft-out"><img src="${m.url}" alt="${escapeHtml(m.alt_text || '')}" style="width:100%;height:120px;object-fit:contain;background:var(--surface-2);border-radius:10px"><span class="muted">${escapeHtml(m.filename)} · ${(m.size_bytes / 1024).toFixed(1)} KB</span><span class="badge">${m.media_type || m.kind}</span>${m.game_id ? `<span class="badge">game #${m.game_id}</span>` : ''}${m.product_id ? `<span class="badge">product #${m.product_id}</span>` : ''}<div class="row gap"><button class="btn btn-sm" data-mas="${m.id}">Assign</button><button class="btn btn-sm" data-mdel="${m.id}">Delete</button></div></div>`
        ).join('') + `</div>` || '<p>No media</p>';
        content.querySelectorAll('[data-mdel]').forEach((b) => b.onclick = async () => {
          if (await confirmDlg('Delete this file?')) { await api('/api/admin/media/' + b.dataset.mdel, { method: 'DELETE' }); load(); }
        });
        content.querySelectorAll('[data-mas]').forEach((b) => b.onclick = () => {
          const m = modal(`<h3>Assign media #${b.dataset.mas}</h3><div class="stack">
            <select id="aTarget" class="select soft-in"><option value="game_logo">Game logo</option><option value="game_cover">Game cover</option><option value="game_banner">Game banner</option><option value="product_image">Product image</option><option value="donation_cover">Donation cover</option></select>
            <input id="aGame" class="input soft-in" type="number" placeholder="Game ID">
            <input id="aProd" class="input soft-in" type="number" placeholder="Product ID">
            <input id="aProf" class="input soft-in" type="number" placeholder="Donation profile ID">
            <div class="row gap"><button class="btn btn-primary" id="aSave">Assign</button><button class="btn btn-sm" id="aUn">Unassign</button></div></div>`);
          m.querySelector('#aSave').onclick = async () => {
            const num = (id) => { const v = m.querySelector(id).value; return v ? +v : null; };
            await api(`/api/admin/media/${b.dataset.mas}/assign`, { method: 'POST', body: JSON.stringify({ target: m.querySelector('#aTarget').value, game_id: num('#aGame'), product_id: num('#aProd'), profile_id: num('#aProf') }) });
            m.remove(); toast('Assigned'); load();
          };
          m.querySelector('#aUn').onclick = async () => {
            await api(`/api/admin/media/${b.dataset.mas}/unassign`, { method: 'POST', body: JSON.stringify({}) });
            m.remove(); load();
          };
        });
      };
      document.getElementById('medGo').onclick = load;
      document.getElementById('medUp').onclick = async () => {
        const f = document.getElementById('medFile').files[0];
        if (!f) { toast('Choose a file'); return; }
        const fd = new FormData();
        fd.append('file', f);
        const r = await fetch('/api/media/upload?kind=' + document.getElementById('medKind').value, { method: 'POST', body: fd });
        if (!r.ok) { toast('Upload failed'); return; }
        toast('Uploaded'); load();
      };
      await load();
      return;
    }

    content.innerHTML = '<div class="alert err">Unknown section</div>';
  } catch (e) {
    content.innerHTML = `<div class="alert err">${escapeHtml(e.message)}</div>`;
  }
});
