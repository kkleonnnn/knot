// TableTile.jsx — v0.8.6 (②b) 表格板块。复用 WideTableReport.orderedCols（通用动态列）+ fmtValue。
import { fmtValue } from '../../chat/ResultBlock/fmt.js';
import { Card, TileState } from './_shared.jsx';
import { parseTile, orderedCols } from './tile_data.js';

export function TableTile({ T, tile }) {
  const { rows, viz, error } = parseTile(tile);
  if (error || !rows.length) return <Card T={T} title={tile.title}><TileState T={T} error={error} /></Card>;
  const cfg = viz.cols || {};
  const cols = orderedCols(rows, cfg);
  const label = (c) => (cfg[c] && cfg[c].label) || c;
  return (
    <Card T={T} title={tile.title} style={{ padding: 0, overflow: 'hidden' }}>
      <div className="cb-sb" style={{ overflow: 'auto', maxHeight: 320 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: T.sans }}>
          <thead>
            <tr>{cols.map((c, i) => (
              <th key={c} style={{ padding: '9px 12px', textAlign: i === 0 ? 'left' : 'right', fontSize: 10.5, fontFamily: T.mono, color: T.muted, fontWeight: 500, letterSpacing: '0.03em', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{label(c)}</th>
            ))}</tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>{cols.map((c, i) => (
                <td key={c} style={{ padding: '8px 12px', textAlign: i === 0 ? 'left' : 'right', fontSize: 12, color: T.text, fontFamily: i === 0 ? T.sans : T.mono, borderBottom: `1px solid ${T.borderSoft}`, whiteSpace: 'nowrap' }}>{fmtValue(r[c], cfg[c] && cfg[c].unit)}</td>
              ))}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
