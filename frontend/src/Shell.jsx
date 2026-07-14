import { useState } from 'react';
import { I, KnotLogo, iconBtn, ACCENT_HUES } from './Shared.jsx';
import { getAppearance, setAppearance } from './utils.jsx';
import { APP_VERSION } from './version.js';
import { ModeToggle } from './screens/bi/ModeToggle.jsx';  // v0.8.5 ②a — 右上角 ASK/BI 集群（两模式一致）  // v0.6.4.11 task #44 — 前端版本单一真相源（不再硬编）

// v0.4.1.1: 非 admin 屏（chat / saved-reports / 未来用户屏）一律渲染传入的 sidebarContent；
// admin 屏（active 以 'admin-' 开头）走硬写导航。
// 命名约定：所有 admin 类屏的 active 标识必须以 'admin-' 开头（v0.3.3 已统一）；
// 新增 admin 屏漏前缀会 fallthrough 到 sidebarContent 分支（行为退化但不崩溃）。
export function AppShell({
  T, user, active = 'chat', sidebarContent,
  topbarTitle, topbarTrailing,
  showConnectionPill = false, connectionOk = true,
  connectedCount = null,  // v0.5.38 — 数据源已连接数（null 不显示 N）
  homeMode,               // v0.8.5 ②a — 子屏「返回」目标（chat / bi）；不传则回落读持久化
  // onToggleTheme v0.9.2 后 Shell 内不再使用（模式入弹层）；留位防调用方破缺（App.jsx 仍传）
  // eslint-disable-next-line no-unused-vars
  onToggleTheme, onNavigate, onLogout,
  children,
}) {
  const isAdmin = user && user.role === 'admin';
  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';
  // v0.9.0 外观弹层开关（风格/主题色/模式 — setAppearance 即时生效）
  const [showAppearance, setShowAppearance] = useState(false);
  // v0.6.4.2 UI v2 — floating inset 面板 chrome（R-313 rgba 豁免 — boxShadow；dark 无阴影）
  // v0.9.0 — 玻璃 chrome：panelShadow 归 token（含 inset 高光），旧主题回退保留
  const panelShadow = T.panelShadow || (T.dark ? 'none' : '0 1px 3px rgba(15,30,45,0.04)');
  // v0.8.5 ②a —「返回」目标 = 来时的顶层模式：优先 prop，回落读 App 写入的持久化 cb_home_mode
  // （子屏 AdminScreen/SavedReports 等不透传 prop → 靠持久化，从 BI 进设置返回 BI 而非硬回 chat）
  const backMode = homeMode || (() => {
    try { return JSON.parse(localStorage.getItem('cb_home_mode') || '"chat"') === 'bi' ? 'bi' : 'chat'; }
    catch { return 'chat'; }
  })();

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', gap: 10, padding: 10,
      background: T.ambient || T.bg, color: T.text, fontFamily: T.sans,
      fontSize: 13.5, overflow: 'hidden', letterSpacing: '-0.003em', lineHeight: 1.5,
      fontVariantNumeric: T.nums,  // v0.9.1 全局 tabular-nums：表格/KPI/趋势数字等宽对齐
    }}>
      {/* ═══ Sidebar — v0.9.0 玻璃浮窗（radius 18 + backdrop-blur + 高光描边 + panelShadow token） ═══ */}
      <aside style={{
        width: 236, flexShrink: 0,
        background: T.sidebar, border: `1px solid ${T.glassBorder || T.border}`,
        backdropFilter: T.blur, WebkitBackdropFilter: T.blur,
        borderRadius: 18, overflow: 'hidden', boxShadow: panelShadow,
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
        {active !== 'chat' && active !== 'bi' && onNavigate && (
          <div style={{ padding: '0 8px 8px' }}>
            {/* v0.8.5 ②a — 回到来时的顶层模式（从 BI 进设置 → 返回报表；从 ASK 进 → 返回对话）*/}
            <button onClick={() => onNavigate(backMode)} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 10, width: '100%',
              padding: '10px 14px', borderRadius: 8, background: T.card,
              color: T.text, border: `1px solid ${T.border}`,
              fontFamily: 'inherit', fontSize: 13, fontWeight: 500, cursor: 'pointer',
            }}>
              <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回{backMode === 'bi' ? '报表' : '对话'}
            </button>
          </div>
        )}
        {!active.startsWith('admin-') ? (
          <>
            {sidebarContent}
          </>
        ) : (
          <>
            {/* v0.8.12 C1 — 设置按模式分栏：从 BI 齿轮进（backMode==='bi'）只显 全局项(数据源/用户) + BI 专属(目录/权限/da-asst)；
                从 ASK 进显 全局项 + ASK/治理全量。互不串（kk）。 */}
            {isAdmin && backMode === 'bi' && (
              <>
                {/* v0.8.12 返工：去标题；全局项(数据源/用户/API&模型) + BI 专属(报表目录/权限)；da-asst 并入 API&模型 */}
                <SideNavRow T={T} icon={<I.db/>} label="数据源" active={active === 'admin-sources'}
                            onClick={() => onNavigate('admin-sources')}/>
                <SideNavRow T={T} icon={<I.users/>} label="用户" active={active === 'admin-users'}
                            onClick={() => onNavigate('admin-users')}/>
                <SideNavRow T={T} icon={<I.zap/>} label="API &amp; 模型" active={active === 'admin-models'}
                            onClick={() => onNavigate('admin-models')}/>
                <SideNavRow T={T} icon={<I.catalog/>} label="报表目录" active={active === 'admin-bi-directory'}
                            onClick={() => onNavigate('admin-bi-directory')}/>
                <SideNavRow T={T} icon={<I.shield/>} label="目录权限" active={active === 'admin-bi-permissions'}
                            onClick={() => onNavigate('admin-bi-permissions')}/>
              </>
            )}
            {isAdmin && backMode !== 'bi' && (
              <>
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
                {/* v0.7.0 C5 — 语义层指标注册表（≠ 内测指标 admin-metrics KPI 屏）；icon I.sql = 口径 SQL 定义语义 */}
                <SideNavRow T={T} icon={<I.sql/>} label="指标注册表" active={active === 'admin-metric-registry'}
                            onClick={() => onNavigate('admin-metric-registry')}/>
                <SideNavRow T={T} icon={<I.flow/>} label="LogicForm 审计" active={active === 'admin-logicform'}
                            onClick={() => onNavigate('admin-logicform')}/>
                <SideNavRow T={T} icon={<I.zap/>} label="指标监控" active={active === 'admin-monitors'}
                            onClick={() => onNavigate('admin-monitors')}/>
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
            display: 'grid', placeItems: 'center', fontSize: 12, fontWeight: 650, flexShrink: 0,
          }}>{initials}</div>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.2, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user?.display_name || user?.username}
            </span>
            <span style={{ fontSize: 11, color: T.muted, fontWeight: 500, letterSpacing: '0.02em', textTransform: 'uppercase' }}>
              {user?.role}
            </span>
          </div>
          {isAdmin && (
            <button onClick={() => onNavigate('settings')} style={iconBtn(T)} title="设置"><I.gear/></button>
          )}
          <button onClick={onLogout} style={iconBtn(T)} title="退出"><I.logout/></button>
        </div>
      </aside>

      {/* ═══ Main — v0.9.0 玻璃浮窗（radius 18 + backdrop-blur + 高光描边 + panelShadow token） ═══ */}
      <main style={{
        flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column',
        background: T.content, border: `1px solid ${T.glassBorder || T.border}`,
        backdropFilter: T.blur, WebkitBackdropFilter: T.blur,
        borderRadius: 18, overflow: 'hidden', boxShadow: panelShadow,
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
            {/* v0.9.0 外观弹层：风格（雾面/极光）× 主题色（4 色）× 浅深模式 */}
            <span style={{ position: 'relative', display: 'inline-flex' }}>
              <button onClick={() => setShowAppearance(s => !s)} title="外观"
                style={{ ...iconBtn(T), width: 30, height: 30, border: `1px solid ${showAppearance ? T.accent : T.border}`, color: showAppearance ? T.accent : T.subtext }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
                  <circle cx="12" cy="12" r="9"/>
                  <circle cx="12" cy="7.5" r="1.3" fill="currentColor" stroke="none"/>
                  <circle cx="8" cy="12" r="1.3" fill="currentColor" stroke="none"/>
                  <circle cx="15.5" cy="13.5" r="1.3" fill="currentColor" stroke="none"/>
                </svg>
              </button>
              {showAppearance && <AppearancePopover T={T} onClose={() => setShowAppearance(false)}/>}
            </span>
            {/* v0.9.2 顶栏独立深浅 switch 剔除（与弹层「模式」重复）；onToggleTheme prop 保留给 Login/Enroll/FCP 无弹层屏 */}
            {/* v0.8.5 ②a：ASK/BI 模式切换（chat + bi 两模式共用同一 Shell topbar 集群；admin 屏不渲染 → byte-equal 不变）*/}
            {(active === 'chat' || active === 'bi') && onNavigate && <ModeToggle T={T} active={active} onNavigate={onNavigate}/>}
          </div>
        </header>
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {children}
        </div>
      </main>
    </div>
  );
}

// v0.9.0 外观弹层：风格（frosted 雾面 / aurora 极光）× 主题色（ACCENT_HUES 4 色）× 浅深模式。
// setAppearance 写 cb_appearance + 通知 useTheme 订阅者 → 全局即时生效；选项点击不关闭（活预览）。
function AppearancePopover({ T, onClose }) {
  const cur = getAppearance();
  const label = { fontSize: 11, color: T.muted, fontWeight: 500, letterSpacing: '0.02em' };
  const frostedPrev = T.dark
    ? 'radial-gradient(70px 40px at 20% 0%, oklch(24% 0.04 210 / 0.7), transparent 70%), #0a0d11'
    : 'radial-gradient(70px 40px at 20% 0%, oklch(96% 0.02 195), transparent 70%), #f3f6f8';
  const auroraPrev = T.dark
    ? 'radial-gradient(60px 36px at 15% 10%, oklch(30% 0.09 292 / 0.85), transparent 70%), radial-gradient(60px 36px at 90% 30%, oklch(26% 0.08 250 / 0.75), transparent 70%), radial-gradient(70px 40px at 50% 110%, oklch(26% 0.07 325 / 0.65), transparent 70%), #0a070d'
    : 'radial-gradient(60px 36px at 15% 10%, oklch(90% 0.07 292 / 0.9), transparent 70%), radial-gradient(60px 36px at 90% 30%, oklch(91% 0.06 245 / 0.8), transparent 70%), radial-gradient(70px 40px at 50% 110%, oklch(92% 0.06 165 / 0.7), transparent 70%), #f4f3f8';
  const styleTile = (key, name, preview) => {
    const on = cur.style === key;
    return (
      <button key={key} onClick={() => setAppearance({ style: key })} style={{
        borderRadius: 12, padding: on ? 4 : 5, display: 'flex', flexDirection: 'column', gap: 5,
        cursor: 'pointer', textAlign: 'left', background: T.card, fontFamily: 'inherit',
        border: on ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
        boxShadow: on ? `0 0 0 3px color-mix(in oklch, ${T.accent} 14%, transparent)` : 'none',
      }}>
        <span style={{ height: 44, borderRadius: 8, border: `1px solid ${T.borderSoft}`, background: preview, display: 'block' }}/>
        <span style={{ fontSize: 12, fontWeight: on ? 600 : 400, color: on ? T.text : T.subtext, padding: '0 3px 2px' }}>{name}</span>
      </button>
    );
  };
  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 998 }}/>
      <div style={{
        position: 'absolute', top: 38, right: 0, width: 288, zIndex: 999,
        borderRadius: 16, background: T.content, border: `1px solid ${T.glassBorder || T.border}`,
        backdropFilter: T.blur, WebkitBackdropFilter: T.blur,
        boxShadow: T.panelShadow, padding: 14,
        display: 'flex', flexDirection: 'column', gap: 13, cursor: 'default',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline' }}>
          <span style={{ fontSize: 13, fontWeight: 650, color: T.text }}>外观</span>
          <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: T.mono, color: T.muted }}>仅影响本人 · 即时生效</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={label}>风格</span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {styleTile('frosted', '雾面 · 克制', frostedPrev)}
            {styleTile('aurora', '极光 · 多彩', auroraPrev)}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={label}>主题色</span>
          <div style={{ display: 'flex', gap: 10, padding: 2, alignItems: 'center' }}>
            {Object.entries(ACCENT_HUES).map(([key, def]) => {
              const on = cur.hue === key;
              const c = `oklch(${T.dark ? '72%' : '58%'} 0.17 ${def.h})`;
              return (
                <button key={key} onClick={() => setAppearance({ hue: key })} title={def.label} style={{
                  width: 24, height: 24, borderRadius: '50%', border: 'none', cursor: 'pointer', padding: 0,
                  background: c,
                  boxShadow: on ? `0 0 0 2px ${T.dark ? '#11151b' : '#ffffff'}, 0 0 0 4px ${c}` : 'none',
                }}/>
              );
            })}
            <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: T.mono, color: T.muted }}>OKLCH 同亮度</span>
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={label}>模式</span>
          <div style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 10, border: `1px solid ${T.border}`, background: T.card }}>
            {[['light', '浅色'], ['dark', '深色'], ['system', '跟随系统']].map(([m, name]) => {
              const on = cur.mode === m;
              return (
                <button key={m} onClick={() => setAppearance({ mode: m })} style={{
                  flex: 1, textAlign: 'center', padding: '6px 0', borderRadius: 8, border: 'none', cursor: 'pointer',
                  fontFamily: 'inherit', fontSize: 12, fontWeight: on ? 500 : 400,
                  background: on ? T.accent : 'transparent', color: on ? T.sendFg : T.subtext,
                  boxShadow: on ? (T.glow || 'none') : 'none',
                }}>{name}</button>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}

export function SideHeading({ T, children }) {
  // R-204: 字体改 T.mono（与 Login "SIGN IN" mono 风格统一）
  return (
    <div style={{
      padding: '14px 20px 6px', fontSize: 11, color: T.muted,
      fontWeight: 500, letterSpacing: '0.02em',
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
