// ModeToggle.jsx — v0.8.5 (②a) BI/ASK 模式切换 pill（handoff §2 定稿形态）。
// 纯图标方块：容器 gap2/padding2/border/radius8/等高30；2 seg 各 24×24 grid-center radius6 icon16；
// ASK 左(对话气泡) · BI 右(柱状图)；激活 accent 底+send-fg，未激活 subtext + hover。无文字，title 提示。
export function ModeToggle({ T, active, onNavigate }) {
  const seg = (on) => ({
    width: 24, height: 24, display: 'grid', placeItems: 'center', borderRadius: 6,
    border: 'none', cursor: 'pointer', background: on ? T.accent : 'transparent',
    color: on ? T.sendFg : T.subtext,
  });
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 2, padding: 2, height: 30,
      border: `1px solid ${T.border}`, borderRadius: 8,
    }}>
      <button onClick={() => onNavigate('chat')} style={seg(active === 'chat')} title="ASK 问数模式">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
      <button onClick={() => onNavigate('bi')} style={seg(active === 'bi')} title="BI 报表模式">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6" />
        </svg>
      </button>
    </div>
  );
}
