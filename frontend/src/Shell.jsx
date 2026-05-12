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
            v0.5.30 #28 logoArea 56 → 52 — 与 main header 52 字节对齐
            v0.5.31 #34 — KnotLogo 右侧加版本号（demo thinking.jsx L28 byte-equal；R-181 三处同步 → 四处同步） */}
        <div style={{
          height: 52, padding: '0 16px', flexShrink: 0,
          display: 'flex', alignItems: 'center',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <KnotLogo T={T} size={20}/>
          <span style={{
            marginLeft: 'auto',
            fontSize: 11, fontFamily: T.mono, color: T.muted,
            letterSpacing: '0.1em',
          }}>v0.5.33</span>
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
                {/* v0.5.26 #18 API & 模型 icon sparkle → zap (lightning bolt — demo 风格) */}
                <SideNavRow T={T} icon={<I.zap/>} label="API &amp; 模型" active={active === 'admin-models'}
                            onClick={() => onNavigate('admin-models')}/>
                <SideNavRow T={T} icon={<I.book/>} label="知识库" active={active === 'admin-knowledge'}
                            onClick={() => onNavigate('admin-knowledge')}/>
                {/* v0.5.26 #18 Few-shot icon zap → flask (Q2 VRP 局部例外 — Shared 无 I.flask) */}
                <SideNavRow T={T} icon={<FlaskIcon/>} label="Few-shot 示例" active={active === 'admin-fewshots'}
                            onClick={() => onNavigate('admin-fewshots')}/>
                <SideNavRow T={T} icon={<I.pencil/>} label="Prompt 模板" active={active === 'admin-prompts'}
                            onClick={() => onNavigate('admin-prompts')}/>
                {/* v0.5.26 #18 业务目录 icon gear → folder-tree (Q2 VRP) */}
                <SideNavRow T={T} icon={<FolderIcon/>} label="业务目录" active={active === 'admin-catalog'}
                            onClick={() => onNavigate('admin-catalog')}/>
                {/* admin 看板（R-202: emoji 前缀 → SVG icon 统一） */}
                {/* v0.5.26 #18 预算 icon zap → wallet (Q2 VRP) */}
                <SideNavRow T={T} icon={<WalletIcon/>} label="预算" active={active === 'admin-budgets'}
                            onClick={() => onNavigate('admin-budgets')}/>
                <SideNavRow T={T} icon={<I.shield/>} label="Recovery" active={active === 'admin-recovery'}
                            onClick={() => onNavigate('admin-recovery')}/>
                {/* v0.5.26 #18 审计日志 icon book → clipboard-check (Q2 VRP) */}
                <SideNavRow T={T} icon={<ClipboardCheckIcon/>} label="审计日志" active={active === 'admin-audit'}
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
                {/* v0.5.30 #32 — 字面对齐 demo "数据源 · 已连接"（count 受限于后端 endpoint，并入 v0.5.34 真数实现）*/}
                {connectionOk ? '数据源 · 已连接' : '数据源 · 未连接'}
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

// v0.5.26 #18 — 4 inline svg icons（Q2 VRP 局部例外 — Shared 无 flask/folder/wallet/clipboard）
const FlaskIcon = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M9 2h6m-5 0v6L4 20a2 2 0 0 0 1.7 3h12.6A2 2 0 0 0 20 20l-6-12V2"/></svg>;
const FolderIcon = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>;
const WalletIcon = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/></svg>;
const ClipboardCheckIcon = (p) => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/></svg>;

export function SideNavRow({ T, icon, label, active, onClick }) {
  // v0.5.26 #11/#17 — active 指示纯 bg 填充 color-mix 12%
  // （删 R-203 absolute span 3px brand bar — 资深反馈"边边很丑"，bg 填充已足够辨识）
  return (
    <div onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px',
      margin: '0 8px', borderRadius: 8, cursor: 'pointer', fontSize: 13,
      background: active ? `color-mix(in oklch, ${T.accent} 12%, transparent)` : 'transparent',
      color: active ? T.accent : T.subtext,
      fontWeight: active ? 500 : 400,
      marginBottom: 1,
    }}>
      <span style={{ display: 'inline-flex', flexShrink: 0 }}>{icon}</span>
      <span style={{
        flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }} dangerouslySetInnerHTML={{ __html: label }}/>
    </div>
  );
}
