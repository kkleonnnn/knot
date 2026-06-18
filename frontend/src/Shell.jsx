import { I, KnotLogo, iconBtn } from './Shared.jsx';
import { APP_VERSION } from './version.js';  // v0.6.4.11 task #44 — 前端版本单一真相源（不再硬编）

// v0.4.1.1: 非 admin 屏（chat / saved-reports / 未来用户屏）一律渲染传入的 sidebarContent；
// admin 屏（active 以 'admin-' 开头）走硬写导航。
// 命名约定：所有 admin 类屏的 active 标识必须以 'admin-' 开头（v0.3.3 已统一）；
// 新增 admin 屏漏前缀会 fallthrough 到 sidebarContent 分支（行为退化但不崩溃）。
export function AppShell({
  T, user, active = 'chat', sidebarContent,
  topbarTitle, topbarTrailing,
  showConnectionPill = false, connectionOk = true,
  connectedCount = null,  // v0.5.38 — 数据源已连接数（null 不显示 N）
  onToggleTheme, onNavigate, onLogout,
  children,
}) {
  const isAdmin = user && user.role === 'admin';
  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';
  // v0.6.4.2 UI v2 — floating inset 面板 chrome（R-313 rgba 豁免 — boxShadow；dark 无阴影）
  const panelShadow = T.dark ? 'none' : '0 1px 3px rgba(15,30,45,0.04)';

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', gap: 10, padding: 10,
      background: T.bg, color: T.text, fontFamily: T.sans,
      fontSize: 13.5, overflow: 'hidden', letterSpacing: '-0.003em', lineHeight: 1.5,
    }}>
      {/* ═══ Sidebar — v0.6.4.2 floating inset 面板（radius 14 + 全 border + boxShadow） ═══ */}
      <aside style={{
        width: 224, flexShrink: 0,
        background: T.sidebar, border: `1px solid ${T.border}`,
        borderRadius: 14, overflow: 'hidden', boxShadow: panelShadow,
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Brand 区 — R-199 KnotLogo（R-186 抗诱惑解禁仅限 Shell 一处 R-199.5）
            v0.6.4.2 #VRP — logoArea 56 与 TopBar 56 字节对齐；KnotLogo size 16；
            v0.5.31 #34 版本号 — R-181 四处同步第 4 处（main.py + smoke + Login footer + 本行 L43） */}
        <div style={{
          height: 56, padding: '0 16px', flexShrink: 0,
          display: 'flex', alignItems: 'center',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <KnotLogo T={T} size={20}/>
          <span style={{
            marginLeft: 'auto',
            fontSize: 11, fontFamily: T.mono, color: T.muted,
            letterSpacing: '0.06em',
          }}>v{APP_VERSION}</span>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 0', display: 'flex', flexDirection: 'column' }}>
        {/* v0.6.0.13 #1：非 chat 屏 sidebar 顶部加「返回对话」大按钮（与 Chat 屏「新建对话」同位置同样式）
            实现"哪来的就哪回的"原则；旧的底部 ghost 链接移除（详 L100+ 注释） */}
        {active !== 'chat' && onNavigate && (
          <div style={{ padding: '0 8px 8px' }}>
            <button onClick={() => onNavigate('chat')} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 10, width: '100%',
              padding: '10px 14px', borderRadius: 8, background: T.card,
              color: T.text, border: `1px solid ${T.border}`,
              fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: 'pointer',
            }}>
              <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
            </button>
          </div>
        )}
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
                {/* v0.6.4.2 — Few-shot icon → Foundation I.flask（v0.6.4.0 已加；偿还 v0.5.26 inline 例外） */}
                <SideNavRow T={T} icon={<I.flask/>} label="Few-shot 示例" active={active === 'admin-fewshots'}
                            onClick={() => onNavigate('admin-fewshots')}/>
                <SideNavRow T={T} icon={<I.pencil/>} label="Prompt 模板" active={active === 'admin-prompts'}
                            onClick={() => onNavigate('admin-prompts')}/>
                {/* v0.6.4.2 — 业务目录 icon → Foundation I.catalog（4-rect 网格；artboard ADMIN_NAV byte-equal） */}
                <SideNavRow T={T} icon={<I.catalog/>} label="业务目录" active={active === 'admin-catalog'}
                            onClick={() => onNavigate('admin-catalog')}/>
                {/* admin 看板（R-202: emoji 前缀 → SVG icon 统一） */}
                {/* v0.6.4.2 — 预算 icon → Foundation I.budget（$ 圆；artboard ADMIN_NAV byte-equal） */}
                <SideNavRow T={T} icon={<I.budget/>} label="预算" active={active === 'admin-budgets'}
                            onClick={() => onNavigate('admin-budgets')}/>
                <SideNavRow T={T} icon={<I.shield/>} label="Recovery" active={active === 'admin-recovery'}
                            onClick={() => onNavigate('admin-recovery')}/>
                {/* v0.6.4.2 — 审计日志 icon → Foundation I.audit（文档+行；artboard ADMIN_NAV byte-equal） */}
                <SideNavRow T={T} icon={<I.audit/>} label="审计日志" active={active === 'admin-audit'}
                            onClick={() => onNavigate('admin-audit')}/>
                {/* v0.6.0.4 F-B 前端 JS 错误上报 */}
                <SideNavRow T={T} icon={<I.x/>} label="前端错误" active={active === 'admin-errors'}
                            onClick={() => onNavigate('admin-errors')}/>
                {/* v0.6.4.2 — 内测指标 icon zap → spark（解与 API&模型 zap 撞名；artboard ADMIN_NAV byte-equal） */}
                <SideNavRow T={T} icon={<I.spark/>} label="内测指标" active={active === 'admin-metrics'}
                            onClick={() => onNavigate('admin-metrics')}/>
                {/* v0.6.0.18 用户查询历史屏（脱敏链 2/3）*/}
                <SideNavRow T={T} icon={<I.search/>} label="查询历史" active={active === 'admin-history'}
                            onClick={() => onNavigate('admin-history')}/>
              </>
            )}
          </>
        )}
        {/* v0.5.38 → v0.6.0.13：底部「返回对话」ghost 链接已挪到 sidebar 顶部（"哪来的就哪回的"内测反馈 #1）*/}

        </div>

        {/* Footer: user row — v0.6.4.2 2 行布局（name + role mono）；avatar 纯 T.accent（R-201/R-211 渐变橘偿还）*/}
        <div style={{
          height: 56, padding: '0 12px', flexShrink: 0,
          display: 'flex', alignItems: 'center', gap: 10,
          borderTop: `1px solid ${T.border}`,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: '50%',
            background: T.accent, color: T.sendFg,
            display: 'grid', placeItems: 'center', fontSize: 11.5, fontWeight: 600, flexShrink: 0,
          }}>{initials}</div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.2, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.display_name || user?.username}
            </span>
            <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              {user?.role}
            </span>
          </div>
          {isAdmin && (
            <button onClick={() => onNavigate('settings')} style={iconBtn(T)} title="设置"><I.gear/></button>
          )}
          <button onClick={onLogout} style={iconBtn(T)} title="退出"><I.logout/></button>
        </div>
      </aside>

      {/* ═══ Main — v0.6.4.2 floating inset 面板（radius 14 + 全 border + boxShadow） ═══ */}
      <main style={{
        flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column',
        background: T.content, border: `1px solid ${T.border}`,
        borderRadius: 14, overflow: 'hidden', boxShadow: panelShadow,
      }}>
        <header style={{
          height: 56, flexShrink: 0, padding: '0 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: `1px solid ${T.border}`, background: T.content,
        }}>
          <div style={{ fontSize: 14, color: T.text, fontWeight: 500 }}>{topbarTitle}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {showConnectionPill && (
              /* v0.5.38 — 删 framed pill（border + bg + radius 999）→ inline dot + text；字面 "数据源 · N 已连接" */
              <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                color: T.muted, fontSize: 12,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: connectionOk ? T.success : T.warn,
                  flexShrink: 0,
                }}/>
                <span>数据源 · {connectionOk
                  ? (connectedCount != null ? `${connectedCount} 已连接` : '已连接')
                  : '未连接'}</span>
              </span>
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
  // v0.5.26 #11/#17 — active 指示纯 bg 填充 color-mix 12%（资深 ack「bg 填充足够辨识」）
  // v0.6.4.2 — 显式 height 34 + radius 6 + gap 10（UI v2 NavItem）
  return (
    <div onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 10, height: 34, padding: '0 12px',
      margin: '0 8px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
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
