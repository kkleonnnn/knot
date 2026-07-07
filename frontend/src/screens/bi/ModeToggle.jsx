// ModeToggle.jsx — v0.8.5 (②a) App 级悬浮 BI/ASK 模式切换（D1 — 不动 AppShell / R-192 / 18 屏 byte-equal）。
// 右上角浮层（VRP：artboard 把握「右上、主题开关旁」方向；本地悬浮锚定实现，首版位置 kk「先看效果」）。
export function ModeToggle({ T, screen, onNavigate }) {
  const seg = (active) => ({
    display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 11px', borderRadius: 7,
    fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none', fontFamily: 'inherit',
    background: active ? T.accent : 'transparent', color: active ? T.sendFg : T.subtext,
  });
  return (
    <div style={{
      position: 'fixed', top: 12, right: 12, zIndex: 200, display: 'inline-flex', gap: 2, padding: 3,
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 9,
      boxShadow: T.dark ? 'none' : '0 1px 4px rgba(15,30,45,0.10)',
    }}>
      <button onClick={() => onNavigate('chat')} style={seg(screen === 'chat')} title="问数模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>ASK
      </button>
      <button onClick={() => onNavigate('bi')} style={seg(screen === 'bi')} title="报表模式">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19V5M4 19h16M8 15v-4M12 15V8M16 15v-6" />
        </svg>BI
      </button>
    </div>
  );
}
