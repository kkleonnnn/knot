// formula.test.js — v0.8.5 (②a) 公式求值器 R-BI-11 单元 + 对抗测（fail-closed / 环 / 越界 / non-finite）
import { describe, it, expect } from 'vitest';
import { evaluateFormula, computeOverlay, FormulaError } from './formula.js';

// 简单 map resolver（测试自控键，非用户输入）
const R = (cells) => (col, row) => cells[col + row];

describe('evaluateFormula — 正确性', () => {
  it('算术 + 优先级 + 括号 + 一元', () => {
    expect(evaluateFormula('=1+2*3', R({}))).toBe(7);
    expect(evaluateFormula('=(1+2)*3', R({}))).toBe(9);
    expect(evaluateFormula('=-5+3', R({}))).toBe(-2);
    expect(evaluateFormula('=10/4', R({}))).toBe(2.5);
    expect(evaluateFormula('=-1.5e1', R({}))).toBe(-15);
  });
  it('单元格引用（含越界补 0）', () => {
    const r = R({ A1: 10, B1: 5 });
    expect(evaluateFormula('=A1+B1', r)).toBe(15);
    expect(evaluateFormula('=A1+Z9', r)).toBe(10);   // Z9 越界 → 0（GAP-2①）
  });
  it('聚合 SUM/AVG/COUNT/MIN/MAX', () => {
    const r = R({ A1: 1, A2: 2, A3: 3 });
    expect(evaluateFormula('=SUM(A1:A3)', r)).toBe(6);
    expect(evaluateFormula('=AVG(A1:A3)', r)).toBe(2);
    expect(evaluateFormula('=COUNT(A1:A3)', r)).toBe(3);
    expect(evaluateFormula('=MIN(A1:A3)', r)).toBe(1);
    expect(evaluateFormula('=MAX(A1:A3)', r)).toBe(3);
    expect(evaluateFormula('=SUM(A1:A3)+10', r)).toBe(16);
  });
  it('SUMIF 精确匹配（kk 截图形态）', () => {
    // B 列 = 币种，C 列 = 数值；SUMIF(B,"USDT",C)
    const r = R({ B1: 'USDT', B2: 'BTC', B3: 'USDT', C1: 100, C2: 200, C3: 92 });
    expect(evaluateFormula('=SUMIF(B1:B3,"USDT",C1:C3)', r)).toBe(192);
    expect(evaluateFormula('=SUMIF(B1:B3,"BTC",C1:C3)', r)).toBe(200);
    expect(evaluateFormula('=SUMIF(B1:B3,"ETH",C1:C3)', r)).toBe(0); // 无匹配
  });
  it('越界求和只算存在的行（补 0）', () => {
    const r = R({ A1: 1, A2: 2 });
    expect(evaluateFormula('=SUM(A1:A100)', r)).toBe(3); // A3..A100 越界 → 0
  });
});

describe('evaluateFormula — fail-closed 对抗（安全承重）', () => {
  const cases = [
    ['eval 注入', '=eval(1)'],
    ['new Function', '=Function("return 1")'],
    ['原型污染 __proto__', '=__proto__'],
    ['constructor', '=constructor(1)'],
    ['属性访问 .', '=window.alert(1)'],
    ['下标访问 [', '=A1[0]'],
    ['未知函数', '=FOO(1)'],
    ['缺右括号', '=SUM(1'],
    ['尾部多余 token', '=1 2'],
    ['裸区间', '=A1:A3'],
    ['非法字符 @', '=@SUM(1)'],
    ['空公式', '='],
    ['除零 non-finite', '=1/0'],           // GAP-2③
    ['0/0 NaN', '=0/0'],
  ];
  for (const [label, formula] of cases) {
    it(`拒：${label}`, () => {
      expect(() => evaluateFormula(formula, R({}))).toThrow(FormulaError);
    });
  }
  it('超长公式拒', () => {
    expect(() => evaluateFormula('=' + '1+'.repeat(300) + '1', R({}))).toThrow(FormulaError);
  });
  it('超大区间拒（>5000 单元）', () => {
    expect(() => evaluateFormula('=SUM(A1:A99999)', R({}))).toThrow(FormulaError);
  });
  it('列字母过长拒（>7，防列下标溢出 DoS · 对抗复核 #1）', () => {
    // 13 字母列 → colToIndex ≥ 2^53 → 旧 rangeCells `ci++` no-op → 无限 push OOM；词法层拒、秒回不 hang
    const t0 = Date.now();
    expect(() => evaluateFormula('=SUM(AAAAAAAAAAAAA1:AAAAAAAAAAAAA5)', R({}))).toThrow(FormulaError);
    expect(Date.now() - t0).toBeLessThan(200);
  });
  it('除零就地 throw、不被 MIN/聚合掩盖（对抗复核 #2）', () => {
    expect(() => evaluateFormula('=1/0', R({}))).toThrow(FormulaError);
    expect(() => evaluateFormula('=MIN(1/0,5)', R({}))).toThrow(FormulaError);   // 旧模型静默返 5
    expect(() => evaluateFormula('=SUM(1/0,5)', R({}))).toThrow(FormulaError);
  });
  it('深嵌套拒（>32）', () => {
    expect(() => evaluateFormula('=' + '('.repeat(40) + '1' + ')'.repeat(40), R({}))).toThrow(FormulaError);
  });
  it('对抗输入不污染 Object 原型', () => {
    try { evaluateFormula('=__proto__', R({})); } catch { /* expected */ }
    expect(({}).polluted).toBeUndefined();
    expect(Object.prototype.polluted).toBeUndefined();
  });
});

