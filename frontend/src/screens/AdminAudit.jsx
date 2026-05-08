import { useEffect, useState } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.6 D3：审计日志 admin 看板（who-did-what 追溯）
// R-61 强制分页：默认 50 / 上限 200（与后端一致）
// 守护者前瞻：不做"加载更多"无限滚；显式 page 1 / page 2 / ...

const _PAGE_SIZES = [50, 100, 200];
const _REDACTED_RE = /••••redacted••••/g;

export function AdminAuditScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  const [filter, setFilter] = useState({ actor_id: '', action: '', resource_type: '', since: '' });
  const [drawerRow, setDrawerRow] = useState(null);  // 详情抽屉

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, size]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: size, offset: (page - 1) * size });
      for (const k of ['actor_id', 'action', 'resource_type', 'since']) {
        if (filter[k]) params.append(k, filter[k]);
      }
      const r = await api.get(`/api/admin/audit-log?${params.toString()}`);
      setItems(r.items || []);
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  const sidebarContent = (
    <button onClick={() => onNavigate('chat')} style={{
      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
      padding: '9px 10px', borderRadius: 8, background: 'transparent',
      color: T.muted, border: `1px solid ${T.border}`,
      fontFamily: 'inherit', fontSize: 13, cursor: 'pointer', marginBottom: 8,
    }}>
      <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
    </button>
  );

  return (
    <AppShell T={T} user={user} active="admin-audit" sidebarContent={sidebarContent}
              topbarTitle="📋 审计日志" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* 筛选栏 */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 10 }}>筛选</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 10 }}>
              <Field T={T} label="actor_id">
                <input value={filter.actor_id} onChange={e => setFilter({...filter, actor_id: e.target.value})}
                       placeholder="如 1" style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="action（如 user.create）">
                <input value={filter.action} onChange={e => setFilter({...filter, action: e.target.value})}
                       placeholder="auth.login_success" style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="resource_type">
                <input value={filter.resource_type} onChange={e => setFilter({...filter, resource_type: e.target.value})}
                       placeholder="user / datasource / ..." style={inputStyle(T)}/>
              </Field>
              <Field T={T} label="since（YYYY-MM-DD）">
                <input value={filter.since} onChange={e => setFilter({...filter, since: e.target.value})}
                       placeholder="2026-05-01" style={inputStyle(T)}/>
              </Field>
              <button onClick={() => { setPage(1); load(); }}
                      style={{ padding: '8px 14px', borderRadius: 6, border: `1px solid ${T.accent}`,
                               background: T.accent, color: '#fff', cursor: 'pointer',
                               fontFamily: 'inherit', fontSize: 13, alignSelf: 'flex-end' }}>
                查询
              </button>
            </div>
          </div>

          {/* 表格 */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : items.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 32, color: T.muted, fontSize: 13 }}>
              当前筛选条件下无审计记录。
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: T.bg }}>
                    {['时间', 'Actor', 'Action', '资源', 'IP', '状态', '详情'].map(c =>
                      <th key={c} style={thStyle(T)}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {items.map(row => (
                    <tr key={row.id} style={{ borderTop: `1px solid ${T.border}` }}>
                      <td style={cellStyle(T)}>{row.created_at}</td>
                      <td style={cellStyle(T)}>
                        {row.actor_name || <span style={{color: T.muted}}>(匿名)</span>}
                        {row.actor_role && <span style={{color: T.muted, marginLeft: 4, fontSize: 11}}>({row.actor_role})</span>}
                      </td>
                      <td style={{...cellStyle(T), fontFamily: 'monospace', fontSize: 11.5}}>{row.action}</td>
                      <td style={cellStyle(T)}>
                        {row.resource_type}{row.resource_id ? `:${row.resource_id}` : ''}
                      </td>
                      <td style={{...cellStyle(T), fontSize: 11.5, color: T.muted}}>{row.client_ip || '-'}</td>
                      <td style={cellStyle(T)}>
                        {row.success
                          ? <span style={{color: T.success || '#2e7d32'}}>✓</span>
                          : <span style={{color: T.accent}}>✗</span>}
                      </td>
                      <td style={cellStyle(T)}>
                        <button onClick={() => setDrawerRow(row)}
                                style={{...iconBtn(T), padding: '3px 8px', fontSize: 11}}>
                          查看
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* 分页 */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12 }}>
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
                    style={pageBtnStyle(T, page === 1)}>‹ 上一页</button>
            <span style={{ fontSize: 12.5, color: T.muted }}>第 {page} 页（每页 {size}）</span>
            <button onClick={() => setPage(page + 1)} disabled={items.length < size}
                    style={pageBtnStyle(T, items.length < size)}>下一页 ›</button>
            <select value={size} onChange={e => { setSize(parseInt(e.target.value)); setPage(1); }}
                    style={{...inputStyle(T), width: 'auto', marginLeft: 16}}>
              {_PAGE_SIZES.map(s => <option key={s} value={s}>{s} / 页</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* 详情抽屉 */}
      {drawerRow && (
        <div onClick={() => setDrawerRow(null)} style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.4)', zIndex: 100,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            position: 'absolute', top: 0, right: 0, height: '100%', width: '600px', maxWidth: '92vw',
            background: T.content, borderLeft: `1px solid ${T.border}`,
            padding: 20, overflowY: 'auto',
            display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 14, fontWeight: 500, color: T.text }}>审计详情 #{drawerRow.id}</div>
              <button onClick={() => setDrawerRow(null)} style={iconBtn(T)}>✕</button>
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
      )}
    </AppShell>
  );
}

