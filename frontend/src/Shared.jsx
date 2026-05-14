import { useRef, useEffect } from 'react';
import * as echarts from 'echarts';

export const I = {
  plus:    (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><path d="M12 5v14M5 12h14"/></svg>,
  search:  (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>,
  history: (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/></svg>,
  db:      (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>,
  gear:    (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
  send:    (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M5 12h14M13 6l6 6-6 6"/></svg>,
  users:   (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
  key:     (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="8" cy="15" r="4"/><path d="M10.85 12.15 19 4"/><path d="m18 5 3 3"/><path d="m15 8 3 3"/></svg>,
  plug:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 1 1-12 0z"/><path d="M12 18v4"/></svg>,
  chart:   (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 20h18"/><path d="m4 16 5-6 4 3 7-8"/></svg>,
  sql:     (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m8 6-6 6 6 6"/><path d="m16 6 6 6-6 6"/></svg>,
  copy:    (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>,
  dl:      (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>,
  refresh: (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>,
  more:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none" {...p}><circle cx="6" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18" cy="12" r="1.4"/></svg>,
  chev:    (p={}) => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m6 9 6 6 6-6"/></svg>,
  sun:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>,
  moon:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>,
  collapse:(p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg>,
  check:   (p={}) => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><polyline points="4 12 10 18 20 6"/></svg>,
  x:       (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><path d="M18 6 6 18M6 6l12 12"/></svg>,
  pencil:  (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>,
  trash:   (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>,
  logout:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg>,
  eye:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  eyeoff:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><path d="m1 1 22 22"/></svg>,
  wifi:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r=".8" fill="currentColor"/></svg>,
  zap:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>,
  sparkle: (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z"/></svg>,
  lock:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  user:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
  shield:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  robot:   (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M12 2v4M8 11V9a4 4 0 0 1 8 0v2"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/></svg>,
  clip:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>,
  file:    (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>,
  book:    (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>,
  // v0.6.0.3 F-A 用户反馈（M-A1 Shared 优先 / M-A2 Feather byte-equal）
  thumbsUp:   (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>,
  thumbsDown: (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zM17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>,
};

export function buildTheme(dark) {
  // v0.5.6 Claude Design — OKLCH 设计 tokens
  // brand: electric cyan 195°（signal, insight, decision）；R-167 语义色远离 brand
  const brand = dark ? 'oklch(72% 0.17 195)' : 'oklch(58% 0.17 195)';  // brand[400] / brand[600]
  return {
    dark,
    bg:          dark ? '#080a0e' : '#fafbfc',                            // ink[950] / ink[25]
    content:     dark ? '#11151b' : '#ffffff',                            // ink[900] / ink[0]
    sidebar:     dark ? '#11151b' : '#f5f7f9',                            // ink[900] / ink[50]
    border:      dark ? 'rgba(255,255,255,0.08)' : '#dde2e8',             // ink[200]
    borderSoft:  dark ? 'rgba(255,255,255,0.05)' : '#eef1f4',             // ink[100]
    text:        dark ? '#e8edf3' : '#11151b',                            // ink[900]
    subtext:     dark ? '#8c97a4' : '#475260',                            // ink[600]
    muted:       dark ? '#5d6773' : '#6b7684',                            // ink[500]
    accent:      brand,
    accentSoft:  dark ? 'oklch(66% 0.18 195 / 0.14)' : 'oklch(97% 0.02 195)',  // brand[50]
    success:     'oklch(72% 0.18 145)',                                   // R-167 翠绿 145°
    successSoft: dark ? 'oklch(72% 0.18 145 / 0.16)' : 'oklch(72% 0.18 145 / 0.10)',
    warn:        'oklch(82% 0.16 85)',                                    // R-167 琥珀 85°
    hover:       dark ? 'rgba(255,255,255,0.04)' : '#eef1f4',             // ink[100]
    card:        dark ? '#11151b' : '#ffffff',
    codeBg:      dark ? '#1c2129' : '#f5f7f9',                            // ink[800] / ink[50]
    codeText:    dark ? '#e8edf3' : '#11151b',
    inputBg:     dark ? '#11151b' : '#ffffff',
    inputBorder: dark ? 'rgba(255,255,255,0.10)' : '#dde2e8',
    chipBg:      dark ? '#1c2129' : '#f5f7f9',                            // ink[800] / ink[50]
    chipBorder:  dark ? 'rgba(255,255,255,0.08)' : '#dde2e8',
    sendBg:      brand,
    sendFg:      dark ? '#080a0e' : '#ffffff',                            // ink[950] / white
    sans:        '"HarmonyOS Sans SC", "PingFang SC", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
    mono:        '"JetBrains Mono", "Geist Mono", "SF Mono", ui-monospace, Menlo, monospace',
  };
}

export const iconBtn = (T) => ({
  width: 28, height: 28, display: 'inline-grid', placeItems: 'center',
  background: 'transparent', border: 'none', borderRadius: 8,
  color: T.subtext, cursor: 'pointer',
  transition: 'background 0.15s, color 0.15s',
});

export const pillBtn = (T, primary = false) => ({
  display: 'inline-flex', alignItems: 'center', gap: 6,
  padding: '6px 11px', borderRadius: 8, fontSize: 12.5,
  background: primary ? T.accent : 'transparent',
  color: primary ? T.sendFg : T.subtext,
  border: primary ? 'none' : `1px solid ${T.border}`,
  fontFamily: 'inherit', cursor: 'pointer', fontWeight: 500,
  letterSpacing: '-0.005em',
  transition: 'opacity 0.15s, transform 0.05s',
  whiteSpace: 'nowrap',
});

// v0.5.6 R-169 — hue 45° 均匀分布；lightness 65~70% / chroma 0.16~0.20
export const CHART_COLORS = [
  'oklch(65% 0.18 195)',  // brand cyan 195°
  'oklch(65% 0.18 240)',  // azure 240°
  'oklch(65% 0.18 285)',  // violet 285°
  'oklch(65% 0.18 330)',  // magenta 330°
  'oklch(65% 0.18 15)',   // red 15°
  'oklch(70% 0.16 60)',   // amber 60°
  'oklch(70% 0.18 105)',  // lime 105°
  'oklch(65% 0.18 150)',  // emerald 150°
];

const EC_TOOLTIP = {
  backgroundColor: 'rgba(20,25,35,0.92)',
  borderColor: 'rgba(255,255,255,0.1)',
  textStyle: { color: '#e0e0e0', fontSize: 12 },
  confine: true,
};

const fmtNum = v =>
  Math.abs(v) >= 1e8 ? `${(v/1e8).toFixed(1)}亿` :
  Math.abs(v) >= 1e4 ? `${(v/1e4).toFixed(0)}万` :
  Math.abs(v) >= 1e3 ? `${(v/1e3).toFixed(0)}K` :
  typeof v === 'number' ? v.toLocaleString() : v;

export function LineChart({ data, height = 220, stroke = 'oklch(58% 0.17 195)', colors = CHART_COLORS,
                           fill = true, labelColor = '#8a8d93', gridColor = 'rgba(0,0,0,0.06)' }) {
  const elRef = useRef(null);
  const ec    = useRef(null);

  useEffect(() => {
    ec.current = echarts.init(elRef.current, null, { renderer: 'svg' });
    return () => { ec.current.dispose(); ec.current = null; };
  }, []);

  useEffect(() => {
    if (!ec.current || !data || data.length < 2) return;
    const keys  = Object.keys(data[0]);
    const xKey  = keys[0];
    const yKeys = keys.slice(1).filter(k => data.some(d => typeof d[k] === 'number'));
    if (!yKeys.length) return;
    const multi = yKeys.length > 1;

    ec.current.setOption({
      backgroundColor: 'transparent',
      grid: { top: multi ? 36 : 12, right: 12, bottom: 28, left: 16, containLabel: true },
      tooltip: { ...EC_TOOLTIP, trigger: 'axis',
        formatter: ps => ps.map(p => `${p.marker}${p.seriesName}: <b>${fmtNum(p.value)}</b>`).join('<br/>') },
      legend: multi ? { top: 4, textStyle: { color: labelColor, fontSize: 11 }, itemWidth: 12, itemHeight: 8 } : { show: false },
      xAxis: {
        type: 'category',
        data: data.map(d => String(d[xKey])),
        boundaryGap: false,
        axisLabel: { color: labelColor, fontSize: 10, hideOverlap: true },
        axisLine: { lineStyle: { color: gridColor } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: labelColor, fontSize: 10, formatter: fmtNum },
        splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      series: yKeys.map((k, i) => {
        const c = multi ? colors[i % colors.length] : stroke;
        return {
          name: k, type: 'line',
          data: data.map(d => d[k] == null ? null : Number(d[k])),
          smooth: 0.3,
          lineStyle: { color: c, width: 2 },
          itemStyle: { color: c },
          symbol: 'circle', symbolSize: 5, showSymbol: false,
          emphasis: { focus: 'series' },
          areaStyle: (fill && i === 0) ? { opacity: 0.12, color: c } : null,
        };
      }),
    }, true);
  }, [data, stroke, fill, labelColor, gridColor]);

  return <div ref={elRef} style={{ width: '100%', height }} />;
}

export function BarChart({ data, height = 220, color = 'oklch(58% 0.17 195)', colors = CHART_COLORS,
                          labelColor = '#8a8d93', gridColor = 'rgba(0,0,0,0.06)' }) {
  const elRef = useRef(null);
  const ec    = useRef(null);

  useEffect(() => {
    ec.current = echarts.init(elRef.current, null, { renderer: 'svg' });
    return () => { ec.current.dispose(); ec.current = null; };
  }, []);

  useEffect(() => {
    if (!ec.current || !data || !data.length) return;
    const keys  = Object.keys(data[0]);
    const xKey  = keys[0];
    const yKeys = keys.slice(1).filter(k => data.some(d => typeof d[k] === 'number'));
    if (!yKeys.length) return;
    const multi = yKeys.length > 1;

    ec.current.setOption({
      backgroundColor: 'transparent',
      grid: { top: multi ? 36 : 12, right: 12, bottom: 48, left: 16, containLabel: true },
      tooltip: { ...EC_TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: ps => ps.map(p => `${p.marker}${p.seriesName}: <b>${fmtNum(p.value)}</b>`).join('<br/>') },
      legend: multi ? { top: 4, textStyle: { color: labelColor, fontSize: 11 }, itemWidth: 12, itemHeight: 8 } : { show: false },
      xAxis: {
        type: 'category',
        data: data.map(d => String(d[xKey])),
        axisLabel: { color: labelColor, fontSize: 10, interval: 0, rotate: data.length > 8 ? 35 : 0 },
        axisLine: { lineStyle: { color: gridColor } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: labelColor, fontSize: 10, formatter: fmtNum },
        splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      series: yKeys.map((k, i) => ({
        name: k, type: 'bar',
        data: data.map(d => d[k] == null ? null : Number(d[k])),
        itemStyle: { color: multi ? colors[i % colors.length] : color, borderRadius: [2, 2, 0, 0], opacity: 0.88 },
        emphasis: { focus: 'series', itemStyle: { opacity: 1 } },
        barMaxWidth: 40,
      })),
    }, true);
  }, [data, color, labelColor, gridColor]);

  return <div ref={elRef} style={{ width: '100%', height }} />;
}

export function PieChart({ data, height = 220, colors = CHART_COLORS, labelColor = '#8a8d93' }) {
  const elRef = useRef(null);
  const ec    = useRef(null);

  useEffect(() => {
    ec.current = echarts.init(elRef.current, null, { renderer: 'svg' });
    return () => { ec.current.dispose(); ec.current = null; };
  }, []);

  useEffect(() => {
    if (!ec.current || !data || !data.length) return;
    const keys = Object.keys(data[0]);
    const labelKey = keys[0], valKey = keys[1];

    const sorted = [...data].sort((a, b) => (Number(b[valKey])||0) - (Number(a[valKey])||0));
    const top  = sorted.slice(0, 7);
    const rest = sorted.slice(7);
    const items = rest.length
      ? [...top, { [labelKey]: '其他', [valKey]: rest.reduce((s, d) => s + (Number(d[valKey])||0), 0) }]
      : top;

    ec.current.setOption({
      backgroundColor: 'transparent',
      tooltip: { ...EC_TOOLTIP, trigger: 'item',
        formatter: p => `${p.marker}${p.name}: <b>${fmtNum(p.value)}</b> (${p.percent}%)` },
      legend: {
        orient: 'vertical', right: 8, top: 'middle',
        textStyle: { color: labelColor, fontSize: 11 },
        icon: 'roundRect', itemWidth: 9, itemHeight: 9,
        formatter: n => n.length > 12 ? n.slice(0, 12) + '…' : n,
      },
      series: [{
        type: 'pie',
        center: ['35%', '50%'],
        radius: ['42%', '68%'],
        data: items.map((d, i) => ({
          name: String(d[labelKey]),
          value: Number(d[valKey]) || 0,
          itemStyle: { color: colors[i % colors.length], opacity: 0.9 },
        })),
        label: { show: false },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.3)' }, focus: 'self' },
      }],
    }, true);
  }, [data, labelColor]);

  return <div ref={elRef} style={{ width: '100%', height }} />;
}

export function TypingDots({ color = 'oklch(58% 0.17 195)' }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
      {[0,1,2].map(i => <span key={i} style={{
        width: 5, height: 5, borderRadius: '50%', background: color,
        animation: `cb-pulse 1.2s ${i*0.16}s infinite ease-in-out`,
      }}/>)}
    </span>
  );
}

/* ─── KNOT Logo lockup (v0.5.7 R-174 +3 exports / R-183 size props / Q2 viewBox 100×100 / Q4 T.dark) ─── */

// Atom mark: 3 elliptical orbits + central nucleus. fg derived from T.dark (no theme string).
export function KnotMark({ T, size = 32 }) {
  const fg = T.dark ? '#f4f6f8' : '#0d1014';
  const sw = size <= 16 ? 6 : 4.5;
  const r  = size <= 16 ? 11 : 9;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100"
         xmlns="http://www.w3.org/2000/svg"
         style={{ display: 'block', flexShrink: 0 }}>
      {[0, 60, -60].map(angle => (
        <ellipse key={angle} cx="50" cy="50" rx="42" ry="14"
                 transform={`rotate(${angle} 50 50)`}
                 fill="none" stroke={fg} strokeWidth={sw}/>
      ))}
      <circle cx="50" cy="50" r={r} fill={fg}/>
    </svg>
  );
}

// "KNOT" wordmark — Inter Black, tight tracking, no dot.
export function KnotWordmark({ T, size = 24 }) {
  const fg = T.dark ? '#f4f6f8' : '#0d1014';
  const w = size * (240 / 80);
  return (
    <svg width={w} height={size} viewBox="0 0 240 80"
         xmlns="http://www.w3.org/2000/svg"
         style={{ display: 'block', flexShrink: 0 }}>
      <text x="0" y="64"
            fontFamily='"Inter", "Geist", system-ui, -apple-system, sans-serif'
            fontWeight="900" fontSize="72"
            fill={fg} letterSpacing="-3.5">KNOT</text>
    </svg>
  );
}

// Default brand logo = horizontal lockup (Atom + KNOT). `size` = total mark height.
export function KnotLogo({ T, size = 32 }) {
  const wordHeight = Math.round(size * 0.62);
  const gap = Math.max(4, Math.round(size * 0.32));
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap,
      lineHeight: 0,
    }}>
      <KnotMark T={T} size={size}/>
      <KnotWordmark T={T} size={wordHeight}/>
    </div>
  );
}

// Inject global CSS animations + scrollbar styles
(function injectStyles() {
  if (document.getElementById('cb-styles')) return;
  const s = document.createElement('style');
  s.id = 'cb-styles';
  s.textContent = `
    @keyframes cb-pulse { 0%,80%,100%{opacity:.25;transform:scale(.8)}40%{opacity:1;transform:scale(1)} }
    @keyframes cb-caret { 0%,100%{opacity:1}50%{opacity:0} }
    @keyframes cb-fadein { from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none} }
    @keyframes cb-spin   { to{transform:rotate(360deg)} }
    .cb-fadein { animation: cb-fadein .35s ease both; }
    .cb-sb::-webkit-scrollbar { width:6px;height:6px }
    .cb-sb::-webkit-scrollbar-thumb { background:rgba(0,0,0,0.1);border-radius:3px }
    .cb-sb { scrollbar-width:thin;scrollbar-color:rgba(0,0,0,0.12) transparent }
    .cb-grid-bg {
      background-image:
        linear-gradient(oklch(58% 0.17 195 / 0.03) 1px,transparent 1px),
        linear-gradient(90deg,oklch(58% 0.17 195 / 0.03) 1px,transparent 1px);
      background-size:24px 24px;
    }
    input,select,textarea { font-family:inherit; }
    button:focus-visible { outline:2px solid oklch(58% 0.17 195); outline-offset:2px; }
  `;
  document.head.appendChild(s);
})();
