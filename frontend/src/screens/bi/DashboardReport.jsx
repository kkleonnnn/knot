// DashboardReport.jsx — v0.8.6 (②b) 结构化 tile 仪表盘：读 report.tiles[]（按 sort_order），
// 按 tile_type 分发渲染器，grid_span(1/2/3) 布局；insight 保报表级 footer（dashboard_config.insight）。
// 每 tile 从自己冻结快照 last_run_rows_json 渲染（②a 静态 config 手写字面已废）。
import { useMemo } from 'react';
import { InsightCard } from './InsightCard.jsx';
import { KpiTile } from './tiles/KpiTile.jsx';
import { LineTile } from './tiles/LineTile.jsx';
import { DonutTile } from './tiles/DonutTile.jsx';
import { BarTile } from './tiles/BarTile.jsx';
import { TableTile } from './tiles/TableTile.jsx';

const RENDERERS = { kpi: KpiTile, line: LineTile, donut: DonutTile, bar: BarTile, table: TableTile };

export function DashboardReport({ T, report }) {
  const cfg = useMemo(() => { try { return JSON.parse(report.dashboard_config || '{}'); } catch { return {}; } }, [report.dashboard_config]);
  const tiles = useMemo(
    () => [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)),
    [report.tiles],
  );

  if (!tiles.length) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
        该仪表盘暂无板块 —— admin 点「编辑」添加。
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* 3 列基网格 + 每 tile grid_span(1/2/3) 占列（D4 order+span，手写 DnD 在 builder）*/}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14 }}>
        {tiles.map((tile) => {
          const Renderer = RENDERERS[tile.tile_type] || KpiTile;
          const span = Math.min(3, Math.max(1, tile.grid_span || 1));
          return (
            <div key={tile.id} style={{ gridColumn: `span ${span}`, minWidth: 0 }}>
              <Renderer T={T} tile={tile} />
            </div>
          );
        })}
      </div>
      <InsightCard T={T} text={cfg.insight} />
    </div>
  );
}
