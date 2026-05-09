import { useState } from 'react';
import { I } from '../Shared.jsx';
import { Spinner } from '../utils.jsx';
import { api } from '../api.js';

export function LoginScreen({ T, onLogin, onToggleTheme }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPw, setShowPw] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true); setError('');
    try {
      const data = await api.login(username.trim(), password);
      localStorage.setItem('cb_token', data.token);
      onLogin(data.user);
    } catch {
      setError('用户名或密码错误');
    } finally { setLoading(false); }
  };

  const iconBtnStyle = {
    width: 28, height: 28, display: 'inline-grid', placeItems: 'center',
    background: 'transparent', border: 'none', borderRadius: 6,
    color: T.subtext, cursor: 'pointer',
  };

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex',
      background: T.bg, color: T.text, fontFamily: T.sans, fontSize: 13.5,
    }}>
      <button onClick={onToggleTheme} style={{
        position: 'absolute', top: 20, right: 22,
        width: 32, height: 32, borderRadius: 8, background: T.content,
        border: `1px solid ${T.border}`, color: T.subtext,
        display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      {/* Left brand panel */}
      <div className="cb-grid-bg" style={{
        flex: 1, borderRight: `1px solid ${T.border}`,
        padding: '48px 60px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: T.accent, display: 'grid', placeItems: 'center', color: '#fff' }}><I.sparkle/></div>
          <span style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em', color: T.text }}>KNOT</span>
          <span style={{ fontSize: 11, color: T.muted, padding: '2px 7px', background: T.chipBg, border: `1px solid ${T.border}`, borderRadius: 999, marginLeft: 4 }}>v 0.2</span>
        </div>

        <div>
          <div style={{ fontSize: 32, fontWeight: 600, color: T.text, lineHeight: 1.2, letterSpacing: '-0.02em', marginBottom: 14 }}>
            用自然语言<br/>查询你的业务数据
          </div>
          <div style={{ fontSize: 14, color: T.subtext, maxWidth: 360, lineHeight: 1.6 }}>
            用中文提问，自动生成 SQL、展示图表与数据洞察。
          </div>
          <div style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 360 }}>
            {['接入任意 MySQL 兼容数据库', '多模型支持（Claude / GPT / Gemini / DeepSeek）', '管理员统一管理账号与数据源'].map((t, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: T.subtext }}>
                <span style={{ width: 18, height: 18, borderRadius: '50%', background: T.accentSoft, color: T.accent, display: 'grid', placeItems: 'center', flexShrink: 0 }}><I.check width="10" height="10"/></span>
                {t}
              </div>
            ))}
          </div>
        </div>

        <div style={{ fontSize: 11, color: T.muted }}>© 2026 KNOT · 内部系统</div>
      </div>

      {/* Right form */}
      <div style={{ width: 420, flexShrink: 0, padding: '80px 48px', display: 'flex', flexDirection: 'column', justifyContent: 'center', background: T.content }}>
        <div style={{ fontSize: 22, fontWeight: 600, color: T.text, letterSpacing: '-0.015em', marginBottom: 6 }}>欢迎回来</div>
        <div style={{ fontSize: 13, color: T.muted, marginBottom: 26 }}>使用你的账号登录 KNOT</div>

        <form onSubmit={submit}>
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>账号</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '9px 11px' }}>
              <I.user style={{ color: T.muted, flexShrink: 0 }}/>
              <input autoFocus value={username} onChange={e => setUsername(e.target.value)}
                placeholder="用户名" type="text" style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: T.sans }}/>
            </div>
          </div>
          <div style={{ marginBottom: 18 }}>
            <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>密码</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '9px 11px' }}>
              <I.lock style={{ color: T.muted, flexShrink: 0 }}/>
              <input value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••" type={showPw ? 'text' : 'password'}
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 13, color: T.text, fontFamily: T.sans }}/>
              <button type="button" onClick={() => setShowPw(!showPw)} style={{ ...iconBtnStyle, width: 20, height: 20 }}>{showPw ? <I.eyeoff/> : <I.eye/>}</button>
            </div>
          </div>
          {error && <div style={{ color: T.accent, fontSize: 12.5, marginBottom: 12, padding: '8px 12px', background: T.accentSoft, borderRadius: 6 }}>{error}</div>}
          <button type="submit" disabled={loading} style={{
            width: '100%', padding: '11px 14px', border: 'none', borderRadius: 8,
            background: loading ? T.muted : T.accent, color: '#fff', fontFamily: 'inherit',
            fontSize: 13.5, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
            {loading ? <><Spinner size={14} color="#fff"/> 登录中…</> : '登录'}
          </button>
        </form>

        <div style={{ marginTop: 22, fontSize: 11, color: T.muted, textAlign: 'center' }}>
          内部系统 · 账号由管理员分配
        </div>
      </div>
    </div>
  );
}
