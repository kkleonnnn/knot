// v0.6.0.14 lint sweep：utils.jsx 是 Foundation 契约文件（v0.5.6 R-159 锁定 8 exports）—
// hooks (useTheme/usePersist) + helpers (toast) + components (Modal/ModalHeader/Input/Select/Spinner)
// 必须共存以维持单一 import 入口。同 Shared.jsx 决议。
/* eslint-disable react-refresh/only-export-components */
import { useEffect, useState } from 'react';
import { buildTheme, I, iconBtn } from './Shared.jsx';

// v0.9.0 外观预设 store（cb_appearance: {mode, hue, style}）— 模块级订阅，Shell 外观弹层
// v0.9.2 mode: 'light'|'dark'|'system'（跟随系统听 matchMedia）；旧 {dark:boolean} / cb_theme 读迁移 + 双写兼容。
const APPEAR_KEY = 'cb_appearance';
const appearListeners = new Set();
const _mq = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

export function getAppearance() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(APPEAR_KEY) || '{}') || {}; } catch { /* 解析失败保留默认 {} */ }
  const legacyDark = localStorage.getItem('cb_theme');
  const mode = ['light', 'dark', 'system'].includes(saved.mode) ? saved.mode
    : typeof saved.dark === 'boolean' ? (saved.dark ? 'dark' : 'light')   // v0.9.0 旧形状
    : legacyDark ? (legacyDark === 'dark' ? 'dark' : 'light') : 'dark';
  return { mode, hue: saved.hue || 'cyan', style: saved.style || 'frosted' };
}

export function resolveDark(mode) {
  return mode === 'system' ? !!(_mq && _mq.matches) : mode === 'dark';
}

export function setAppearance(patch) {
  const next = { ...getAppearance(), ...patch };
  try {
    localStorage.setItem(APPEAR_KEY, JSON.stringify(next));
    localStorage.setItem('cb_theme', resolveDark(next.mode) ? 'dark' : 'light');  // ErrorBoundary 等旧读点
  } catch { /* 隐私模式 / 配额 静默降级 */ }
  appearListeners.forEach(fn => fn(next));
}

// v0.9.3 — 全局确认框（替代 window.confirm，风格跟随玻璃 chrome）：Promise API + 单例宿主。
// 用法：if (!await confirmDialog('删除？')) return;  宿主 <ConfirmHost/> 在 main.jsx 挂 App 兄弟节点。
let _confirmResolve = null;
const confirmListeners = new Set();

export function confirmDialog(message, { confirmText = '确认', cancelText = '取消' } = {}) {
  return new Promise(resolve => {
    if (_confirmResolve) _confirmResolve(false);  // 罕见：叠加请求时取消前一个
    _confirmResolve = resolve;
    confirmListeners.forEach(fn => fn({ message, confirmText, cancelText }));
  });
}

export function ConfirmHost() {
  const [T] = useTheme();
  const [req, setReq] = useState(null);
  const done = ok => { setReq(null); if (_confirmResolve) { _confirmResolve(ok); _confirmResolve = null; } };
  useEffect(() => {
    confirmListeners.add(setReq);
    return () => confirmListeners.delete(setReq);
  }, []);
  useEffect(() => {
    if (!req) return;
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); done(false); }
      if (e.key === 'Enter') { e.preventDefault(); done(true); }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [req]);
  if (!req) return null;
  const btn = primary => ({
    padding: '8px 18px', borderRadius: 9, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13,
    fontWeight: primary ? 500 : 400,
    background: primary ? T.accent : 'transparent',
    color: primary ? T.sendFg : T.subtext,
    border: primary ? 'none' : `1px solid ${T.border}`,
    boxShadow: primary ? (T.glow || 'none') : 'none',
  });
  return (
    <div onClick={e => e.target === e.currentTarget && done(false)} style={{
      position: 'fixed', inset: 0, background: 'rgba(14,17,23,0.45)', backdropFilter: 'blur(8px)',
      display: 'grid', placeItems: 'center', zIndex: 1200,
    }}>
      <div style={{
        width: 380, background: T.content, borderRadius: 16, border: `1px solid ${T.glassBorder || T.border}`,
        backdropFilter: T.blur, WebkitBackdropFilter: T.blur,
        boxShadow: T.panelShadow || '0 24px 60px -20px rgba(0,0,0,0.4)',
        padding: '22px 22px 18px', display: 'flex', flexDirection: 'column', gap: 18,
        color: T.text, fontFamily: T.sans,
      }}>
        <div style={{ fontSize: 14, lineHeight: 1.65 }}>{req.message}</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button onClick={() => done(false)} style={btn(false)}>{req.cancelText}</button>
          <button onClick={() => done(true)} autoFocus style={btn(true)}>{req.confirmText}</button>
        </div>
      </div>
    </div>
  );
}

