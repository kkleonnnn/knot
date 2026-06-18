import { useState, useEffect } from 'react';
import { iconBtn, PeriodTab, TagChip } from '../Shared.jsx';
import { toast, Spinner, Modal, ModalHeader, Input } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.6.0.18 — 用户查询历史屏（脱敏链 2/3）
// admin 跨用户聚合查询：什么人问了什么 / 系统怎么答 / cost / latency / error
// 支持按 user / period / kind / status 过滤 + 分页
// 复用 v0.5.17 AdminAudit pattern：CSS Grid table + filter strip + drawer detail

const PERIOD_LABELS = { '7d': '近 7 天', '30d': '近 30 天', '90d': '近 90 天' };
const KIND_LABELS = {
  '': '所有 agent',
  clarifier: 'Clarifier（澄清）',
  sql_planner: 'SQL Planner',
  fix_sql: 'Fix SQL（重试）',
  presenter: 'Presenter（洞察）',
};
const ERROR_LABELS = { '': '所有', 'true': '只看错误', 'false': '只看成功' };

function fmt(ms) { return ms == null ? '—' : (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`); }
function fmtCost(c) { return c == null ? '—' : (c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`); }

export function AdminQueryHistoryScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [period, setPeriod] = useState('7d');
  const [agentKind, setAgentKind] = useState('');
  const [hasError, setHasError] = useState('');
  const [userIdFilter, setUserIdFilter] = useState('');
  const [page, setPage] = useState(1);
  const size = 50;
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [openItem, setOpenItem] = useState(null);

  /* eslint-disable react-hooks/immutability, react-hooks/exhaustive-deps */
  useEffect(() => { load(); }, [period, agentKind, hasError, userIdFilter, page]);
  /* eslint-enable react-hooks/immutability, react-hooks/exhaustive-deps */

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ period, page: String(page), size: String(size) });
      if (agentKind) params.set('agent_kind', agentKind);
      if (hasError) params.set('has_error', hasError);
      if (userIdFilter && /^\d+$/.test(userIdFilter)) params.set('user_id', userIdFilter);
      const d = await api.get(`/api/admin/query-history?${params.toString()}`);
      setData(d);
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  const insetBg = `color-mix(in oklch, ${T.accent} 8%, transparent)`;
  const totalPages = Math.max(1, Math.ceil(data.total / size));

  // 7-col grid：时间 / 用户 / 问题 / kind / latency / cost / status
  const gridCols = '150px 130px 1fr 110px 80px 80px 70px';

  return (
    <AppShell T={T} user={user} active="admin-history"
              onToggleTheme={onToggleTheme} onNavigate={onNavigate} onLogout={onLogout}
              topbarTitle="用户查询历史">
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Filter strip */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
          padding: '12px 16px', background: insetBg, borderRadius: 8,
        }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {['7d', '30d', '90d'].map(p => (
              <PeriodTab key={p} T={T} label={PERIOD_LABELS[p]}
                         height={28} radius={6} fontSize={12} letterSpacing="normal" shadow={false}
                         active={period === p} onClick={() => { setPeriod(p); setPage(1); }}/>
            ))}
          </div>
          <select value={agentKind} onChange={e => { setAgentKind(e.target.value); setPage(1); }}
                  style={{ height: 28, padding: '0 10px', borderRadius: 6, background: T.content,
                           border: `1px solid ${T.border}`, color: T.text, fontSize: 12, fontFamily: 'inherit' }}>
            {Object.entries(KIND_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={hasError} onChange={e => { setHasError(e.target.value); setPage(1); }}
                  style={{ height: 28, padding: '0 10px', borderRadius: 6, background: T.content,
                           border: `1px solid ${T.border}`, color: T.text, fontSize: 12, fontFamily: 'inherit' }}>
            {Object.entries(ERROR_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <div style={{ width: 160 }}>
            <Input T={T} value={userIdFilter} onChange={v => { setUserIdFilter(v); setPage(1); }}
                   placeholder="user_id（可选）" mono/>
          </div>
          <div style={{ marginLeft: 'auto', fontSize: 12, color: T.muted, fontFamily: T.mono }}>
            {data.total} 条 · 第 {page} / {totalPages} 页
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: T.muted }}><Spinner/></div>
        ) : data.items.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: T.muted }}>暂无数据</div>
        ) : (
          <div style={{ background: T.content, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
            <div style={{
              display: 'grid', gridTemplateColumns: gridCols, gap: 0,
              padding: '10px 14px', borderBottom: `1px solid ${T.border}`,
              background: insetBg, fontSize: 11, color: T.subtext, fontFamily: T.mono,
              textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 500,
            }}>
              <div>时间</div><div>用户</div><div>问题</div><div>Agent</div>
              <div>延迟</div><div>成本</div><div>状态</div>
            </div>
            {data.items.map(item => (
              <div key={item.id} onClick={() => setOpenItem(item)} style={{
                display: 'grid', gridTemplateColumns: gridCols, gap: 0, alignItems: 'center',
                padding: '10px 14px', borderBottom: `1px solid ${T.borderSoft}`,
                fontSize: 12.5, cursor: 'pointer',
              }}>
                <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden' }}>{item.created_at}</div>
                <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T.text }}>
                  {item.actor_display_name || item.actor_username || '—'}
                </div>
                <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: T.text }}>
                  {item.question || '—'}
                </div>
                <div><TagChip T={T} kind={item.agent_kind === 'clarifier' ? 'warn' : 'accent'}>{item.agent_kind}</TagChip></div>
                <div style={{ fontFamily: T.mono, fontSize: 11, color: T.muted }}>{fmt(item.latency_ms)}</div>
                <div style={{ fontFamily: T.mono, fontSize: 11, color: T.muted }}>{fmtCost(item.cost_usd)}</div>
                <div>{item.db_error ? <TagChip T={T} kind="warn">FAIL</TagChip> : <TagChip T={T} kind="success">OK</TagChip>}</div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {data.total > size && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 8 }}>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    style={{ ...iconBtn(T), opacity: page === 1 ? 0.4 : 1 }}>上一页</button>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages}
                    style={{ ...iconBtn(T), opacity: page >= totalPages ? 0.4 : 1 }}>下一页</button>
          </div>
        )}
      </div>

      {/* Detail drawer modal */}
      {openItem && (
        <Modal T={T} onClose={() => setOpenItem(null)} width={680}>
          <ModalHeader T={T} title={`#${openItem.id} · ${openItem.actor_username || '—'}`}
                       subtitle={openItem.created_at} onClose={() => setOpenItem(null)}/>
          <div style={{ padding: '16px 20px', maxHeight: '70vh', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <DetailRow T={T} k="问题" v={openItem.question}/>
            <DetailRow T={T} k="Agent" v={openItem.agent_kind}/>
            <DetailRow T={T} k="Intent" v={openItem.intent || '—'}/>
            <DetailRow T={T} k="Confidence" v={openItem.confidence || '—'}/>
            <DetailRow T={T} k="延迟 / 成本" v={`${fmt(openItem.latency_ms)} · ${fmtCost(openItem.cost_usd)}`}/>
            <DetailRow T={T} k="对话" v={`#${openItem.conversation_id} ${openItem.conversation_title || ''}`}/>
            {openItem.sql_text && (
              <div>
                <div style={{ fontSize: 11, color: T.muted, marginBottom: 4, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.06em' }}>SQL</div>
                <pre style={{ margin: 0, padding: 10, background: T.codeBg, borderRadius: 6, border: `1px solid ${T.border}`, fontSize: 11.5, fontFamily: T.mono, color: T.codeText, overflow: 'auto', maxHeight: 200 }}>{openItem.sql_text}</pre>
              </div>
            )}
            {openItem.explanation && <DetailRow T={T} k="洞察" v={openItem.explanation}/>}
            {openItem.db_error && (
              <DetailRow T={T} k="错误" v={openItem.db_error} kind="warn"/>
            )}
          </div>
        </Modal>
      )}
    </AppShell>
  );
}

function DetailRow({ T, k, v, kind }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 4, fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k}</div>
      <div style={{ fontSize: 13, color: kind === 'warn' ? T.warn : T.text, lineHeight: 1.55, wordBreak: 'break-word' }}>{v}</div>
    </div>
  );
}
