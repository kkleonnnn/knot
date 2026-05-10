// v0.5.3: extracted from Chat.jsx L861-925 (Composer 输入框组件)
// 共用：被 ChatEmpty + Conversation 各自 import 渲染。
import { useRef } from 'react';
import { I, iconBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

export function Composer({ T, value, onChange, loading, onSubmit, onKeyDown,
                          placeholder = '用中文提问…',
                          activeUpload, setActiveUpload, onUpload }) {
  const fileRef = useRef(null);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f && onUpload) onUpload(f);
    e.target.value = '';
  };

  return (
    <div style={{ position: 'relative', width: '100%', maxWidth: 640 }}>
      {activeUpload && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
          padding: '5px 10px', background: T.accentSoft, borderRadius: 8,
          border: `1px solid ${T.accent}30`,
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
      <div style={{
        background: T.inputBg, border: `1px solid ${T.inputBorder}`,
        borderRadius: 14, padding: '12px 14px', width: '100%',
        boxShadow: '0 1px 2px rgba(0,0,0,0.03), 0 8px 24px -16px rgba(0,0,0,0.12)',
      }}>
        <textarea
          value={value} onChange={e => onChange(e.target.value)} onKeyDown={onKeyDown}
          placeholder={activeUpload ? `询问关于 ${activeUpload.filename} 的问题…` : placeholder} rows={1}
          style={{
            width: '100%', background: 'transparent', border: 'none', outline: 'none', resize: 'none',
            fontSize: 14, color: T.text, fontFamily: T.sans, lineHeight: 1.5, minHeight: 24, maxHeight: 120,
            overflow: 'auto',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
          <div style={{ flex: 1 }}/>
          {onUpload && (
            <>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFile} style={{ display: 'none' }}/>
              <button onClick={() => fileRef.current?.click()} title="上传 CSV / Excel"
                style={{ ...iconBtn(T), color: activeUpload ? T.accent : T.muted }}>
                <I.clip/>
              </button>
            </>
          )}
          <button onClick={onSubmit} disabled={loading || !value.trim()} style={{
            width: 30, height: 30, borderRadius: 8, border: 'none',
            background: loading || !value.trim() ? T.muted : T.sendBg, color: T.sendFg,
            display: 'grid', placeItems: 'center', cursor: loading || !value.trim() ? 'not-allowed' : 'pointer',
          }}>
            {loading ? <Spinner size={12} color="#fff"/> : <I.send/>}
          </button>
        </div>
      </div>
    </div>
  );
}
