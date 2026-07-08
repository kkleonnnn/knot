// tile_data.test.js — v0.8.8 orderedCols 列序守护（对抗复核 #3：rows-first，cfg-only 幻影列不渲染）。
import { describe, it, expect } from 'vitest';
import { orderedCols } from './tile_data.js';

describe('orderedCols（v0.8.8 数据列为准）', () => {
  it('列序 = rows/SQL 键序', () => {
    expect(orderedCols([{ a: 1, b: 2, c: 3 }], {})).toEqual(['a', 'b', 'c']);
  });

  it('cfg-only 键（当前 SQL 不返）不渲染 —— 无空幻影列', () => {
    // 改 SQL 掉列后 cfg 仍留旧键 dropped → 不应出现在列里
    const cols = orderedCols([{ a: 1, b: 2 }], { a: { label: 'A' }, b: {}, dropped: { label: '旧列' } });
    expect(cols).toEqual(['a', 'b']);
    expect(cols).not.toContain('dropped');
  });

  it('cfg 键序不改列序（rows 序胜出，admin 乱序编辑不重排）', () => {
    expect(orderedCols([{ a: 1, b: 2 }], { b: { label: 'B' }, a: {} })).toEqual(['a', 'b']);
  });

  it('无数据行时回退 cfg 键（空态可见性）', () => {
    expect(orderedCols([], { x: {}, y: {} })).toEqual(['x', 'y']);
  });
});
