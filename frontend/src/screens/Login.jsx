/**
 * Login screen — v0.5.7 1:1 复刻 demo (Claude Design pilot)
 *
 * R-170 export name + props { T, onLogin, onToggleTheme } byte-equal
 * R-171 api.login + cb_token localStorage 链路 0 改动
 * R-172 error 文案 "用户名或密码错误" byte-equal
 * R-175 ≤ 200 行
 * R-181 页脚 "v0.5.7" 字面（与 main.py FastAPI version 同步守护）
 * R-184 input focus → T.accent 蓝青 outline/border
 * R-185 引用 KnotLogo（DOM 哨兵守护）
 * Q3   remember-me checkbox title 提示防误导
 */
import { useState } from 'react';
import { I, KnotLogo } from '../Shared.jsx';
import { Spinner } from '../utils.jsx';
import NarrativeMotif from '../decor/NarrativeMotif.jsx';
import { api } from '../api.js';

export function LoginScreen({ T, onLogin, onToggleTheme }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(localStorage.getItem('knot_remember') === '1');
  const [focused, setFocused] = useState(null);  // R-184 焦点 tracker

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setLoading(true); setError('');
    try {
      const data = await api.login(username.trim(), password);
      localStorage.setItem('cb_token', data.token);
      localStorage.setItem('knot_remember', remember ? '1' : '0');  // Q3 仅 UI flag
      onLogin(data.user);
    } catch {
      setError('用户名或密码错误');
    } finally { setLoading(false); }
  };

  // R-184 input wrapper：focus → T.accent 蓝青边
  const fieldBox = (key) => ({
    height: 44, padding: '0 14px',
    background: T.inputBg,
    border: `1px solid ${focused === key ? T.accent : T.inputBorder}`,
    borderRadius: 8, display: 'flex', alignItems: 'center', gap: 10,
    transition: 'border-color 0.15s',
  });

  const REMEMBER_TIP = '目前仅作为偏好记录，Token 有效期受服务器策略控制';

  return (
    <div style={{
      width: '100vw', height: '100vh',
      color: T.text, fontFamily: T.sans, fontSize: 13.5,
      display: 'grid', gridTemplateColumns: '1.05fr 1fr',
      position: 'relative', overflow: 'hidden',
    }}>
      {/* 主题切换按钮 — fixed 到 viewport 右上（永远跟随 viewport 边角） */}
      <button onClick={onToggleTheme} style={{
        position: 'fixed', top: 20, right: 22, zIndex: 3,
        width: 32, height: 32, borderRadius: 8, background: T.content,
        border: `1px solid ${T.border}`, color: T.subtext,
        display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      {/* Left narrative panel — 占满 viewport 左半，内容贴 viewport 边角；v0.5.25 删除 borderRight 灰线分隔 */}
      <div style={{
        position: 'relative', overflow: 'hidden',
        background: T.bg,
        padding: '48px 60px',
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      }}>
        {/* motif 铺满 left panel — radial-gradient 蔓延到边缘；SVG 内部居中固定尺寸 */}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          <NarrativeMotif T={T}/>
        </div>

        {/* 左上 Logo（贴 viewport 左上边角） */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <KnotLogo T={T} size={22}/>
        </div>

        {/* 左下 headline + desc（贴 viewport 左下边角） */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ fontSize: 13, color: T.accent, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 14 }}>
            Knowledge · Nexus · Objective · Trace
          </div>
          <div style={{ fontSize: 38, fontWeight: 600, color: T.text, lineHeight: 1.2, letterSpacing: '-0.03em' }}>
            复杂结于此，洞察始于此
          </div>
          <div style={{ fontSize: 14, color: T.subtext, marginTop: 18, lineHeight: 1.7, maxWidth: 480 }}>
            KNOT 协同三个专家级 Agent，不仅是生成 SQL 与图表，更在于它解开需求的乱麻，将散落在看板里的数据，转化为可追溯的决策支撑。
          </div>
        </div>
      </div>

      {/* Right form panel — 占满 viewport 右半，表单组件几何居中，footer 贴底 */}
      <div style={{
        position: 'relative', overflow: 'hidden',
        background: T.content,
        display: 'grid', placeItems: 'center',
        padding: '0 64px',
      }}>
        <div style={{ width: '100%', maxWidth: 380 }}>
        <div style={{ marginBottom: 40 }}>
          <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>
            sign in
          </div>
          <div style={{ fontSize: 28, fontWeight: 600, color: T.text, letterSpacing: '-0.025em' }}>欢迎回来</div>
          <div style={{ fontSize: 13, color: T.subtext, marginTop: 6 }}>使用账号登录访问你的数据空间</div>
        </div>

        <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* 账号 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>账号</label>
            <div style={fieldBox('user')}>
              <I.user style={{ color: T.muted, flexShrink: 0 }}/>
              <input autoFocus value={username} onChange={e => setUsername(e.target.value)}
                onFocus={() => setFocused('user')} onBlur={() => setFocused(null)}
                placeholder="用户名" type="text"
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 14, color: T.text, fontFamily: T.sans }}/>
            </div>
          </div>

          {/* 密码 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>密码</label>
            <div style={fieldBox('pw')}>
              <I.lock style={{ color: T.muted, flexShrink: 0 }}/>
              <input value={password} onChange={e => setPassword(e.target.value)}
                onFocus={() => setFocused('pw')} onBlur={() => setFocused(null)}
                placeholder="••••••••" type={showPw ? 'text' : 'password'}
                style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', fontSize: 14, color: T.text, fontFamily: showPw ? T.sans : T.mono, letterSpacing: showPw ? 'normal' : '0.2em' }}/>
              <button type="button" onClick={() => setShowPw(!showPw)} style={{
                width: 24, height: 24, display: 'inline-grid', placeItems: 'center',
                background: 'transparent', border: 'none', borderRadius: 6,
                color: T.muted, cursor: 'pointer',
              }}>{showPw ? <I.eyeoff/> : <I.eye/>}</button>
            </div>
          </div>

          {/* Remember + Forgot — Q3 title 提示防误导 */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13, color: T.subtext, cursor: 'pointer' }} title={REMEMBER_TIP}>
              <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} title={REMEMBER_TIP}
                style={{ accentColor: T.accent, width: 14, height: 14, cursor: 'pointer' }}/>
              7 天内自动登录
            </label>
            <a style={{ fontSize: 13, color: T.accent, textDecoration: 'none', cursor: 'default' }}>忘记密码？</a>
          </div>

          {/* Error banner — D6 oklch 红 */}
          {error && (
            <div style={{
              fontSize: 12.5, padding: '8px 12px', borderRadius: 6,
              color: 'oklch(62% 0.22 27)',
              background: 'color-mix(in oklch, oklch(62% 0.22 27) 12%, transparent)',
              border: '1px solid color-mix(in oklch, oklch(62% 0.22 27) 25%, transparent)',
            }}>{error}</div>
          )}

          {/* Submit — D7 demo 文案 "进入 KNOT" + arrow */}
          <button type="submit" disabled={loading} style={{
            marginTop: 12, width: '100%',
            padding: '13px 14px', border: 'none', borderRadius: 8,
            background: loading ? T.muted : T.accent, color: '#fff', fontFamily: 'inherit',
            fontSize: 14, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}>
            {loading ? <><Spinner size={14} color="#fff"/> 登录中…</> : <>进入 KNOT <I.send/></>}
          </button>
        </form>
        </div>

        {/* Footer — absolute 贴右板底（与左下文案对称）；R-181 "v0.5.7" 字面同步 */}
        <div style={{
          position: 'absolute', bottom: 24, left: 64, right: 64,
          fontSize: 12, color: T.muted, display: 'flex', justifyContent: 'space-between',
        }}>
          <span>v0.6.0.2 · build 202605151330</span>
          <span style={{ fontFamily: T.mono }}>knot.local</span>
        </div>
      </div>
    </div>
  );
}
