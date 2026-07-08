// WideTableReport.jsx — v0.8.5 (②a) 宽表报表（handoff §5 忠实还原）。
// sheet 折叠页标签(日/周/月，选中页 bg=--bg 与表头相连) + 冻结首列 + 冻结表头 + 横向滚动 +
// 数值列条件着色(绿正/红负，column_config[col].conditional) + 覆盖层公式(kk D3「插入」，formula.js 安全求值)。
// 复用 Foundation：T token / fmtValue / cb-sb。显式有序 cols（union 保序）。
import { useMemo, useState } from 'react';
import { fmtValue } from '../chat/ResultBlock/fmt.js';
import { computeOverlay } from './formula.js';
import { orderedCols } from './tiles/tile_data.js';   // v0.8.6 ②b B-5：单一真相源（TableTile 共用）

const RED = 'oklch(66% 0.20 25)';

function colLetter(i) { let s = '', n = i + 1; while (n > 0) { s = String.fromCharCode(65 + (n - 1) % 26) + s; n = Math.floor((n - 1) / 26); } return s; }

export function WideTableReport({ T, report }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });
  const [tab, setTab] = useState(0);  // 日/周/月（视觉态；数据按粒度重取留后端 ②）

  const rows = useMemo(() => { try { return JSON.parse(report.last_run_rows_json || '[]'); } catch { return []; } }, [report.last_run_rows_json]);
  const cfg = useMemo(() => { try { return report.column_config ? JSON.parse(report.column_config) : {}; } catch { return {}; } }, [report.column_config]);
  const overlay = useMemo(() => { try { return report.overlay_config ? JSON.parse(report.overlay_config) : []; } catch { return []; } }, [report.overlay_config]);
  const cols = useMemo(() => orderedCols(rows, cfg), [rows, cfg]);
  const label = (c) => (cfg[c] && cfg[c].label) || c;

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

  const SHEETS = ['日汇总', '周汇总', '月汇总'];
  const tabStyle = (on) => ({
    padding: '8px 16px', background: on ? T.bg : T.content, border: `1px solid ${T.border}`,
    borderBottom: `1px solid ${on ? T.bg : T.border}`, borderRadius: '7px 7px 0 0', marginBottom: -1,
    color: on ? T.accent : T.subtext, fontSize: 12.5, fontFamily: T.sans, cursor: 'pointer', fontWeight: on ? 600 : 500,
  });
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
    <div>
      {/* sheet 折叠页标签 —— 黏在一起、左对齐、选中页与表头同色相连 */}
      <div style={{ display: 'flex', alignItems: 'flex-end', paddingLeft: 2 }}>
        {SHEETS.map((s, i) => (
          <button key={s} onClick={() => setTab(i)} style={tabStyle(i === tab)}>{s}</button>
        ))}
      </div>
      {/* 表体：顶部不加框（标签落上去），左右下 1px + 圆角 0 0 12 12 */}
      <div className="cb-sb" style={{ overflow: 'auto', maxHeight: 520, border: `1px solid ${T.border}`, borderTop: 'none', borderRadius: '0 0 12px 12px', background: T.content }}>
        <table style={{ borderCollapse: 'separate', borderSpacing: 0, width: 'max-content', minWidth: '100%' }}>
          <thead>
            <tr>
              {cols.map((c, i) => (
                <th key={c} onClick={() => setSort((s) => ({ key: c, dir: s.key === c ? -s.dir : 1 }))} title={`列 ${colLetter(i)} · 点击排序`} style={thStyle(i)}>
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
                  return <td key={c} style={{ ...tdStyle(c, i, v), fontWeight: 600, color: warn ? T.warn : (i === 0 ? T.text : T.text), background: i === 0 ? T.accentSoft : T.accentSoft }}>{v === undefined ? '' : (typeof v === 'number' ? v.toLocaleString() : String(v))}</td>;
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
    </div>
  );
}
