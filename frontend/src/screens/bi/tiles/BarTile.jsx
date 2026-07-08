// BarTile.jsx — v0.8.6 (②b) 横条榜板块。rows[{labelCol,valueCol}] → 自绘水平条（CHART_COLORS 循环）。
import { CHART_COLORS } from '../../../Shared.jsx';
import { Card, TileState } from './_shared.jsx';
import { parseTile } from './tile_data.js';

export function BarTile({ T, tile }) {
  const { rows, viz, error } = parseTile(tile);
  if (error || !rows.length) return <Card T={T} title={tile.title}><TileState T={T} error={error} /></Card>;
  const keys = Object.keys(rows[0]);
  const labelCol = viz.labelCol || keys[0];
  const valueCol = viz.valueCol || keys.find((k) => typeof rows[0][k] === 'number') || keys[1] || keys[0];
  const bars = rows.map((r) => ({ label: String(r[labelCol]), value: Number(r[valueCol]) || 0 }));
  const bmax = Math.max(1, ...bars.map((b) => b.value));
  return (
    <Card T={T} title={tile.title}>
      {bars.map((b, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <span style={{ width: 80, fontSize: 12, color: T.subtext, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.label}</span>
          <div style={{ flex: 1, height: 8, borderRadius: 5, background: T.chipBg, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${(b.value / bmax * 100).toFixed(1)}%`, borderRadius: 5, background: CHART_COLORS[i % CHART_COLORS.length] }} />
          </div>
          <span style={{ width: 72, textAlign: 'right', fontSize: 12, color: T.text, fontFamily: T.mono, flexShrink: 0 }}>{b.value.toLocaleString()}</span>
        </div>
      ))}
    </Card>
  );
}
