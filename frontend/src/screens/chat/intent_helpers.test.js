// v0.7.43 B5.1 — intent_helpers 纯逻辑回归网（node 环境 vitest，显式 import 无 globals）
import { describe, it, expect } from 'vitest'
import { INTENT_TO_HINT, inferIntentFromShape, resolveEffectiveHint } from './intent_helpers.js'

describe('INTENT_TO_HINT', () => {
  it('7 类 intent → layout 映射（与后端一一对应）', () => {
    expect(INTENT_TO_HINT).toEqual({
      metric: 'metric_card',
      trend: 'line',
      compare: 'bar',
      rank: 'rank_view',
      distribution: 'pie',
      retention: 'retention_matrix',
      detail: 'detail_table',
    })
  })
})

describe('inferIntentFromShape', () => {
  it('空/无 rows → detail', () => {
    expect(inferIntentFromShape([], ['a'])).toBe('detail')
    expect(inferIntentFromShape(null, ['a'])).toBe('detail')
  })

  it('单行（不论列数）→ metric', () => {
    expect(inferIntentFromShape([{ a: 1, b: 2 }], ['a', 'b'])).toBe('metric')
  })

  it('首行含年份形态列 → trend（须 ≥2 行避开 metric 分支）', () => {
    const rows = [{ month: '2024-01', v: 1 }, { month: '2024-02', v: 2 }]
    expect(inferIntentFromShape(rows, ['month', 'v'])).toBe('trend')
  })

  it('≥4 列且无年份 → detail', () => {
    const rows = [{ a: 1, b: 2, c: 3, d: 4 }, { a: 5, b: 6, c: 7, d: 8 }]
    expect(inferIntentFromShape(rows, ['a', 'b', 'c', 'd'])).toBe('detail')
  })

  it('含 id-like 列且 ≤3 列 → detail', () => {
    const rows = [{ user_id: 1, name: 'a' }, { user_id: 2, name: 'b' }]
    expect(inferIntentFromShape(rows, ['user_id', 'name'])).toBe('detail')
  })

  it('多行普通维度+值（无年份/无 id/<4 列）→ rank 兜底', () => {
    const rows = [{ name: 'a', v: 1 }, { name: 'b', v: 2 }]
    expect(inferIntentFromShape(rows, ['name', 'v'])).toBe('rank')
  })
})

describe('resolveEffectiveHint 三级优先链', () => {
  it('① display_hint 最高优先（saved_report 快照）', () => {
    expect(resolveEffectiveHint({ display_hint: 'pie', intent: 'trend' }, [], [])).toBe('pie')
  })

  it('② intent 映射（无 display_hint）', () => {
    expect(resolveEffectiveHint({ intent: 'trend' }, [], [])).toBe('line')
  })

  it('③ 无 display_hint + 未知/无 intent → 形态推断映射', () => {
    // 未知 intent 落形态推断：单行 → metric → metric_card
    expect(resolveEffectiveHint({ intent: 'bogus' }, [{ a: 1 }], ['a'])).toBe('metric_card')
    // 无 intent + 空 rows → detail → detail_table
    expect(resolveEffectiveHint({}, [], [])).toBe('detail_table')
  })
})
