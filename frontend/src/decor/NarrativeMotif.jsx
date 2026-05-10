/**
 * NarrativeMotif — Login screen decorative SVG (v0.5.7 R-173 / R-182 / Q1 / Q4)
 *
 * 原子结构 motif：3 椭圆轨道 + 4 电子 + 核心，左侧汇入 7 条曲线（输入 → 收敛）。
 * 视觉隐喻：复杂需求 → 三个专家 Agent (K/N/O/T) → 核心可追溯洞察。
 *
 * R-173 单文件 ≤ 120 行 pure SVG func（不引 deps）
 * R-182 React.memo 包裹（防 Login state 变化触发 SVG 巨量 path 重绘）
 * Q1   color-mix(in oklch, T.accent, transparent) 替代 demo 原 brand[100]
 *      （严禁扩 buildTheme 加新字段 — 守 R-158 25 字段契约）
 * Q4   T.dark boolean 分支（严禁 theme 字串）
 */
import { memo } from 'react';

function NarrativeMotif({ T }) {
  const stroke     = T.accent;
  const muted      = T.dark ? 'rgba(255,255,255,0.18)' : 'rgba(13,16,20,0.18)';
  const node       = T.dark ? '#f4f6f8' : '#0d1014';
  const orbitColor = T.dark ? 'rgba(255,255,255,0.22)' : 'rgba(13,16,20,0.18)';
  // Q1 OKLCH color-mix 替代 demo brand[100]
  const tint = `color-mix(in oklch, ${T.accent} 15%, transparent)`;
  const themeKey = T.dark ? 'dark' : 'light';

  const cx = 320, cy = 350;
  const orbits = [
    { rx: 200, ry: 72, rot: -22 },
    { rx: 200, ry: 72, rot:  22 },
    { rx: 72,  ry: 200, rot: 0 },
  ];

  const pointOn = (o, deg) => {
    const a = deg * Math.PI / 180;
    const r = o.rot * Math.PI / 180;
    const px = o.rx * Math.cos(a);
    const py = o.ry * Math.sin(a);
    return {
      x: cx + px * Math.cos(r) - py * Math.sin(r),
      y: cy + px * Math.sin(r) + py * Math.cos(r),
    };
  };

  // 4 electrons (1 brand-tinted)
  const electrons = [
    { pos: pointOn(orbits[1], 180) },
    { pos: pointOn(orbits[0],   0), brand: true },
    { pos: pointOn(orbits[1],   0) },
    { pos: pointOn(orbits[0], 180) },
  ];

  // tangled inputs streaming in from far left, converging at the nucleus
  const inputs = [];
  for (let i = 0; i < 7; i++) {
    const startY = 50 + i * 95;
    const cp1 = { x: 50 + (i % 3) * 30, y: startY + (i % 2 ? 50 : -50) };
    const cp2 = { x: 220, y: cy + (i - 3) * 32 };
    inputs.push({
      d: `M -20 ${startY} C ${cp1.x} ${cp1.y}, ${cp2.x} ${cp2.y}, ${cx} ${cy}`,
      opacity: 0.16 + (i % 3) * 0.08,
    });
  }

  return (
    <div style={{
      width: '100%', height: '100%', position: 'relative',
      background: `radial-gradient(ellipse at 30% 30%, ${tint}, transparent 60%)`,
    }}>
      {/* SVG absolute 定位 — left:65% 让 motif 中心偏右 15%（match demo 比例） */}
      <svg viewBox="0 0 600 700" preserveAspectRatio="xMidYMid meet"
           style={{
             position: 'absolute',
             left: '65%', top: '50%',
             transform: 'translate(-50%, -50%)',
             width: 540, height: 630,
             maxWidth: '85%', maxHeight: '90%',
             display: 'block',
           }}>
        <defs>
          <linearGradient id={`nm-in-${themeKey}`} x1="0" x2="1">
            <stop offset="0%"  stopColor={muted} stopOpacity="0" />
            <stop offset="70%" stopColor={muted} stopOpacity="1" />
          </linearGradient>
          <radialGradient id={`nm-core-${themeKey}`} cx="50%" cy="50%" r="50%">
            <stop offset="0%"   stopColor={stroke} stopOpacity="0.32" />
            <stop offset="55%"  stopColor={stroke} stopOpacity="0.10" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* tangled inputs */}
        {inputs.map((p, i) => (
          <path key={i} d={p.d} stroke={`url(#nm-in-${themeKey})`} strokeWidth="1"
                fill="none" opacity={p.opacity} strokeLinecap="round" />
        ))}

        {/* atomic orbits */}
        {orbits.map((o, i) => (
          <ellipse key={i} cx={cx} cy={cy} rx={o.rx} ry={o.ry}
                   fill="none" stroke={orbitColor} strokeWidth="1"
                   transform={`rotate(${o.rot} ${cx} ${cy})`} />
        ))}

        {/* nucleus = convergence point = traceable insight */}
        <circle cx={cx} cy={cy} r="50" fill={`url(#nm-core-${themeKey})`} />
        <circle cx={cx} cy={cy} r="16" fill="none" stroke={stroke} strokeWidth="1" opacity="0.55" />
        <circle cx={cx} cy={cy} r="9" fill={stroke} />

        {/* electrons (K/N/O/T agents) */}
        {electrons.map((e, i) => (
          <g key={i}>
            <circle cx={e.pos.x} cy={e.pos.y} r="11"
                    fill={e.brand ? stroke : node} opacity={e.brand ? 0.18 : 0.10} />
            <circle cx={e.pos.x} cy={e.pos.y} r="5" fill={e.brand ? stroke : node} />
          </g>
        ))}
      </svg>
    </div>
  );
}

export default memo(NarrativeMotif);
