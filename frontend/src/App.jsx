import { useEffect, useState } from 'react';
import { useTheme, usePersist, Spinner } from './utils.jsx';
import { api } from './api.js';
import { LoginScreen } from './screens/Login.jsx';
import { ForceChangePasswordScreen } from './screens/ForceChangePassword.jsx';
import { EnrollScreen } from './screens/Enroll.jsx';
import { ChatScreen } from './screens/Chat.jsx';
import { AdminScreen } from './screens/Admin.jsx';
import { SavedReportsScreen } from './screens/SavedReports.jsx';
import { AdminBudgetsScreen } from './screens/AdminBudgets.jsx';
import { AdminRecoveryScreen } from './screens/AdminRecovery.jsx';
import { AdminAuditScreen } from './screens/AdminAudit.jsx';
import { AdminErrorsScreen } from './screens/AdminErrors.jsx';
import { AdminMetricsScreen } from './screens/AdminMetrics.jsx';
import { AdminQueryHistoryScreen } from './screens/AdminQueryHistory.jsx';

// v0.6.5.0 R-2FA-5：403 totp_enroll_required 共享判定 — 覆盖 mount me() + 所有 post-login
// prefetch catch（强制 2FA 默认 on 后，未 enroll 用户任一受保护端点都会 403 → 须跳 Enroll，非静默吞）
const isEnrollErr = (err) => err && err.status === 403 && err.detail === 'totp_enroll_required';

