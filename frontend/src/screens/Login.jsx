/**
 * Login screen — v0.6.4.1 UI v2 复刻 (artboard knot_demo_ui/v0.6/artboards/login.jsx)
 *
 * R-PB-L-1 export name + props { T, onLogin, onToggleTheme } byte-equal
 * R-PB-L-2 api.login + cb_token localStorage 链路 byte-equal（need_totp 二阶段）+ race guard 2 行 carve-out（资深 ack）
 * R-PB-L-3 error 4 文案 / REMEMBER_TIP / 忘记密码 toast / 标题 / placeholder byte-equal
 * R-PB-L-4 VRP per artboard：共享 radial-gradient + 浮动 card + Btn primary lg + chipBg field（§9.3 token 映射）
 * R-PB-L-5 Btn primitive 采纳（type='submit' loading + iconRight={<I.arrow/>} node）；error → TOKENS_V2.err（27°→25° VRP 演进 ack）
 * R-PB-L-7 footer R-181（与 main.py version 同步守护）+ R-185 KnotLogo DOM 哨兵
 *
 * v0.5.7 pilot 沿用：R-184 focus 蓝青 / Q3 remember title 防误导 / TOTP 二阶段 6 位码验证
 */
import { useState } from 'react';
import { I, KnotLogo, TOKENS_V2 } from '../Shared.jsx';
import { toast } from '../utils.jsx';
import { Btn } from '../primitives.jsx';
import NarrativeMotif from '../decor/NarrativeMotif.jsx';
import { api } from '../api.js';

