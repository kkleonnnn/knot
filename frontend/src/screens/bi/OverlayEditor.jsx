// OverlayEditor.jsx — v0.8.9 per-页公式行编辑器（kk：表头↔数据之间插聚合/筛选行）。
// 复用 ②a 覆盖层模型 + formula.js 零 eval 求值器（SUM/SUMIF/AVG/COUNT/MIN/MAX + 算术 + A1 引用）。
// 单元格 {col:字母, row:覆盖行序(1-based), kind:'text'|'formula', value}。写 viz_config.overlay；WideTable 渲染在表头与数据之间。
// A1 引用指向**数据行**（col 字母 + 数据行号），如 =SUM(J1:J387) = J 列全 387 行求和。列字母图例助记。
import { colLetter } from './tiles/tile_data.js';

export function OverlayEditor({ T, tile, viz, overlay = [], onChange }) {
  const fld = { padding: '4px 6px', borderRadius: 5, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 11.5, fontFamily: T.sans };
  const cfg = viz.columns || {};

  let cols = [];
  let dataRows = 0;
  try {
    const rows = tile.last_run_rows_json ? JSON.parse(tile.last_run_rows_json) : [];
    dataRows = rows.length;
    if (rows.length) cols = Object.keys(rows[0]);
  } catch { /* 无快照 */ }
  const legend = cols.map((c, i) => `${colLetter(i)}=${(cfg[c] && cfg[c].label) || c}`);

  const add = () => onChange([...overlay, { col: 'A', row: 1, kind: 'formula', value: '' }]);
  const upd = (i, patch) => onChange(overlay.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const rm = (i) => onChange(overlay.filter((_, j) => j !== i));

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 11, color: T.muted }}>公式行单元格（插在表头↔数据之间；文本 / Excel 式公式）{dataRows ? ` · 数据 ${dataRows} 行` : ''}</span>
        <button onClick={add} style={{ border: `1px solid ${T.border}`, background: 'transparent', color: T.accent, borderRadius: 6, padding: '2px 8px', fontSize: 11.5, cursor: 'pointer', fontFamily: 'inherit' }}>+ 单元格</button>
      </div>
      {legend.length > 0 && (
        <div className="cb-sb" style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, marginBottom: 6, whiteSpace: 'nowrap', overflowX: 'auto', paddingBottom: 2 }}>
          {legend.join('  ·  ')}
        </div>
      )}
      {overlay.map((c, i) => (
        <div key={i} style={{ display: 'flex', gap: 5, marginBottom: 4, alignItems: 'center' }}>
          <input value={c.col} onChange={(e) => upd(i, { col: e.target.value.toUpperCase() })} placeholder="列(A)" style={{ ...fld, width: 44 }} />
          <input type="number" value={c.row} onChange={(e) => upd(i, { row: Number(e.target.value) })} title="公式行序（1=第一行）" style={{ ...fld, width: 50 }} />
          <select value={c.kind} onChange={(e) => upd(i, { kind: e.target.value })} style={{ ...fld, width: 66, cursor: 'pointer' }}>
            <option value="text">文本</option>
            <option value="formula">公式</option>
          </select>
          <input value={c.value} onChange={(e) => upd(i, { value: e.target.value })}
            placeholder={c.kind === 'formula' ? (dataRows ? `=SUM(J1:J${dataRows})` : '=SUM(J1:J10)') : '文本(如 合计)'}
            style={{ ...fld, flex: 1, minWidth: 0, fontFamily: c.kind === 'formula' ? T.mono : T.sans }} />
          <button onClick={() => rm(i)} title="删除" style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 14, flexShrink: 0 }}>×</button>
        </div>
      ))}
      {overlay.length > 0 && (
        <div style={{ fontSize: 10, color: T.muted, marginTop: 2 }}>支持 SUM/SUMIF/AVG/COUNT/MIN/MAX + 算术；A1 引用数据行（列字母见上）。</div>
      )}
    </div>
  );
}
