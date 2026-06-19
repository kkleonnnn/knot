/**
 * KNOT API client (v0.6.2.0+)
 *
 * 401 拦截器：JWT 失效（含 R-PB-B1-13 JWT_REVOKED detail）→ 清 token + reload
 * 错误抛出含 .status + .detail 字段供调用方区分（如 403 totp_enroll_required）
 *
 * v0.6.2.0 加 4 TOTP endpoints（v0.6.5.2 P2-a：删过期 status 注释，前后端均无该端点）：
 *   enrollInit  → POST /api/totp/enroll-init       interim_token 或正常 JWT
 *   enrollComplete → POST /api/totp/enroll-complete + 1 个 6 位码 → recovery_codes[10]
 *   verify      → POST /api/totp/verify  interim_token 在 body（v0.6.5.2 C1）→ 完整 JWT
 *   reset       → POST /api/totp/reset (admin only) — target_user_id（v0.6.5.2 C2）
 */
// v0.6.5.2 F3：把后端 detail 规整为 string（前端直接渲染）。防 {ja,zh} 等对象塞进 React
// state → 渲染对象触发 React #31「Objects are not valid as a React child」整屏白屏。
//   string → 严格原样返回（identity，零变换 — 守 isEnrollErr / JWT_REVOKED /
//            must_change_password 等字面比较不断裂）
//   {ja,zh} → 取 zh（KNOT zh-only）；{message} → message；422 数组 → 各 msg 用 ；拼接
export function normalizeDetail(detail) {
  if (typeof detail === 'string') return detail;              // identity — 不变换
  if (detail == null) return '';
  if (Array.isArray(detail)) {                                // FastAPI 422 校验错误数组
    return detail.map(d => d && d.msg).filter(Boolean).join('；');
  }
  if (typeof detail === 'object') {
    if (typeof detail.zh === 'string') return detail.zh;      // 旧 {ja,zh} → zh 优先
    if (typeof detail.message === 'string') return detail.message;
  }
  try { return JSON.stringify(detail); } catch { return String(detail); }
}

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
      // v0.6.5.2 F5 硬伤2：清 sessionStorage enroll secret 缓存 —— admin reset / rollout bump
      // → 旧 JWT 401 → 同 tab 重进 Enroll 若命中作废 secret 则 enroll-complete 必 400。
      try {
        Object.keys(sessionStorage).filter(k => k.startsWith('cb_enroll_init_'))
          .forEach(k => sessionStorage.removeItem(k));
      } catch { /* sessionStorage 不可用降级 */ }
      window.location.reload();
      return;
    }
    if (!r.ok) {
      // v0.6.2.0：保留 detail 字段供调用方区分场景（如 403 totp_enroll_required）
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail ?? j.message ?? detail; } catch { /* not JSON */ }
      // v0.6.5.2 F3：err.detail 恒 string（防对象渲染白屏）；err.detailRaw 保原值零损失
      const detailStr = normalizeDetail(detail);
      const err = new Error(detailStr);
      err.status = r.status;
      err.detail = detailStr;
      err.detailRaw = detail;
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
    // verify 用 interim_token（login 时拿到）
    async verify(code, interimToken) {
      // v0.6.5.2 C1：interim_token 必须在 body（TotpVerifyRequest 必填字段）。
      // 旧版放 Authorization header（verify 端点无 get_current_user 不读 header）→ Pydantic
      // 报 interim_token field required → 422 → 已 enrolled 用户全员登录第二步卡死。
      const r = await fetch('/api/totp/verify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interim_token: interimToken, code }),
      });
      if (!r.ok) {
        let detail = r.statusText;
        try { const j = await r.json(); detail = j.detail ?? detail; } catch { /* */ }
        const detailStr = normalizeDetail(detail);  // v0.6.5.2 F3
        const err = new Error(detailStr);
        err.status = r.status; err.detail = detailStr; err.detailRaw = detail;
        throw err;
      }
      return r.json();
    },
    // v0.6.5.2 C2：字段名 target_user_id（TotpResetRequest）；旧版 user_id 致 422 → admin 无法救援
    reset: (userId) => api.post('/api/totp/reset', { target_user_id: userId }),
  },
};
