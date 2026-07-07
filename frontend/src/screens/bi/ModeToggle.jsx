// ModeToggle.jsx — v0.8.5 (②a) BI/ASK 模式切换 pill（handoff §2 定稿形态）。
// 纯图标方块：容器 gap2/padding2/border/radius8/等高30；2 seg 各 24×24 grid-center radius6 icon16；
// ASK 左(对话气泡) · BI 右(柱状图)；激活 accent 底+send-fg，未激活 subtext + hover 淡底。无文字，title 提示。
import { useState } from 'react';

export function ModeToggle({ T, active, onNavigate }) {
  const [hover, setHover] = useState(null);
  const seg = (key, on) => ({
    width: 24, height: 24, padding: 0, lineHeight: 0,  // 正方 + line-height:0 → 双轴真居中（消 SVG 基线下沉）
    display: 'grid', placeItems: 'center', borderRadius: 6,
    border: 'none', cursor: 'pointer',
    background: on ? T.accent : (hover === key ? T.hover : 'transparent'),  // 未激活 hover → 淡底
    color: on ? T.sendFg : T.subtext,
    transition: 'background 120ms ease',
  });
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 2, padding: 2, height: 30,
      border: `1px solid ${T.border}`, borderRadius: 8,
    }}>
      <button onClick={() => onNavigate('chat')} style={seg('chat', active === 'chat')} title="ASK 问数模式"
        onMouseEnter={() => setHover('chat')} onMouseLeave={() => setHover(null)}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
      <button onClick={() => onNavigate('bi')} style={seg('bi', active === 'bi')} title="BI 报表模式"
        onMouseEnter={() => setHover('bi')} onMouseLeave={() => setHover(null)}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
          <path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6" />
        </svg>
      </button>
    </div>
  );
}