export function LoginScreen({ T, onLogin, onToggleTheme }) {
  const [step, setStep] = useState('login');   // v0.6.2.0 'login' | 'totp_verify'
  const [interimToken, setInterimToken] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(localStorage.getItem('knot_remember') === '1');
  const [focused, setFocused] = useState(null);  // R-184 焦点 tracker

  const submit = async (e) => {
    e.preventDefault();
    if (loading) return;   // §9.4b race guard — 闭 Enter-spam 重入（R-PB-L-2 carve-out 资深 ack）
    if (!username.trim() || !password) return;
    setLoading(true); setError('');
    try {
      const data = await api.login(username.trim(), password);
      // v0.6.2.0 need_totp 二阶段：暂不写 cb_token，跳 totp_verify 步骤
      if (data.need_totp) {
        setInterimToken(data.interim_token);
        setStep('totp_verify');
        setTotpCode('');
        return;
      }
      localStorage.setItem('cb_token', data.token);
      localStorage.setItem('knot_remember', remember ? '1' : '0');  // Q3 仅 UI flag
      onLogin(data.user);
    } catch {
      setError('用户名或密码错误');
    } finally { setLoading(false); }
  };

  // v0.6.2.0 R-PB-B1-7：TOTP 6 位码 / recovery code 验证（interim_token 鉴权）
  const submitTotp = async (e) => {
    e.preventDefault();
    if (loading) return;   // §9.4b race guard
    if (!totpCode.trim()) return;
    setLoading(true); setError('');
    try {
      const data = await api.totp.verify(totpCode.trim(), interimToken);
      localStorage.setItem('cb_token', data.token);
      localStorage.setItem('knot_remember', remember ? '1' : '0');
      onLogin(data.user);
    } catch (err) {
      setError(err.detail === 'TOTP_INVALID' ? '验证码错误' :
               err.detail === 'TOTP_LOCKED' ? '验证过于频繁，请稍后再试' : '验证失败');
    } finally { setLoading(false); }
  };

  // R-184 input wrapper：focus → T.accent 蓝青边；field bg = chipBg（§9.3 bgInset 等价）
  const fieldBox = (key) => ({
    height: 44, padding: '0 14px',
    background: T.chipBg,
    border: `1px solid ${focused === key ? T.accent : T.inputBorder}`,
    borderRadius: 8, display: 'flex', alignItems: 'center', gap: 10,
    transition: 'border-color 0.15s',
  });

  // error banner → TOKENS_V2.err（§9.4a 27°→25° VRP 演进 ack；停用 ad-hoc 红）
  const errBox = {
    fontSize: 12.5, padding: '8px 12px', borderRadius: 6,
    color: TOKENS_V2.err,
    background: `color-mix(in oklch, ${TOKENS_V2.err} 12%, transparent)`,
    border: `1px solid color-mix(in oklch, ${TOKENS_V2.err} 25%, transparent)`,
  };

  const REMEMBER_TIP = '目前仅作为偏好记录，Token 有效期受服务器策略控制';

  return (
    <div style={{
      width: '100vw', height: '100vh',
      color: T.text, fontFamily: T.sans, fontSize: 13.5,
      display: 'grid', gridTemplateColumns: '1.05fr 1fr',
      position: 'relative', overflow: 'hidden',
      // v0.6.4.1.1 修：去 artboard 写死 radial-gradient(at 22% 18%)（宽 viewport farthest-corner ellipse 胀开/偏移破 VRP）；
      // 回归 v0.5.7 标准 — 实底 fluid + 绿光由 motif 自身锚定（element-anchored，不随 viewport 偏移）
      background: T.chipBg,
    }}>
      {/* 主题切换按钮 — fixed 到 viewport 右上 */}
      <button onClick={onToggleTheme} style={{
        position: 'fixed', top: 20, right: 22, zIndex: 3,
        width: 32, height: 32, borderRadius: 8, background: T.content,
        border: `1px solid ${T.border}`, color: T.subtext,
        display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      {/* Left narrative panel — 透明（实底透出）；motif inset 0 铺满 left panel（v0.5.7 标准 — 绿光锚定）*/}
      <div style={{
        position: 'relative', overflow: 'hidden',
        padding: 56,
        display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      }}>
        {/* motif inset 0 铺满 left panel（v0.5.7 element-anchored 标准，替 artboard 写死 right 70%）*/}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          <NarrativeMotif T={T}/>
        </div>

        {/* 左上 Logo（R-185 哨兵） */}
        <div style={{ position: 'relative', zIndex: 1 }}>
          <KnotLogo T={T} size={22}/>
        </div>

        {/* 左下 headline + desc */}
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

      {/* Right form panel — 透明；表单浮动 card 几何居中，footer 贴底 */}
      <div style={{
        position: 'relative', overflow: 'hidden',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        padding: '56px 72px',
      }}>
        {/* 浮动 card — 两 step 共享同容器 maxWidth 440（Q2 防抖）*/}
        <div style={{
          width: '100%', maxWidth: 440,
          border: `1px solid ${T.border}`, borderRadius: 20,
          background: T.content,
          padding: '52px 52px',
          boxShadow: T.dark
            ? '0 1px 2px rgba(0,0,0,0.4), 0 20px 48px rgba(0,0,0,0.55)'
            : '0 1px 2px rgba(15,30,45,0.04), 0 20px 48px rgba(15,30,45,0.10)',
        }}>
          <div style={{ marginBottom: 36 }}>
            <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>
              {step === 'login' ? 'sign in' : 'verify'}
            </div>
            <div style={{ fontSize: 28, fontWeight: 600, color: T.text, letterSpacing: '-0.025em' }}>
              {step === 'login' ? '欢迎回来' : '验证身份'}
            </div>
            <div style={{ fontSize: 13, color: T.subtext, marginTop: 6 }}>
              {step === 'login' ? '使用账号登录访问你的数据空间' : '请输入认证 APP 中显示的 6 位动态码（或 10 位 recovery code）'}
            </div>
          </div>

          {step === 'totp_verify' ? (
            <form onSubmit={submitTotp} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <label style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>动态码 / Recovery Code</label>
                <div style={fieldBox('totp')}>
                  <I.shield style={{ color: T.muted, flexShrink: 0 }}/>
                  <input autoFocus value={totpCode} onChange={e => setTotpCode(e.target.value)}
                    onFocus={() => setFocused('totp')} onBlur={() => setFocused(null)}
                    placeholder="123456 或 ABCDE-12345" type="text" autoComplete="one-time-code"
                    style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none',
                             fontSize: 16, color: T.text, fontFamily: T.mono, letterSpacing: '0.15em' }}/>
                </div>
              </div>
              {error && <div style={errBox}>{error}</div>}
              <Btn T={T} variant="primary" size="lg" type="submit" loading={loading}
                   iconRight={<I.arrow/>} style={{ marginTop: 12, width: '100%' }}>验证</Btn>
              <button type="button" onClick={() => { setStep('login'); setError(''); setTotpCode(''); }} style={{
                fontSize: 13, color: T.subtext, background: 'transparent', border: 'none',
                cursor: 'pointer', padding: 4, textAlign: 'center',
              }}>← 返回登录</button>
            </form>
          ) : (
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
              {/* v0.6.0.7: 内测期密码重置走 admin — 点击提示文案而非走自助流程 */}
              <a onClick={(e) => { e.preventDefault(); toast('内测期间请联系管理员重置密码'); }}
                 style={{ fontSize: 13, color: T.accent, textDecoration: 'none', cursor: 'pointer' }}>忘记密码？</a>
            </div>

            {error && <div style={errBox}>{error}</div>}

            {/* Submit — Btn primary lg + iconRight arrow（artboard "进入 KNOT"）*/}
            <Btn T={T} variant="primary" size="lg" type="submit" loading={loading}
                 iconRight={<I.arrow/>} style={{ marginTop: 12, width: '100%' }}>进入 KNOT</Btn>
          </form>
          )}
        </div>

        {/* Footer — absolute 贴右板底；R-181 version 字面同步 */}
        <div style={{
          position: 'absolute', bottom: 24, left: 80, right: 80,
          fontSize: 12, color: T.muted, display: 'flex', justifyContent: 'space-between',
        }}>
          <span>v0.6.4.1 · build 202606170600</span>
          <span style={{ fontFamily: T.mono }}>knot.local</span>
        </div>
      </div>
    </div>
  );
}
