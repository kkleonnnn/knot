import { I, iconBtn, StatusDot, Avatar } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）

// R-411 Action color mapping helper
function actionColor(T, action) {
  if (!action) return T.muted;
  if (action.startsWith('auth.')) return T.warn;
  if (action.startsWith('budget.') || action.startsWith('prompt.') || action.startsWith('fewshot.')) return T.accent;
  if (action.startsWith('export.')) return T.warn;
  return T.muted;
}

// v0.5.32 — ActionChip 简化对齐 demo audit.jsx L135（删 bg/padding/radius；仅保 mono + actionColor + fontWeight 500）
function ActionChip({ T, action }) {
  const color = actionColor(T, action);
  return (
    <span style={{
      color, fontFamily: T.mono, fontWeight: 500, fontSize: 12,
    }}>{action}</span>
  );
}

// R-408 Table HTML → CSS Grid 7-col
// VRP 基线：thead bg = 灰 T.bg（v0.5.38 回退 R-409 brandSoft 8%；严禁恢复 — 守护者 §二）
// root-element 铁律：返回 loading? : empty? : grid 三元（无 wrapper — 守护者 §三）
export function AuditTable({ T, items, loading, onOpenDrawer }) {
  return loading ? (
    <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
  ) : items.length === 0 ? (
    <div style={{ textAlign: 'center', padding: 32, color: T.muted, fontSize: 13 }}>
      当前筛选条件下无审计记录。
    </div>
  ) : (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
      {/* v0.5.38 thead bg brandSoft 8% → T.bg gray + color T.subtext → T.muted（资深反馈"底色改成灰色 + 字体统一"）*/}
      <div style={{
        display: 'grid', gridTemplateColumns: '1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px',
        padding: '10px 18px',
        background: T.bg,
        borderBottom: `1px solid ${T.border}`,
        fontSize: 11, color: T.muted, fontFamily: T.mono,
        fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
      }}>
        <span>时间</span><span>Actor</span><span>Action</span><span>资源</span><span>IP</span><span>状态</span><span></span>
      </div>
      {items.map((row, i) => {
        // R-428 actor null check — actor_name || actor_id || 'System'
        const displayName = row.actor_name || row.actor_id || 'System';
        const displayInitial = (displayName || 'S').toString().charAt(0).toUpperCase();
        return (
          <div key={row.id} style={{
            display: 'grid', gridTemplateColumns: '1.4fr 1fr 1.3fr 2fr 0.7fr 0.6fr 60px',
            padding: '11px 18px', alignItems: 'center', fontSize: 12.5,
            borderBottom: i === items.length - 1 ? 'none' : `1px solid ${T.borderSoft}`,
          }}>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.created_at}</span>
            {/* R-410 Avatar 22 brandSoft + role chip mono */}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden' }}>
              <Avatar T={T}>{displayInitial}</Avatar>
              <span style={{ fontWeight: 500, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{displayName}</span>
              {row.actor_role && <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, textTransform: 'uppercase', flexShrink: 0 }}>{row.actor_role}</span>}
            </span>
            {/* R-411/R-426 ActionChip — color-mix 12% bg + padding 2px 8px + radius 4 + fontWeight 500 */}
            <span style={{ minWidth: 0, overflow: 'hidden' }}>
              <ActionChip T={T} action={row.action}/>
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 11.5, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {row.resource_type}{row.resource_id ? `:${row.resource_id}` : ''}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.client_ip || '-'}</span>
            {/* R-412 StatusDot inline */}
            <span style={{ minWidth: 0 }}><StatusDot T={T} ok={row.success}/></span>
            <span style={{ display: 'inline-flex', justifyContent: 'flex-end' }}>
              <button onClick={() => onOpenDrawer(row)} style={iconBtn(T)} title="查看详情">
                <I.eye/>
              </button>
            </span>
          </div>
        );
      })}
    </div>
  );
}
