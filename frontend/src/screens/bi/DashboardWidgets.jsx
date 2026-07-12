// DashboardWidgets.jsx — v0.8.11 仪表盘可组合组件（基准 §5 + kk 迭代）。
// 6 类型 · 固定 w×h（同类尺寸一致；pair=3列/9）· 统一卡头（色点 + 标题 + 类型标签 + 6 点拖拽手柄）。
// kk 迭代：对比「可选 + 灵活」(compare none/dod/wow + agg latest/sum + window) · 趋势「有值」(y 轴刻度 +
//   最新值标) · 明细表「横向滚动」(全字段不截 + overflow-x)。每组件从 tile 冻结快照 + viz_config 渲染。
import { CHART_COLORS } from '../../Shared.jsx';
import { fmtBig, fmtValue } from '../chat/ResultBlock/fmt.js';
import { parseTile, orderedCols, sparkPath, WIDGET_META } from './tiles/tile_data.js';
import { Donut } from './tiles/_shared.jsx';

const RED = 'oklch(66% 0.20 25)';
const dotColor = (i) => CHART_COLORS[i % CHART_COLORS.length];   // 卡头色点（按序循环 8 色板）

// 升序日期序列 → 数值数组（stat/pair/trend 共用）
function seriesAsc(rows, dateCol, valueCol) {
  return [...rows]
    .sort((a, b) => String(a[dateCol]).localeCompare(String(b[dateCol])))
    .map((r) => Number(r[valueCol]))
    .filter((n) => Number.isFinite(n));
}
const sumOf = (arr) => arr.reduce((a, b) => a + b, 0);
function dateLabels(rows, dateCol) {
  return [...rows].sort((a, b) => String(a[dateCol]).localeCompare(String(b[dateCol]))).map((r) => String(r[dateCol]));
}

// ── 对比 + 聚合模型（kk 迭代）─────────────────────────────────────────────────────
// compare: none（不对比）| dod（环比上期＝末值 vs 前值）| wow（环比前 N 期＝近 N 求和 vs 前 N 求和）
// agg: latest（末值）| sum（近 window 求和）；window：wow / sum 的期数（默认 7）
function statOf(tile) {
  const { rows, viz } = parseTile(tile);
  const keys = rows.length ? Object.keys(rows[0]) : [];
  const dateCol = viz.dateCol || keys[0];
  const valueCol = viz.valueCol || keys.find((k) => k !== dateCol) || keys[0];
  const s = seriesAsc(rows, dateCol, valueCol);
  const win = Math.max(1, Number(viz.window) || 7);
  const compare = viz.compare || 'dod';
  const value = (viz.agg === 'sum') ? sumOf(s.slice(-win)) : (s.length ? s[s.length - 1] : null);
  let delta = null;
  let cmpLabel = null;
  if (compare === 'wow') {
    const cur = sumOf(s.slice(-win));
    const prev = sumOf(s.slice(-2 * win, -win));
    delta = prev ? (cur - prev) / Math.abs(prev) : null;
    cmpLabel = viz.compareLabel || `较前${win}日`;
  } else if (compare === 'dod') {
    const last = s.length ? s[s.length - 1] : null;
    const prev = s.length > 1 ? s[s.length - 2] : null;
    delta = (prev != null && prev !== 0) ? (last - prev) / Math.abs(prev) : null;
    cmpLabel = viz.compareLabel || '较昨日';
  }
  return { rows, viz, s, win, dateCol, value, delta, cmpLabel };
}
const deltaStr = (d) => (d == null ? '—' : `${d >= 0 ? '▲' : '▼'}${(Math.abs(d) * 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`);

