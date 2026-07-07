// DashboardReport.jsx — v0.8.5 (②a) 仪表盘（overview_grid，handoff §4 忠实还原）。
// 4×KPI 卡 → 折线面积（Shared LineChart 复用）+ 环形图 → 横条榜 + 迷你表。数据来自 report.dashboard_config。
import { useMemo } from 'react';
import { LineChart, CHART_COLORS } from '../../Shared.jsx';
import { InsightCard } from './InsightCard.jsx';

const RED = 'oklch(66% 0.20 25)';

function Card({ T, title, children, style }) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 16, ...style }}>
      {title && <div style={{ fontSize: 13, fontWeight: 600, color: T.text, marginBottom: 12 }}>{title}</div>}
      {children}
    </div>
  );
}

// 环形图（2 段 · 中心大数）——自绘 SVG（stroke-dasharray donut）
function Donut({ T, slices, big, sub }) {
  const total = slices.reduce((s, x) => s + x.value, 0) || 1;
  const R = 52, C = 2 * Math.PI * R;
  const dashes = slices.map((s) => (s.value / total) * C);
  const offsets = dashes.map((_, i) => dashes.slice(0, i).reduce((a, b) => a + b, 0));  // 纯前缀和（无 render 内变量突变）
  return (
    <div style={{ position: 'relative', width: 140, height: 140, margin: '0 auto' }}>
      <svg width="140" height="140" viewBox="0 0 140 140">
        <g transform="translate(70 70) rotate(-90)">
          {slices.map((s, i) => (
            <circle key={i} r={R} cx="0" cy="0" fill="none" stroke={s.color || CHART_COLORS[i]} strokeWidth="16"
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

export function DashboardReport({ T, report }) {
  const cfg = useMemo(() => { try { return JSON.parse(report.dashboard_config || '{}'); } catch { return {}; } }, [report.dashboard_config]);
  const kpis = cfg.kpis || [];
  const vol = useMemo(() => cfg.vol || [], [cfg.vol]);
  const volData = useMemo(() => vol.map((v, i) => ({ d: String(i), [cfg.volTitle || '值']: v })), [vol, cfg.volTitle]);
  const bars = cfg.bars || [];
  const bmax = Math.max(1, ...bars.map((b) => b.value || 0));
  const donut = cfg.donut || [];
  const mini = cfg.miniRows || [];
  const miniCols = cfg.miniCols || ['时间', '品种', '方向', '名义', '状态'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* KPI 行 */}
      {kpis.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(158px, 1fr))', gap: 12 }}>
          {kpis.map((k, i) => (
            <div key={i} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '14px 16px' }}>
              <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>{k.label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 3 }}>
                <span style={{ fontSize: 26, fontWeight: 700, color: k.main ? T.accent : T.text, fontFamily: T.mono }}>{k.value}</span>
                {k.unit && <span style={{ fontSize: 13, color: T.muted }}>{k.unit}</span>}
              </div>
              {k.hint && <div style={{ fontSize: 11, color: T.muted, marginTop: 6 }}>{k.hint}</div>}
            </div>
          ))}
        </div>
      )}

      {/* 折线 + 环形（2 列 auto-fit）*/}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
        {vol.length > 0 && (
          <Card T={T} title={cfg.volTitle || '趋势'}>
            <LineChart data={volData} height={230} stroke={T.accent} />
          </Card>
        )}
        {donut.length > 0 && (
          <Card T={T} title={cfg.donutTitle || ''}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
              <Donut T={T} slices={donut} big={cfg.donutBig} sub={cfg.donutSub} />
              <div style={{ flex: 1 }}>
                {(cfg.donutLegend || donut).map((l, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: donut[i] && donut[i].color ? donut[i].color : CHART_COLORS[i] }} />
                    <span style={{ flex: 1, fontSize: 12.5, color: T.subtext }}>{l.name}</span>
                    <span style={{ fontSize: 12.5, color: T.text, fontFamily: T.mono }}>{l.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        )}
      </div>

      {/* 横条榜 + 迷你表 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
        {bars.length > 0 && (
          <Card T={T} title={cfg.barsTitle || ''}>
            {bars.map((b, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <span style={{ width: 72, fontSize: 12, color: T.subtext, flexShrink: 0 }}>{b.label}</span>
                <div style={{ flex: 1, height: 8, borderRadius: 5, background: T.chipBg, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: (b.value / bmax * 100).toFixed(1) + '%', borderRadius: 5, background: CHART_COLORS[i % CHART_COLORS.length] }} />
                </div>
                <span style={{ width: 64, textAlign: 'right', fontSize: 12, color: T.text, fontFamily: T.mono, flexShrink: 0 }}>{b.valueLabel}</span>
              </div>
            ))}
          </Card>
        )}
        {mini.length > 0 && (
          <Card T={T} title={cfg.miniTitle || ''} style={{ padding: 0, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: T.sans }}>
              <thead>
                <tr>{miniCols.map((c) => <th key={c} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 10.5, fontFamily: T.mono, color: T.muted, fontWeight: 500, letterSpacing: '0.03em', borderBottom: `1px solid ${T.border}` }}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {mini.map((r, i) => (
                  <tr key={i}>
                    <td style={{ padding: '8px 14px', fontSize: 12, fontFamily: T.mono, color: T.subtext, borderBottom: `1px solid ${T.borderSoft}` }}>{r.time}</td>
                    <td style={{ padding: '8px 14px', fontSize: 12, color: T.text, borderBottom: `1px solid ${T.borderSoft}` }}>{r.symbol}</td>
                    <td style={{ padding: '8px 14px', fontSize: 12, fontWeight: 600, color: r.side === '空' ? RED : T.success, borderBottom: `1px solid ${T.borderSoft}` }}>{r.side}</td>
                    <td style={{ padding: '8px 14px', fontSize: 12, fontFamily: T.mono, color: T.text, borderBottom: `1px solid ${T.borderSoft}` }}>{r.notional}</td>
                    <td style={{ padding: '8px 14px', fontSize: 12, color: T.muted, borderBottom: `1px solid ${T.borderSoft}` }}>{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>

      <InsightCard T={T} text={cfg.insight} />
    </div>
  );
}
