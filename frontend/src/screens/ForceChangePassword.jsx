// v0.6.0.20 admin 默认账号强制改密守护屏
// 触发：login response.user.must_change_password === true（或业务 API 返回 403 detail=must_change_password）
// 视觉：沿用 v0.5.7 Login pilot 模式 + R-PA-PB-V1 视觉延续性立约（brandSoft 8% inset + OKLCH 25 字段 + I 36 icons）
// 业务：调 api.changePassword(old, new)；成功后 setUser({...user, must_change_password: false}) → 进入主应用
import { useState } from 'react';
import { I, KnotLogo } from '../Shared.jsx';
import { api } from '../api.js';

const _MIN_LEN = 8;  // 与后端 services/auth_service._MIN_NEW_PASSWORD_LEN 字面对齐

export function ForceChangePasswordScreen({ T, user, onChanged, onToggleTheme }) {
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);

  const canSubmit = oldPwd && newPwd.length >= _MIN_LEN && newPwd === confirmPwd && !loading;
  const newPwdHint = (() => {
    if (!newPwd) return '';
    if (newPwd.length < _MIN_LEN) return `至少 ${_MIN_LEN} 字符`;
    if (newPwd === oldPwd) return '不能与旧密码相同';
    if (newPwd === 'admin123') return '不能使用系统默认值';
    if (confirmPwd && newPwd !== confirmPwd) return '两次输入不一致';
    return '✓ 密码合规';
  })();

  const onSubmit = async (e) => {
    e.preventDefault();
    setErr('');
    if (!canSubmit) return;
    setLoading(true);
    try {
      await api.changePassword(oldPwd, newPwd);
      onChanged({ ...user, must_change_password: false });
    } catch (e) {
      setErr(e.message || '修改密码失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      width: '100vw', height: '100vh', background: T.bg,
      display: 'grid', placeItems: 'center', fontFamily: T.sans, color: T.text,
    }}>
      <button onClick={onToggleTheme} title="切换主题" style={{
        position: 'fixed', top: 20, right: 24, width: 32, height: 32,
        border: `1px solid ${T.border}`, borderRadius: 6, background: 'transparent',
        color: T.muted, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      <div style={{
        width: 440, padding: '36px 40px', background: T.content,
        border: `1px solid ${T.border}`, borderRadius: 12,
        boxShadow: T.dark ? '0 8px 32px rgba(0,0,0,0.4)' : '0 8px 32px rgba(0,0,0,0.08)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <KnotLogo T={T} size={28}/>
          <span style={{ fontSize: 16, fontWeight: 600, color: T.text }}>KNOT</span>
          <span style={{
            marginLeft: 'auto', fontSize: 10, color: T.warn,
            padding: '2px 8px', borderRadius: 4, fontFamily: T.mono, letterSpacing: '0.06em',
            background: `color-mix(in oklch, ${T.warn} 12%, transparent)`,
            border: `1px solid color-mix(in oklch, ${T.warn} 25%, transparent)`,
            textTransform: 'uppercase',
          }}>首次登录</span>
        </div>

        <div style={{ fontSize: 19, fontWeight: 600, marginBottom: 8 }}>请设置新密码</div>
        <div style={{
          fontSize: 12.5, color: T.subtext, lineHeight: 1.55, marginBottom: 22,
          padding: '10px 12px',
          background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
          borderLeft: `3px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
          borderRadius: 4,
        }}>
          检测到您当前用的是默认密码 <span style={{ fontFamily: T.mono, color: T.warn }}>admin123</span>。
          为安全起见，必须先修改密码才能继续使用 KNOT。
        </div>

        <form onSubmit={onSubmit}>
          <div style={{ fontSize: 12, color: T.subtext, marginBottom: 6, fontWeight: 500 }}>当前密码</div>
          <input type="password" autoFocus value={oldPwd} onChange={e => setOldPwd(e.target.value)}
                 placeholder="输入当前密码"
                 style={fieldStyle(T)}/>

          <div style={{ fontSize: 12, color: T.subtext, marginTop: 14, marginBottom: 6, fontWeight: 500,
                        display: 'flex', alignItems: 'center', gap: 4 }}>
            <span>新密码</span>
            <span style={{ color: T.muted, fontSize: 10.5 }}>(至少 {_MIN_LEN} 字符 / 不可为 admin123)</span>
          </div>
          <div style={{ position: 'relative' }}>
            <input type={showNew ? 'text' : 'password'} value={newPwd} onChange={e => setNewPwd(e.target.value)}
                   placeholder="输入新密码"
                   style={fieldStyle(T)}/>
            <button type="button" onClick={() => setShowNew(s => !s)} style={{
              position: 'absolute', right: 8, top: 8, width: 24, height: 24,
              border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>{showNew ? <I.eyeoff/> : <I.eye/>}</button>
          </div>
          {newPwdHint && (
            <div style={{
              fontSize: 11.5, marginTop: 4,
              color: newPwdHint.startsWith('✓') ? T.success : T.warn,
              fontFamily: T.mono,
            }}>{newPwdHint}</div>
          )}

          <div style={{ fontSize: 12, color: T.subtext, marginTop: 14, marginBottom: 6, fontWeight: 500 }}>确认新密码</div>
          <input type="password" value={confirmPwd} onChange={e => setConfirmPwd(e.target.value)}
                 placeholder="再次输入新密码"
                 style={fieldStyle(T)}/>

          {err && (
            <div style={{
              marginTop: 14, padding: '8px 12px', borderRadius: 6, fontSize: 12,
              color: T.warn,
              background: `color-mix(in oklch, ${T.warn} 12%, transparent)`,
              border: `1px solid color-mix(in oklch, ${T.warn} 25%, transparent)`,
            }}>{err}</div>
          )}

          <button type="submit" disabled={!canSubmit} style={{
            width: '100%', marginTop: 22, padding: '11px 14px',
            background: canSubmit ? T.accent : T.border,
            color: canSubmit ? T.sendFg : T.muted,
            border: 'none', borderRadius: 7, fontSize: 14, fontWeight: 600,
            cursor: canSubmit ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
            transition: 'background .2s',
          }}>{loading ? '修改中…' : '修改密码并进入 KNOT'}</button>
        </form>

        <div style={{ marginTop: 18, fontSize: 11.5, color: T.muted, textAlign: 'center', fontFamily: T.mono }}>
          {user?.username && `账户 · ${user.username}`}
        </div>
      </div>
    </div>
  );
}

function fieldStyle(T) {
  return {
    width: '100%', padding: '9px 11px', fontSize: 13.5,
    background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
    color: T.text, fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box',
  };
}
