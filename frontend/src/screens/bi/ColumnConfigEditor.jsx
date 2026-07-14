// ColumnConfigEditor.jsx — v0.8.8 ② admin 逐列配置（kk：列名自定义编辑）。
// 每列可编：label（短表头）/ desc（口径 · 表头 hover tooltip）/ unit（%）/ conditional（正负着色）→ 写 viz_config.columns[col]。
// 列来源 = 该页最近快照（last_run_rows_json 首行键 = SQL 查询列序）；新页未跑无列 → 提示先重跑。
// v0.8.8 修（对抗复核 #3）：orderedCols 已改「数据列为准」→ 列序恒 = SQL 查询序（不依赖 cfg 键序）；
//   updCol 按 all（当前快照列）重建 columns → 顺带剪除改 SQL 掉列后的陈旧 config 键（不再留空占位幻影列）。
// v0.8.9：每列显示列字母（A/B/…，= 渲染列序）助记公式行 A1 引用。
import { colLetter } from './tiles/tile_data.js';

export function ColumnConfigEditor({ T, tile, viz, onChange }) {
  const fld = { padding: '4px 6px', borderRadius: 5, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 12, fontFamily: T.sans };
  const cfg = viz.columns || {};

  let snapCols = [];
  try {
    const rows = tile.last_run_rows_json ? JSON.parse(tile.last_run_rows_json) : [];
    if (rows.length) snapCols = Object.keys(rows[0]);
  } catch { /* 快照解析失败 → 无列 */ }
  // 有快照 → 只列当前 SQL 返回列（陈旧 cfg 键不显）；无快照（跑过返 0 行）→ 回退已存 config 键
  const all = snapCols.length ? snapCols : Object.keys(cfg);

  // 按 all（当前列）重建 columns，仅改目标列 → 剪除陈旧键 + 保留现列配置
  const updCol = (col, patch) => {
    const next = {};
    for (const k of all) next[k] = k === col ? { ...(cfg[k] || {}), ...patch } : (cfg[k] || {});
    onChange(next);
  };

  if (!all.length) {
    return <div style={{ fontSize: 11, color: T.muted, marginTop: 4 }}>先创建并「重跑」该页，载入列后可编辑表头名 / 口径。</div>;
  }
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 4 }}>列配置（表头名 · 口径 hover · 单位 · 正负色）</div>
      {all.map((col, idx) => {
        const c = cfg[col] || {};
        return (
          <div key={col} style={{ display: 'flex', gap: 5, marginBottom: 4, alignItems: 'center' }}>
            <span title={`列 ${colLetter(idx)} · ${col}`} style={{ width: 96, flexShrink: 0, fontSize: 11, color: T.subtext, fontFamily: T.mono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ color: T.accent, fontWeight: 650 }}>{colLetter(idx)}</span> {col}
            </span>
            <input value={c.label || ''} onChange={(e) => updCol(col, { label: e.target.value })} placeholder="表头名" style={{ ...fld, flex: 1, minWidth: 0 }} />
            <input value={c.desc || ''} onChange={(e) => updCol(col, { desc: e.target.value })} placeholder="口径(hover)" style={{ ...fld, flex: 1.4, minWidth: 0 }} />
            <select value={c.unit || ''} onChange={(e) => updCol(col, { unit: e.target.value || undefined })} title="单位" style={{ ...fld, width: 54, cursor: 'pointer' }}>
              <option value="">—</option><option value="percentage">%</option>
            </select>
            <label title="正负着色（正绿负红）" style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 12, color: T.subtext, flexShrink: 0, cursor: 'pointer' }}>
              <input type="checkbox" checked={!!c.conditional} onChange={(e) => updCol(col, { conditional: e.target.checked })} />±
            </label>
          </div>
        );
      })}
    </div>
  );
}
