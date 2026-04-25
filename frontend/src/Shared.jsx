import { useRef, useEffect } from 'react';
import * as echarts from 'echarts';

export const I = {
  plus:    (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><path d="M12 5v14M5 12h14"/></svg>,
  search:  (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>,
  history: (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/></svg>,
  db:      (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>,
  gear:    (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
  send:    (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 19V5"/><path d="m5 12 7-7 7 7"/></svg>,
  users:   (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
  key:     (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="8" cy="15" r="4"/><path d="M10.85 12.15 19 4"/><path d="m18 5 3 3"/><path d="m15 8 3 3"/></svg>,
  plug:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 1 1-12 0z"/><path d="M12 18v4"/></svg>,
  chart:   (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 20h18"/><path d="m4 16 5-6 4 3 7-8"/></svg>,
  sql:     (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m8 6-6 6 6 6"/><path d="m16 6 6 6-6 6"/></svg>,
  copy:    (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>,
  dl:      (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>,
  refresh: (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></svg>,
  more:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" {...p}><circle cx="6" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="18" cy="12" r="1.4"/></svg>,
  chev:    (p={}) => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m6 9 6 6 6-6"/></svg>,
  sun:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>,
  moon:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>,
  collapse:(p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg>,
  check:   (p={}) => <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M20 6 9 17l-5-5"/></svg>,
  x:       (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><path d="M18 6 6 18M6 6l12 12"/></svg>,
  pencil:  (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>,
  trash:   (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="m19 6-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>,
  logout:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/></svg>,
  eye:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  eyeoff:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><path d="m1 1 22 22"/></svg>,
  wifi:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r=".8" fill="currentColor"/></svg>,
  zap:     (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>,
  sparkle: (p={}) => <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" {...p}><path d="M12 2l1.7 5.8L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-2.2z"/></svg>,
  lock:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  user:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
  shield:  (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  robot:   (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M12 2v4M8 11V9a4 4 0 0 1 8 0v2"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/></svg>,
  clip:    (p={}) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>,
  file:    (p={}) => <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>,
  book:    (p={}) => <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>,
};

export function buildTheme(dark) {
  return {
    dark,
    bg:          dark ? '#0E1117' : '#F5F5F4',
    content:     dark ? '#131720' : '#FFFFFF',
    sidebar:     dark ? '#0A0D12' : '#F0F2F6',
    border:      dark ? 'rgba(255,255,255,0.08)' : 'rgba(49,51,63,0.12)',
    borderSoft:  dark ? 'rgba(255,255,255,0.05)' : 'rgba(49,51,63,0.06)',
    text:        dark ? '#FAFAFA' : '#31333E',
    subtext:     dark ? '#C9CCD3' : '#4E5058',
    muted:       dark ? '#7E848F' : '#8A8D94',
    accent:      '#FF4B4B',
    accentSoft:  dark ? 'rgba(255,75,75,0.14)' : 'rgba(255,75,75,0.10)',
    success:     '#09AB3B',
    successSoft: dark ? 'rgba(9,171,59,0.14)' : 'rgba(9,171,59,0.10)',
    warn:        '#FFA421',
    hover:       dark ? 'rgba(255,255,255,0.04)' : 'rgba(49,51,63,0.04)',
    card:        dark ? '#1A1F29' : '#FFFFFF',
    codeBg:      dark ? '#0A0D12' : '#F7F7F7',
    codeText:    dark ? '#E6E6E6' : '#31333E',
    inputBg:     dark ? '#1A1F29' : '#FFFFFF',
    inputBorder: dark ? 'rgba(255,255,255,0.1)' : 'rgba(49,51,63,0.18)',
    chipBg:      dark ? '#1A1F29' : '#F0F2F6',
    chipBorder:  dark ? 'rgba(255,255,255,0.08)' : 'rgba(49,51,63,0.08)',
    sendBg:      '#FF4B4B',
    sendFg:      '#FFFFFF',
    sans:        `'Inter', 'Noto Sans SC', system-ui, sans-serif`,
    mono:        `'JetBrains Mono', ui-monospace, monospace`,
  };
}

export const iconBtn = (T) => ({
  width: 28, height: 28, display: 'inline-grid', placeItems: 'center',
  background: 'transparent', border: 'none', borderRadius: 6,
  color: T.subtext, cursor: 'pointer',
});

export const pillBtn = (T, primary = false) => ({
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '6px 11px', borderRadius: 6, fontSize: 12.5,
  background: primary ? T.accent : 'transparent',
  color: primary ? '#fff' : T.subtext,
  border: primary ? 'none' : `1px solid ${T.border}`,
  fontFamily: 'inherit', cursor: 'pointer', fontWeight: 500,
});

export const CHART_COLORS = ['#FF4B4B','#3B82F6','#10B981','#F59E0B','#8B5CF6','#EC4899','#06B6D4','#84CC16'];

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

export function LineChart({ data, height = 220, stroke = '#FF4B4B', colors = CHART_COLORS,
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

export function BarChart({ data, height = 220, color = '#FF4B4B', colors = CHART_COLORS,
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

export function TypingDots({ color = '#FF4B4B' }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
      {[0,1,2].map(i => <span key={i} style={{
        width: 5, height: 5, borderRadius: '50%', background: color,
        animation: `cb-pulse 1.2s ${i*0.16}s infinite ease-in-out`,
      }}/>)}
    </span>
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
        linear-gradient(rgba(255,75,75,0.03) 1px,transparent 1px),
        linear-gradient(90deg,rgba(255,75,75,0.03) 1px,transparent 1px);
      background-size:24px 24px;
    }
    input,select,textarea { font-family:inherit; }
    button:focus-visible { outline:2px solid #FF4B4B; outline-offset:2px; }
  `;
  document.head.appendChild(s);
})();