// 守护者前瞻：高亮 ••••redacted••••（PII 妥善处理的直观证明，提升 admin 信任感）
function DetailJsonView({ T, detail }) {
  const json = JSON.stringify(detail || {}, null, 2);
  if (!_REDACTED_RE.test(json)) {
    return (
      <pre style={preStyle(T)}>{json}</pre>
    );
  }
  // 包含 redacted 标记 → 切片高亮
  const parts = json.split(/(••••redacted••••)/g);
  return (
    <pre style={preStyle(T)}>
      {parts.map((p, i) => p === '••••redacted••••'
        ? <span key={i} style={{
            background: '#FF990033', color: '#cc6600',
            padding: '0 4px', borderRadius: 3, fontWeight: 600,
          }}>{p}</span>
        : <span key={i}>{p}</span>)}
    </pre>
  );
}

function KV({ T, k, v, mono }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 2 }}>{k}</div>
      <div style={{ fontSize: 13, color: T.text, fontFamily: mono ? 'monospace' : 'inherit' }}>{v}</div>
    </div>
  );
}

function Field({ T, label, children }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

function inputStyle(T) {
  return {
    width: '100%', padding: '6px 10px', borderRadius: 6,
    border: `1px solid ${T.border}`, background: T.content, color: T.text,
    fontSize: 13, fontFamily: 'inherit',
  };
}

function thStyle(T) {
  return {
    padding: '8px 12px', textAlign: 'left', color: T.muted,
    fontWeight: 600, fontSize: 11, letterSpacing: '0.03em',
    textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`,
  };
}

function cellStyle(T) {
  return { padding: '8px 12px', color: T.text, whiteSpace: 'nowrap' };
}

function pageBtnStyle(T, disabled) {
  return {
    padding: '6px 14px', borderRadius: 6,
    border: `1px solid ${T.border}`,
    background: 'transparent',
    color: disabled ? T.muted : T.text,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit', fontSize: 12.5,
    opacity: disabled ? 0.5 : 1,
  };
}

function preStyle(T) {
  return {
    background: T.bg, padding: 12, borderRadius: 6,
    fontSize: 11.5, fontFamily: 'monospace', color: T.text,
    overflow: 'auto', maxHeight: '50vh',
    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
    border: `1px solid ${T.border}`, margin: 0,
  };
}