// ── 统一卡头 + 外壳 ─────────────────────────────────────────────────────────────
export function WidgetCard({ T, title, kind, dot, children }) {
  return (
    <div style={{ width: '100%', height: '100%', background: T.content, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '11px 12px 8px 14px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <span style={{ width: 6, height: 6, borderRadius: 2, flexShrink: 0, background: dot }} />
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</span>
        {kind && <span style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, letterSpacing: '0.05em', flexShrink: 0 }}>{kind}</span>}
        <span style={{ display: 'inline-flex', color: T.muted, flexShrink: 0 }} title="拖拽排布">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3" /><circle cx="15" cy="6" r="1.3" /><circle cx="9" cy="12" r="1.3" /><circle cx="15" cy="12" r="1.3" /><circle cx="9" cy="18" r="1.3" /><circle cx="15" cy="18" r="1.3" /></svg>
        </span>
      </div>
      {children}
    </div>
  );
}

// 窄单值卡（147px）要容纳 大数 + 多字符 USDT badge → 统一 20（保行内一致，不逐卡跳字号）。
const valueStyle = (T, neg, main) => ({ fontSize: 20, fontWeight: 700, fontFamily: T.mono, letterSpacing: '-0.03em', whiteSpace: 'nowrap', color: neg ? RED : (main ? T.accent : T.text) });
const deltaStyle = (T, up) => ({ fontSize: 12.5, fontWeight: 600, color: up ? T.success : RED });

// 币种/货币标记（kk）：有 unit → unit；否则 money → USDT（crypto 平台一律 USDT，不用 ¥）；count/percentage → 无。
const unitMarker = (viz) => viz.unit || (viz.fmt === 'money' ? 'USDT' : '');
// 小字号带背景 badge，贴数值右侧（统一 USDT 呈现）
function UnitBadge({ T, children }) {
  if (!children) return null;
  return <span style={{ fontSize: 9, fontWeight: 600, fontFamily: T.mono, color: T.subtext, background: T.chipBg, border: `1px solid ${T.borderSoft}`, padding: '2px 4px', borderRadius: 5, lineHeight: 1, flexShrink: 0 }}>{children}</span>;
}

// 对比行（可选）：compare==='none' 时调用方不渲染本行 → 「对比可选」
function DeltaRow({ T, delta, cmpLabel }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={deltaStyle(T, (delta || 0) >= 0)}>{deltaStr(delta)}</span>
      {cmpLabel && <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{cmpLabel}</span>}
    </div>
  );
}

// 折线图（有值）：y 轴 max/mid/min 刻度（HTML，不随 SVG 拉伸）+ 最新值标 + 可选 x 轴日期。
function TrendChart({ T, series, dates, fmt, unit, compact }) {
  if (series.length < 2) return <div style={{ flex: 1, display: 'grid', placeItems: 'center', fontSize: 11, color: T.muted }}>数据不足</div>;
  const { line, area } = sparkPath(series, 1000, 300, 12);
  const max = Math.max(...series), min = Math.min(...series), last = series[series.length - 1];
  const c = T.accent;   // kk：取消负值红趋势 → 一律 accent
  const yLab = { fontSize: 9, color: T.chartLabel || T.muted, fontFamily: T.mono, whiteSpace: 'nowrap' };
  const ticks = (dates && dates.length) ? [0, 1, 2, 3].map((k) => dates[Math.round((k / 3) * (dates.length - 1))]) : [];
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 6 }}>
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-end', flexShrink: 0, padding: '1px 0' }}>
          <span style={yLab}>{fmtBig(max, fmt, unit)}</span>
          {!compact && <span style={yLab}>{fmtBig((max + min) / 2, fmt, unit)}</span>}
          <span style={yLab}>{fmtBig(min, fmt, unit)}</span>
        </div>
        <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
          <svg viewBox="0 0 1000 300" preserveAspectRatio="none" style={{ width: '100%', height: '100%', display: 'block' }}>
            {[60, 150, 240].map((y) => <line key={y} x1="0" y1={y} x2="1000" y2={y} style={{ stroke: T.chartGrid || T.border, strokeWidth: 1, strokeDasharray: '4 5', vectorEffect: 'non-scaling-stroke' }} />)}
            <path d={area} style={{ fill: `color-mix(in oklch, ${c} 13%, transparent)`, stroke: 'none' }} />
            <path d={line} style={{ fill: 'none', stroke: c, strokeWidth: 2, vectorEffect: 'non-scaling-stroke', strokeLinejoin: 'round', strokeLinecap: 'round' }} />
          </svg>
          <div style={{ position: 'absolute', top: 1, right: 2, fontSize: 9.5, fontFamily: T.mono, color: c, background: `color-mix(in oklch, ${T.content} 82%, transparent)`, padding: '1px 5px', borderRadius: 5 }}>最新 {fmtBig(last, fmt, unit)}</div>
        </div>
      </div>
      {ticks.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5, color: T.chartLabel || T.muted, fontFamily: T.mono, padding: '7px 0 0', marginLeft: 34 }}>
          {ticks.map((t, i) => <span key={i}>{t}</span>)}
        </div>
      )}
    </div>
  );
}

