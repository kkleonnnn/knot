// tile_data.js — v0.8.6 (②b) tile 纯数据 helper（无组件 → .js，随 formula.js/fmt.js 惯例，过 react-refresh 门）。

// 通用「SQL rows → 有序列」（union 保序，cfg 键优先）—— WideTableReport + TableTile 共用（B-5 单一真相源）。
export function orderedCols(rows, cfg) {
  const seen = [];
  const push = (k) => { if (!seen.includes(k)) seen.push(k); };
  if (cfg && typeof cfg === 'object') Object.keys(cfg).forEach(push);
  for (const r of rows) Object.keys(r || {}).forEach(push);
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
