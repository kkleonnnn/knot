import { useState, useEffect } from 'react';
import { I, iconBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

const SAVED_SVG = {
  bookmark:   'M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z',
  chevronL:   'M15 18l-6-6 6-6',
  pencil:     'M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z',
  refresh:    'M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5',
  download:   'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  table:      'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18',
};

// R-348 INTENT_EMOJI 字典名 + 7 keys byte-equal；R-351 value 偿还为 svg path
const INTENT_EMOJI = {
  metric:       'M3 20h18M4 16l5-6 4 3 7-8',
  trend:        'M3 17l6-6 4 4 8-8M22 7h-5v5',
  compare:      'M3 6h18M6 6v15M18 6v15M3 21h18',
  rank:         'M8 21h8M12 17v4M17 4h3v4a5 5 0 0 1-5 5 5 5 0 0 1-5-5V4h3M7 4H4v4a5 5 0 0 0 5 5',
  distribution: 'M21.21 15.89A10 10 0 1 1 8 2.83M22 12A10 10 0 0 0 12 2v10z',
  retention:    'M19 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM16 2v4M8 2v4M3 10h18',
  detail:       'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8',
};

// R-373 time formatter "YYYY.MM.DD"
const formatTime = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`;
  } catch { return ''; }
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

  // R-353 Sidebar header T.mono + 删 📌；R-354 SavedItem bookmark + brandSoft + time mono
  const sidebarContent = (
    <>
      <button onClick={() => onNavigate('chat')} style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '9px 10px', borderRadius: 8, background: 'transparent',
        color: T.muted, border: `1px solid ${T.border}`,
        fontFamily: 'inherit', fontSize: 13, cursor: 'pointer', marginBottom: 8,
      }}>
        <SvgPath d={SAVED_SVG.chevronL} size={12}/> 返回对话
      </button>
      <div style={{
        padding: '10px 10px 4px', fontSize: 10, color: T.muted,
        fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>收藏报表 <span style={{ color: T.muted, fontWeight: 600 }}>{reports.length}</span></div>
      <div className="cb-sb" style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {reports.map(r => {
          const isActive = r.id === activeId;
          return (
            <div key={r.id} onClick={() => setActiveId(r.id)} style={{
              margin: '0 8px', padding: '8px 10px',
              borderRadius: 6, cursor: 'pointer',
              background: isActive ? T.accentSoft : 'transparent',
              border: `1px solid ${isActive ? `color-mix(in oklch, ${T.accent} 25%, transparent)` : 'transparent'}`,
              display: 'flex', alignItems: 'flex-start', gap: 10,
            }}>
              <span style={{ color: isActive ? T.accent : T.muted, flexShrink: 0, marginTop: 1 }}>
                <SvgPath d={SAVED_SVG.bookmark} size={14} fill={isActive ? T.accent : 'none'}/>
              </span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: isActive ? 500 : 400, color: isActive ? T.accent : T.text,
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.35 }}>{r.title || '未命名报表'}</div>
                <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, letterSpacing: '0.04em', marginTop: 2 }}>{formatTime(r.updated_at || r.created_at)}</div>
              </div>
              <button onClick={(e) => { e.stopPropagation(); handleDelete(r.id); }} style={{ ...iconBtn(T), width: 20, height: 20, opacity: 0.5, flexShrink: 0 }}><I.trash/></button>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <AppShell T={T} user={user} active="saved-reports" sidebarContent={sidebarContent}
              topbarTitle={active ? active.title : '收藏报表'} hideSidebarNewChat
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
        <div style={{ color: T.muted, marginBottom: 12, display: 'flex', justifyContent: 'center' }}>
          <SvgPath d={SAVED_SVG.bookmark} size={36}/>
        </div>
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
  const [runResult, setRunResult] = useState(null);
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

  async function handleExport(format) {
    try {
      const r = await fetch(`/api/saved-reports/${report.id}/export.${format}`, {
        headers: { Authorization: `Bearer ${api._token()}` },
      });
      if (!r.ok) { toast(`导出失败: ${r.status}`, true); return; }
      const truncated = r.headers.get('x-export-truncated') === 'true';
      const total = r.headers.get('x-export-total-rows');
      const exported = r.headers.get('x-export-returned-rows');
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `saved_report_${report.id}.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
      if (truncated) toast(`已截断至 ${exported} 行（共 ${total} 行）。如需全量请联系 admin。`, true);
    } catch (e) {
      toast(`导出失败: ${e.message}`, true);
    }
  }

  const rowsSource = runResult?.rows ?? safeParseRows(report.last_run_rows_json);
  const truncated = runResult ? runResult.truncated : (report.last_run_truncated === 1);
  const cols = rowsSource && rowsSource.length > 0 ? Object.keys(rowsSource[0]) : [];
  const lastRunMs = runResult?.last_run_ms ?? report.last_run_ms;
  const lastRunAt = runResult?.last_run_at || report.last_run_at;
  const warning = runResult?.warning;

  return (
    <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
      <div style={{ maxWidth: 880, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14 }}>

        {/* Title block: 22px + meta │ + StatusDot frozen (R-355/370/Q5) */}
        <div>
          {editing ? (
            <input value={titleDraft} onChange={e => setTitleDraft(e.target.value)}
                   style={{ width: '100%', padding: '8px 12px', borderRadius: 6,
                            border: `1px solid ${T.border}`, background: T.content, color: T.text,
                            fontSize: 22, fontWeight: 600, fontFamily: 'inherit' }}/>
          ) : (
            <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.01em', color: T.text, lineHeight: 1.3 }}>{report.title}</div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, fontSize: 12, color: T.muted, fontFamily: T.mono, letterSpacing: '0.02em', flexWrap: 'wrap' }}>
            <span>intent · <span style={{ color: T.text }}>{report.intent || 'detail'}</span></span>
            <span style={{ color: T.muted }}>│</span>
            <span>layout · <span style={{ color: T.text }}>{report.display_hint || 'detail_table'}</span></span>
            {lastRunAt && <><span style={{ color: T.muted }}>│</span><span>last_run · <span style={{ color: T.text }}>{lastRunAt}</span></span></>}
            {lastRunMs > 0 && <><span style={{ color: T.muted }}>│</span><span>{lastRunMs}ms</span></>}
            <span style={{ color: T.muted }}>│</span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.muted }}/>
              frozen
            </span>
          </div>
        </div>

        {/* 按钮行 (R-352 emoji→svg; R-371 hover state via pillBtn helper) */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {editing ? (
            <>
              <button onClick={handleSaveEdit} style={pillBtn(T, true)}>保存</button>
              <button onClick={() => setEditing(false)} style={pillBtn(T)}>取消</button>
            </>
          ) : (
            <>
              <button onClick={() => setEditing(true)} style={pillBtn(T)} title="改名 / 备注">
                <SvgPath d={SAVED_SVG.pencil} size={12}/> 编辑
              </button>
              <button onClick={handleRun} disabled={running} style={pillBtn(T, true)}>
                <SvgPath d={SAVED_SVG.refresh} size={12}/> {running ? '运行中…' : '重跑'}
              </button>
              <button onClick={() => handleExport('csv')} style={pillBtn(T)} title="导出 CSV">
                <SvgPath d={SAVED_SVG.download} size={12}/> CSV
              </button>
              <button onClick={() => handleExport('xlsx')} style={pillBtn(T)} title="导出 Excel xlsx（5000 行硬限）">
                <SvgPath d={SAVED_SVG.table} size={12}/> Excel
              </button>
            </>
          )}
        </div>

        {/* warning banner — R-360 hex 清理 → T.warn + color-mix；R-362 ⚠️ 保留 */}
        {warning && (
          <div style={{ padding: '10px 14px', borderRadius: 8,
                        background: `color-mix(in oklch, ${T.warn} 13%, transparent)`,
                        border: `1px solid ${T.warn}`, color: T.warn, fontSize: 12.5 }}>
            ⚠️ {warning}
          </div>
        )}
        {truncated && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: T.accentSoft, color: T.accent, fontSize: 12 }}>
            🔍 仅展示前 200 行预览（完整结果请点 CSV 导出）
          </div>
        )}
        {runResult?.error && (
          <div style={{ padding: '10px 14px', borderRadius: 8, background: T.accentSoft,
                        border: `1px solid color-mix(in oklch, ${T.accent} 19%, transparent)`, color: T.accent, fontSize: 12.5 }}>
            ❌ {runResult.error}
          </div>
        )}

        {editing && (
          <textarea value={noteDraft} onChange={e => setNoteDraft(e.target.value)}
                    placeholder="备注（可选）..." rows={3}
                    style={{ padding: 10, borderRadius: 6, border: `1px solid ${T.border}`,
                             background: T.content, color: T.text, fontSize: 13,
                             fontFamily: 'inherit', resize: 'vertical' }}/>
        )}

        {rowsSource && rowsSource.length > 0 ? (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>{rowsSource.length} 行 · {cols.length} 列</span>
              {INTENT_EMOJI[report.intent] && (
                <span style={{ color: T.muted }}>
                  <SvgPath d={INTENT_EMOJI[report.intent]} size={13}/>
                </span>
              )}
            </div>
            <div className="cb-sb" style={{ overflowX: 'auto', maxHeight: 480 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  {/* v0.5.27 #24 全站表头统一 — brandSoft 8% bg + mono + 0.06em + uppercase + T.subtext（与 admin 屏 R-480/R-444/R-409/R-504 字面 byte-equal）*/}
                  <tr style={{ background: `color-mix(in oklch, ${T.accent} 8%, transparent)` }}>
                    {cols.map(c => <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.subtext, fontFamily: T.mono, fontWeight: 500, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{c}</th>)}
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
            暂无数据 — 点上方"重跑"
          </div>
        )}

        {/* Original question quote — R-356/372 inset color-mix 8% 闭环 v0.5.14 R-323 */}
        <div style={{
          padding: '12px 14px',
          borderLeft: `3px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
          background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
          borderRadius: 6, fontSize: 12.5, color: T.subtext, lineHeight: 1.6,
        }}>
          <div style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, letterSpacing: '0.08em',
                        textTransform: 'uppercase', marginBottom: 4 }}>原始问题</div>
          {report.question || '(无)'}
          {report.pin_note && <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid color-mix(in oklch, ${T.accent} 15%, transparent)` }}>
            <span style={{ color: T.muted, fontSize: 10, fontFamily: T.mono, letterSpacing: '0.08em', textTransform: 'uppercase' }}>备注 · </span>{report.pin_note}
          </div>}
        </div>

        {/* SQL details */}
        <details style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <summary style={{ cursor: 'pointer', padding: '10px 14px', color: T.subtext, fontSize: 12, fontFamily: T.mono, listStyle: 'none', display: 'flex', alignItems: 'center', gap: 8 }}>
            <SvgPath d={SAVED_SVG.chevronL} size={11}/>
            <span style={{ color: T.text }}>{'<>'}</span>
            查看冻结 SQL
            <span style={{ marginLeft: 'auto', color: T.muted, fontSize: 10 }}>注 · 收藏时的快照 SQL</span>
          </summary>
          <pre style={{ margin: 0, padding: '10px 16px 14px', borderTop: `1px solid ${T.border}`,
                        fontFamily: T.mono, fontSize: 11.5, color: T.codeText,
                        background: T.codeBg, overflowX: 'auto' }}>{report.sql_text}</pre>
        </details>
      </div>
    </div>
  );
}

function safeParseRows(json) {
  if (!json) return [];
  try { return JSON.parse(json); } catch { return []; }
}

// R-361 pillBtn primary color → T.sendFg
function pillBtn(T, primary = false) {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '6px 12px', borderRadius: 6, fontSize: 12.5,
    border: `1px solid ${primary ? T.accent : T.border}`,
    background: primary ? T.accent : 'transparent',
    color: primary ? T.sendFg : T.text,
    cursor: 'pointer', fontFamily: 'inherit',
  };
}
