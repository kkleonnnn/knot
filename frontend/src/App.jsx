import { useEffect } from 'react';
import { useTheme, usePersist, Spinner } from './utils.jsx';
import { api } from './api.js';
import { LoginScreen } from './screens/Login.jsx';
import { ChatScreen } from './screens/Chat.jsx';
import { AdminScreen } from './screens/Admin.jsx';

export default function App() {
  const [T, toggleTheme] = useTheme();
  const [user, setUser] = usePersist('cb_user', null);
  const [screen, setScreen] = usePersist('cb_screen', 'chat');
  const [loading, setLoading] = usePersist('cb_loading', true);

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

  const commonProps = { T, user, onToggleTheme: toggleTheme, onNavigate: navigate, onLogout: handleLogout };

  const adminTabMap = {
    'admin-sources': 'sources', 'admin-users': 'users', 'admin-models': 'models',
    'admin-knowledge': 'knowledge', 'admin-fewshots': 'fewshots', 'admin-prompts': 'prompts',
    'admin-catalog': 'catalog',
  };
  if (adminTabMap[screen] && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab={adminTabMap[screen]}/>;
  if (screen === 'admin' && user.role === 'admin') return <AdminScreen {...commonProps} screen={screen} initialTab="users"/>;
  // v0.2.1 批次2：API key / agent 模型已归口管理员；user-config 与 settings 重定向至「API & 模型」管理面板
  if ((screen === 'user-config' || screen === 'settings') && user.role === 'admin')
    return <AdminScreen {...commonProps} screen="admin-models" initialTab="models"/>;
  return <ChatScreen {...commonProps}/>;
}
