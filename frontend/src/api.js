/**
 * KNOT API client (v0.6.2.0+)
 *
 * 401 拦截器：JWT 失效（含 R-PB-B1-13 JWT_REVOKED detail）→ 清 token + reload
 * 错误抛出含 .status + .detail 字段供调用方区分（如 403 totp_enroll_required）
 *
 * v0.6.2.0 加 5 TOTP endpoints：
 *   enrollInit  → POST /api/totp/enroll-init       interim_token 或正常 JWT
 *   enrollComplete → POST /api/totp/enroll-complete + 1 个 6 位码 → recovery_codes[10]
 *   verify      → POST /api/totp/verify  interim_token auth → 完整 JWT
 *   reset       → POST /api/totp/reset (admin only) — bump_token_version 触发旧 JWT 失效
 *   status      → GET  /api/totp/status — enroll 状态查询
 */
export const api = {
  _token: () => localStorage.getItem('cb_token') || '',
  _h() { return { 'Content-Type': 'application/json', Authorization: `Bearer ${this._token()}` }; },
  _hWith(token) { return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }; },
  async req(method, path, body) {
    const r = await fetch(path, {
      method, headers: this._h(),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (r.status === 401) {
      localStorage.removeItem('cb_token');
      localStorage.removeItem('cb_user');
      localStorage.removeItem('cb_screen');
      localStorage.removeItem('cb_conv');
      localStorage.removeItem('cb_loading');
      window.location.reload();
      return;
    }
    if (!r.ok) {
      // v0.6.2.0：保留 detail 字段供调用方区分场景（如 403 totp_enroll_required）
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail || j.message || detail; } catch { /* not JSON */ }
      const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      err.status = r.status;
      err.detail = detail;
      throw err;
    }
    if (r.status === 204) return {};
    return r.json();
  },
  get:   (p)    => api.req('GET',    p),
  post:  (p, b) => api.req('POST',   p, b),
  put:   (p, b) => api.req('PUT',    p, b),
  del:   (p)    => api.req('DELETE', p),
  login: (u, p) => api.req('POST', '/api/auth/login', { username: u, password: p }),
  me:    ()     => api.get('/api/auth/me'),
  // v0.6.0.20 admin 默认账号强制改密
  changePassword: (oldPw, newPw) => api.req('POST', '/api/auth/change-password',
    { old_password: oldPw, new_password: newPw }),
  // v0.6.2.0 TOTP 2FA — 5 endpoints
  totp: {
    enrollInit: () => api.post('/api/totp/enroll-init'),
    // secret 由 enrollInit 返回，前端原样回传（KNOT 不持久化中间态 — 防 secret 提前暴露）
    enrollComplete: (secret, code) => api.post('/api/totp/enroll-complete', { secret, code }),
    // verify 用 interim_token（login 时拿到）— 显式传入 token，不走 _token()
    async verify(code, interimToken) {
      const r = await fetch('/api/totp/verify', {
        method: 'POST', headers: api._hWith(interimToken),
        body: JSON.stringify({ code }),
      });
      if (!r.ok) {
        let detail = r.statusText;
        try { const j = await r.json(); detail = j.detail || detail; } catch { /* */ }
        const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        err.status = r.status; err.detail = detail;
        throw err;
      }
      return r.json();
    },
    reset: (userId) => api.post('/api/totp/reset', { user_id: userId }),
  },
};
