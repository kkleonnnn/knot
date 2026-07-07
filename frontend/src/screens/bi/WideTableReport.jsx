// WideTableReport.jsx — v0.8.5 (②a) 宽表报表渲染器（只读）
// 复用 Foundation：theadStyle / T token / fmtValue / cb-sb 滚动壳（R-BI-3 视觉语言）。
// 净新：排序 + 冻结列（sticky） + 覆盖层（overlay，公式经 formula.js 客户端安全求值）。
// 显式有序 cols（union 保序，非脆弱 Object.keys(rows[0]) —— 守护者 D5 加分）。
import { useMemo, useState } from 'react';
import { theadStyle } from '../../Shared.jsx';
import { fmtValue } from '../chat/ResultBlock/fmt.js';
import { computeOverlay } from './formula.js';

const FROZEN_W = 150;   // 冻结列默认宽（sticky left 偏移用）

// 显式有序列：union 所有行的 key 保首见序（防 ragged 宽表丢列）；column_config 顺序优先
function orderedCols(rows, columnConfig) {
  const seen = [];
  const push = (k) => { if (!seen.includes(k)) seen.push(k); };
  if (columnConfig && typeof columnConfig === 'object') Object.keys(columnConfig).forEach(push);
  for (const r of rows) Object.keys(r || {}).forEach(push);
  return seen;
}

export function WideTableReport({ T, report }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });

  const rows = useMemo(() => {
    try { return JSON.parse(report.last_run_rows_json || '[]'); } catch { return []; }
  }, [report.last_run_rows_json]);

  const cfg = useMemo(() => {
    try { return report.column_config ? JSON.parse(report.column_config) : {}; } catch { return {}; }
  }, [report.column_config]);

  const overlay = useMemo(() => {
    try { return report.overlay_config ? JSON.parse(report.overlay_config) : []; } catch { return []; }
  }, [report.overlay_config]);

  const cols = useMemo(() => orderedCols(rows, cfg), [rows, cfg]);
  const label = (c) => (cfg[c] && cfg[c].label) || c;
  const frozenCols = cols.filter((c) => cfg[c] && cfg[c].frozen);
  const leftOf = (c) => frozenCols.slice(0, frozenCols.indexOf(c)).length * FROZEN_W;

  const sortedRows = useMemo(() => {
    if (!sort.key) return rows;
    return [...rows].sort((a, b) => {
      const x = a[sort.key], y = b[sort.key];
      const nx = Number(x), ny = Number(y);
      const cmp = (Number.isFinite(nx) && Number.isFinite(ny))
        ? nx - ny : String(x ?? '').localeCompare(String(y ?? ''));
      return cmp * sort.dir;
    });
  }, [rows, sort]);

  // 覆盖层：公式客户端求值（fail-closed）→ 按 row 号分组渲染为顶部汇总行
  const { values, errors } = useMemo(() => computeOverlay({ rows, cols, overlay }), [rows, cols, overlay]);
  const overlayRows = useMemo(() => {
    const byRow = new Map();
    for (const cell of overlay) {
      if (!cell || typeof cell.col !== 'string' || !Number.isInteger(cell.row)) continue;
      if (!byRow.has(cell.row)) byRow.set(cell.row, {});
      const key = cell.col.toUpperCase() + cell.row;
      byRow.get(cell.row)[cell.col.toUpperCase()] =
        cell.kind === 'formula'
          ? (errors.has(key) ? '⚠ ' + errors.get(key) : values.get(key))
          : cell.value;
    }
    return [...byRow.entries()].sort((a, b) => a[0] - b[0]).map(([, cells]) => cells);
  }, [overlay, values, errors]);

  if (!rows.length && !overlayRows.length) {
    return (
      <div style={{ padding: '48px 20px', textAlign: 'center', color: T.muted, fontSize: 13 }}>
        暂无数据 —— 点「重跑」拉取最新结果（admin）。
      </div>
    );
  }

  const colLetter = (i) => { let s = '', n = i + 1; while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); } return s; };
  const cellStyle = (c, extra) => ({
    padding: '9px 14px', fontSize: 12.5, whiteSpace: 'nowrap',
    borderBottom: `1px solid ${T.borderSoft}`,
    ...(cfg[c] && cfg[c].frozen ? { position: 'sticky', left: leftOf(c), background: T.card, zIndex: 1, minWidth: FROZEN_W } : {}),
    ...extra,
  });

  return (
    <div className="cb-sb" style={{ overflowX: 'auto', border: `1px solid ${T.border}`, borderRadius: 12, background: T.card }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: '100%', fontFamily: T.sans }}>
        <thead>
          <tr>
            {cols.map((c, i) => (
              <th key={c} onClick={() => setSort((s) => ({ key: c, dir: s.key === c ? -s.dir : 1 }))}
                  title={`列 ${colLetter(i)} · 点击排序`}
                  style={{
                    ...theadStyle(T), padding: '10px 14px', textAlign: 'left', cursor: 'pointer', userSelect: 'none',
                    position: 'sticky', top: 0, zIndex: cfg[c] && cfg[c].frozen ? 3 : 2,
                    ...(cfg[c] && cfg[c].frozen ? { left: leftOf(c), background: T.bg, minWidth: FROZEN_W } : {}),
                  }}>
                {label(c)}{sort.key === c ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* 覆盖层汇总行（overlay）—— 顶部，视觉区分 */}
          {overlayRows.map((cells, ri) => (
            <tr key={`ov-${ri}`} style={{ background: T.accentSoft }}>
              {cols.map((c) => {
                const L = colLetter(cols.indexOf(c));
                const v = cells[L];
                return (
                  <td key={c} style={cellStyle(c, { fontWeight: 600, color: typeof v === 'string' && v.startsWith('⚠') ? T.warn : T.text })}>
                    {v === undefined ? '' : (typeof v === 'number' ? v.toLocaleString() : String(v))}
                  </td>
                );
              })}
            </tr>
          ))}
          {sortedRows.map((r, ri) => (
            <tr key={ri}>
              {cols.map((c) => (
                <td key={c} style={cellStyle(c, { color: T.text })}>
                  {fmtValue(r[c], cfg[c] && cfg[c].unit)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
