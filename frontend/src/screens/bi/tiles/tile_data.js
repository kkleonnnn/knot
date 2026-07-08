// tile_data.js — v0.8.6 (②b) tile 纯数据 helper（无组件 → .js，随 formula.js/fmt.js 惯例，过 react-refresh 门）。

// 列序号 → Excel 列字母（0→A, 25→Z, 26→AA…）—— 公式行 A1 引用 / 列配置字母提示共用（v0.8.9）。
export function colLetter(i) {
  let s = '', n = i + 1;
  while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); }
  return s;
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
