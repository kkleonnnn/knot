// v0.7.43 B5.1 — normalizeDetail 纯 transform 回归网（兑现 test_frontend_2fa_contract 挂账；6 分支）
import { describe, it, expect } from 'vitest'
import { normalizeDetail } from './api.js'

describe('normalizeDetail — 6 return 分支', () => {
  it('① string → 原样 identity（守 JWT_REVOKED / must_change_password 字面比较）', () => {
    expect(normalizeDetail('JWT_REVOKED')).toBe('JWT_REVOKED')
    expect(normalizeDetail('')).toBe('')
  })

  it('② null / undefined → 空串', () => {
    expect(normalizeDetail(null)).toBe('')
    expect(normalizeDetail(undefined)).toBe('')
  })

  it('③ Array（FastAPI 422）→ 各 msg 用 ； 拼接，过滤空/null', () => {
    expect(normalizeDetail([{ msg: 'a' }, { msg: 'b' }])).toBe('a；b')
    expect(normalizeDetail([{ msg: 'a' }, null, { msg: '' }, { msg: 'c' }])).toBe('a；c')
    expect(normalizeDetail([])).toBe('')
  })

  it('④ {zh} → zh 优先（旧 {ja,zh}）', () => {
    expect(normalizeDetail({ ja: 'エラー', zh: '错误' })).toBe('错误')
  })

  it('⑤ {message} → message', () => {
    expect(normalizeDetail({ message: 'hi' })).toBe('hi')
  })

  it('⑥ 其它 object / 值 → JSON.stringify 兜底', () => {
    expect(normalizeDetail({ foo: 'bar' })).toBe('{"foo":"bar"}')
    expect(normalizeDetail(42)).toBe('42')
  })
})
