// v0.6.4.0 UI v2 — 新组件原语 Btn / Tag（资深拍 B 拆独立文件；守护者 §9.2 映射表为唯一可审契约）。
// 结构色自 T（prop）+ semantic/brand 阶自模块引 TOKENS_V2（不穿 prop）。
// dumb presentational：无硬编 margin（间距由宿主 gap 决定 — Stage 2 Q3）。
import { TOKENS_V2 } from './Shared.jsx';
import { Spinner } from './utils.jsx';  // v0.6.4.1 D1 additive — Btn loading 态

// === Btn 5-variant × 3-size ===
// sizes / radius 8 / fontWeight 500 / translateY 0.5px press（demo ui.jsx byte-equal 等价）
const _BTN_SIZES = {
  sm: { h: 28, px: 10, fs: 12, gap: 6 },
  md: { h: 34, px: 14, fs: 13, gap: 8 },
  lg: { h: 40, px: 18, fs: 14, gap: 8 },
};

// v0.6.4.1 D1 additive +3 prop（守护者 §9.2）：type 默认 'button' 安全（防全站 submit 潜伏）；
// disabled / loading（loading → Spinner 替 children + 禁用）。现有 5-variant 映射 byte-equal。
export function Btn({ T, variant = 'default', size = 'md', type = 'button', disabled = false, loading = false, icon, iconRight, onClick, style, children }) {
  const s = _BTN_SIZES[size] || _BTN_SIZES.md;
  const variants = {
    default: { bg: T.content,    fg: T.text,     border: T.border },
    primary: { bg: T.accent,     fg: T.sendFg,   border: T.accent },
    ghost:   { bg: 'transparent', fg: T.text,    border: 'transparent' },
    soft:    { bg: T.accentSoft, fg: T.accent,   border: TOKENS_V2.brand[200] },
    danger:  { bg: 'transparent', fg: TOKENS_V2.err, border: T.border },
  };
  const v = variants[variant] || variants.default;
  const off = disabled || loading;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={off}
      onMouseDown={(e) => { if (!off) e.currentTarget.style.transform = 'translateY(0.5px)'; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
      style={{
        height: s.h, padding: `0 ${s.px}px`, fontSize: s.fs, fontWeight: 500,
        background: v.bg, color: v.fg, border: `1px solid ${v.border}`,
        borderRadius: 8,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: s.gap,
        cursor: off ? 'not-allowed' : 'pointer', opacity: off ? 0.5 : 1,
        fontFamily: T.sans, letterSpacing: '-0.005em',
        transition: 'opacity 0.15s, transform 0.05s', whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {loading ? <Spinner size={14} color={v.fg}/> : <>{icon}{children}{iconRight}</>}
    </button>
  );
}
