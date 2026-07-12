// tile_data.js — v0.8.6 (②b) tile 纯数据 helper（无组件 → .js，随 formula.js/fmt.js 惯例，过 react-refresh 门）。

// v0.8.10 仪表盘组件类型 → 栅格尺寸(w 列 × h 行) + 类型标签（同类尺寸完全一致 §5）。非组件常量放 .js 过 react-refresh 门。
export const WIDGET_META = {
  stat:  { w: 3, h: 1, kind: '单值' },
  pair:  { w: 9, h: 1, kind: '单值+趋势' },   // v0.8.11 kk：单值+趋势扩到 3 列（9/12）→ 趋势有呼吸空间
  trend: { w: 6, h: 2, kind: '趋势' },
  donut: { w: 6, h: 2, kind: '占比' },
  bars:  { w: 6, h: 2, kind: '排行' },
  table: { w: 6, h: 2, kind: '明细' },
};

// 列序号 → Excel 列字母（0→A, 25→Z, 26→AA…）—— 公式行 A1 引用 / 列配置字母提示共用（v0.8.9）。
export function colLetter(i) {
  let s = '', n = i + 1;
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); }
  return s;
}

// v0.8.10 值序列 → SVG path d（line + area），归一化到 viewBox w×h（pad 内边距）。
//   基准 §5 sparkline/trend：preserveAspectRatio:none 拉伸 + vector-effect:non-scaling-stroke。area 闭合到底边。
export function sparkPath(values, w, h, pad = 4) {
  const vals = (values || []).map(Number).filter((n) => Number.isFinite(n));
  if (vals.length < 2) return { line: '', area: '' };
  const min = Math.min(...vals), max = Math.max(...vals), range = (max - min) || 1;
  const xy = vals.map((v, i) => [
    (i / (vals.length - 1)) * w,
    h - pad - ((v - min) / range) * (h - 2 * pad),
  ]);
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` };
}

// 通用「SQL rows → 有序列」—— WideTableReport + TableTile + tabbed WideTable 共用（B-5 单一真相源）。
// v0.8.8 修（对抗复核 #3）：**数据列（rows 键 = SQL 查询序）为准**；cfg-only 键（配置了但当前 SQL 不返 =
//   陈旧/幻影列）**不渲染**（防列配置编辑后改 SQL 掉列，留下空「—」幻影列）。仅当无数据行时回退 cfg 键（空态可见性）。
export function orderedCols(rows, cfg) {
  const seen = [];
  const push = (k) => { if (!seen.includes(k)) seen.push(k); };
  for (const r of rows) Object.keys(r || {}).forEach(push);
  if (!seen.length && cfg && typeof cfg === 'object') Object.keys(cfg).forEach(push);
  return seen;
}

// 解析 tile 冻结快照 rows + viz_config（后端下发 JSON 串，前端 parse；同 dashboard_config 惯例）。
export function parseTile(tile) {
  let rows, viz;
  try { rows = JSON.parse(tile.last_run_rows_json || '[]'); } catch { rows = []; }
  try { viz = JSON.parse(tile.viz_config || '{}'); } catch { viz = {}; }
  return { rows, viz, error: tile.last_run_error || '' };
}

// 数值列取值：显式 col 优先；否则第一个 number 列（C-3 —— KPI render 期启发式仅作回退，
// builder 强制持久化 valueCol，吸 v0.7.30 ID-like 列坑）。
export function numericCol(row, explicit) {
  if (!row) return null;
  if (explicit && explicit in row) return explicit;
  for (const k of Object.keys(row)) {
    if (typeof row[k] === 'number') return k;
  }
  return Object.keys(row)[0] || null;
}
