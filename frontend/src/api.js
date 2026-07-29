/**
 * KNOT API client (v0.6.2.0+)
 *
 * 401 拦截器：JWT 失效（含 R-PB-B1-13 JWT_REVOKED detail）→ 清 token + reload
 * 错误抛出含 .status + .detail 字段供调用方区分（如 403 totp_enroll_required）
 *
 * v0.6.2.0 加 4 TOTP endpoints（v0.6.5.2 P2-a：删过期 status 注释，前后端均无该端点）：
 *   enrollInit  → POST /api/totp/enroll-init       **完整 JWT**（interim_token 自 v0.9.3.x 起被后端拒收）
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

// v0.9.4 D11：会话清理**单一实现**。此前三处各清一份不同的 key 清单：
//   api.js 401 拦截器 → cb_token/cb_user/cb_screen/cb_conv/cb_loading + sessionStorage enroll 缓存
//   App.jsx handleLogout → …+ cb_home_mode，但**不清** cb_loading、**不清** enroll 缓存
//   App.jsx me() catch  → 只清 cb_token/cb_user
// 后果不是洁癖问题：**从登出走会残留作废的 `cb_enroll_init_*`** ⇒ 同 tab 重进 Enroll 命中作废
// secret → enroll-complete 必 400（v0.6.5.2 F5 修过的那个 bug 能从登出路径复发）。
// `keepNavigation` 供「网络错/500 落 Login」场景保留浏览位置（再登录后回到原屏）——
// 用一个开关而不是第二份清单，避免分叉再长回来。
export function clearAuthSession({ keepNavigation = false } = {}) {
  localStorage.removeItem('cb_token');
  localStorage.removeItem('cb_user');
  if (!keepNavigation) {
    localStorage.removeItem('cb_screen');
    localStorage.removeItem('cb_conv');
    localStorage.removeItem('cb_loading');
    localStorage.removeItem('cb_home_mode');
  }
  // v0.6.5.2 F5 硬伤2：清 sessionStorage enroll secret 缓存 —— admin reset / rollout bump
  // → 旧 JWT 401 → 同 tab 重进 Enroll 若命中作废 secret 则 enroll-complete 必 400。
  try {
    Object.keys(sessionStorage).filter(k => k.startsWith('cb_enroll_init_'))
      .forEach(k => sessionStorage.removeItem(k));
  } catch { /* sessionStorage 不可用降级 */ }
}

// v0.9.4 D4''/kk 决策①：**专属登录链接**的公司代号 `?c=<slug>`。
// 放在 api.js 而非 Login.jsx：① 组件文件导出非组件函数会破 react-refresh（eslint 拦）；
// ② 「登录请求里带什么」本就是本模块的契约；③ 可被 vitest 直接单测。
// 只做 trim + 长度截断，**不做存在性校验** —— 界面上原样回显用户自己 URL 里的串，
// 不能变成「这个代号存在吗」的探测口（那正是 kk 决策②要堵的公司枚举）。
export function readCompanyFromUrl(search) {
  try {
    const src = search ?? (typeof window !== 'undefined' ? window.location.search : '');
    return (new URLSearchParams(src).get('c') || '').trim().slice(0, 40);
  } catch { return ''; }        // 极端环境无 URLSearchParams → 退化为不带代号
}

// v0.9.4 D11：**会话失效的唯一处置**。此前只存在于 `api.req` 的 401 分支里，而 SSE 走自己的
// fetch（`chat/sse_handler.js`）⇒ 流式查询遇 401 只会把响应正文当普通错误显示
//（升级后旧 token 会看到裸的 `{"detail":"JWT_NO_TID"}`，而不是被登出）。抽成一处供两边共用。
export function handleUnauthorized() {
  clearAuthSession();
  window.location.reload();
}