describe('computeOverlay — 数据 + 公式行（v0.8.9 option A：公式只引数据）', () => {
  it('公式 cell 引用数据列（SUMIF 落到 values）', () => {
    const rows = [
      { 币种: 'USDT', 余额: 100 },
      { 币种: 'BTC', 余额: 200 },
      { 币种: 'USDT', 余额: 92 },
    ];
    const cols = ['币种', '余额'];  // A=币种, B=余额
    const overlay = [
      { row: 5, col: 'A', kind: 'text', value: 'USDT部分' },
      { row: 5, col: 'B', kind: 'formula', value: '=SUMIF(A1:A3,"USDT",B1:B3)' },
    ];
    const { values, errors } = computeOverlay({ rows, cols, overlay });
    expect(errors.size).toBe(0);
    expect(values.get('B5')).toBe(192);
  });
  it('⭐ 列合计放在数据列 → 求该列全数据、不自引（option A 核心：合计格不参与 A1 寻址）', () => {
    const rows = [{ v: 100 }, { v: 200 }, { v: 92 }];   // A1..A3 = 100,200,92
    const cols = ['v'];  // A=v
    const overlay = [
      { row: 1, col: 'A', kind: 'formula', value: '=SUM(A1:A3)' },  // 合计格在 A 列第 1 行，求 A 列全 3 行
    ];
    const { values, errors } = computeOverlay({ rows, cols, overlay });
    expect(errors.size).toBe(0);           // 旧模型此处会报「循环引用：A1」；option A 无自引
    expect(values.get('A1')).toBe(392);    // 100+200+92
  });
  it('公式 A1 引用恒解析为数据（overlay 公式格不遮蔽/不互引）', () => {
    const rows = [{ x: 5, y: 7 }];    // A1=5, B1=7
    const cols = ['x', 'y'];
    const overlay = [
      { row: 1, col: 'A', kind: 'formula', value: '=B1' },   // 读数据 B1=7（非另一 overlay 格）
      { row: 1, col: 'B', kind: 'formula', value: '=A1' },   // 读数据 A1=5 → 无环
    ];
    const { values, errors } = computeOverlay({ rows, cols, overlay });
    expect(errors.size).toBe(0);
    expect(values.get('A1')).toBe(7);
    expect(values.get('B1')).toBe(5);
  });
});

describe('computeOverlay — option A 安全（公式只引数据 → 递归 DoS 结构性消失）', () => {
  it('cross-cell 形态（=A{r+1}）不再递归：读数据（越界→0）、无环无深链、瞬时', () => {
    // 旧模型此形态是深链/fan-out DoS 源；option A 下 =A2 读「数据」A2（非 overlay 格）→ 无递归。
    const N = 500;
    const overlay = [];
    for (let r = 1; r <= N; r++) overlay.push({ row: r, col: 'A', kind: 'formula', value: `=A${r + 1}` });
    const t0 = Date.now();
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay });
    expect(Date.now() - t0).toBeLessThan(500);   // 无递归 → 每格读一次数据，O(N)
    expect(errors.size).toBe(0);                 // 无环/深链错误（结构上不可能）
    expect(values.get('A1')).toBe(0);            // 数据空 → 越界补 0
  });

  it('全局步数预算兜底：大量 cell × 大 range → 部分 fail-closed、不挂死', () => {
    const cols = ['a'];
    const rows = Array.from({ length: 4000 }, () => ({ a: 1 }));
    const overlay = [];
    for (let r = 1; r <= 500; r++) overlay.push({ row: r, col: 'B', kind: 'formula', value: '=SUM(A1:A4000)' });
    const t0 = Date.now();
    const { values, errors } = computeOverlay({ rows, cols, overlay });
    expect(Date.now() - t0).toBeLessThan(3000);
    expect(errors.size).toBeGreaterThan(0);      // 500×4000=2M > 1M 预算 → 后段耗尽 fail-closed
    expect(values.size).toBeGreaterThan(0);      // 前段算出（finite）
    expect(values.size + errors.size).toBe(500); // 每 cell → 值或错，无丢
  });

  it('evaluateFormula 契约：resolver 抛非 FormulaError → 归一为 FormulaError', () => {
    const throwyResolve = () => { throw new TypeError('boom'); };
    expect(() => evaluateFormula('=A1', throwyResolve)).toThrow(FormulaError);
  });

  it('畸形 overlay 条目（col 非串 / row 非整）被跳过不崩', () => {
    const overlay = [
      { row: 1, col: 42, kind: 'formula', value: '=1' },       // col 非串
      { row: 'x', col: 'A', kind: 'formula', value: '=1' },    // row 非整
      { row: 2, col: 'A', kind: 'formula', value: '=9' },      // 合法
    ];
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay });
    expect(values.get('A2')).toBe(9);
    expect(errors.size).toBe(0);
  });

  it('非数组 overlay（坏持久化）安全降级不崩（对抗复核 #5）', () => {
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay: { bad: 1 } });
    expect(values.size).toBe(0);
    expect(errors.size).toBe(0);
  });
});