export function useTheme() {
  const [app, setApp] = useState(getAppearance);
  const [, bump] = useState(0);
  useEffect(() => {
    appearListeners.add(setApp);
    const onMq = () => bump(n => n + 1);  // mode==='system' 时跟随 OS 切换重算
    if (_mq) _mq.addEventListener('change', onMq);
    return () => { appearListeners.delete(setApp); if (_mq) _mq.removeEventListener('change', onMq); };
  }, []);
  const dark = resolveDark(app.mode);
  // toggle 保留给无弹层的屏（Login/Enroll/ForceChangePassword 固定按钮）：翻转当前解析值并退出 system
  const toggle = () => setAppearance({ mode: resolveDark(getAppearance().mode) ? 'light' : 'dark' });
  return [buildTheme(dark, app), toggle];
}

export function usePersist(key, def) {
  const [v, set] = useState(() => {
    try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : def; } catch { return def; }
  });
  const setP = nv => {
    set(nv);
    try { localStorage.setItem(key, JSON.stringify(nv)); } catch { /* localStorage 写失败（隐私模式 / 配额）静默降级 */ }
  };
  return [v, setP];
}

export function toast(msg, err = false) {
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
    // v0.5.6 R-167 语义色：error 朱红 27° / success 翠绿 145°（远离 brand 195°）
    background: err ? 'oklch(62% 0.22 27)' : 'oklch(72% 0.18 145)', color: '#fff',
    padding: '9px 18px', borderRadius: 8, fontSize: 13.5, fontFamily: 'inherit',
    boxShadow: '0 4px 20px rgba(0,0,0,0.2)', zIndex: 9999, animation: 'cb-fadein .3s ease',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export function Modal({ T, onClose, children, width = 480 }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(14,17,23,0.45)', backdropFilter: 'blur(8px)',
      display: 'grid', placeItems: 'center', zIndex: 1000,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      {/* v0.9.0 玻璃弹窗：blur + glassBorder + panelShadow（overlay 已 blur 8，卡内容不透） */}
      <div style={{
        width, background: T.content, borderRadius: 16, border: `1px solid ${T.glassBorder || T.border}`,
        backdropFilter: T.blur, WebkitBackdropFilter: T.blur,
        boxShadow: T.panelShadow || '0 24px 60px -20px rgba(0,0,0,0.4)', overflow: 'hidden',
      }}>
        {children}
      </div>
    </div>
  );
}

export function ModalHeader({ T, title, subtitle, onClose }) {
  return (
    <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
      <div>
        <div style={{ fontSize: 14, color: T.text, fontWeight: 650 }}>{title}</div>
        {subtitle && <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>{subtitle}</div>}
      </div>
      <button onClick={onClose} style={iconBtn(T)}><I.x/></button>
    </div>
  );
}

export function Input({ T, label, value, onChange, type = 'text', placeholder, mono, required, optional, trailing }) {
  const [show, setShow] = useState(false);
  const isPass = type === 'password';
  return (
    <div style={{ marginBottom: 12 }}>
      {label && (
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500, display: 'flex', gap: 4 }}>
          {label}
          {optional && <span style={{ fontSize: 11, color: T.muted, fontWeight: 400 }}>(可选)</span>}
          {required && <span style={{ color: T.accent }}>*</span>}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7 }}>
        <input
          type={isPass && !show ? 'password' : 'text'}
          value={value} onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            flex: 1, background: 'transparent', border: 'none', outline: 'none',
            padding: '9px 11px', fontSize: 13, color: T.text,
            fontFamily: mono ? T.mono : T.sans,
          }}
        />
        {isPass && <button type="button" onClick={() => setShow(!show)} style={{ ...iconBtn(T), marginRight: 4 }}>{show ? <I.eyeoff/> : <I.eye/>}</button>}
        {trailing && <div style={{ paddingRight: 8 }}>{trailing}</div>}
      </div>
    </div>
  );
}

export function Select({ T, label, value, onChange, options }) {
  return (
    <div style={{ marginBottom: 12 }}>
      {label && <div style={{ fontSize: 12, color: T.subtext, marginBottom: 5, fontWeight: 500 }}>{label}</div>}
      <select value={value} onChange={e => onChange(e.target.value)} style={{
        width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`,
        borderRadius: 7, padding: '9px 11px', fontSize: 13, color: T.text, cursor: 'pointer',
      }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

export function Spinner({ size = 16, color = 'oklch(58% 0.17 195)' }) {
  // v0.5.6 brand 蓝青；OKLCH 不支持 ${color}30 hex 透明语法 → 用 oklch( ... / 0.18) 的 ring
  return <span style={{ display: 'inline-block', width: size, height: size, border: `2px solid oklch(58% 0.17 195 / 0.18)`, borderTopColor: color, borderRadius: '50%', animation: 'cb-spin 0.7s linear infinite' }}/>;
}
