// v0.5.3: extracted from Admin.jsx L295-343 (Users + Sources tab JSX dumb renderer)
// D4 mapping: Access (Users + Sources) — 访问与连接
import { I, iconBtn } from '../../Shared.jsx';

export function TabAccess({ T, tab, users, sources, onEditUser, onDeleteUser,
                          onEditSource, onDeleteSource, roleChip }) {
  return (
    <>
      {tab === 'users' && (
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          {/* R-504/R-505 thead Inset 8% 闭环字面（与 Sources thead byte-equal）+ mono + 0.06em + uppercase + fontWeight 500 + T.subtext */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '9px 16px', background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, fontSize: 11, color: T.subtext, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
            <div>用户</div><div>账号</div><div>角色</div><div>状态</div><div></div>
          </div>
          {users.map((u, i) => (
            <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < users.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0, overflow: 'hidden' }}>
                {/* R-500~R-503/R-516 Avatar 22 brandSoft 8% + T.accent + inline-flex + lineHeight:1 + fontSize:10.5（与 AdminAudit R-410 + AdminRecovery R-479 字面 byte-equal；R-376 hex 债务清偿）*/}
                <div style={{ width: 22, height: 22, borderRadius: '50%', background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, color: T.accent, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10.5, fontWeight: 600, lineHeight: 1, flexShrink: 0 }}>
                  {(u.display_name || u.username || '?').slice(0, 1).toUpperCase()}
                </div>
                <span style={{ color: T.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.display_name || u.username}</span>
              </div>
              <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.username}</div>
              <div style={{ minWidth: 0 }}>{roleChip(u.role)}</div>
              <div style={{ fontSize: 11.5, color: u.is_active ? T.success : T.muted, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.is_active ? '正常' : '已停用'}</div>
              <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                <button onClick={() => onEditUser(u)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                <button onClick={() => onDeleteUser(u.id)} style={iconBtn(T)} title="停用"><I.trash/></button>
              </div>
            </div>
          ))}
          {users.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无用户</div>}
        </div>
      )}

      {tab === 'sources' && (
        <>
          {/* v0.5.28 #19 — 4 卡片同 plain T.card+T.border（demo datasources.jsx L58）；
              已连接 value 走 T.success 绿色 tone='ok'（demo s.tone==='ok'?T.ok:t.text） */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>已连接</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.success, letterSpacing: '-0.01em' }}>{sources.length}</div>
            </div>
            <div title="后端数据对接中 (v0.6+)" style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>总 schema</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono }}>—</div>
            </div>
            <div title="后端数据对接中 (v0.6+)" style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>总表数</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono }}>—</div>
            </div>
            <div title="后端数据对接中 (v0.6+)" style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>上次心跳</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono }}>—</div>
            </div>
          </div>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
            {/* v0.5.28 #23 — thead 字体 T.subtext → T.muted（demo bgInset+textFaint；保 brandSoft 8% bg 维持 v0.5.27 #24 全站一致）*/}
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.4fr 0.6fr 0.8fr 80px', padding: '9px 16px', background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, fontSize: 11, color: T.muted, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
              <div>名称</div><div>类型</div><div>主机</div><div>表数</div><div>状态</div><div></div>
            </div>
            {sources.map((s, i) => (
              <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.4fr 0.6fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < sources.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, overflow: 'hidden' }}>
                  {/* v0.5.28 #24 — db icon borderRadius 8 → 6（demo L96 radius 6 byte-equal）*/}
                  <div style={{ width: 28, height: 28, borderRadius: 6, background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, color: T.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <I.db width="14" height="14"/>
                  </div>
                  <span style={{ color: T.text, fontWeight: 500, fontFamily: T.mono, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                </div>
                <div style={{ minWidth: 0, overflow: 'hidden' }}>
                  <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 999, background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, color: T.accent, fontSize: 11, letterSpacing: '0.02em', fontFamily: T.mono }}>{s.db_type || 'doris'}</span>
                </div>
                <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.db_host}:{s.db_port}/{s.db_database}</div>
                <div title="后端数据对接中 (v0.6+)" style={{ color: T.muted, fontFamily: T.mono, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>—</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: s.status === 'online' ? T.success : T.warn, minWidth: 0, overflow: 'hidden' }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.status === 'online' ? T.success : T.warn, flexShrink: 0 }}/>
                  <span style={{ fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.status === 'online' ? '正常' : '异常'}</span>
                </div>
                <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                  <button onClick={() => onEditSource(s)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                  <button onClick={() => onDeleteSource(s.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
                </div>
              </div>
            ))}
            {sources.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无数据源</div>}
          </div>
        </>
      )}
    </>
  );
}
