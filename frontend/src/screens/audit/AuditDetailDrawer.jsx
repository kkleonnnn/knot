import { iconBtn, preStyle } from '../../Shared.jsx';

// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）
const _REDACTED_RE = /••••redacted••••/g;

// R-415 R-313 sustained 扩展豁免 #2（首处 v0.5.11 R-254 boxShadow）
//   理由：Chrome < 111 / WebKit backdrop-filter OKLCH→sRGB fallback GPU 渲染抖动；
//         rgba 是全平台一致性稳健选择；架构原则确立 — 红线服从浏览器真理
export function AuditDetailDrawer({ T, drawerRow, onClose }) {
  if (!drawerRow) return null;
  return (
    <div onClick={onClose} style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.4)',
      zIndex: 100,
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        position: 'absolute', top: 0, right: 0, height: '100%', width: '600px', maxWidth: '92vw',
        background: T.content, borderLeft: `1px solid ${T.border}`,
        padding: 20, overflowY: 'auto',
        display: 'flex', flexDirection: 'column', gap: 12,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: T.text }}>审计详情 #{drawerRow.id}</div>
          <button onClick={onClose} style={iconBtn(T)}>✕</button>
        </div>
        <KV T={T} k="时间" v={drawerRow.created_at}/>
        <KV T={T} k="Actor" v={`${drawerRow.actor_name || '(匿名)'} (${drawerRow.actor_role || '-'}, id=${drawerRow.actor_id ?? 'null'})`}/>
        <KV T={T} k="Action" v={drawerRow.action} mono/>
        <KV T={T} k="Resource" v={`${drawerRow.resource_type}${drawerRow.resource_id ? ':' + drawerRow.resource_id : ''}`}/>
        <KV T={T} k="Client IP" v={drawerRow.client_ip || '-'}/>
        <KV T={T} k="User-Agent" v={drawerRow.user_agent || '-'}/>
        <KV T={T} k="Request ID" v={drawerRow.request_id || '-'}/>
        <KV T={T} k="Success" v={drawerRow.success ? '✓ 成功' : '✗ 失败'}/>
        <div>
          <div style={{ fontSize: 11, color: T.muted, marginBottom: 6 }}>详情（detail_json）</div>
          <DetailJsonView T={T} detail={drawerRow.detail_json}/>
        </div>
      </div>
    </div>
  );
}

// R-429 DetailJsonView try-catch 性能守护 + R-427 cursor:help + R-414 redacted color-mix
function DetailJsonView({ T, detail }) {
  let json;
  try {
    if (typeof detail === 'string') {
      json = JSON.stringify(JSON.parse(detail), null, 2);
    } else {
      json = JSON.stringify(detail || {}, null, 2);
    }
  } catch {
    // 畸形 JSON 兜底 — 显原始字符串，防主界面卡死
    return <pre style={preStyle(T)}>{String(detail ?? '')}</pre>;
  }

  if (!_REDACTED_RE.test(json)) {
    return <pre style={preStyle(T)}>{json}</pre>;
  }
  // 含 ••••redacted•••• → 切片 + R-414 color-mix 高亮 + R-427 cursor:help
  const parts = json.split(/(••••redacted••••)/g);
  return (
    <pre style={preStyle(T)}>
      {parts.map((p, i) => p === '••••redacted••••'
        ? <span key={i} style={{
            background: `color-mix(in oklch, ${T.warn} 20%, transparent)`,
            color: T.warn,
            padding: '0 4px', borderRadius: 3, fontWeight: 600,
            cursor: 'help',
          }} title="敏感字段已脱敏">{p}</span>
        : <span key={i}>{p}</span>)}
    </pre>
  );
}

function KV({ T, k, v, mono }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 2 }}>{k}</div>
      <div style={{ fontSize: 13, color: T.text, fontFamily: mono ? T.mono : 'inherit' }}>{v}</div>
    </div>
  );
}
