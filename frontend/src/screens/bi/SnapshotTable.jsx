// SnapshotTable.jsx — v0.8.15 分享：宽表 / tabbed 当前页 离屏快照重建（截图源节点）。
// 复用 WideTable 渲染器（0 新视觉）；≤50 行（D3）；无滚动（maxHeight 极大 → 全内容全列铺开）。
// 数据抽取与 WideTableReport / TabbedTableReport 逐字对齐（同源渲染）。样式全内联（foreignObject 前提）。
import { WideTable } from './WideTable.jsx';
import { parseTile } from './tiles/tile_data.js';

const SNAP_MAX_ROWS = 50;   // D3：报表快照 ≤50 行

export function SnapshotTable({ T, report, activeTileId }) {
  let rows = [], cfg = {}, overlay = [];
  if (report.report_type === 'tabbed') {
    const tiles = [...(report.tiles || [])].sort((a, b) => (a.sort_order - b.sort_order) || (a.id - b.id));
    const tile = tiles.find((t) => t.id === activeTileId) || tiles[0];
    if (tile) {
      const { rows: r, viz } = parseTile(tile);   // 同 TabbedTableReport 抽取
      rows = r || [];
      cfg = viz.columns || {};
      overlay = viz.overlay || [];
    }
  } else {   // wide_table（同 WideTableReport 抽取）
    try { rows = JSON.parse(report.last_run_rows_json || '[]'); } catch { /* [] */ }
    try { cfg = report.column_config ? JSON.parse(report.column_config) : {}; } catch { /* {} */ }
    try { overlay = report.overlay_config ? JSON.parse(report.overlay_config) : []; } catch { /* [] */ }
  }
  const capped = rows.slice(0, SNAP_MAX_ROWS);
  return (
    <div style={{ background: T.bg, padding: 20, boxSizing: 'border-box', fontFamily: T.sans, display: 'inline-block' }}>
      {/* #MEDIUM：显示截 SNAP_MAX_ROWS 行，但覆盖层合计（=SUM 全列等）走 computeRows=全量 rows
          → 与 live 表体口径一致，不会把 51..N 行当 0 少算，避免向群里播错误合计。 */}
      <WideTable T={T} rows={capped} computeRows={rows} cfg={cfg} overlay={overlay} maxHeight={99999} roundTop />
      {rows.length > SNAP_MAX_ROWS && (
        <div style={{ fontSize: 11, color: T.muted, marginTop: 8, fontFamily: T.sans }}>
          共 {rows.length} 行，图中显示前 {SNAP_MAX_ROWS} 行（合计按全量计）
        </div>
      )}
    </div>
  );
}
