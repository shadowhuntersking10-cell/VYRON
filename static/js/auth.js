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
    try {
      await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ email: f.get('email') || null, username: f.get('username') || null, password: f.get('password') }) });
      location.href = '/app';
    } catch (ex) { err.hidden = false; err.textContent = ex.message; }
  });
});
