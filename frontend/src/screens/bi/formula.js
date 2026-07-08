// formula.js — v0.8.5 (②a) 客户端电子表格公式求值器（R-BI-11 · 新安全承重面）
//
// admin 在宽表覆盖单元格写 Excel 式公式（=SUMIF(B4:B28,"USDT",O4:O28) 类）→ 本模块在
// **已 fetch、已脱敏**的结果 grid 上**客户端**求值。镜像后端 fragment_guard.py 纪律：
// 手写 tokenizer → 递归下降 parser → 白名单 evaluator，**fail-closed**。
//
// 安全红线（R-BI-11）：
//  1. 零 eval / new Function / Function() / with —— 全靠手写文法（无版本漂移攻击面）。
//  2. fail-closed：任何未知 token/函数/解析失败 → throw FormulaError（调用方显错，不静默）。
//  3. 白名单函数：SUM/AVG/COUNT/MIN/MAX/SUMIF + 算术(+−*/) + A1 单元格/区间引用。
//  4. 无动态属性逃逸：函数名只与白名单 Set 比较 + Map 分派（非 obj[name]）；A1 按列下标 /
//     数组索引解析（非 obj[userStr]）；标识符文法仅 [A-Za-z]，`__proto__`/`constructor` 含
//     `_` 或不接 `(` → 词法/语法层即 fail-closed，永不触达属性访问。
//  5. DoS 护栏：公式长度 ≤500 / token ≤200 / range ≤5000 单元 / 递归深度 ≤32。
//  6. 环检测（GAP-1）：overlay 公式 cell 互引（A=B / B=A）→ 求值 visited-set 命中 → throw。
//  7. A1 语义（GAP-2 · kk 拍板）：越界引用 → 补 0（Excel 手感）；non-finite（NaN/±Inf，如除零）
//     → throw（cell 显错误标记，不静默补 0）。

const MAX_FORMULA_LEN = 500;
const MAX_TOKENS = 200;
const MAX_RANGE = 5000;
const MAX_DEPTH = 32;
const MAX_OVERLAY_DEPTH = 64;    // 跨 cell 引用链深度上限（防深链栈溢出；与 parser MAX_DEPTH 正交）
const MAX_TOTAL_STEPS = 1000000; // computeOverlay 全局求值步数预算（红队复验 residual 修）：
// 记忆化只 bound 成功路径；深链 fail-closed 路径不入 memo → O(N×64) re-walk 大 overlay 挂死。
// 全局步数预算 bound 所有 resolve 调用总功（含 range/失败 re-walk）→ 结构无关的硬上限、fail-closed。

// 白名单函数（Set 成员判定 + 下方 switch 分派 —— 绝不 obj[name] 动态属性访问）
const WHITELIST_FUNCS = new Set(['SUM', 'AVG', 'COUNT', 'MIN', 'MAX', 'SUMIF']);

export class FormulaError extends Error {
  constructor(msg) { super(msg); this.name = 'FormulaError'; }
}

// ── 列字母 ↔ 下标（A→0, B→1, …, Z→25, AA→26）───────────────────────────────────
function colToIndex(letters) {
  let n = 0;
  for (let i = 0; i < letters.length; i++) {
    n = n * 26 + (letters.charCodeAt(i) - 64); // 'A'=65
  }
  return n - 1;
}

