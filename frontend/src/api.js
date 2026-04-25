export const api = {
  _token: () => localStorage.getItem('cb_token') || '',
  _h() { return { 'Content-Type': 'application/json', Authorization: `Bearer ${this._token()}` }; },
  async req(method, path, body) {
    const r = await fetch(path, {
      method, headers: this._h(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401) { localStorage.removeItem('cb_token'); window.location.reload(); return; }
    if (!r.ok) { const t = await r.text(); throw new Error(t || r.statusText); }
    if (r.status === 204) return {};
    return r.json();
  },
  get:   (p)    => api.req('GET',    p),
  post:  (p, b) => api.req('POST',   p, b),
  put:   (p, b) => api.req('PUT',    p, b),
  del:   (p)    => api.req('DELETE', p),
  login: (u, p) => api.req('POST', '/api/auth/login', { username: u, password: p }),
  me:    ()     => api.get('/api/auth/me'),
};
