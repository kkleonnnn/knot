// v0.7.43 B5.1 — fmt 值格式化回归网（守 v0.7.25 R1 unit=percentage 双缩放 footgun）
import { describe, it, expect } from 'vitest'
import { fmtValue, fmtPercent } from './fmt.js'

describe('fmtValue — 非-percentage byte-equal subsume 原 _fmt', () => {
  it('null / undefined → 长破折号', () => {
    expect(fmtValue(null)).toBe('—')
    expect(fmtValue(undefined)).toBe('—')
  })

  it('number（无 unit）→ toLocaleString（与原 _fmt 逐字节一致）', () => {
    expect(fmtValue(1234)).toBe((1234).toLocaleString())
    expect(fmtValue(0)).toBe((0).toLocaleString())
  })

  it('非 number → String()', () => {
    expect(fmtValue('abc')).toBe('abc')
  })
})

describe('fmtPercent + fmtValue percentage — R1 双缩放守护', () => {
  it('值 ×100 + %（0-1 小数假设）', () => {
    // footgun 守护：0.5 → 50%（非 0.5% 漏乘 / 非 5000% 双乘）
    expect(fmtPercent(0.5)).toBe('50%')
    // 派生费率 0.0486 → 4.86%（非 486% silent-wrong）
    expect(fmtPercent(0.0486)).toBe('4.86%')
  })

  it('fmtValue(unit=percentage, number) 路由到 fmtPercent', () => {
    expect(fmtValue(0.0486, 'percentage')).toBe(fmtPercent(0.0486))
  })

  it('percentage 但非 number → 不缩放，走 String/破折号分支', () => {
    expect(fmtValue(null, 'percentage')).toBe('—')
    expect(fmtValue('N/A', 'percentage')).toBe('N/A')
  })
})
