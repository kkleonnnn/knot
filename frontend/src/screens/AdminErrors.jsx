// v0.6.0.4 F-B AdminErrors — 前端 JS 错误列表 + top hashes 聚合
// 视觉沿用 AdminAudit/Recovery 模式：Inset 8% brandSoft + thead mono uppercase + KpiCard
import { useState, useEffect } from 'react';
import { I } from '../Shared.jsx';
import { Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

function _relTime(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 60) return `${sec}s 前`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

export function AdminErrorsScreen({ T, user, onToggleTheme, onNavigate, onLogout, convs, setConvs, dbOk, sourceCount }) {
  const [items, setItems] = useState([]);
  const [topHashes, setTopHashes] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [size] = useState(50);

  useEffect(() => {
    setLoading(true);
    api.get(`/api/admin/frontend-errors?limit=${size}&offset=${(page - 1) * size}`)
      .then(d => { setItems(d.items || []); setTotal(d.total || 0); setTopHashes(d.top_hashes || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page]);

  return (
    <AppShell T={T} user={user} active="admin-errors" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}
              topbarTitle="前端错误"
              convs={convs} setConvs={setConvs} dbOk={dbOk} sourceCount={sourceCount}>
      <div className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>
        {/* KPI 行 */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>错误总数</div>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>{total}</div>
          </div>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6 }}>独立 Hash</div>
            <div style={{ fontSize: 22, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>{topHashes.length}</div>
          </div>
        </div>

        {/* Top hashes */}
        {topHashes.length > 0 && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ padding: '10px 16px', background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, fontSize: 11, color: T.muted, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>高频错误（Top 10）</div>
            {topHashes.map((h, i) => (
              <div key={h.error_hash} style={{ padding: '10px 16px', borderBottom: i < topHashes.length - 1 ? `1px solid ${T.borderSoft}` : 'none', display: 'flex', gap: 12, alignItems: 'center', fontSize: 12 }}>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, width: 80 }}>{h.error_hash}</span>
                <span style={{ flex: 1, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{h.last_message}</span>
                <span style={{ padding: '2px 8px', borderRadius: 999, background: `color-mix(in oklch, ${T.warn} 12%, transparent)`, color: T.warn, fontSize: 11, fontFamily: T.mono, fontWeight: 500 }}>{h.cnt}</span>
                <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, width: 80, textAlign: 'right' }}>{_relTime(h.last_at)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Recent errors list */}
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '120px 100px 1fr 90px', padding: '9px 16px', background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, fontSize: 11, color: T.muted, fontFamily: T.mono, fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
            <div>时间</div><div>用户</div><div>错误</div><div style={{ textAlign: 'right' }}>Hash</div>
          </div>
          {loading ? (
            <div style={{ padding: 24, display: 'flex', justifyContent: 'center' }}><Spinner T={T}/></div>
          ) : items.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无错误记录</div>
          ) : items.map((it, i) => (
            <div key={it.id} style={{ display: 'grid', gridTemplateColumns: '120px 100px 1fr 90px', padding: '11px 16px', borderBottom: i < items.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5, minWidth: 0 }}>
              <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{_relTime(it.created_at)}</div>
              <div style={{ color: T.subtext, fontSize: 11.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.username || '<anon>'}</div>
              <div style={{ color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{it.message}</div>
              <div style={{ fontFamily: T.mono, fontSize: 10.5, color: T.muted, textAlign: 'right' }}>{it.error_hash || '—'}</div>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {total > size && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12, fontSize: 12 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    style={{ padding: '6px 12px', borderRadius: 6, border: `1px solid ${T.border}`, background: 'transparent', color: T.text, cursor: page === 1 ? 'default' : 'pointer', opacity: page === 1 ? 0.5 : 1, fontFamily: 'inherit' }}>上一页</button>
            <span style={{ alignSelf: 'center', color: T.muted, fontFamily: T.mono }}>第 {page} / {Math.ceil(total / size)} 页</span>
            <button onClick={() => setPage(p => p + 1)} disabled={items.length < size}
                    style={{ padding: '6px 12px', borderRadius: 6, border: `1px solid ${T.border}`, background: 'transparent', color: T.text, cursor: items.length < size ? 'default' : 'pointer', opacity: items.length < size ? 0.5 : 1, fontFamily: 'inherit' }}>下一页</button>
          </div>
        )}
      </div>
    </AppShell>
  );
}
