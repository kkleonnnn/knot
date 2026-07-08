// DonutTile.jsx — v0.8.6 (②b) 圆盘板块。slices = rows[{labelCol,valueCol}]；自绘 Donut + 图例。
import { CHART_COLORS } from '../../../Shared.jsx';
import { Card, Donut, TileState } from './_shared.jsx';
import { parseTile } from './tile_data.js';

export function DonutTile({ T, tile }) {
  const { rows, viz, error } = parseTile(tile);
  if (error || !rows.length) return <Card T={T} title={tile.title}><TileState T={T} error={error} /></Card>;
  const keys = Object.keys(rows[0]);
  const labelCol = viz.labelCol || keys[0];
  const valueCol = viz.valueCol || keys.find((k) => typeof rows[0][k] === 'number') || keys[1] || keys[0];
  const slices = rows.map((r) => ({ name: String(r[labelCol]), value: Number(r[valueCol]) || 0 }));
  const total = slices.reduce((a, s) => a + s.value, 0);
  const big = viz.big || (slices[0] && total ? `${Math.round((slices[0].value / total) * 100)}%` : '');
  return (
    <Card T={T} title={tile.title}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <Donut T={T} slices={slices} big={big} sub={viz.sub} />
        <div style={{ flex: 1, minWidth: 0 }}>
          {slices.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: CHART_COLORS[i % CHART_COLORS.length] }} />
              <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: T.subtext, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
              <span style={{ fontSize: 12.5, color: T.text, fontFamily: T.mono }}>{s.value.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
