// v0.9.4 step 8 — 登录流程请求契约 + clearAuthSession 收敛（D11/B-5②）
//
// ⚠️ 这块此前**零覆盖**：api.test.js 只测 normalizeDetail。而登录 401 的处理方式直接决定
// 「用户看不看得见错误提示」—— 改前 api.login 走通用 req，其 401 分支会
// `clearAuthSession() + window.location.reload()` ⇒ **密码错时整页重载，统一错误提示被冲掉**。
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api, clearAuthSession, fetchAuthed, readCompanyFromUrl } from './api.js'

// jsdom **未装**，且抗诱惑清单禁本 PATCH 新增 npm 依赖 ⇒ 内联最小 Storage/window stub。
// 方法用 enumerable:false 定义，使 `Object.keys(sessionStorage)` 只列出真实 key
// （api.js 的 enroll 缓存清理正是靠 `Object.keys(sessionStorage)`，stub 若把方法名也列出来，
//  那段逻辑在测里的行为就与浏览器不一致 = 假绿/假红）。
function makeStorage() {
  const st = {}
  for (const [name, fn] of Object.entries({
    getItem: k => (Object.prototype.hasOwnProperty.call(st, k) ? st[k] : null),
    setItem: (k, v) => { st[k] = String(v) },
    removeItem: k => { delete st[k] },
    clear: () => { Object.keys(st).forEach(k => { delete st[k] }) },
  })) {
    Object.defineProperty(st, name, { value: fn, enumerable: false, writable: true })
  }
  return st
}

let reloadSpy
beforeEach(() => {
  globalThis.localStorage = makeStorage()
  globalThis.sessionStorage = makeStorage()
  reloadSpy = vi.fn()
  globalThis.window = { location: { reload: reloadSpy } }
})

function mockFetch(status, body = {}) {
  const calls = []
  globalThis.fetch = vi.fn(async (path, init) => {
    calls.push({ path, init })
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: 'x',
      json: async () => body,
    }
  })
  return calls
}

describe('api.login — 登录流程专用请求（reqPublic）', () => {
  it('⭐ 不带 Authorization（陈旧 token 不该参与登录）', async () => {
    localStorage.setItem('cb_token', 'stale-token-xyz')
    const calls = mockFetch(200, { token: 't' })
    await api.login('admin', 'pw')
    const h = calls[0].init.headers
    expect(h.Authorization).toBeUndefined()
    expect(JSON.stringify(h)).not.toContain('stale-token-xyz')
  })

  it('⭐ 401 时**抛错**而不是清会话+重载 —— 否则「账号或密码错误」被整页重载冲掉', async () => {
    localStorage.setItem('cb_token', 'keep-me')
    localStorage.setItem('cb_screen', 'chat')
    mockFetch(401, { detail: '账号或密码错误' })
    await expect(api.login('admin', 'bad')).rejects.toMatchObject({
      status: 401, detail: '账号或密码错误',
    })
    expect(reloadSpy).not.toHaveBeenCalled()
    // 登录页上的 401 不是「会话过期」⇒ 不该清掉别的状态
    expect(localStorage.getItem('cb_screen')).toBe('chat')
  })

  it('company 有则带、无则不带该字段（不发 company: undefined）', async () => {
    let calls = mockFetch(200, { token: 't' })
    await api.login('u', 'p', 'acme')
    expect(JSON.parse(calls[0].init.body)).toEqual({ username: 'u', password: 'p', company: 'acme' })

    calls = mockFetch(200, { token: 't' })
    await api.login('u', 'p')
    expect(JSON.parse(calls[0].init.body)).toEqual({ username: 'u', password: 'p' })

    calls = mockFetch(200, { token: 't' })
    await api.login('u', 'p', '')          // 空串视为未带
    expect(JSON.parse(calls[0].init.body)).toEqual({ username: 'u', password: 'p' })
  })
})

describe('api.totp.verify — 同为登录流程端点', () => {
  it('interim_token 在 body（v0.6.5.2 C1）+ 不带 Authorization + 401 抛错不重载', async () => {
    localStorage.setItem('cb_token', 'stale')
    const calls = mockFetch(200, { token: 't' })
    await api.totp.verify('123456', 'interim-abc')
    expect(JSON.parse(calls[0].init.body)).toEqual({ interim_token: 'interim-abc', code: '123456' })
    expect(calls[0].init.headers.Authorization).toBeUndefined()

    mockFetch(401, { detail: 'TOTP 验证失败' })
    await expect(api.totp.verify('000000', 'i')).rejects.toMatchObject({ status: 401 })
    expect(reloadSpy).not.toHaveBeenCalled()
  })
})

describe('api.req — 普通端点的 401 仍须清会话 + 重载（回归守护）', () => {
  it('⭐ 反向守护：别把「登录不重载」误改成「全都不重载」', async () => {
    localStorage.setItem('cb_token', 'expired')
    localStorage.setItem('cb_screen', 'chat')
    mockFetch(401, { detail: 'JWT_NO_TID' })
    await api.get('/api/conversations')
    expect(reloadSpy).toHaveBeenCalled()
    expect(localStorage.getItem('cb_token')).toBeNull()
    expect(localStorage.getItem('cb_screen')).toBeNull()
  })
})

