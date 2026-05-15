import { useEffect, useState } from 'react';
import { useTheme, usePersist, Spinner } from './utils.jsx';
import { api } from './api.js';
import { LoginScreen } from './screens/Login.jsx';
import { ChatScreen } from './screens/Chat.jsx';
import { AdminScreen } from './screens/Admin.jsx';
import { SavedReportsScreen } from './screens/SavedReports.jsx';
import { AdminBudgetsScreen } from './screens/AdminBudgets.jsx';
import { AdminRecoveryScreen } from './screens/AdminRecovery.jsx';
import { AdminAuditScreen } from './screens/AdminAudit.jsx';
import { AdminErrorsScreen } from './screens/AdminErrors.jsx';

export default function App() {
  const [T, toggleTheme] = useTheme();
  const [user, setUser] = usePersist('cb_user', null);
  const [screen, setScreen] = usePersist('cb_screen', 'chat');
  const [loading, setLoading] = usePersist('cb_loading', true);
  // v0.6.1.2 F1 — shared backend data lifted from ChatScreen，避免每次切屏 re-mount 时重 fetch
  const [convs, setConvs] = useState([]);
  const [dbOk, setDbOk] = useState(null);
  const [sourceCount, setSourceCount] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('cb_token');
    if (!token) { setLoading(false); return; }
    api.me().then(u => {
      setUser(u);
      setLoading(false);
    }).catch(() => {
      localStorage.removeItem('cb_token');
      setUser(null);
      setLoading(false);
    });
  }, []);

  // v0.6.1.2 F1 — 用户认证完成后并行 prefetch 共享数据；user 切换时重新 fetch
  useEffect(() => {
    if (!user) { setConvs([]); setDbOk(null); setSourceCount(null); return; }
    api.get('/api/conversations').then(setConvs).catch(() => {});
    api.get('/api/db/status').then(d => setDbOk(d.connected)).catch(() => setDbOk(false));
    if (user.role === 'admin') {
      api.get('/api/admin/sources')
         .then(ds => setSourceCount(Array.isArray(ds) ? ds.filter(s => s.status === 'online').length : 1))
         .catch(() => {});
    }
  }, [user?.id]);

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
  };
  const navigate = (s) => setScreen(s);

  if (loading) {
    return (
      <div style={{ width: '100vw', height: '100vh', display: 'grid', placeItems: 'center', background: T.bg }}>
        <Spinner size={28} color={T.accent}/>
      </div>
    );
  }

  if (!user) return <LoginScreen T={T} onLogin={handleLogin} onToggleTheme={toggleTheme}/>;

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
  if (adminTabMap[screen] && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab={adminTabMap[screen]}/>;
  if (screen === 'admin' && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab="users"/>;
  // v0.2.1 批次2：API key / agent 模型已归口管理员；user-config 与 settings 重定向至「API & 模型」管理面板
  if ((screen === 'user-config' || screen === 'settings') && user.role === 'admin')
    return <AdminScreen {...commonProps} screen="admin-models" initialTab="models"/>;
  return <ChatScreen {...commonProps}/>;
}
