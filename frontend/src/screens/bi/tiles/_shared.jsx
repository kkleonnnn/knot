// _shared.jsx — v0.8.6 (②b) tile 渲染共享件。
// B-4：Card / Donut 原为 DashboardReport.jsx 文件内私有；拆 tile 组件后移到此处共享
// （R-BI-1 禁改 Shared.jsx → 落 bi/tiles 内共享，不进 Foundation）。
import { CHART_COLORS } from '../../../Shared.jsx';

export function Card({ T, title, children, style }) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16, ...style }}>
      {title && <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 12 }}>{title}</div>}
      {children}
    </div>
  );
}

// 环形图（2+ 段 · 中心大数）——自绘 SVG（stroke-dasharray donut，纯前缀和偏移）
export function Donut({ T, slices, big, sub }) {
  const total = slices.reduce((s, x) => s + (Number(x.value) || 0), 0) || 1;
  const R = 52, C = 2 * Math.PI * R;
  const dashes = slices.map((s) => ((Number(s.value) || 0) / total) * C);
  const offsets = dashes.map((_, i) => dashes.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <div style={{ position: 'relative', width: 140, height: 140, margin: '0 auto' }}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <g transform="translate(70 70) rotate(-90)">
          {slices.map((s, i) => (
            <circle key={i} r={R} cx="0" cy="0" fill="none" stroke={s.color || CHART_COLORS[i % CHART_COLORS.length]} strokeWidth="16"
              strokeDasharray={`${dashes[i]} ${C - dashes[i]}`} strokeDashoffset={-offsets[i]} />
          ))}
        </g>
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
        <div>
          <div style={{ fontSize: 24, fontWeight: 700, color: T.text }}>{big}</div>
          <div style={{ fontSize: 11, color: T.muted }}>{sub}</div>
        </div>
      </div>
    </div>
  );
}

// tile 空态/错误壳（per-tile error 隔离展示：一 tile 挂不连累其余）
export function TileState({ T, error }) {
  return (
    <div style={{ padding: '20px 8px', textAlign: 'center', fontSize: 12, color: error ? 'oklch(66% 0.20 25)' : T.muted }}>
      {error ? `⚠ ${error}` : '暂无数据 —— 点「重跑」拉取（admin）'}
    </div>
  );
}
