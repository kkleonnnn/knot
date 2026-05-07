import { useState, useEffect } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.1: intent → 头像 emoji（与 INTENT_TO_HINT 对齐）
const INTENT_EMOJI = {
  metric: '📊',
  trend: '📈',
  compare: '⚖️',
  rank: '🏆',
  distribution: '🥧',
  retention: '🗓️',
  detail: '📋',
};

export function SavedReportsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [reports, setReports] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadReports(); }, []);

  async function loadReports() {
    setLoading(true);
    try {
      const d = await api.get('/api/saved-reports');
      setReports(d || []);
      if (d && d.length > 0 && activeId == null) setActiveId(d[0].id);
    } catch (e) {
      toast(`加载收藏失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm('删除该收藏报表？此操作不可恢复（不影响原对话历史）。')) return;
    try {
      await api.del(`/api/saved-reports/${id}`);
      toast('已删除');
      const next = reports.filter(r => r.id !== id);
      setReports(next);
      if (activeId === id) setActiveId(next[0]?.id || null);
    } catch (e) {
      toast(`删除失败: ${e.message}`, true);
    }
  }

  const active = reports.find(r => r.id === activeId);

  const sidebarContent = (
    <>
      <button onClick={() => onNavigate('chat')} style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '9px 10px', borderRadius: 8, background: 'transparent',
        color: T.muted, border: `1px solid ${T.border}`,
        fontFamily: 'inherit', fontSize: 13, cursor: 'pointer', marginBottom: 8,
      }}>
        <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
      </button>
      <div style={{
        padding: '10px 10px 4px', fontSize: 10.5, color: T.muted,
        letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 600,
      }}>📌 收藏报表（{reports.length}）</div>
      <div className="cb-sb" style={{ display: 'flex', flexDirection: 'column', gap: 1, flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {reports.map(r => (
          <div key={r.id} onClick={() => setActiveId(r.id)} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '7px 10px',
            borderRadius: 6, cursor: 'pointer',
            background: r.id === activeId ? T.accentSoft : 'transparent',
            color: r.id === activeId ? T.accent : T.subtext, fontSize: 12.5,
            borderLeft: r.id === activeId ? `2px solid ${T.accent}` : '2px solid transparent',
            paddingLeft: r.id === activeId ? 8 : 10,
            fontWeight: r.id === activeId ? 500 : 400,
          }}>
            <span style={{ fontSize: 13, flexShrink: 0 }}>{INTENT_EMOJI[r.intent] || '📋'}</span>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.title || '未命名报表'}</span>
            <button onClick={(e) => { e.stopPropagation(); handleDelete(r.id); }} style={{ ...iconBtn(T), width: 20, height: 20, opacity: 0.5, flexShrink: 0 }}><I.trash/></button>
          </div>
        ))}
      </div>
    </>
  );

  return (
    <AppShell T={T} user={user} active="saved-reports" sidebarContent={sidebarContent}
              topbarTitle={active ? active.title : '📌 收藏报表'} hideSidebarNewChat
              onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      {loading
        ? <div style={{ flex: 1, display: 'grid', placeItems: 'center' }}><Spinner size={28} color={T.accent}/></div>
        : reports.length === 0
          ? <EmptyView T={T} onBack={() => onNavigate('chat')}/>
          : active && <DetailView T={T} report={active} onChanged={loadReports}/>}
    </AppShell>
  );
}

function EmptyView({ T, onBack }) {
  return (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', padding: 32 }}>
      <div style={{ textAlign: 'center', maxWidth: 320 }}>
        <div style={{ fontSize: 38, marginBottom: 8 }}>📌</div>
        <div style={{ fontSize: 15, color: T.text, marginBottom: 4 }}>还没有收藏报表</div>
        <div style={{ fontSize: 12.5, color: T.muted, lineHeight: 1.6, marginBottom: 16 }}>
          在对话里点 ⭐ 把任意结果钉成报表，下次直接重跑。
        </div>
        <button onClick={onBack} style={{
          padding: '8px 16px', borderRadius: 6, border: `1px solid ${T.border}`,
          background: 'transparent', color: T.text, fontSize: 13, cursor: 'pointer',
          fontFamily: 'inherit',
        }}>返回对话</button>
      </div>
    </div>
  );
}

function DetailView({ T, report, onChanged }) {
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);  // { rows, error, warning, last_run_ms, last_run_at, truncated }
  const [editing, setEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState(report.title);
  const [noteDraft, setNoteDraft] = useState(report.pin_note || '');

  useEffect(() => {
    setRunResult(null);
    setTitleDraft(report.title);
    setNoteDraft(report.pin_note || '');
    setEditing(false);
  }, [report.id]);

  async function handleRun() {
    setRunning(true);
    try {
      const r = await api.post(`/api/saved-reports/${report.id}/run`);
      setRunResult(r);
      if (r.error) toast(`重跑失败: ${r.error}`, true);
      else toast(`已重跑（${r.last_run_ms}ms${r.truncated ? '，已截断到 200 行' : ''}）`);
    } catch (e) {
      toast(`重跑失败: ${e.message}`, true);
    } finally {
      setRunning(false);
    }
  }

  async function handleSaveEdit() {
    try {
      await api.put(`/api/saved-reports/${report.id}`, { title: titleDraft, pin_note: noteDraft });
      toast('已保存');
      setEditing(false);
      onChanged && onChanged();
    } catch (e) {
      toast(`保存失败: ${e.message}`, true);
    }
  }

  async function handleExport() {
    try {
      const r = await fetch(`/api/saved-reports/${report.id}/export.csv`, {
        headers: { Authorization: `Bearer ${api._token()}` },
      });
      if (!r.ok) { toast(`导出失败: ${r.status}`, true); return; }
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `saved_report_${report.id}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) {
      toast(`导出失败: ${e.message}`, true);
    }
  }

  // 优先用重跑结果，否则用 last_run_rows_json 快照
  const rowsSource = runResult?.rows ?? safeParseRows(report.last_run_rows_json);
  const truncated = runResult ? runResult.truncated : (report.last_run_truncated === 1);
  const cols = rowsSource && rowsSource.length > 0 ? Object.keys(rowsSource[0]) : [];
  const lastRunMs = runResult?.last_run_ms ?? report.last_run_ms;
  const lastRunAt = runResult?.last_run_at || report.last_run_at;
  const warning = runResult?.warning;

  return (
    <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
      <div style={{ maxWidth: 880, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* 顶栏：title + 编辑 / 重跑 / 导出 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {editing ? (
            <input value={titleDraft} onChange={e => setTitleDraft(e.target.value)}
                   style={{ flex: 1, minWidth: 200, padding: '6px 10px', borderRadius: 6,
                            border: `1px solid ${T.border}`, background: T.content, color: T.text,
                            fontSize: 14, fontFamily: 'inherit' }}/>
          ) : (
            <div style={{ flex: 1, fontSize: 16, fontWeight: 500, color: T.text }}>{report.title}</div>
          )}
          {editing ? (
            <>
              <button onClick={handleSaveEdit} style={pillBtn(T, true)}>保存</button>
              <button onClick={() => setEditing(false)} style={pillBtn(T)}>取消</button>
            </>
          ) : (
            <>
              <button onClick={() => setEditing(true)} style={pillBtn(T)} title="改名 / 备注">✏️ 编辑</button>
              <button onClick={handleRun} disabled={running} style={pillBtn(T, true)}>
                {running ? '运行中…' : '🔄 重跑一遍'}
              </button>
              <button onClick={handleExport} style={pillBtn(T)} title="导出 CSV">📥 CSV</button>
            </>
          )}
        </div>

        {/* meta 行 */}
        <div style={{ display: 'flex', gap: 12, fontSize: 11.5, color: T.muted, fontFamily: T.mono, flexWrap: 'wrap' }}>
          <span>intent: {report.intent || 'detail'}</span>
          <span>layout: {report.display_hint || 'detail_table'}</span>
          {lastRunAt && <span>上次重跑: {lastRunAt}</span>}
          {lastRunMs > 0 && <span>{lastRunMs}ms</span>}
        </div>

        {/* warning banner（R-S2 fallback） */}
        {warning && (
          <div style={{ padding: '10px 14px', borderRadius: 8, background: '#FF990022',
                        border: `1px solid #FF9900`, color: '#cc6600', fontSize: 12.5 }}>
            ⚠️ {warning}
          </div>
        )}
        {truncated && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: T.accentSoft, color: T.accent, fontSize: 12 }}>
            🔍 仅展示前 200 行预览（完整结果请点 📥 CSV 导出）
          </div>
        )}
        {runResult?.error && (
          <div style={{ padding: '10px 14px', borderRadius: 8, background: T.accentSoft,
                        border: `1px solid ${T.accent}30`, color: T.accent, fontSize: 12.5 }}>
            ❌ {runResult.error}
          </div>
        )}

        {/* 编辑模式：备注输入 */}
        {editing && (
          <textarea value={noteDraft} onChange={e => setNoteDraft(e.target.value)}
                    placeholder="备注（可选）..." rows={3}
                    style={{ padding: 10, borderRadius: 6, border: `1px solid ${T.border}`,
                             background: T.content, color: T.text, fontSize: 13,
                             fontFamily: 'inherit', resize: 'vertical' }}/>
        )}

        {/* 表格预览 */}
        {rowsSource && rowsSource.length > 0 ? (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>{rowsSource.length} 行 · {cols.length} 列</span>
            </div>
            <div className="cb-sb" style={{ overflowX: 'auto', maxHeight: 480 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: T.bg }}>
                    {cols.map(c => <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted, fontWeight: 600, fontSize: 11, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rowsSource.slice(0, 200).map((row, ri) => (
                    <tr key={ri} style={{ borderBottom: ri < rowsSource.length - 1 ? `1px solid ${T.borderSoft}` : 'none' }}>
                      {cols.map(c => <td key={c} style={{ padding: '8px 12px', color: T.text, whiteSpace: 'nowrap', fontFamily: typeof row[c] === 'number' ? T.mono : 'inherit' }}>{row[c] === null || row[c] === undefined ? <span style={{ color: T.muted }}>—</span> : String(row[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div style={{ padding: 24, textAlign: 'center', color: T.muted, fontSize: 13 }}>
            暂无数据 — 点上方"🔄 重跑一遍"
          </div>
        )}

        {/* 原始问题 + 备注 + SQL 折叠 */}
        <div style={{ padding: '12px 16px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, fontSize: 12.5, color: T.subtext }}>
          <div style={{ marginBottom: 4 }}><span style={{ color: T.muted }}>原始问题：</span>{report.question || '(无)'}</div>
          {report.pin_note && <div style={{ marginBottom: 4 }}><span style={{ color: T.muted }}>备注：</span>{report.pin_note}</div>}
          <details style={{ marginTop: 6 }}>
            <summary style={{ cursor: 'pointer', color: T.subtext, fontSize: 12 }}>查看冻结 SQL</summary>
            <pre style={{ margin: '6px 0 0', padding: '8px 10px', background: T.codeBg,
                          color: T.codeText, fontFamily: T.mono, fontSize: 11.5,
                          borderRadius: 6, overflowX: 'auto' }}>{report.sql_text}</pre>
          </details>
          <div style={{ fontSize: 11, color: T.muted, marginTop: 8 }}>
            注：本报表执行收藏时的快照 SQL，如需最新时间口径请重新发起对话。
          </div>
        </div>
      </div>
    </div>
  );
}

function safeParseRows(json) {
  if (!json) return [];
  try { return JSON.parse(json); } catch { return []; }
}

function pillBtn(T, primary = false) {
  return {
    padding: '6px 12px', borderRadius: 6, fontSize: 12.5,
    border: `1px solid ${primary ? T.accent : T.border}`,
    background: primary ? T.accent : 'transparent',
    color: primary ? '#fff' : T.text,
    cursor: 'pointer', fontFamily: 'inherit',
  };
}
