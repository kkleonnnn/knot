// TabbedTableReport.jsx — v0.8.7 多页表报表（report_type='tabbed'）。
// report.tiles[] 每 tile = 一个页签：一条自己的 SQL + 独立冻结快照 + 列配置（对齐运营日报 日/周/月 三 sheet）。
// 页签栏（复用宽表页签视觉）+ 选中页 <WideTable>。tile.viz_config = { columns:{col:{label,desc,conditional,unit}}, overlay:[] }。
import { useMemo, useState } from 'react';
import { WideTable } from './WideTable.jsx';
import { parseTile } from './tiles/tile_data.js';

export function TabbedTableReport({ T, report }) {
  const [tab, setTab] = useState(0);
  const tiles = useMemo(
    () => [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [report.tiles],
  );

  if (!tiles.length) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
        该报表暂无页签 —— admin 点「编辑」添加。
      </div>
    );
  }

  const active = tiles[Math.min(tab, tiles.length - 1)];
  const { rows, viz, error } = parseTile(active);
  const cfg = viz.columns || {};
  const overlay = viz.overlay || [];

  const tabStyle = (on) => ({
    padding: '8px 16px', background: on ? T.bg : T.content, border: `1px solid ${T.border}`,
    borderBottom: `1px solid ${on ? T.bg : T.border}`, borderRadius: '7px 7px 0 0', marginBottom: -1,
    color: on ? T.accent : T.subtext, fontSize: 12.5, fontFamily: T.sans, cursor: 'pointer', fontWeight: on ? 600 : 500,
  });

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', paddingLeft: 2, flexWrap: 'wrap' }}>
        {tiles.map((t, i) => (
          <button key={t.id} onClick={() => setTab(i)} style={tabStyle(i === tab)}>{t.title || `页 ${i + 1}`}</button>
        ))}
      </div>
      {error && (
        <div style={{ padding: '8px 14px', fontSize: 12, color: 'oklch(66% 0.20 25)', border: `1px solid ${T.border}`, borderTop: 'none', background: T.content }}>⚠ {error}</div>
      )}
      <WideTable T={T} rows={rows} cfg={cfg} overlay={overlay} />
    </div>
  );
}
