import { useState } from 'react';
import { buildTheme, I, iconBtn } from './Shared.jsx';

export function useTheme() {
  const saved = localStorage.getItem('cb_theme');
  const [dark, setDark] = useState(saved ? saved === 'dark' : true);
  const toggle = () => {
    setDark(d => {
      const nd = !d;
      localStorage.setItem('cb_theme', nd ? 'dark' : 'light');
      return nd;
    });
  };
  return [buildTheme(dark), toggle];
}

export function usePersist(key, def) {
  const [v, set] = useState(() => {
    try { const s = localStorage.getItem(key); return s ? JSON.parse(s) : def; } catch { return def; }
  });
  const setP = nv => {
    set(nv);
    try { localStorage.setItem(key, JSON.stringify(nv)); } catch {}
  };
  return [v, setP];
}

export function toast(msg, err = false) {
  const el = document.createElement('div');
  el.textContent = msg;
  Object.assign(el.style, {
    position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
    background: err ? '#FF4B4B' : '#09AB3B', color: '#fff',
    padding: '9px 18px', borderRadius: 8, fontSize: 13.5, fontFamily: 'inherit',
    boxShadow: '0 4px 20px rgba(0,0,0,0.2)', zIndex: 9999, animation: 'cb-fadein .3s ease',
  });
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

export function Modal({ T, onClose, children, width = 480 }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(14,17,23,0.5)', backdropFilter: 'blur(2px)',
      display: 'grid', placeItems: 'center', zIndex: 1000,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        width, background: T.content, borderRadius: 12, border: `1px solid ${T.border}`,
        boxShadow: '0 24px 60px -20px rgba(0,0,0,0.4)', overflow: 'hidden',
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
        <div style={{ fontSize: 15, color: T.text, fontWeight: 600 }}>{title}</div>
        {subtitle && <div style={{ fontSize: 11.5, color: T.muted, marginTop: 2 }}>{subtitle}</div>}
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
          {optional && <span style={{ fontSize: 10, color: T.muted, fontWeight: 400 }}>(可选)</span>}
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

export function Spinner({ size = 16, color = '#FF4B4B' }) {
  return <span style={{ display: 'inline-block', width: size, height: size, border: `2px solid ${color}30`, borderTopColor: color, borderRadius: '50%', animation: 'cb-spin 0.7s linear infinite' }}/>;
}
