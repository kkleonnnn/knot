// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）
// v0.6.0.5 F-C — Retention 配置 + 立即清理 banner
// _relPurge 是格式化器（父算好结果传 relPurgeText，子保纯展示 — 守护者 §三）
export function AuditRetentionBar({ T, relPurgeText, retention, setRetention, purging, onPurge, onSaveRetention }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '12px 18px',
      display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
    }}>
      <div style={{ fontSize: 12, color: T.muted, fontFamily: T.mono, letterSpacing: '0.04em' }}>上次清理</div>
      <div style={{ fontSize: 13, color: T.text, fontWeight: 500 }}>{relPurgeText}</div>
      <div style={{ flex: 1 }}/>
      <div style={{ fontSize: 12, color: T.muted, fontFamily: T.mono, letterSpacing: '0.04em' }}>Retention</div>
      <input type="number" min={7} max={3650} value={retention}
             onChange={e => setRetention(Number(e.target.value) || 90)}
             onBlur={() => {
               const d = Math.max(7, Math.min(3650, Number(retention) || 90));
               if (d !== retention) setRetention(d);
               onSaveRetention(d);
             }}
             style={{ width: 70, padding: '4px 8px', border: `1px solid ${T.border}`, borderRadius: 6, background: T.content, color: T.text, fontFamily: T.mono, fontSize: 12 }}/>
      <span style={{ fontSize: 12, color: T.muted }}>天</span>
      <button onClick={onPurge} disabled={purging}
              style={{ padding: '6px 12px', borderRadius: 6, border: `1px solid ${T.border}`, background: T.content, color: T.text, fontSize: 12.5, cursor: purging ? 'not-allowed' : 'pointer', opacity: purging ? 0.5 : 1, fontFamily: 'inherit' }}>
        {purging ? '清理中…' : '立即清理'}
      </button>
    </div>
  );
}