describe('clearAuthSession — 三份分叉的 key 清单收成一份', () => {
  const ALL = ['cb_token', 'cb_user', 'cb_screen', 'cb_conv', 'cb_loading', 'cb_home_mode']

  it('默认清全部 + sessionStorage 的 enroll 缓存', () => {
    ALL.forEach(k => localStorage.setItem(k, 'v'))
    sessionStorage.setItem('cb_enroll_init_7', 'secret')
    sessionStorage.setItem('unrelated', 'keep')
    clearAuthSession()
    ALL.forEach(k => expect(localStorage.getItem(k)).toBeNull())
    // ⭐ 这条是本次收敛的真实收益：登出路径此前**不清** enroll 缓存 ⇒ 同 tab 重进 Enroll
    // 命中作废 secret → enroll-complete 必 400（v0.6.5.2 F5 那个 bug 从登出路径复发）
    expect(sessionStorage.getItem('cb_enroll_init_7')).toBeNull()
    expect(sessionStorage.getItem('unrelated')).toBe('keep')
  })

  it('keepNavigation 保留浏览位置，但仍清凭据与 enroll 缓存', () => {
    ALL.forEach(k => localStorage.setItem(k, 'v'))
    sessionStorage.setItem('cb_enroll_init_7', 'secret')
    clearAuthSession({ keepNavigation: true })
    expect(localStorage.getItem('cb_token')).toBeNull()
    expect(localStorage.getItem('cb_user')).toBeNull()
    expect(localStorage.getItem('cb_screen')).toBe('v')
    expect(localStorage.getItem('cb_conv')).toBe('v')
    expect(sessionStorage.getItem('cb_enroll_init_7')).toBeNull()
  })
})

describe('readCompanyFromUrl — 专属登录链接的公司代号', () => {
  it('取 ?c= 并 trim；缺失/空 → 空串', () => {
    expect(readCompanyFromUrl('?c=acme')).toBe('acme')
    expect(readCompanyFromUrl('?x=1&c=%20acme%20&y=2')).toBe('acme')
    expect(readCompanyFromUrl('?c=')).toBe('')
    expect(readCompanyFromUrl('')).toBe('')
    expect(readCompanyFromUrl('?other=1')).toBe('')
  })

  it('截断到 40 字符（防超长串撑破布局）', () => {
    expect(readCompanyFromUrl('?c=' + 'a'.repeat(80))).toHaveLength(40)
  })

  it('⭐ 不做存在性校验：原样返回用户输入（回显 ≠ 确认存在，否则就是公司枚举口）', () => {
    expect(readCompanyFromUrl('?c=definitely-not-a-tenant')).toBe('definitely-not-a-tenant')
  })
})

// ─── v0.9.4 MF9（守护者 Stage 4）：fetchAuthed —— 带鉴权裸 fetch 的唯一入口 ───
describe('fetchAuthed — 401 必接单一处置（MF9）', () => {
  it('⭐ 401 → clearAuthSession + reload（此前 10 处裸 fetch 一处都不做）', async () => {
    localStorage.setItem('cb_token', 'tok-abc')
    localStorage.setItem('cb_user', '{"id":1}')
    globalThis.fetch = vi.fn(async () => ({ status: 401, ok: false, text: async () => 'x' }))
    const r = await fetchAuthed('/api/messages/1/export.csv')
    expect(r.status).toBe(401)
    expect(localStorage.getItem('cb_token')).toBeNull()   // 会话已清
    expect(reloadSpy).toHaveBeenCalled()
  })

  it('非 401 不触发登出（500 只是普通失败，调用点自己提示）', async () => {
    localStorage.setItem('cb_token', 'tok-abc')
    globalThis.fetch = vi.fn(async () => ({ status: 500, ok: false, text: async () => 'boom' }))
    const r = await fetchAuthed('/api/x')
    expect(r.status).toBe(500)
    expect(localStorage.getItem('cb_token')).toBe('tok-abc')
    expect(reloadSpy).not.toHaveBeenCalled()
  })

  it('自动带上 Authorization，且**不覆盖**调用方给的其它 header', async () => {
    localStorage.setItem('cb_token', 'tok-xyz')
    const seen = []
    globalThis.fetch = vi.fn(async (url, opts) => { seen.push([url, opts]); return { status: 200, ok: true } })
    await fetchAuthed('/api/upload', { method: 'POST', headers: { 'X-Trace': 't1' }, body: 'B' })
    const [url, opts] = seen[0]
    expect(url).toBe('/api/upload')
    expect(opts.method).toBe('POST')
    expect(opts.body).toBe('B')
    expect(opts.headers.Authorization).toBe('Bearer tok-xyz')
    expect(opts.headers['X-Trace']).toBe('t1')          // 调用方 header 保留
  })
})
