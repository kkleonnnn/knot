// KpiTile.jsx — v0.8.6 (②b) 单数值板块。value = viz.valueCol（builder 强制存 · C-3）或第一数值列（仅回退）。
import { fmtValue } from '../../chat/ResultBlock/fmt.js';
import { Card, TileState } from './_shared.jsx';
import { parseTile, numericCol } from './tile_data.js';

export function KpiTile({ T, tile }) {
  const { rows, viz, error } = parseTile(tile);
  const row = rows[0];
  if (error || !row) return <Card T={T} title={tile.title}><TileState T={T} error={error} /></Card>;
  const col = numericCol(row, viz.valueCol);
  const val = col != null ? row[col] : '';
  return (
    <Card T={T} title={tile.title}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
        <span style={{ fontSize: 26, fontWeight: 700, color: viz.main ? T.accent : T.text, fontFamily: T.mono }}>{fmtValue(val, viz.unit)}</span>
        {viz.suffix && <span style={{ fontSize: 13, color: T.muted }}>{viz.suffix}</span>}
      </div>
      {viz.hint && <div style={{ fontSize: 11, color: T.muted, marginTop: 6 }}>{viz.hint}</div>}
    </Card>
  );
}