/**
 * ⭐ v0.9.4 MF9（守护者 Stage 4）：**带鉴权的裸 fetch 唯一入口**。
 *
 * `api.req` 只处理 JSON；文件上传 / blob 下载 / 导出这些场景必须用裸 fetch，于是全仓有 9 处
 * 各自手拼 `Authorization` —— 且**没有一处处置 401**。这在平时只是「导出失败」的小事，
 * 但 v0.9.4 会**把所有人的存量 token 一次性 401**（判别式是 tid 有无）⇒ 恰在那一刻，
 * 走这些路径的用户既不会被登出、也看不懂为什么失败（`api.req` 那条会登出、这些不会 = 行为分裂）。
 *
 * 故收成一处：附 token + 401 → `handleUnauthorized()`（清会话 + 重载，与 `api.req` / SSE 同一实现）。
 * **刻意不 throw**：9 个调用点里有 `.then()` 链（无 catch），throw 会变成未处理 rejection；
 * 且 `handleUnauthorized` 本身就会重载页面，后续控制流无意义 ⇒ 原样返回 response，
 * 让各调用点既有的 `!r.ok` 分支照旧工作。
 */
export async function fetchAuthed(url, opts = {}) {
  const r = await fetch(url, {
    ...opts,
    headers: { ...(opts.headers || {}), Authorization: `Bearer ${api._token()}` },
  });
  if (r.status === 401) handleUnauthorized();
  return r;
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
      // 会话失效（含 JWT_REVOKED / v0.9.4 JWT_NO_TID / TENANT_UNAVAILABLE）→ 清会话 + 整页重载。
      // ⚠️ **登录流程的端点绝不能走这里** —— 它们的 401 是「密码错/验证码错」而非「会话过期」，
      // 重载会把错误提示冲掉。故 login / totp.verify 走 reqPublic（见下）。
      handleUnauthorized();
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
  // v0.9.4 D11/B-5②：**登录流程专用**请求 —— ① 不带 Authorization（陈旧 token 不该参与登录：
  // 后端 middleware 会据它把租户 ctx 设成别家公司，虽有端点入口清 ctx 兜底，但客户端本就不该发）；
  // ② **不触发 401 拦截器** —— 登录/验证码的 401 是「凭据错」不是「会话过期」，重载会把
  // 统一错误提示（「账号或密码错误」）直接冲掉，用户什么都看不到。
  // 抛错形状与 `req` 一致（.status/.detail/.detailRaw），调用方无需分支。
  async reqPublic(method, path, body) {
    const r = await fetch(path, {
      method, headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) {
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail ?? j.message ?? detail; } catch { /* not JSON */ }
      const detailStr = normalizeDetail(detail);   // v0.6.5.2 F3：恒 string 防 React #31 白屏
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
  // v0.9.4 D4''：`company` = 公司代号（专属登录链接的 `?c=<slug>`）。未带时后端回退到唯一 active
  // 租户 —— 仅在 R-T-GATE 锁死单租户期间成立（lift 前后端会改必填，届时本处必须带上）。
  login: (u, p, company) => api.reqPublic('POST', '/api/auth/login',
    company ? { username: u, password: p, company } : { username: u, password: p }),
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
    // v0.6.5.2 C1：interim_token 必须在 **body**（TotpVerifyRequest 必填字段）。
    // 旧版放 Authorization header（verify 端点无 get_current_user 不读 header）→ Pydantic
    // 报 interim_token field required → 422 → 已 enrolled 用户全员登录第二步卡死。
    // v0.9.4 D11：原先此处自己写了一份裸 fetch + 错误规整（与 reqPublic 逐行等价）——
    // 收成一份实现（它本来就是「不带 Authorization + 不触发 401 拦截器」的先例）。
    verify: (code, interimToken) => api.reqPublic('POST', '/api/totp/verify',
      { interim_token: interimToken, code }),
    // v0.6.5.2 C2：字段名 target_user_id（TotpResetRequest）；旧版 user_id 致 422 → admin 无法救援
    reset: (userId) => api.post('/api/totp/reset', { target_user_id: userId }),
  },
};
