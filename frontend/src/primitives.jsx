// v0.6.4.0 UI v2 — 新组件原语 Btn / Tag（资深拍 B 拆独立文件；守护者 §9.2 映射表为唯一可审契约）。
// 结构色自 T（prop）+ semantic/brand 阶自模块引 TOKENS_V2（不穿 prop）。
// dumb presentational：无硬编 margin（间距由宿主 gap 决定 — Stage 2 Q3）。
import { TOKENS_V2 } from './Shared.jsx';

// === Btn 5-variant × 3-size ===
// sizes / radius 8 / fontWeight 500 / translateY 0.5px press（demo ui.jsx byte-equal 等价）
const _BTN_SIZES = {
  sm: { h: 28, px: 10, fs: 12, gap: 6 },
  md: { h: 34, px: 14, fs: 13, gap: 8 },
  lg: { h: 40, px: 18, fs: 14, gap: 8 },
};

export function Btn({ T, variant = 'default', size = 'md', icon, iconRight, onClick, style, children }) {
  const s = _BTN_SIZES[size] || _BTN_SIZES.md;
  const variants = {
    default: { bg: T.content,    fg: T.text,     border: T.border },
    primary: { bg: T.accent,     fg: T.sendFg,   border: T.accent },
    ghost:   { bg: 'transparent', fg: T.text,    border: 'transparent' },
    soft:    { bg: T.accentSoft, fg: T.accent,   border: TOKENS_V2.brand[200] },
    danger:  { bg: 'transparent', fg: TOKENS_V2.err, border: T.border },
  };
  const v = variants[variant] || variants.default;
  return (
    <button
      onClick={onClick}
      onMouseDown={(e) => { e.currentTarget.style.transform = 'translateY(0.5px)'; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
      style={{
        height: s.h, padding: `0 ${s.px}px`, fontSize: s.fs, fontWeight: 500,
        background: v.bg, color: v.fg, border: `1px solid ${v.border}`,
        borderRadius: 8,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: s.gap,
        cursor: 'pointer', fontFamily: T.sans, letterSpacing: '-0.005em',
        transition: 'opacity 0.15s, transform 0.05s', whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {icon}
      {children}
      {iconRight}
    </button>
  );
}

// === Tag 5-tone ===
// h20 / padding 0 8 / fs11 / radius 4 / mono / letterSpacing 0.02em / lowercase
export function Tag({ T, tone = 'neutral', children }) {
  const tones = {
    neutral: { bg: T.chipBg,     fg: T.muted,   border: T.border },
    brand:   { bg: T.accentSoft, fg: T.accent,  border: TOKENS_V2.brand[200] },
    ok:      { bg: `color-mix(in oklch, ${T.success} 12%, transparent)`,    fg: T.success,    border: `color-mix(in oklch, ${T.success} 30%, transparent)` },
    warn:    { bg: `color-mix(in oklch, ${T.warn} 12%, transparent)`,       fg: T.warn,       border: `color-mix(in oklch, ${T.warn} 30%, transparent)` },
    err:     { bg: `color-mix(in oklch, ${TOKENS_V2.err} 12%, transparent)`, fg: TOKENS_V2.err, border: `color-mix(in oklch, ${TOKENS_V2.err} 30%, transparent)` },
  };
  const v = tones[tone] || tones.neutral;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px',
      fontSize: 11, fontWeight: 500, color: v.fg, background: v.bg,
      border: `1px solid ${v.border}`, borderRadius: 4,
      fontFamily: T.mono, letterSpacing: '0.02em', textTransform: 'lowercase',
    }}>
      {children}
    </span>
  );
}