// ── tokenizer（fail-closed：非白名单字符即 throw）─────────────────────────────────
function tokenize(src) {
  if (typeof src !== 'string') throw new FormulaError('公式必须是字符串');
  let s = src.trim();
  if (s.startsWith('=')) s = s.slice(1);
  if (s.length === 0) throw new FormulaError('空公式');
  if (s.length > MAX_FORMULA_LEN) throw new FormulaError('公式过长（>500 字符）');

  const toks = [];
  let i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === ' ' || c === '\t') { i++; continue; }
    // 数字（含小数 / 科学计数）
    if ((c >= '0' && c <= '9') || (c === '.' && s[i + 1] >= '0' && s[i + 1] <= '9')) {
      let j = i;
      while (j < s.length && ((s[j] >= '0' && s[j] <= '9') || s[j] === '.')) j++;
      if (s[j] === 'e' || s[j] === 'E') {
        j++;
        if (s[j] === '+' || s[j] === '-') j++;
        while (j < s.length && s[j] >= '0' && s[j] <= '9') j++;
      }
      const num = Number(s.slice(i, j));
      if (!Number.isFinite(num)) throw new FormulaError('无效数字字面');
      toks.push({ t: 'num', v: num });
      i = j; continue;
    }
    // 字符串字面（SUMIF criteria）
    if (c === '"') {
      let j = i + 1;
      while (j < s.length && s[j] !== '"') j++;
      if (j >= s.length) throw new FormulaError('未闭合字符串');
      toks.push({ t: 'str', v: s.slice(i + 1, j) });
      i = j + 1; continue;
    }
    // 标识符：字母串。接数字 → A1 单元格引用；否则 → 函数名
    if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')) {
      let j = i;
      while (j < s.length && ((s[j] >= 'A' && s[j] <= 'Z') || (s[j] >= 'a' && s[j] <= 'z'))) j++;
      const letters = s.slice(i, j).toUpperCase();
      if (s[j] >= '0' && s[j] <= '9') {
        let k = j;
        while (k < s.length && s[k] >= '0' && s[k] <= '9') k++;
        const row = parseInt(s.slice(j, k), 10);
        if (!(row >= 1)) throw new FormulaError('行号非法');
        toks.push({ t: 'cell', col: letters, row });
        i = k; continue;
      }
      toks.push({ t: 'func', name: letters });   // 白名单校验推迟到 parse
      i = j; continue;
    }
    if (c === '(') { toks.push({ t: 'lp' }); i++; continue; }
    if (c === ')') { toks.push({ t: 'rp' }); i++; continue; }
    if (c === ',') { toks.push({ t: 'comma' }); i++; continue; }
    if (c === ':') { toks.push({ t: 'colon' }); i++; continue; }
    if (c === '+' || c === '-' || c === '*' || c === '/') { toks.push({ t: 'op', v: c }); i++; continue; }
    throw new FormulaError('非法字符：' + c);   // fail-closed（`_` / `@` / `[` 等一律拒 → __proto__ 挡在词法层）
  }
  if (toks.length > MAX_TOKENS) throw new FormulaError('token 过多');
  return toks;
}

// ── 递归下降 parser → AST ────────────────────────────────────────────────────────
function parse(toks) {
  let pos = 0;
  const peek = () => toks[pos];
  const next = () => toks[pos++];

  function parseExpr(depth) {
    if (depth > MAX_DEPTH) throw new FormulaError('表达式嵌套过深');
    let node = parseTerm(depth);
    while (peek() && peek().t === 'op' && (peek().v === '+' || peek().v === '-')) {
      const op = next().v;
      node = { t: 'binop', op, l: node, r: parseTerm(depth) };
    }
    return node;
  }
  function parseTerm(depth) {
    let node = parseFactor(depth);
    while (peek() && peek().t === 'op' && (peek().v === '*' || peek().v === '/')) {
      const op = next().v;
      node = { t: 'binop', op, l: node, r: parseFactor(depth) };
    }
    return node;
  }
  function parseFactor(depth) {
    const tk = peek();
    if (!tk) throw new FormulaError('表达式意外结束');
    if (tk.t === 'op' && (tk.v === '+' || tk.v === '-')) {   // 一元 ±
      next();
      return { t: 'unary', op: tk.v, x: parseFactor(depth + 1) };
    }
    if (tk.t === 'num') { next(); return { t: 'num', v: tk.v }; }
    if (tk.t === 'cell') { next(); return parseMaybeRange(tk); }
    if (tk.t === 'lp') {
      next();
      const e = parseExpr(depth + 1);
      if (!peek() || peek().t !== 'rp') throw new FormulaError('缺右括号');
      next();
      return e;
    }
    if (tk.t === 'func') {
      next();
      if (!WHITELIST_FUNCS.has(tk.name)) throw new FormulaError('未知函数：' + tk.name); // fail-closed
      if (!peek() || peek().t !== 'lp') throw new FormulaError('函数缺左括号');
      next();
      const args = [];
      if (peek() && peek().t !== 'rp') {
        args.push(parseArg(depth + 1));
        while (peek() && peek().t === 'comma') { next(); args.push(parseArg(depth + 1)); }
      }
      if (!peek() || peek().t !== 'rp') throw new FormulaError('函数缺右括号');
      next();
      return { t: 'call', name: tk.name, args };
    }
    throw new FormulaError('意外 token');
  }
  // 函数实参可以是 range / str / 普通表达式
  function parseArg(depth) {
    const tk = peek();
    if (tk && tk.t === 'str') { next(); return { t: 'str', v: tk.v }; }
    if (tk && tk.t === 'cell') { next(); return parseMaybeRange(tk); }
    return parseExpr(depth);
  }
  function parseMaybeRange(cellTk) {
    if (peek() && peek().t === 'colon') {
      next();
      const c2 = peek();
      if (!c2 || c2.t !== 'cell') throw new FormulaError('区间右端非单元格');
      next();
      return { t: 'range', c1: cellTk, c2 };
    }
    return { t: 'cell', col: cellTk.col, row: cellTk.row };
  }

  const ast = parseExpr(0);
  if (pos !== toks.length) throw new FormulaError('公式尾部有多余 token'); // fail-closed（-2+3 之类被完整消费）
  return ast;
}

