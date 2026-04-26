import { I, iconBtn } from './Shared.jsx';

export function AppShell({
  T, user, active = 'chat', sidebarContent,
  topbarTitle, topbarTrailing,
  showConnectionPill = false, connectionOk = true,
  hideSidebarNewChat = false,
  onToggleTheme, onNewChat, onNavigate, onLogout,
  children,
}) {
  const isAdmin = user && user.role === 'admin';
  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex',
      background: T.bg, color: T.text, fontFamily: T.sans,
      fontSize: 13.5, overflow: 'hidden', letterSpacing: '-0.003em', lineHeight: 1.5,
    }}>
      {/* ═══ Sidebar ═══ */}
      <aside style={{
        width: 256, flexShrink: 0, height: '100%',
        background: T.sidebar, borderRight: `1px solid ${T.border}`,
        display: 'flex', flexDirection: 'column', padding: '14px 12px 12px',
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 4px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 24, height: 24, borderRadius: 6, background: T.accent,
              display: 'grid', placeItems: 'center', color: '#fff',
            }}>
              <I.sparkle width="14" height="14"/>
            </div>
            <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.01em', color: T.text }}>BI-Agent</span>
          </div>
        </div>

        {active === 'chat' ? (
          <>
            {sidebarContent}
          </>
        ) : (
          <>
            {isAdmin && (
              <>
                <SideHeading T={T}>个人</SideHeading>
                <SideNavRow T={T} icon={<I.key/>} label="API &amp; 模型" active={active === 'user-config'}
                            onClick={() => onNavigate('user-config')}/>
                <SideHeading T={T}>管理员</SideHeading>
                <SideNavRow T={T} icon={<I.db/>} label="数据源" active={active === 'admin-sources'}
                            onClick={() => onNavigate('admin-sources')}/>
                <SideNavRow T={T} icon={<I.users/>} label="用户" active={active === 'admin-users'}
                            onClick={() => onNavigate('admin-users')}/>
                <SideNavRow T={T} icon={<I.sparkle/>} label="模型库" active={active === 'admin-models'}
                            onClick={() => onNavigate('admin-models')}/>
                <SideNavRow T={T} icon={<I.book/>} label="知识库" active={active === 'admin-knowledge'}
                            onClick={() => onNavigate('admin-knowledge')}/>
              </>
            )}
            <div style={{ flex: 1 }}/>
            <div style={{ padding: '10px 10px 6px' }}>
              <button onClick={() => onNavigate('chat')} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'none', border: 'none', color: T.muted,
                fontSize: 12.5, fontFamily: 'inherit', cursor: 'pointer', padding: 0,
              }}>
                <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
              </button>
            </div>
          </>
        )}

        {/* Footer: user row */}
        <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 10, marginTop: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 4px' }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: `linear-gradient(135deg, ${T.accent}, #ff7a3a)`, color: '#fff',
              display: 'grid', placeItems: 'center', fontSize: 11.5, fontWeight: 600, flexShrink: 0,
            }}>{initials}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 4 }}>
                {user?.display_name || user?.username}
                {isAdmin && <span style={{ fontSize: 9, padding: '1px 4px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>ADMIN</span>}
              </div>
            </div>
            {isAdmin && (
              <button onClick={() => onNavigate('settings')} style={iconBtn(T)} title="设置"><I.gear/></button>
            )}
            <button onClick={onLogout} style={iconBtn(T)} title="退出"><I.logout/></button>
          </div>
        </div>
      </aside>

      {/* ═══ Main ═══ */}
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', height: '100%', background: T.content }}>
        <header style={{
          height: 52, flexShrink: 0, padding: '0 22px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: `1px solid ${T.border}`, background: T.content,
        }}>
          <div style={{ fontSize: 14, color: T.text, fontWeight: 500 }}>{topbarTitle}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {showConnectionPill && (
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '5px 10px', borderRadius: 999,
                border: `1px solid ${T.border}`, background: T.content, color: T.subtext, fontSize: 11.5,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: connectionOk ? T.success : T.warn,
                  boxShadow: connectionOk ? `0 0 0 2px ${T.successSoft}` : `0 0 0 2px rgba(255,164,33,0.18)`,
                }}/>
                {connectionOk ? '数据库已连接' : '未连接数据库'}
              </div>
            )}
            {topbarTrailing}
            <button onClick={onToggleTheme} style={{ ...iconBtn(T), width: 30, height: 30, border: `1px solid ${T.border}` }} title="切换主题">
              {T.dark ? <I.sun/> : <I.moon/>}
            </button>
          </div>
        </header>
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {children}
        </div>
      </main>
    </div>
  );
}

export function SideHeading({ T, children }) {
  return (
    <div style={{
      padding: '12px 10px 4px', fontSize: 10.5, color: T.muted,
      letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600,
    }}>{children}</div>
  );
}

export function SideNavRow({ T, icon, label, active, onClick }) {
  return (
    <div onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 9, padding: '8px 10px',
      borderRadius: 6, cursor: 'pointer', fontSize: 13,
      background: active ? T.accentSoft : 'transparent',
      color: active ? T.accent : T.subtext,
      borderLeft: active ? `2px solid ${T.accent}` : '2px solid transparent',
      paddingLeft: active ? 8 : 10, fontWeight: active ? 500 : 400,
      marginBottom: 1,
    }}>
      <span style={{ display: 'inline-flex' }}>{icon}</span>
      <span dangerouslySetInnerHTML={{ __html: label }}/>
    </div>
  );
}
