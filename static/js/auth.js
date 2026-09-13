document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const err = document.getElementById('loginErr');
    try {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ login: f.get('login'), password: f.get('password') }) });
      location.href = '/app';
    } catch (ex) { err.hidden = false; err.textContent = ex.message; }
  });
  document.getElementById('regForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const err = document.getElementById('regErr');
    if (f.get('password') !== f.get('password_confirm')) { err.hidden = false; err.textContent = 'Passwords do not match'; return; }
    try {
      await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ email: f.get('email') || null, username: f.get('username') || null, password: f.get('password'), password_confirm: f.get('password_confirm') }) });
      location.href = '/app';
    } catch (ex) { err.hidden = false; err.textContent = ex.message; }
  });
  document.getElementById('forgotForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const msg = document.getElementById('forgotMsg');
    try {
      const r = await api('/api/auth/forgot', { method: 'POST', body: JSON.stringify({ login: f.get('login') }) });
      msg.hidden = false; msg.className = 'alert ok';
      msg.textContent = r.email_sent ? 'Reset link sent — check your inbox.' : 'If the account exists, a reset link will be sent when email is configured.';
    } catch (ex) { msg.hidden = false; msg.className = 'alert err'; msg.textContent = ex.message; }
  });
  document.getElementById('resetForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const msg = document.getElementById('resetMsg');
    try {
      await api('/api/auth/reset', { method: 'POST', body: JSON.stringify({ token: f.get('token'), password: f.get('password'), password_confirm: f.get('password_confirm') }) });
      msg.hidden = false; msg.className = 'alert ok'; msg.textContent = 'Password changed — you can log in now.';
    } catch (ex) { msg.hidden = false; msg.className = 'alert err'; msg.textContent = ex.message; }
  });
  const qs = new URLSearchParams(location.search);
  const path = location.pathname;
  if (qs.get('reset') || qs.get('token') || path === '/reset-password') {
    const box = document.getElementById('resetBox');
    if (box) { box.hidden = false; box.open = true; if (qs.get('token')) box.querySelector('[name=token]').value = qs.get('token'); }
  }
  if (path === '/forgot-password') {
    const fb = document.getElementById('forgotBox');
    if (fb) fb.open = true;
  }
  document.getElementById('verifyForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const msg = document.getElementById('verifyMsg');
    try {
      await api('/api/auth/verify/confirm', { method: 'POST', body: JSON.stringify({ token: f.get('token') }) });
      msg.hidden = false; msg.className = 'alert ok'; msg.textContent = 'Email verified — you can log in now.';
    } catch (ex) { msg.hidden = false; msg.className = 'alert err'; msg.textContent = ex.message; }
  });
  if (qs.get('verify') || qs.get('token')) {
    const inp = document.querySelector('#verifyForm [name=token]');
    if (inp) inp.value = qs.get('verify') || qs.get('token');
  }
});
