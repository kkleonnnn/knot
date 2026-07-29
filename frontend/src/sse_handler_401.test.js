// v0.9.4 step 9 — SSE 的 401 打标签（handler 保持纯函数）+ 上层统一处置（D11/D8）
//
// 此前 `!resp.ok` 抛的是 `new Error(await resp.text())`（无 status）⇒ 升级后旧 token（无 tid）
// 发起的流式查询只会显示裸的 `{"detail":"JWT_NO_TID"}`，用户**不会被登出**、也不知道该重登。
// R-118 规定 sse_handler **严禁含新副作用** ⇒ 它只打标签，处置留给上层。
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { runQueryStream } from './screens/chat/sse_handler.js'

function makeStorage() {
  const st = {}
  for (const [name, fn] of Object.entries({
    getItem: k => (Object.prototype.hasOwnProperty.call(st, k) ? st[k] : null),
    setItem: (k, v) => { st[k] = String(v) },
    removeItem: k => { delete st[k] },
  })) Object.defineProperty(st, name, { value: fn, enumerable: false, writable: true })
  return st
}

let reloadSpy
beforeEach(() => {
  globalThis.localStorage = makeStorage()
  globalThis.sessionStorage = makeStorage()
  reloadSpy = vi.fn()
  globalThis.window = { location: { reload: reloadSpy } }
})

function mockResp(status, text) {
  globalThis.fetch = vi.fn(async () => ({
    ok: status >= 200 && status < 300, status, text: async () => text,
  }))
}

const noop = () => {}
const CBS = extra => ({
  onAgentEvent: noop, onClarification: noop, onError: noop, onFinal: noop,
  onException: noop, ...extra,
})

describe('runQueryStream — 非 200 的错误形状', () => {
  it('⭐ 401 → onException 收到带 status=401 + detail 的错误（可被上层识别）', async () => {
    mockResp(401, JSON.stringify({ detail: 'JWT_NO_TID' }))
    let got
    await runQueryStream('/u', {}, 'tok', CBS({ onException: e => { got = e } }))
    expect(got).toBeDefined()
    expect(got.status).toBe(401)
    expect(got.detail).toBe('JWT_NO_TID')
  })

  it('非 401（如 500）同样带 status，上层据此区分（不误登出）', async () => {
    mockResp(500, JSON.stringify({ detail: 'boom' }))
    let got
    await runQueryStream('/u', {}, 'tok', CBS({ onException: e => { got = e } }))
    expect(got.status).toBe(500)
    expect(got.detail).toBe('boom')
  })

  it('非 JSON 正文 → detail 原样（不因解析失败而丢信息）', async () => {
    mockResp(502, '<html>bad gateway</html>')
    let got
    await runQueryStream('/u', {}, 'tok', CBS({ onException: e => { got = e } }))
    expect(got.status).toBe(502)
    expect(got.detail).toBe('<html>bad gateway</html>')
  })

  it('⭐ R-118：handler 本身**不做任何处置** —— 401 时不得清会话/重载', async () => {
    localStorage.setItem('cb_token', 'keep')
    mockResp(401, JSON.stringify({ detail: 'JWT_NO_TID' }))
    await runQueryStream('/u', {}, 'tok', CBS({}))
    expect(reloadSpy).not.toHaveBeenCalled()
    expect(localStorage.getItem('cb_token')).toBe('keep')
  })
})

describe('handleUnauthorized — 上层处置的单一实现', () => {
  it('清会话 + 重载（api.req 与 SSE 上层共用同一实现）', async () => {
    const { handleUnauthorized } = await import('./api.js')
    localStorage.setItem('cb_token', 'x')
    localStorage.setItem('cb_screen', 'chat')
    handleUnauthorized()
    expect(localStorage.getItem('cb_token')).toBeNull()
    expect(localStorage.getItem('cb_screen')).toBeNull()
    expect(reloadSpy).toHaveBeenCalled()
  })
})