// ── evaluator ────────────────────────────────────────────────────────────────────
// resolve(col, row) → 原始 cell 值（越界返 undefined → 视 0）；数值/字符串原样返回。
function rangeCells(node) {
  const c1 = colToIndex(node.c1.col), c2 = colToIndex(node.c2.col);
  const r1 = node.c1.row, r2 = node.c2.row;
  const cLo = Math.min(c1, c2), cHi = Math.max(c1, c2);
  const rLo = Math.min(r1, r2), rHi = Math.max(r1, r2);
  const size = (cHi - cLo + 1) * (rHi - rLo + 1);
  if (size > MAX_RANGE) throw new FormulaError('区间过大（>5000 单元）');
  const cells = [];
  for (let ci = cLo; ci <= cHi; ci++) {
    for (let ri = rLo; ri <= rHi; ri++) cells.push({ ci, ri });
  }
  return cells;
}
function toNum(v) {                       // 越界/空/非数 → 0（GAP-2① Excel 手感）
  if (v === undefined || v === null || v === '') return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function evalNode(node, resolve) {
  switch (node.t) {
    case 'num': return node.v;
    case 'unary': { const x = evalNode(node.x, resolve); return node.op === '-' ? -x : x; }
    case 'cell': return toNum(resolve(node.col, node.row));
    case 'binop': {
      const a = evalNode(node.l, resolve), b = evalNode(node.r, resolve);
      switch (node.op) {
        case '+': return a + b;
        case '-': return a - b;
        case '*': return a * b;
        case '/': return a / b;   // 除零 → ±Inf；顶层 non-finite 检查兜住（GAP-2③）
        default: throw new FormulaError('未知算子');
      }
    }
    case 'range': throw new FormulaError('区间只能作函数实参'); // 裸区间非法
    case 'str': throw new FormulaError('字符串只能作 SUMIF criteria');
    case 'call': return evalCall(node, resolve);
    default: throw new FormulaError('未知节点');
  }
}

function evalCall(node, resolve) {
  const name = node.name;
  // 聚合类：展平所有实参（range → 各 cell 数值；标量表达式 → 单值）
  const flatNums = () => {
    const out = [];
    for (const arg of node.args) {
      if (arg.t === 'range') { for (const { ci, ri } of rangeCells(arg)) out.push(toNum(resolve(colFromIndex(ci), ri))); }
      else if (arg.t === 'str') throw new FormulaError(name + ' 不接受字符串实参');
      else out.push(evalNode(arg, resolve));
    }
    return out;
  };
  switch (name) {
    case 'SUM': return flatNums().reduce((a, b) => a + b, 0);
    case 'AVG': { const xs = flatNums(); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0; }
    case 'COUNT': return flatNums().length;
    case 'MIN': { const xs = flatNums(); if (!xs.length) throw new FormulaError('MIN 空集'); return Math.min(...xs); }
    case 'MAX': { const xs = flatNums(); if (!xs.length) throw new FormulaError('MAX 空集'); return Math.max(...xs); }
    case 'SUMIF': return evalSumIf(node.args, resolve);
    default: throw new FormulaError('未知函数：' + name);   // 冗余 fail-closed
  }
}

function evalSumIf(args, resolve) {
  if (args.length !== 3) throw new FormulaError('SUMIF 需 3 参（范围, 条件, 求和范围）');
  const [rangeNode, critNode, sumNode] = args;
  if (rangeNode.t !== 'range' || sumNode.t !== 'range') throw new FormulaError('SUMIF 首/末参须为区间');
  const rc = rangeCells(rangeNode), sc = rangeCells(sumNode);
  // criteria：字符串字面 或 标量表达式 → 精确匹配（string / number 相等）；不解释为代码/正则
  const crit = critNode.t === 'str' ? critNode.v : evalNode(critNode, resolve);
  const critStr = String(crit);
  let sum = 0;
  const n = Math.min(rc.length, sc.length);
  for (let k = 0; k < n; k++) {
    const cellVal = resolve(colFromIndex(rc[k].ci), rc[k].ri);
    if (String(cellVal ?? '') === critStr) sum += toNum(resolve(colFromIndex(sc[k].ci), sc[k].ri));
  }
  return sum;
}

// 下标 → 列字母（供 range 展开后回传 resolve；纯计算无属性访问）
function colFromIndex(idx) {
  let s = '', n = idx + 1;
  while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

// ── 公共 API ───────────────────────────────────────────────────────────────────

/** 求值单条公式。resolve(col, row) → 原始 cell 值（越界返 undefined）。**总是** throw FormulaError（fail-closed）。*/
export function evaluateFormula(formula, resolve) {
  let result;
  try {
    result = evalNode(parse(tokenize(formula)), resolve);
  } catch (e) {
    // 契约：对外只抛 FormulaError（栈溢出 RangeError / 解析器内 TypeError 等一律归一）
    if (e instanceof FormulaError) throw e;
    throw new FormulaError('求值失败：' + String(e && e.message ? e.message : e).slice(0, 80));
  }
  if (typeof result !== 'number' || !Number.isFinite(result)) {
    throw new FormulaError('结果非有限数（NaN/Infinity，如除零）'); // GAP-2③
  }
  return result;
}

/**
 * 计算宽表覆盖层。
 *   rows: 冻结 SQL 结果行（list of dict）；cols: 有序列名（cols[0]→A, cols[1]→B, …）。
 *   overlay: [{ row, col, kind:'text'|'formula', value }]（row=A1 行号 1-based；col=列字母）。
 * 返回 { values: Map<'col+row', 值>, errors: Map<'col+row', 错误消息> }。
 * 环检测（GAP-1）：公式 cell 互引 → visited-set 命中 → 该 cell 记 error（不崩全表）。
 */
export function computeOverlay({ rows = [], cols = [], overlay = [] }) {
  // overlay 索引：'COL+ROW' → cell（用普通对象但键是拼接字符串；读取仅 Object.prototype.hasOwnProperty 经 Map 规避）
  const ovMap = new Map();
  for (const cell of overlay) {
    if (cell && typeof cell.col === 'string' && Number.isInteger(cell.row)) {
      ovMap.set(cell.col.toUpperCase() + cell.row, cell);
    }
  }
  const colIndexByLetter = (letter) => colToIndex(letter);
  // ⭐ 记忆化（红队 wmme5n9x4 GAP 修）：每公式 cell 至多算一次 → 消跨 cell 指数(diamond fan-out)
  // 与二次(deep chain)放大；visiting 只挡真环，memo 挡「重复求值」。跨 cell 深度上限防深链栈溢出。
  const memo = new Map();
  let totalSteps = 0;   // 全局求值步数（跨所有 top-level cell + 递归，共享）

  // resolve：overlay 公式 cell 递归求值（visiting 环检测 + memo 记忆化 + depth 深链护栏 + 全局步数预算）
  function makeResolve(visiting, depth) {
    return function resolve(col, row) {
      if (++totalSteps > MAX_TOTAL_STEPS) throw new FormulaError('覆盖层求值预算耗尽（overlay 过大/过深）'); // 结构无关硬上限
      const key = col + row;
      const ov = ovMap.get(key);
      if (ov) {
        if (ov.kind === 'formula') {
          if (memo.has(key)) return memo.get(key);                              // 记忆化命中 → O(cells)
          if (visiting.has(key)) throw new FormulaError('单元格循环引用：' + key); // GAP-1 真环
          if (depth > MAX_OVERLAY_DEPTH) throw new FormulaError('覆盖层引用链过深'); // 防深链栈溢出
          visiting.add(key);
          try {
            const v = evaluateFormula(ov.value, makeResolve(visiting, depth + 1));
            memo.set(key, v);
            return v;
          } finally {
            visiting.delete(key);
          }
        }
        return ov.value;                 // overlay text
      }
      // 数据格：row(1-based) → rows[row-1]；col 字母 → cols[idx]（受信列名，非用户串）
      const ri = row - 1, ci = colIndexByLetter(col);
      if (ri < 0 || ri >= rows.length || ci < 0 || ci >= cols.length) return undefined; // 越界 → 0
      return rows[ri][cols[ci]];
    };
  }

  const values = new Map();
  const errors = new Map();
  for (const cell of overlay) {
    // 跳过畸形 overlay 条目（col 非串 / row 非整 → 防 to* 崩，LENS-1 note）
    if (!cell || cell.kind !== 'formula' || typeof cell.col !== 'string' || !Number.isInteger(cell.row)) continue;
    const key = cell.col.toUpperCase() + cell.row;
    if (memo.has(key)) { values.set(key, memo.get(key)); continue; }  // 已被前面 cell 引用时算过
    try {
      const v = evaluateFormula(cell.value, makeResolve(new Set([key]), 0));
      values.set(key, v);
      memo.set(key, v);
    } catch (e) {
      errors.set(key, e instanceof FormulaError ? e.message : '公式错误');
    }
  }
  return { values, errors };
}
