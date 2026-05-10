// v0.5.3: extracted from Admin.jsx L295-343 (Users + Sources tab JSX dumb renderer)
// D4 mapping: Access (Users + Sources) — 访问与连接
import { I, iconBtn } from '../../Shared.jsx';

export function TabAccess({ T, tab, users, sources, onEditUser, onDeleteUser,
                          onEditSource, onDeleteSource, roleChip }) {
  return (
    <>
      {tab === 'users' && (
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
            <div>用户</div><div>账号</div><div>角色</div><div>状态</div><div></div>
          </div>
          {users.map((u, i) => (
            <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < users.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{ width: 26, height: 26, borderRadius: '50%', background: `linear-gradient(135deg, ${T.accent}, #ff7a3a)`, color: '#fff', display: 'grid', placeItems: 'center', fontSize: 10.5, fontWeight: 600, flexShrink: 0 }}>
                  {(u.display_name || u.username || '?').slice(0, 1).toUpperCase()}
                </div>
                <span style={{ color: T.text, fontWeight: 500 }}>{u.display_name || u.username}</span>
              </div>
              <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11.5 }}>{u.username}</div>
              <div>{roleChip(u.role)}</div>
              <div style={{ fontSize: 11.5, color: u.is_active ? T.success : T.muted }}>{u.is_active ? '正常' : '已停用'}</div>
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
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
            <div>名称</div><div>类型</div><div>主机</div><div>状态</div><div></div>
          </div>
          {sources.map((s, i) => (
            <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < sources.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
              <div style={{ color: T.text, fontWeight: 500, fontFamily: T.mono }}>{s.name}</div>
              <div style={{ color: T.subtext }}>{s.db_type || 'doris'}</div>
              <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.db_host}:{s.db_port}/{s.db_database}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: s.status === 'online' ? T.success : T.warn }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.status === 'online' ? T.success : T.warn }}/>
                <span style={{ fontSize: 11.5 }}>{s.status === 'online' ? '正常' : '异常'}</span>
              </div>
              <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                <button onClick={() => onEditSource(s)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                <button onClick={() => onDeleteSource(s.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
              </div>
            </div>
          ))}
          {sources.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无数据源</div>}
        </div>
      )}
    </>
  );
}
