import { I, KnotLogo, iconBtn } from './Shared.jsx';

// v0.4.1.1: 非 admin 屏（chat / saved-reports / 未来用户屏）一律渲染传入的 sidebarContent；
// admin 屏（active 以 'admin-' 开头）走硬写导航。
// 命名约定：所有 admin 类屏的 active 标识必须以 'admin-' 开头（v0.3.3 已统一）；
// 新增 admin 屏漏前缀会 fallthrough 到 sidebarContent 分支（行为退化但不崩溃）。
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
      {/* ═══ Sidebar (R-198: 256→224；Q2 加码 Label ellipsis) ═══ */}
      <aside style={{
        width: 224, flexShrink: 0, height: '100%',
        background: T.sidebar, borderRight: `1px solid ${T.border}`,
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Brand 区 — R-199 KnotLogo size=20（R-186 抗诱惑解禁仅限 Shell 一处 R-199.5）
            R-200 logoArea 56px + borderBottom（与 main header 52px 视觉对齐） */}
        <div style={{
          height: 56, padding: '0 16px', flexShrink: 0,
          display: 'flex', alignItems: 'center',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <KnotLogo T={T} size={20}/>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 0' }}>
        {!active.startsWith('admin-') ? (
          <>
            {sidebarContent}
          </>
        ) : (
          <>
            {isAdmin && (
              <>
                <SideHeading T={T}>管理员</SideHeading>
                <SideNavRow T={T} icon={<I.db/>} label="数据源" active={active === 'admin-sources'}
                            onClick={() => onNavigate('admin-sources')}/>
                <SideNavRow T={T} icon={<I.users/>} label="用户" active={active === 'admin-users'}
                            onClick={() => onNavigate('admin-users')}/>
                <SideNavRow T={T} icon={<I.sparkle/>} label="API &amp; 模型" active={active === 'admin-models'}
                            onClick={() => onNavigate('admin-models')}/>
                <SideNavRow T={T} icon={<I.book/>} label="知识库" active={active === 'admin-knowledge'}
                            onClick={() => onNavigate('admin-knowledge')}/>
                <SideNavRow T={T} icon={<I.zap/>} label="Few-shot 示例" active={active === 'admin-fewshots'}
                            onClick={() => onNavigate('admin-fewshots')}/>
                <SideNavRow T={T} icon={<I.pencil/>} label="Prompt 模板" active={active === 'admin-prompts'}
                            onClick={() => onNavigate('admin-prompts')}/>
                <SideNavRow T={T} icon={<I.gear/>} label="业务目录" active={active === 'admin-catalog'}
                            onClick={() => onNavigate('admin-catalog')}/>
                {/* admin 看板（R-202: emoji 前缀 → SVG icon 统一） */}
                <SideNavRow T={T} icon={<I.zap/>} label="预算" active={active === 'admin-budgets'}
                            onClick={() => onNavigate('admin-budgets')}/>
                <SideNavRow T={T} icon={<I.shield/>} label="Recovery" active={active === 'admin-recovery'}
                            onClick={() => onNavigate('admin-recovery')}/>
                {/* v0.4.6 D3 落地：审计日志 */}
                <SideNavRow T={T} icon={<I.book/>} label="审计日志" active={active === 'admin-audit'}
                            onClick={() => onNavigate('admin-audit')}/>
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

        </div>

        {/* Footer: user row — R-201/R-211 渐变橘色偿还 → 纯 T.accent；高度 56px borderTop */}
        <div style={{
          height: 56, padding: '0 12px', flexShrink: 0,
          display: 'flex', alignItems: 'center', gap: 10,
          borderTop: `1px solid ${T.border}`,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: T.accent, color: '#fff',
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
  // R-204: 字体改 T.mono（与 Login "SIGN IN" mono 风格统一）
  return (
    <div style={{
      padding: '14px 20px 6px', fontSize: 10, color: T.muted,
      fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase',
    }}>{children}</div>
  );
}

export function SideNavRow({ T, icon, label, active, onClick }) {
  // R-203 + Q4: active 指示改 absolute span 2px brand bar 右侧（避 overflow:hidden 裁切）
  // Q2 加码: Label ellipsis 防 224px 宽度下中文长 label 溢出
  return (
    <div onClick={onClick} style={{
      position: 'relative',
      display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px',
      margin: '0 8px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
      background: active ? T.accentSoft : 'transparent',
      color: active ? T.accent : T.subtext,
      fontWeight: active ? 500 : 400,
      marginBottom: 1,
    }}>
      {active && <span style={{
        position: 'absolute', right: 0, top: '50%',
        transform: 'translateY(-50%)',
        width: 2, height: '60%',
        background: T.accent, borderRadius: 2,
      }}/>}
      <span style={{ display: 'inline-flex', flexShrink: 0 }}>{icon}</span>
      <span style={{
        flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }} dangerouslySetInnerHTML={{ __html: label }}/>
    </div>
  );
}