export default function App() {
  const [T, toggleTheme] = useTheme();
  const [user, setUser] = usePersist('cb_user', null);
  const [screen, setScreen] = usePersist('cb_screen', 'chat');
  // v0.6.5.2 F4-fe 硬伤1：loading 用 useState 非 usePersist —— 持久化 loading 会让刷新
  // 首帧 loading=false 先用旧 cb_user 闪主应用再等 me()（FOUC + 中间帧发请求）。loading 本就不该持久化。
  const [loading, setLoading] = useState(true);
  // v0.6.2.0 R-PB-B1-4：KNOT_TOTP_REQUIRED=true + user 未 enroll → server 返 403 totp_enroll_required
  const [needsEnroll, setNeedsEnroll] = useState(false);
  // v0.6.1.2 F1 — shared backend data lifted from ChatScreen，避免每次切屏 re-mount 时重 fetch
  const [convs, setConvs] = useState([]);
  const [dbOk, setDbOk] = useState(null);
  const [sourceCount, setSourceCount] = useState(null);

  // v0.6.5.2 F4-fe：cb_loading 由 usePersist 降级为 useState 后，eslint 识别 setLoading 为
  // useState setter → mount-only effect 内同步 setLoading 触发 set-state-in-effect（此前 usePersist
  // setter 不被识别）。同 prefetch effect（下方）禁该规则 —— mount-once 同步初始化是合理模式。
  /* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
  useEffect(() => {
    const token = localStorage.getItem('cb_token');
    if (!token) { setLoading(false); return; }
    api.me().then(u => {
      setUser(u);
      setLoading(false);
    }).catch(() => {
      // v0.6.5.2 F4-fe：删死代码 isEnrollErr 分支 —— me()(/api/auth/me) 命中 gate 白名单
      // （deps.py:144 /api/auth/ 前缀）永不返 403 totp_enroll_required。enroll 触发由
      // user-ready 后的 prefetch onErr（下方 useEffect）负责。401（含 rollout bump JWT_REVOKED）
      // 已由 api.js 拦截器清 token+reload。本 catch 仅兜 500/网络错 → 清 token 落 Login。
      localStorage.removeItem('cb_token');
      localStorage.removeItem('cb_user');
      setUser(null);
      setLoading(false);
    });
  }, []);
  /* eslint-enable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */

  // v0.6.1.2 F1 — 用户认证完成后并行 prefetch 共享数据；user 切换时重新 fetch
  // v0.6.0.14 lint sweep：sync 清空 + async prefetch 是 SPA 用户切换标准模式
  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    if (!user) { setConvs([]); setDbOk(null); setSourceCount(null); return; }
    // v0.6.5.0 R-2FA-5：post-login 路径也须跳 Enroll（login 直接返 token 不走 mount me()；
    // 强制 2FA 下未 enroll 用户 prefetch 会 403 → 共享 isEnrollErr 覆盖全部 catch，非静默吞）
    const onErr = (err) => { if (isEnrollErr(err)) setNeedsEnroll(true); };
    api.get('/api/conversations').then(setConvs).catch(onErr);
    api.get('/api/db/status').then(d => setDbOk(d.connected)).catch((e) => { onErr(e); setDbOk(false); });
    if (user.role === 'admin') {
      // v0.6.1.4 fix: endpoint is /api/admin/datasources not /api/admin/sources
      api.get('/api/admin/datasources')
         .then(ds => setSourceCount(Array.isArray(ds) ? ds.filter(s => s.status === 'online').length : 1))
         .catch(onErr);
    }
  }, [user?.id]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const handleLogin = (u) => {
    // 切账号时清掉上一个 user 的会话引用，防止 cb_conv 残留导致 POST 404
    localStorage.removeItem('cb_conv');
    setUser(u);
    setScreen('chat');
  };
  const handleLogout = () => {
    localStorage.removeItem('cb_token');
    localStorage.removeItem('cb_user');
    localStorage.removeItem('cb_screen');
    localStorage.removeItem('cb_conv');
    setUser(null);
    setScreen('chat');
    // v0.6.5.2 F4-fe：重置 needsEnroll —— 否则 Enroll 屏点退出后 needsEnroll 仍 true →
    // 渲染顺序 needsEnroll 在 !user 前 → 卡在 Enroll 屏无法回 Login。
    setNeedsEnroll(false);
  };
  const navigate = (s) => setScreen(s);

  if (loading) {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'grid', placeItems: 'center', background: T.bg }}>
        <Spinner size={28} color={T.accent}/>
      </div>
    );
  }

  // v0.6.2.0 R-PB-B1-4：needsEnroll = true 时（403 totp_enroll_required）强制 Enroll 屏
  // 没 user 但有 token + needsEnroll → Enroll；Enroll 完成后调 me 拿 user
  // v0.6.5.2 F4-fe：加 cb_token 守卫 —— 无 token 时（已登出 / rollout 清空）不渲染 Enroll，
  // 防 needsEnroll 残留 true 卡死（与 handleLogout setNeedsEnroll(false) 双保险）。
  if (needsEnroll && localStorage.getItem('cb_token')) {
    const handleEnrolled = () => {
      setNeedsEnroll(false);
      // 重新 me 拿 user 信息（enroll 完成后 server 不再返 403）
      api.me().then(u => { setUser(u); }).catch(handleLogout);
    };
    return <EnrollScreen T={T} user={user} onEnrolled={handleEnrolled} onLogout={handleLogout} onToggleTheme={toggleTheme}/>;
  }
  if (!user) return <LoginScreen T={T} onLogin={handleLogin} onToggleTheme={toggleTheme}/>;
  // v0.6.0.20 admin 默认账号强制改密守护：has token + must_change_password=1 → 强制改密屏
  // 改密成功后 onChanged({...user, must_change_password: false}) → 解禁主应用
  if (user.must_change_password) {
    return <ForceChangePasswordScreen T={T} user={user} onChanged={setUser} onToggleTheme={toggleTheme}/>;
  }

  const commonProps = { T, user, onToggleTheme: toggleTheme, onNavigate: navigate, onLogout: handleLogout,
                        convs, setConvs, dbOk, sourceCount };

  const adminTabMap = {
    'admin-sources': 'sources', 'admin-users': 'users', 'admin-models': 'models',
    'admin-knowledge': 'knowledge', 'admin-fewshots': 'fewshots', 'admin-prompts': 'prompts',
    'admin-catalog': 'catalog',
  };
  if (screen === 'saved-reports') return <SavedReportsScreen {...commonProps}/>;
  // v0.4.3 admin 看板（budgets + recovery 是独立屏，不走 AdminScreen tab）
  if (screen === 'admin-budgets' && user.role === 'admin') return <AdminBudgetsScreen {...commonProps}/>;
  if (screen === 'admin-recovery' && user.role === 'admin') return <AdminRecoveryScreen {...commonProps}/>;
  if (screen === 'admin-audit' && user.role === 'admin') return <AdminAuditScreen {...commonProps}/>;
  if (screen === 'admin-errors' && user.role === 'admin') return <AdminErrorsScreen {...commonProps}/>;
  if (screen === 'admin-metrics' && user.role === 'admin') return <AdminMetricsScreen {...commonProps}/>;
  if (screen === 'admin-history' && user.role === 'admin') return <AdminQueryHistoryScreen {...commonProps}/>;
  if (adminTabMap[screen] && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab={adminTabMap[screen]}/>;
  if (screen === 'admin' && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab="users"/>;
  // v0.2.1 批次2：API key / agent 模型已归口管理员；user-config 与 settings 重定向至「API & 模型」管理面板
  if ((screen === 'user-config' || screen === 'settings') && user.role === 'admin')
    return <AdminScreen {...commonProps} screen="admin-models" initialTab="models"/>;
  return <ChatScreen {...commonProps}/>;
}
