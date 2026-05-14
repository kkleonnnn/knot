// v0.5.3: extracted from Admin.jsx L295-343 (Users + Sources tab JSX dumb renderer)
// D4 mapping: Access (Users + Sources) — 访问与连接
// v0.5.40: Sources Hero card 真数据 from /api/admin/datasources-stats
import { useEffect, useState } from 'react';
import { I, iconBtn } from '../../Shared.jsx';
import { api } from '../../api.js';

// v0.5.40 — 上次心跳 relative time helper
function _heartbeatRelative(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 60) return `${sec}s 前`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

export function TabAccess({ T, tab, users, sources, loading, onEditUser, onDeleteUser,
                          onEditSource, onDeleteSource, roleChip }) {
  // v0.5.40 — DataSources Hero stats（仅 sources tab 激活时 fetch）
  const [dsStats, setDsStats] = useState(null);
  useEffect(() => {
    if (tab === 'sources') api.get('/api/admin/datasources-stats').then(setDsStats).catch(() => {});
  }, [tab]);
  return (
    <>
      {tab === 'users' && (
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          {/* v0.5.38 thead bg brandSoft 8% → T.bg gray + color T.subtext → T.muted（资深反馈"底色改成灰色 + 字体统一"）*/}
          <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
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
          {/* v0.6.1.2 F2 — loading 时显示"加载中..."，避免误显"暂无用户"幻觉 */}
          {users.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>{loading ? '加载中…' : '暂无用户'}</div>}
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
            {/* v0.5.40 — 真数据 from /api/admin/datasources-stats */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>总 schema</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.text, fontFamily: T.mono }}>{dsStats ? dsStats.total_schemas : '—'}</div>
            </div>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>总表数</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.text, fontFamily: T.mono }}>{dsStats ? dsStats.total_tables : '—'}</div>
            </div>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>上次心跳</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.text, fontFamily: T.mono }}>{dsStats ? _heartbeatRelative(dsStats.last_heartbeat) : '—'}</div>
            </div>
          </div>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
            {/* v0.5.38 thead bg brandSoft 8% → T.bg gray（v0.5.28 #23 局部撤回 — 资深"底色改成灰色"）*/}
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.4fr 0.6fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
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
            {sources.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>{loading ? '加载中…' : '暂无数据源'}</div>}
          </div>
        </>
      )}
    </>
  );
}
