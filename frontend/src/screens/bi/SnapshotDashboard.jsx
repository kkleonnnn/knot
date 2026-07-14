// SnapshotDashboard.jsx — v0.8.15 分享：仪表盘离屏快照重建（截图源节点）。
// 与 DashboardReport 同栅格 + 同 DashboardWidget 渲染，但为截图去 chrome：
//   noGrip（省 ⋮⋮ 拖拽手柄）· 无「+添加组件」磁贴 · 无空态 · 固定宽（截图确定尺寸）· 含洞察卡（D1）。
// 复用既有渲染器 = 0 新视觉；样式全内联（0 className 依赖 — foreignObject 序列化前提）。
// 报表标题走 IM caption（不在快照里加标题 chrome）。
import { InsightCard } from './InsightCard.jsx';
import { DashboardWidget } from './DashboardWidgets.jsx';
import { WIDGET_META } from './tiles/tile_data.js';

const SNAP_WIDTH = 1200;   // 固定画布宽（live grid maxWidth 1200；截图须确定尺寸不 collapse）

export function SnapshotDashboard({ T, report }) {
  let cfg = {};
  try { cfg = JSON.parse(report.dashboard_config || '{}'); } catch { /* {} */ }
  const tiles = [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
  return (
    <div style={{ width: SNAP_WIDTH, background: T.bg, padding: 20, boxSizing: 'border-box',
                  fontFamily: T.sans, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, minmax(0, 1fr))', gridAutoRows: '164px', gap: 12 }}>
        {tiles.map((tile, i) => {
          const meta = WIDGET_META[tile.tile_type] || WIDGET_META.stat;
          return (
            <div key={tile.id} style={{ gridColumn: `span ${meta.w}`, gridRow: `span ${meta.h}`, minWidth: 0 }}>
              <DashboardWidget T={T} tile={tile} index={i} noGrip />
            </div>
          );
        })}
      </div>
      {cfg.insight && <InsightCard T={T} text={cfg.insight} />}
    </div>
  );
}