// ── 6 body ─────────────────────────────────────────────────────────────────────
function StatBody({ T, tile }) {
  const { viz, value, delta, cmpLabel } = statOf(tile);
  const showCmp = (viz.compare || 'dod') !== 'none';
  const marker = unitMarker(viz);
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 12px 12px', gap: 9 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={valueStyle(T, value < 0, viz.main)}>{fmtBig(value, viz.fmt, viz.unit, true)}</span>
        <UnitBadge T={T}>{marker}</UnitBadge>
      </div>
      {showCmp && <DeltaRow T={T} delta={delta} cmpLabel={cmpLabel} />}
    </div>
  );
}
function PairBody({ T, tile }) {
  const { viz, s, win, value, delta, cmpLabel, rows, dateCol } = statOf(tile);
  const showCmp = (viz.compare || 'dod') !== 'none';
  const trendSeries = viz.agg === 'sum' ? s.slice(-win) : s;   // 求和型只画近 window（对齐「近7日」语义）
  const trendDates = dateLabels(rows, dateCol).slice(-trendSeries.length);
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'stretch' }}>
      <div style={{ flex: '0 0 32%', minWidth: 120, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 14px 12px', gap: 7, borderRight: `1px solid ${T.borderSoft}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={valueStyle(T, value < 0, viz.main)}>{fmtBig(value, viz.fmt, viz.unit, true)}</span>
          <UnitBadge T={T}>{unitMarker(viz)}</UnitBadge>
        </div>
        {showCmp && <DeltaRow T={T} delta={delta} cmpLabel={cmpLabel} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, padding: '10px 12px 8px' }}>
        <TrendChart T={T} series={trendSeries} dates={trendDates} fmt={viz.fmt} unit={viz.unit} compact />
      </div>
    </div>
  );
}
function TrendBody({ T, tile }) {
  const { s, rows, dateCol, viz } = statOf(tile);
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '6px 12px 8px' }}>
      <TrendChart T={T} series={s} dates={dateLabels(rows, dateCol)} fmt={viz.fmt} unit={viz.unit} />
    </div>
  );
}
function labelValueRows(tile) {
  const { rows, viz } = parseTile(tile);
  const keys = rows.length ? Object.keys(rows[0]) : [];
  const labelCol = viz.labelCol || keys[0];
  const valueCol = viz.valueCol || keys.find((k) => typeof rows[0]?.[k] === 'number') || keys[1] || keys[0];
  return { rows, viz, labelCol, valueCol };
}
function DonutBody({ T, tile }) {
  const { rows, viz, labelCol, valueCol } = labelValueRows(tile);
  const slices = rows.map((r) => ({ name: String(r[labelCol]), value: Number(r[valueCol]) || 0 }));
  const total = slices.reduce((a, x) => a + x.value, 0);
  const big = viz.big || (slices[0] && total ? `${Math.round((slices[0].value / total) * 100)}%` : '');
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', gap: 16, padding: '8px 16px 16px' }}>
      <Donut T={T} slices={slices} big={big} sub={viz.sub || slices[0]?.name} />
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 11 }}>
        {slices.map((x, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <span style={{ width: 9, height: 9, borderRadius: 3, flexShrink: 0, background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{x.name}</span>
            <span style={{ fontSize: 12, color: T.subtext, fontFamily: T.mono }}>{fmtBig(x.value, viz.fmt, viz.unit)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
function BarsBody({ T, tile }) {
  const { rows, viz, labelCol, valueCol } = labelValueRows(tile);
  const bars = rows.map((r) => ({ label: String(r[labelCol]), value: Number(r[valueCol]) || 0 }));
  const max = Math.max(1, ...bars.map((b) => Math.abs(b.value)));
  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 13, padding: '8px 16px 14px' }}>
      {bars.map((b, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ width: 70, flexShrink: 0, fontSize: 12, color: T.subtext, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.label}</span>
          <div style={{ flex: 1, height: 9, borderRadius: 5, background: T.borderSoft, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${(Math.abs(b.value) / max * 100).toFixed(1)}%`, borderRadius: 5, background: CHART_COLORS[i % CHART_COLORS.length] }} />
          </div>
          <span style={{ width: 62, flexShrink: 0, textAlign: 'right', fontSize: 12, color: T.text, fontFamily: T.mono }}>{fmtBig(b.value, viz.fmt, viz.unit)}</span>
        </div>
      ))}
    </div>
  );
}
// 明细表：全字段（不截）+ 横向滚动（kk：多字段超布局 → 手滑）。列 min-width → 总宽超卡触发 overflow-x。
function TableBody({ T, tile }) {
  const { rows, viz } = parseTile(tile);
  const cfg = viz.columns || {};
  const cols = orderedCols(rows, cfg);
  const label = (c) => (cfg[c] && cfg[c].label) || c;
  const gt = cols.map((_, i) => (i === 0 ? '120px' : 'minmax(92px, 1fr)')).join(' ');
  const minW = 120 + Math.max(0, cols.length - 1) * 92;   // 总最小宽 → 超卡宽即横向滚
  const cell = (i) => ({ textAlign: i === 0 ? 'left' : 'right', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' });
  return (
    <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
      <div style={{ minWidth: minW }}>
        <div style={{ display: 'grid', gridTemplateColumns: gt, padding: '7px 16px', background: T.bg, borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}`, fontSize: 10, color: T.muted, fontFamily: T.mono, letterSpacing: '0.04em', position: 'sticky', top: 0 }}>
          {cols.map((c, i) => <span key={c} style={cell(i)}>{label(c)}</span>)}
        </div>
        {rows.map((r, ri) => (
          <div key={ri} style={{ display: 'grid', gridTemplateColumns: gt, padding: '8px 16px', borderBottom: `1px solid ${T.borderSoft}`, fontSize: 12, alignItems: 'center' }}>
            {cols.map((c, i) => <span key={c} style={{ ...cell(i), color: i === 0 ? T.muted : T.text, fontFamily: T.mono }}>{fmtValue(r[c], cfg[c] && cfg[c].unit)}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}

const BODIES = { stat: StatBody, pair: PairBody, trend: TrendBody, donut: DonutBody, bars: BarsBody, table: TableBody };

export function DashboardWidget({ T, tile, index }) {
  const meta = WIDGET_META[tile.tile_type] || WIDGET_META.stat;
  const Body = BODIES[tile.tile_type] || StatBody;
  const { error } = parseTile(tile);
  return (
    <WidgetCard T={T} title={tile.title} kind={meta.w >= 6 ? meta.kind : null} dot={dotColor(index)}>
      {error
        ? <div style={{ flex: 1, display: 'grid', placeItems: 'center', fontSize: 12, color: RED, padding: 12 }}>⚠ {error}</div>
        : <Body T={T} tile={tile} />}
    </WidgetCard>
  );
}
