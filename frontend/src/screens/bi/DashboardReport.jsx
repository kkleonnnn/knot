// DashboardReport.jsx — v0.8.10 仪表盘 = 可组合组件网格（基准 §5）。
// 12 列栅格 · grid-auto-rows 164px · gap 12；组件 w×h 由类型固定（WIDGET_META，同类尺寸一致）。
// 每 tile 从冻结快照渲染（DashboardWidgets）；末尾「+ 添加组件」磁贴（admin）；底部洞察卡。
import { useMemo } from 'react';
import { InsightCard } from './InsightCard.jsx';
import { DashboardWidget } from './DashboardWidgets.jsx';
import { WIDGET_META } from './tiles/tile_data.js';

export function DashboardReport({ T, report, isAdmin = false, onAddWidget }) {
  const cfg = useMemo(() => { try { return JSON.parse(report.dashboard_config || '{}'); } catch { return {}; } }, [report.dashboard_config]);
  const tiles = useMemo(
    () => [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [report.tiles],
  );

  if (!tiles.length && !isAdmin) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
        该仪表盘暂无组件 —— admin 点「编辑」添加。
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, minmax(0, 1fr))', gridAutoRows: '164px', gap: 12 }}>
        {tiles.map((tile, i) => {
          const meta = WIDGET_META[tile.tile_type] || WIDGET_META.stat;
          return (
            <div key={tile.id} style={{ gridColumn: `span ${meta.w}`, gridRow: `span ${meta.h}`, minWidth: 0 }}>
              <DashboardWidget T={T} tile={tile} index={i} />
            </div>
          );
        })}
        {isAdmin && (
          <div style={{ gridColumn: 'span 3', gridRow: 'span 1', minWidth: 0 }}>
            <button onClick={onAddWidget} title="添加组件"
              style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 9, background: 'transparent', border: `1px dashed ${T.border}`, borderRadius: 12, color: T.muted, cursor: 'pointer', fontFamily: 'inherit' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
              <span style={{ fontSize: 13, fontWeight: 500 }}>添加组件</span>
            </button>
          </div>
        )}
      </div>
      {cfg.insight && <InsightCard T={T} text={cfg.insight} />}
    </div>
  );
}
