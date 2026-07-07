// ModeToggle.jsx — v0.8.5 (②a) BI/ASK 模式切换（内联段控，右上角集群一员）。
// 问题①修：非悬浮 → 内联在主题开关**右边**、等高（30）；ASK/BI 两模式右上角一致不变。
// 用 active + onNavigate（AppShell 既有 props，不加 prop 保 R-192）。
export function ModeToggle({ T, active, onNavigate }) {
  const seg = (on) => ({
    display: 'inline-flex', alignItems: 'center', gap: 5, height: 30, padding: '0 11px',
    borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none',
    fontFamily: 'inherit', background: on ? T.accent : 'transparent', color: on ? T.sendFg : T.subtext,
  });
  return (
    <div style={{ display: 'inline-flex', gap: 2, padding: 2, background: T.chipBg, border: `1px solid ${T.border}`, borderRadius: 9 }}>
      <button onClick={() => onNavigate('chat')} style={seg(active === 'chat')} title="问数模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>ASK
      </button>
      <button onClick={() => onNavigate('bi')} style={seg(active === 'bi')} title="报表模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6" />
        </svg>BI
      </button>
    </div>
  );
}
