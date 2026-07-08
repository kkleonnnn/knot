// TabbedTableReport.jsx — v0.8.7 多页表报表（report_type='tabbed'）。
// report.tiles[] 每 tile = 一个页签：一条自己的 SQL + 独立冻结快照 + 列配置（对齐运营日报 日/周/月 三 sheet）。
// 页签栏（复用宽表页签视觉）+ 选中页 <WideTable>。tile.viz_config = { columns:{col:{label,desc,conditional,unit}}, overlay:[] }。
import { useEffect, useMemo, useState } from 'react';
import { WideTable } from './WideTable.jsx';
import { parseTile } from './tiles/tile_data.js';

export function TabbedTableReport({ T, report, onActiveTile }) {
  const [tab, setTab] = useState(0);
  const tiles = useMemo(
    () => [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [report.tiles],
  );
  const active = tiles.length ? tiles[Math.min(tab, tiles.length - 1)] : null;
  // v0.8.9 #3：上报当前页 id 给父（BI.jsx）→ CSV 导出当前页
  useEffect(() => { if (active && onActiveTile) onActiveTile(active.id); }, [active, onActiveTile]);

  if (!tiles.length) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
        该报表暂无页签 —— admin 点「编辑」添加。
      </div>
    );
  }

  const { rows, viz, error } = parseTile(active);
  const cfg = viz.columns || {};
  const overlay = viz.overlay || [];
  const single = tiles.length === 1;   // v0.8.7 ①：单页报表 = 普通表格（隐页签栏 + 圆角顶）

  // 页签接缝（kk 修）：表体保完整上边框；选中 border-bottom=bg 仅咬脚下 1px + margin-bottom:-1 骑线；
  // 未选中 border-bottom:none + margin-bottom:0 落在上边框上（线可见）；左缘与表体对齐（无 paddingLeft）。
  const tabStyle = (on) => ({
    padding: '8px 16px', background: on ? T.bg : T.content, border: `1px solid ${T.border}`,
    borderBottom: on ? `1px solid ${T.bg}` : 'none', marginBottom: on ? -1 : 0, borderRadius: '7px 7px 0 0',
    color: on ? T.accent : T.subtext, fontSize: 12.5, fontFamily: T.sans, cursor: 'pointer', fontWeight: on ? 600 : 500,
  });

  return (
    <div>
      {!single && (
        <div style={{ display: 'flex', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          {tiles.map((t, i) => (
            <button key={t.id} onClick={() => setTab(i)} style={tabStyle(i === tab)}>{t.title || `页 ${i + 1}`}</button>
          ))}
        </div>
      )}
      {error && (
        <div style={{ padding: '8px 14px', fontSize: 12, color: 'oklch(66% 0.20 25)', border: `1px solid ${T.border}`, borderTop: 'none', background: T.content }}>⚠ {error}</div>
      )}
      <WideTable T={T} rows={rows} cfg={cfg} overlay={overlay} roundTop={single && !error} />
    </div>
  );
}
