// WideTable.jsx — v0.8.7 宽表表体核心（从 WideTableReport 抽出，供单宽表 + tabbed 页签共用）。
// 冻结首列 + sticky 表头 + 点击排序 + 条件着色(column_config[c].conditional) + 覆盖层公式(formula.js) +
// 列注释表头(cfg[c].label 短表头 · cfg[c].desc 长口径 hover tooltip)。props: {T, rows, cfg, overlay, maxHeight}。
import { useMemo, useState } from 'react';
import { fmtValue } from '../chat/ResultBlock/fmt.js';
import { computeOverlay } from './formula.js';
import { orderedCols } from './tiles/tile_data.js';

const RED = 'oklch(66% 0.20 25)';
function colLetter(i) { let s = '', n = i + 1; while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); } return s; }

export function WideTable({ T, rows = [], cfg = {}, overlay = [], maxHeight = 520, roundTop = false }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });
  const cols = useMemo(() => orderedCols(rows, cfg), [rows, cfg]);
  const label = (c) => (cfg[c] && cfg[c].label) || c;
  const desc = (c) => (cfg[c] && cfg[c].desc) || '';   // v0.8.7 长口径 → 表头 hover tooltip

  const sortedRows = useMemo(() => {
    if (!sort.key) return rows;
    return [...rows].sort((a, b) => {
      const nx = Number(a[sort.key]), ny = Number(b[sort.key]);
      const cmp = (Number.isFinite(nx) && Number.isFinite(ny)) ? nx - ny : String(a[sort.key] ?? '').localeCompare(String(b[sort.key] ?? ''));
      return cmp * sort.dir;
    });
  }, [rows, sort]);

  const { values, errors } = useMemo(() => computeOverlay({ rows, cols, overlay }), [rows, cols, overlay]);
  const overlayRows = useMemo(() => {
    const byRow = new Map();
    for (const c of overlay) {
      if (!c || typeof c.col !== 'string' || !Number.isInteger(c.row)) continue;
      if (!byRow.has(c.row)) byRow.set(c.row, {});
      const key = c.col.toUpperCase() + c.row;
      byRow.get(c.row)[c.col.toUpperCase()] = c.kind === 'formula' ? (errors.has(key) ? '⚠ ' + errors.get(key) : values.get(key)) : c.value;
    }
    return [...byRow.entries()].sort((a, b) => a[0] - b[0]).map(([, cells]) => cells);
  }, [overlay, values, errors]);

  if (!rows.length && !overlayRows.length) {
    return <div style={{ padding: '48px 20px', textAlign: 'center', color: T.muted, fontSize: 13 }}>暂无数据 —— 点「重跑」拉取最新结果（admin）。</div>;
  }

  const isConditional = (c) => cfg[c] && cfg[c].conditional;
  const thStyle = (i) => ({
    position: 'sticky', top: 0, zIndex: i === 0 ? 4 : 3, background: T.bg,
    padding: '9px 14px', textAlign: i === 0 ? 'left' : 'right', color: T.muted, fontFamily: T.mono,
    fontWeight: 500, fontSize: 10.5, letterSpacing: '0.03em', whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none',
    borderBottom: `1px solid ${T.border}`, ...(i === 0 ? { left: 0, borderRight: `1px solid ${T.border}` } : {}),
  });
  const tdStyle = (c, i, v) => {
    const base = { padding: '8px 14px', textAlign: i === 0 ? 'left' : 'right', color: T.text, fontFamily: T.mono, fontSize: 12, whiteSpace: 'nowrap', borderBottom: `1px solid ${T.borderSoft}` };
    if (i === 0) return { ...base, position: 'sticky', left: 0, zIndex: 1, background: T.content, borderRight: `1px solid ${T.border}` };
    if (isConditional(c)) {
      const pos = Number(v) >= 0;
      return { ...base, fontWeight: 600, color: pos ? T.success : RED, background: pos ? 'color-mix(in oklch, ' + T.success + ' 12%, transparent)' : 'color-mix(in oklch, ' + RED + ' 12%, transparent)' };
    }
    return base;
  };

  return (
    <div className="cb-sb" style={{ overflow: 'auto', maxHeight, border: `1px solid ${T.border}`, borderRadius: roundTop ? 12 : '0 0 12px 12px', background: T.content }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: 'max-content', minWidth: '100%' }}>
        <thead>
          <tr>
            {cols.map((c, i) => (
              <th key={c} onClick={() => setSort((s) => ({ key: c, dir: s.key === c ? -s.dir : 1 }))}
                title={desc(c) || `列 ${colLetter(i)} · 点击排序`} style={thStyle(i)}>
                {label(c)}{sort.key === c ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {overlayRows.map((cells, ri) => (
            <tr key={`ov-${ri}`} style={{ background: T.accentSoft }}>
              {cols.map((c, i) => {
                const v = cells[colLetter(i)];
                const warn = typeof v === 'string' && v.startsWith('⚠');
                return <td key={c} style={{ ...tdStyle(c, i, v), fontWeight: 600, color: warn ? T.warn : T.text, background: T.accentSoft }}>{v === undefined ? '' : (typeof v === 'number' ? v.toLocaleString() : String(v))}</td>;
              })}
            </tr>
          ))}
          {sortedRows.map((r, ri) => (
            <tr key={ri}>
              {cols.map((c, i) => <td key={c} style={tdStyle(c, i, r[c])}>{fmtValue(r[c], cfg[c] && cfg[c].unit)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
