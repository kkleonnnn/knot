/**
 * Enroll screen — v0.6.2.0 TOTP 2FA 强制 enroll 4-step（R-PA-PB-V1 视觉延续）
 *
 * R-PB-B1-7（守护者第 12 次 §III.3 修订）：业界标准对齐 — 1 次 6 位码 + 强制下载 recovery codes
 *   Step 1: 显示 QR + secret 字面
 *   Step 2: 1 次 6 位动态码验证（撤回 v1 双码确认）
 *   Step 3: 显示 10 个 recovery codes + 强制下载（未下载"完成"按钮 disabled）
 *   Step 4: 确认弹窗"已妥善保存 recovery codes?" → 提交
 *
 * R-PB-B1-2 不锁死：任一 step 失败 / 取消 → totp_enrolled_at 仍 NULL → 可重新发起 enroll
 * R-227.5.1 装饰豁免：步骤标题 ENROLL / VERIFY / BACKUP / CONFIRM mono uppercase
 */
import { useEffect, useState } from 'react';
import { I, KnotLogo, TOKENS_V2 } from '../Shared.jsx';
import { Spinner, toast } from '../utils.jsx';
import { api } from '../api.js';

export function EnrollScreen({ T, user, onEnrolled, onLogout, onToggleTheme }) {
  const [step, setStep] = useState(1);             // 1:QR / 2:verify / 3:backup / 4:confirm
  const [secret, setSecret] = useState('');
  const [qrDataurl, setQrDataurl] = useState(''); // 服务端生成的 PNG base64 data URL
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [downloaded, setDownloaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1: enroll_init — 生成 secret + QR payload（不持久化）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.totp.enrollInit();
        if (cancelled) return;
        setSecret(data.secret);
        setQrDataurl(data.qr_dataurl);
      } catch (err) {
        if (!cancelled) setError(err.detail || 'enroll_init 失败');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const submitCode = async (e) => {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true); setError('');
    try {
      const data = await api.totp.enrollComplete(secret, code.trim());
      setRecoveryCodes(data.recovery_codes || []);
      setStep(3);
    } catch (err) {
      setError(err.detail === 'TOTP_INVALID' ? '验证码错误，请重试' : (err.detail || '验证失败'));
    } finally { setLoading(false); }
  };

  const downloadRecoveryCodes = () => {
    const content = `KNOT 2FA Recovery Codes — ${user?.username || 'user'}\n` +
                    `生成时间: ${new Date().toISOString()}\n\n` +
                    `⚠️ 妥善保管 — 每个 code 仅能使用一次\n\n` +
                    recoveryCodes.map((c, i) => `${i + 1}. ${c}`).join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `knot-2fa-recovery-codes-${user?.username || 'user'}.txt`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setDownloaded(true);
  };

  const confirm = () => {
    if (!downloaded) {
      toast('必须先下载 recovery codes 才能完成');
      return;
    }
    if (!confirm_window('已妥善保存 recovery codes? 完成后将进入 KNOT')) return;
    onEnrolled();
  };

  // 安全的 window.confirm wrapper（避免 ESLint no-restricted-globals）
  function confirm_window(msg) { return window.confirm(msg); }

  return (
    <div style={{
      width: '100vw', height: '100vh',
      color: T.text, fontFamily: T.sans, fontSize: 13.5,
      display: 'grid', placeItems: 'center',
      background: T.bg, position: 'relative', overflow: 'auto',
    }}>
      <button onClick={onToggleTheme} style={{
        position: 'fixed', top: 20, right: 22, zIndex: 3,
        width: 32, height: 32, borderRadius: 8, background: T.content,
        border: `1px solid ${T.border}`, color: T.subtext,
        display: 'grid', placeItems: 'center', cursor: 'pointer',
      }}>{T.dark ? <I.sun/> : <I.moon/>}</button>

      <div style={{ width: '100%', maxWidth: 460, padding: '40px 32px' }}>
        <div style={{ marginBottom: 28, display: 'flex', alignItems: 'center', gap: 12 }}>
          <KnotLogo T={T} size={22}/>
          <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            {['enroll', 'verify', 'backup', 'confirm'][step - 1]} · step {step}/4
          </span>
        </div>

        {step === 1 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text }}>启用双因素认证 (2FA)</div>
            <div style={{ fontSize: 13, color: T.subtext, lineHeight: 1.7 }}>
              用 Google Authenticator / Authy / 1Password 等 APP 扫描下方二维码（或手动输入 secret）：
            </div>
            <div style={{
              background: T.content, border: `1px solid ${T.border}`, borderRadius: 12,
              padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16,
            }}>
              {qrDataurl ? (
                <img alt="QR" src={qrDataurl}
                     style={{ width: 200, height: 200, background: '#fff', padding: 8, borderRadius: 8 }}/>
              ) : <Spinner size={28} color={T.accent}/>}
              <div style={{ fontFamily: T.mono, fontSize: 12, color: T.subtext, wordBreak: 'break-all', textAlign: 'center' }}>
                {secret || '生成中…'}
              </div>
            </div>
            <button onClick={() => setStep(2)} disabled={!qrDataurl} style={{
              padding: '13px 14px', border: 'none', borderRadius: 8,
              background: qrDataurl ? T.accent : T.muted, color: T.sendFg,
              fontSize: 14, fontWeight: 600, cursor: qrDataurl ? 'pointer' : 'not-allowed',
            }}>下一步 — 输入动态码</button>
            <button onClick={onLogout} style={{
              fontSize: 13, color: T.subtext, background: 'transparent', border: 'none',
              cursor: 'pointer', padding: 4,
            }}>← 退出登录</button>
            {error && <ErrorBanner T={T} msg={error}/>}
          </div>
        )}

        {step === 2 && (
          <form onSubmit={submitCode} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text }}>输入 6 位动态码</div>
            <div style={{ fontSize: 13, color: T.subtext, lineHeight: 1.7 }}>
              在认证 APP 中查看当前 6 位码（每 30 秒刷新一次）
            </div>
            <input autoFocus value={code} onChange={e => setCode(e.target.value)}
              placeholder="123456" inputMode="numeric" maxLength={6} autoComplete="one-time-code"
              style={{
                padding: '16px 18px', fontSize: 22, fontFamily: T.mono, letterSpacing: '0.3em',
                textAlign: 'center', background: T.content, color: T.text,
                border: `1px solid ${T.border}`, borderRadius: 10, outline: 'none',
              }}/>
            {error && <ErrorBanner T={T} msg={error}/>}
            <button type="submit" disabled={loading || code.length < 6} style={{
              padding: '13px 14px', border: 'none', borderRadius: 8,
              background: (loading || code.length < 6) ? T.muted : T.accent, color: T.sendFg,
              fontSize: 14, fontWeight: 600, cursor: (loading || code.length < 6) ? 'not-allowed' : 'pointer',
            }}>{loading ? <><Spinner size={14} color={T.sendFg}/> 验证中…</> : '验证 + 继续'}</button>
            <button type="button" onClick={() => setStep(1)} style={{
              fontSize: 13, color: T.subtext, background: 'transparent', border: 'none', cursor: 'pointer', padding: 4,
            }}>← 返回扫码</button>
          </form>
        )}

        {step === 3 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text }}>保存 Recovery Codes</div>
            <div style={{
              fontSize: 13, padding: '10px 14px', borderRadius: 8,
              background: `color-mix(in oklch, ${T.warn} 13%, transparent)`,
              border: `1px solid color-mix(in oklch, ${T.warn} 25%, transparent)`,
              color: T.warn,
            }}>⚠️ 这是手机丢失时唯一的恢复方式 — 务必下载保存</div>
            <div style={{
              background: T.content, border: `1px solid ${T.border}`, borderRadius: 10,
              padding: 16, fontFamily: T.mono, fontSize: 13, lineHeight: 1.9,
              display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6,
            }}>
              {recoveryCodes.map((c, i) => (
                <div key={i} style={{ color: T.text }}>{i + 1}. {c}</div>
              ))}
            </div>
            <button onClick={downloadRecoveryCodes} style={{
              padding: '13px 14px', border: `1px solid ${T.accent}`, borderRadius: 8,
              background: downloaded ? `color-mix(in oklch, ${T.accent} 12%, transparent)` : T.content,
              color: T.accent, fontSize: 14, fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}>{downloaded ? <>✓ 已下载（点击重新下载）</> : <>下载 recovery codes 文件</>}</button>
            <button onClick={() => setStep(4)} disabled={!downloaded} style={{
              padding: '13px 14px', border: 'none', borderRadius: 8,
              background: downloaded ? T.accent : T.muted, color: T.sendFg,
              fontSize: 14, fontWeight: 600, cursor: downloaded ? 'pointer' : 'not-allowed',
            }}>下一步</button>
          </div>
        )}

        {step === 4 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text }}>确认完成</div>
            <div style={{ fontSize: 13, color: T.subtext, lineHeight: 1.7 }}>
              下次登录时除账号密码外，还需输入认证 APP 显示的动态码。<br/>
              手机丢失？使用 recovery code（已下载文件）登录。
            </div>
            <button onClick={confirm} style={{
              padding: '13px 14px', border: 'none', borderRadius: 8,
              background: T.accent, color: T.sendFg, fontSize: 14, fontWeight: 600, cursor: 'pointer',
            }}>完成 — 进入 KNOT</button>
            <button onClick={() => setStep(3)} style={{
              fontSize: 13, color: T.subtext, background: 'transparent', border: 'none',
              cursor: 'pointer', padding: 4,
            }}>← 重看 recovery codes</button>
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorBanner({ T: _T, msg }) {
  return (
    <div style={{
      fontSize: 12.5, padding: '8px 12px', borderRadius: 6,
      color: TOKENS_V2.err,
      background: `color-mix(in oklch, ${TOKENS_V2.err} 12%, transparent)`,
      border: `1px solid color-mix(in oklch, ${TOKENS_V2.err} 25%, transparent)`,
    }}>{msg}</div>
  );
}
