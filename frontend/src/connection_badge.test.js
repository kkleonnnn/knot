// v0.8.23 — connectedCountForBadge 纯逻辑回归网（node 环境 vitest，显式 import 无 globals）。
// 修 v0.8.21 冷启假 0：核心命门测 = 「全 error(无 checking) → 0 非 1」（守护者 §IV #1 认账的无测才漏的洞）。
import { describe, it, expect } from 'vitest'
import { connectedCountForBadge } from './connection_badge.js'

describe('connectedCountForBadge — checking-gated 6 态', () => {
  it('① 冷启全 checking → null（未探测=未知 → Chat/BI 回落 dbOk?1:0，消假 0）', () => {
    expect(connectedCountForBadge([{ status: 'checking' }, { status: 'checking' }])).toBe(null)
  })

  it('② 暖缓存全 error（无 checking）→ 0（真 0，不谎报 1 —— 修 ||null 反向假阳性的命门）', () => {
    expect(connectedCountForBadge([{ status: 'error' }, { status: 'error' }])).toBe(0)
  })

  it('③ 空列表 → 0（零注册源 = 零已连接；与旧 .filter().length byte-equal）', () => {
    expect(connectedCountForBadge([])).toBe(0)
  })

  it('④ 混合 checking+error（online=0）→ null（有未探测 → 未知，保守回落，不早断言 0）', () => {
    expect(connectedCountForBadge([{ status: 'checking' }, { status: 'error' }])).toBe(null)
  })

  it('⑤ online>0 → 真实 N（暖缓存透传；含 online 的混合命中 online 首支非 null）', () => {
    expect(connectedCountForBadge([{ status: 'online' }, { status: 'error' }, { status: 'online' }])).toBe(2)
    expect(connectedCountForBadge([{ status: 'online' }, { status: 'checking' }])).toBe(1)
  })

  it('⑥ 非数组（异常响应）→ 1（沿用原 fallback 语义）', () => {
    expect(connectedCountForBadge(null)).toBe(1)
    expect(connectedCountForBadge(undefined)).toBe(1)
    expect(connectedCountForBadge({})).toBe(1)
  })
})
