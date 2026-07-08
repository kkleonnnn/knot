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
  it('深嵌套拒（>32）', () => {
    expect(() => evaluateFormula('=' + '('.repeat(40) + '1' + ')'.repeat(40), R({}))).toThrow(FormulaError);
  });
  it('对抗输入不污染 Object 原型', () => {
    try { evaluateFormula('=__proto__', R({})); } catch { /* expected */ }
    expect(({}).polluted).toBeUndefined();
    expect(Object.prototype.polluted).toBeUndefined();
  });
});

describe('computeOverlay — 数据 + 覆盖层 + 环检测', () => {
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
  it('公式 cell 互引 → 环检测 fail-closed（记 error 不崩）', () => {
    const overlay = [
      { row: 1, col: 'A', kind: 'formula', value: '=B1' },
      { row: 1, col: 'B', kind: 'formula', value: '=A1' },
    ];
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay });
    // 两个公式互引 → 至少一个记环 error；不抛穿全表
    expect(errors.size).toBeGreaterThan(0);
    expect([...errors.values()].some((m) => m.includes('循环'))).toBe(true);
    expect(values.has('A1') && values.has('B1')).toBe(false);
  });
  it('公式 cell 引用另一个（非环）公式 cell → 正常', () => {
    const rows = [{ x: 10 }];
    const cols = ['x']; // A=x
    const overlay = [
      { row: 2, col: 'A', kind: 'formula', value: '=A1*2' },   // A1=10 → 20
      { row: 3, col: 'A', kind: 'formula', value: '=A2+5' },   // A2=20 → 25
    ];
    const { values, errors } = computeOverlay({ rows, cols, overlay });
    expect(errors.size).toBe(0);
    expect(values.get('A2')).toBe(20);
    expect(values.get('A3')).toBe(25);
  });
});

describe('computeOverlay — DoS 修（红队 wmme5n9x4：记忆化 + 深链护栏）', () => {
  it('指数 fan-out（A_r=A_{r+1}+A_{r+1}）不再指数爆炸（记忆化 → 线性、快、finite）', () => {
    const N = 30;
    const overlay = [];
    for (let r = 1; r < N; r++) overlay.push({ row: r, col: 'A', kind: 'formula', value: `=A${r + 1}+A${r + 1}` });
    overlay.push({ row: N, col: 'A', kind: 'formula', value: '=1' });
    const t0 = Date.now();
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay });
    expect(Date.now() - t0).toBeLessThan(1000);   // 未记忆化会 2^29 挂死；记忆化 → 毫秒级
    expect(errors.size).toBe(0);
    expect(values.get('A1')).toBe(2 ** (N - 1));  // 值正确
  });

  it('深链（200 cell A_r=A_{r+1}）不栈溢出/不挂：深端 fail-closed，浅端算出', () => {
    const N = 200;
    const overlay = [];
    for (let r = 1; r < N; r++) overlay.push({ row: r, col: 'A', kind: 'formula', value: `=A${r + 1}` });
    overlay.push({ row: N, col: 'A', kind: 'formula', value: '=1' });
    const t0 = Date.now();
    const { values, errors } = computeOverlay({ rows: [], cols: [], overlay });
    expect(Date.now() - t0).toBeLessThan(2000);
    expect(errors.get('A1')).toContain('过深');       // 链深 > 64 → fail-closed（非栈溢出）
    expect(values.get('A200')).toBe(1);               // 浅端（链 ≤64）正常算出
  });

  it('API-max overlay（500 cell 深链，= 服务端 _MAX_OVERLAY_CELLS 上限）渲染快（红队复验 residual 修）', () => {
    // residual = 大 overlay 深链失败路径 re-walk。真正 bound = API cap ≤500（>500 → 400）+
    // 客户端全局步数预算兜底。此测证 API 可存的最大 overlay（500 cell 深链）秒级内渲染、深端 fail-closed。
    const N = 500;
    const overlay = [];
    for (let r = 1; r < N; r++) overlay.push({ row: r, col: 'A', kind: 'formula', value: `=A${r + 1}` });
    overlay.push({ row: N, col: 'A', kind: 'formula', value: '=1' });
    const t0 = Date.now();
    const { errors } = computeOverlay({ rows: [], cols: [], overlay });
    expect(Date.now() - t0).toBeLessThan(1500);   // 深度上限 + 记忆化 → 快；未修时同规模仍 O(N×64) 可控
    expect(errors.get('A1')).toBeTruthy();          // 链深 >64 → fail-closed（非挂死）
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
});
