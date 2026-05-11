// v0.5.3 extracted from Chat.jsx；共用：ChatEmpty + Conversation 复用
// v0.5.11 (C5+) Composer 重构 — R-217 自 v0.5.10 hold 至今正式清偿 (R-240~R-265)
import { useRef, useState } from 'react';
import { I, iconBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

export function Composer({ T, value, onChange, loading, onSubmit, onKeyDown,
                          placeholder = '用中文提问…',
                          activeUpload, setActiveUpload, onUpload }) {
  const fileRef = useRef(null);
  const [isFocused, setIsFocused] = useState(false);
  const disabled = loading || !value.trim();

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f && onUpload) onUpload(f);
    e.target.value = '';
  };

  // Step 1: boxShadow 双模式 T.dark 切换 (R-254 + Q2 rgba 豁免)
  const baseShadow = T.dark
    ? '0 1px 3px rgba(0,0,0,0.4), 0 8px 32px rgba(0,0,0,0.5)'
    : '0 1px 3px rgba(15,30,45,0.04), 0 8px 32px rgba(15,30,45,0.06)';
  const focusShadow = `${baseShadow}, 0 0 0 3px color-mix(in oklch, ${T.accent} 15%, transparent)`;

  return (
    <div style={{ position: 'relative', width: '100%' /* Q3 解耦 — max-width 由父容器决定 */ }}>
      {activeUpload && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
          padding: '5px 10px', background: T.accentSoft, borderRadius: 8,
          border: `1px solid color-mix(in oklch, ${T.accent} 18%, transparent)`,
        }}>
          <I.file style={{ color: T.accent, flexShrink: 0 }}/>
          <span style={{ flex: 1, fontSize: 12, color: T.accent, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeUpload.filename} · {activeUpload.row_count} 行
          </span>
          <button onClick={() => setActiveUpload(null)} style={{ ...iconBtn(T), width: 18, height: 18, color: T.accent }}>
            <I.x width="10" height="10"/>
          </button>
        </div>
      )}
      {/* Step 2/3/7: 背景 T.content + padding 16 + width 100% + focus-within border/shadow */}
      <div style={{
        background: T.content,
        border: `1px solid ${isFocused ? T.accentSoft : T.inputBorder}`,
        borderRadius: 14, padding: 16, width: '100%',
        boxShadow: isFocused ? focusShadow : baseShadow,
        transition: 'border-color 200ms, box-shadow 200ms',
        display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        {/* Step 4: textarea minHeight 48 + autoresize 业务保留 (R-245/257/263) */}
        <textarea
          value={value} onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown}
          onFocus={() => setIsFocused(true)} onBlur={() => setIsFocused(false)}
          placeholder={activeUpload ? `询问关于 ${activeUpload.filename} 的问题…` : placeholder} rows={1}
          style={{
            width: '100%', background: 'transparent', border: 'none', outline: 'none', resize: 'none',
            fontSize: 14, color: T.text, fontFamily: T.sans, lineHeight: 1.5,
            minHeight: 48, maxHeight: 120, overflow: 'auto',
          }}
        />
        {/* footer row: hint (R-255 去 Unicode) + file upload + submit */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Step 6: Footer hint mono + brand dot — 仅在 focus 或有内容时显，无内容也保占位 */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            fontSize: 11, color: T.muted, fontFamily: T.mono,
            letterSpacing: '0.06em', textTransform: 'uppercase', flex: 1, minWidth: 0,
          }}>
            <span style={{ width: 5, height: 5, borderRadius: '50%', background: T.accent, flexShrink: 0 }}/>
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              Enter 发送 · Shift+Enter 换行
            </span>
          </div>
          {onUpload && (
            <>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFile} style={{ display: 'none' }}/>
              <button onClick={() => fileRef.current?.click()} title="上传 CSV / Excel"
                style={{ ...iconBtn(T), color: activeUpload ? T.accent : T.muted }}>
                <I.clip/>
              </button>
            </>
          )}
          {/* Step 5: Submit 32×32 + disabled opacity 反馈 (R-256/262) */}
          <button onClick={onSubmit} disabled={disabled} style={{
            width: 32, height: 32, borderRadius: 8, border: 'none',
            background: disabled ? T.muted : T.sendBg, color: T.sendFg,
            opacity: disabled ? 0.5 : 1,
            display: 'grid', placeItems: 'center',
            cursor: disabled ? 'not-allowed' : 'pointer',
            transition: 'opacity 150ms, background 150ms',
          }}>
            {loading ? <Spinner size={12} color="#fff"/> : <I.send/>}
          </button>
        </div>
      </div>
    </div>
  );
}
