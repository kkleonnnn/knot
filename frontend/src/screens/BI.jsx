// BI.jsx — v0.8.5 (②a) BIScreen：BI 报表模式屏。
// ⭐ 与 ASK 共用同一 <AppShell>（侧栏壳 + brand + topbar + 用户 footer 全在 Shell 内）——
//    BI 只切换两处 slot：sidebarContent = 报表目录树；children = [报表主区 flex:1 单一纵向滚动 | da-asst 满高 border-left]。
//    右上角集群（数据源·N · 主题 · ASK/BI）+ 用户 footer 由 AppShell 统一渲染 → 两模式严格一致（kk 根因修）。
import { useEffect, useState } from 'react';
import { AppShell } from '../Shell.jsx';
import { usePersist, Modal, ModalHeader, Input, toast } from '../utils.jsx';
import { api } from '../api.js';
import { ReportDirectory } from './bi/ReportDirectory.jsx';
import { WideTableReport } from './bi/WideTableReport.jsx';
import { DashboardReport } from './bi/DashboardReport.jsx';
import { SkillPanel } from './bi/SkillPanel.jsx';
import { ReportBuilderModal } from './bi/ReportBuilderModal.jsx';

async function download(path, filename) {
  try {
    const r = await fetch(path, { headers: { Authorization: `Bearer ${localStorage.getItem('cb_token') || ''}` } });
    if (!r.ok) { toast(`导出失败（${r.status}）`, true); return; }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  } catch (e) { toast(`导出失败：${e.message || e}`, true); }
}

// 操作按钮 line icon（handoff §4）
const ICONS = {
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
  refresh: 'M21 12a9 9 0 1 1-3-6.7M21 4v5h-5',
  csv: 'M12 3v12M8 11l4 4 4-4M5 21h14',
  excel: 'M4 4h16v16H4zM4 9h16M4 14.5h16M9.5 4v16',
  trash: 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14',
};
// v0.8.5 ②a #6 分享 icon = 多元素（3 节点 + 连线）→ 走 iconNode（ICONS 单 path 表达不了）
const SHARE_ICON = (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}>
    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" />
  </svg>
);
function ActBtn({ T, icon, iconNode, label, onClick, primary, disabled, danger, title }) {
  const [hover, setHover] = useState(false);  // #6 幽灵块 hover → var(--hover)
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 6, fontSize: 12.5,
        border: primary ? 'none' : `1px solid ${T.border}`, fontFamily: 'inherit', cursor: disabled ? 'default' : 'pointer',
        background: primary ? T.accent : (!disabled && hover ? T.hover : 'transparent'),
        color: primary ? T.sendFg : (danger ? T.warn : T.subtext), opacity: disabled ? 0.5 : 1,
        transition: 'background 120ms',
      }}>
      {iconNode || <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'block' }}><path d={ICONS[icon]} /></svg>}
      {label}
    </button>
  );
}

export function BIScreen({ T, user, onToggleTheme, onNavigate, onLogout, dbOk, sourceCount }) {
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [dataSources, setDataSources] = useState([]);
  const [selectedId, setSelectedId] = usePersist('cb_bi_report', null);
  const [selected, setSelected] = useState(null);
  const [builder, setBuilder] = useState(null);
  const [folderModal, setFolderModal] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [busy, setBusy] = useState(false);
  const isAdmin = user && user.role === 'admin';

  const loadLists = () => {
    api.get('/api/bi/folders').then((f) => setFolders(Array.isArray(f) ? f : [])).catch(() => {});
    api.get('/api/bi/reports').then((r) => setReports(Array.isArray(r) ? r : [])).catch(() => {});
  };
  const loadSelected = (id) => {
    if (id == null) { setSelected(null); return; }
    api.get(`/api/bi/reports/${id}`).then(setSelected).catch(() => setSelected(null));
  };

  /* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
  useEffect(() => {
    loadLists();
    if (user && user.role === 'admin') {
      api.get('/api/admin/datasources').then((d) => setDataSources(Array.isArray(d) ? d : [])).catch(() => {});
    }
  }, []);
  useEffect(() => { loadSelected(selectedId); }, [selectedId]);
  /* eslint-enable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */

  const refresh = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const out = await api.post(`/api/bi/reports/${selected.id}/refresh`);
      if (out && out.error) toast(out.error, true); else toast('已刷新');
      loadSelected(selected.id); loadLists();
    } catch (e) { toast(`刷新失败：${e.message || e}`, true); } finally { setBusy(false); }
  };
  const del = async () => {
    if (!selected) return;
    if (!window.confirm(`删除报表「${selected.title}」？`)) return;
    try { await api.del(`/api/bi/reports/${selected.id}`); toast('已删除'); setSelectedId(null); loadLists(); }
    catch (e) { toast(`删除失败：${e.message || e}`, true); }
  };
  const saveFolder = async () => {
    if (!folderName.trim()) return;
    try { await api.post('/api/bi/folders', { name: folderName.trim() }); toast('已建文件夹'); setFolderName(''); setFolderModal(false); loadLists(); }
    catch (e) { toast(`建文件夹失败：${e.message || e}`, true); }
  };

  return (
    <>
      <AppShell T={T} user={user} active="bi"
        sidebarContent={
          <ReportDirectory T={T} folders={folders} reports={reports} selectedId={selectedId} onSelect={setSelectedId}
            isAdmin={isAdmin} onNewReport={isAdmin ? () => setBuilder('new') : undefined}
            onNewFolder={isAdmin ? () => setFolderModal(true) : undefined} />
        }
        topbarTitle={selected ? selected.title : ''}
        showConnectionPill connectionOk={dbOk}
        connectedCount={sourceCount != null ? sourceCount : (dbOk ? 1 : 0)}
        onToggleTheme={onToggleTheme} onNavigate={onNavigate} onLogout={onLogout}>
        {/* 主区 = 单主面板内 flex 行：[报表主区 flex:1 单一纵向滚动] [da-asst 满高 · border-left] */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {selected ? (
              <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
                <div style={{ maxWidth: 1200, margin: '0 auto', padding: '22px 30px 30px' }}>
                  {/* #5：报表名已进 topbar（横线上）→ 内容区删大 H1，只留极简副标 last_run */}
                  <div style={{ fontFamily: T.mono, fontSize: 12, color: T.muted, marginBottom: 16 }}>
                    last_run · {selected.last_run_at || '—'}
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                    {isAdmin && <ActBtn T={T} icon="edit" label="编辑" onClick={() => setBuilder(selected)} />}
                    {isAdmin && <ActBtn T={T} icon="clock" label="定时" disabled title="调度器即将上线（②c）" />}
                    {isAdmin && <ActBtn T={T} icon="refresh" label={busy ? '刷新中…' : '重跑'} primary onClick={refresh} disabled={busy} />}
                    {/* C-1/B-7：dashboard 无报表级快照 → 隐藏整表导出（后端 _report_rows_or_404 亦拒 400）*/}
                    {selected.report_type !== 'dashboard' && <ActBtn T={T} icon="csv" label="CSV" onClick={() => download(`/api/bi/reports/${selected.id}/export.csv`, `bi_report_${selected.id}.csv`)} />}
                    {selected.report_type !== 'dashboard' && <ActBtn T={T} icon="excel" label="Excel" onClick={() => download(`/api/bi/reports/${selected.id}/export.xlsx`, `bi_report_${selected.id}.xlsx`)} />}
                    <ActBtn T={T} iconNode={SHARE_ICON} label="分享" title="分享报表（即将上线）" onClick={() => toast('分享功能即将上线')} />
                    {isAdmin && <ActBtn T={T} icon="trash" label="删除" danger onClick={del} />}
                  </div>
                  {selected.report_type === 'dashboard'
                    ? <DashboardReport T={T} report={selected} />
                    : <WideTableReport T={T} report={selected} />}
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
                选择左侧报表查看{isAdmin ? '，或点 + 新建报表' : '（报表由管理员创建）'}。
              </div>
            )}
          </div>
          <SkillPanel T={T} report={selected} />
        </div>
      </AppShell>

      {/* 模态 */}
      {builder && (
        <ReportBuilderModal T={T} editing={builder === 'new' ? null : builder}
          folders={folders} dataSources={dataSources}
          onClose={() => setBuilder(null)} onSaved={() => { loadLists(); if (selected) loadSelected(selected.id); }} />
      )}
      {folderModal && (
        <Modal T={T} onClose={() => setFolderModal(false)} width={420}>
          <ModalHeader T={T} title="新建文件夹" onClose={() => setFolderModal(false)} />
          <div style={{ padding: 20 }}>
            <Input T={T} label="文件夹名" value={folderName} onChange={setFolderName} placeholder="平台经营" required />
          </div>
          <div style={{ padding: '14px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button onClick={() => setFolderModal(false)} style={{ padding: '8px 16px', borderRadius: 7, border: `1px solid ${T.border}`, background: 'transparent', color: T.subtext, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>取消</button>
            <button onClick={saveFolder} style={{ padding: '8px 18px', borderRadius: 7, border: 'none', background: T.accent, color: T.sendFg, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600 }}>创建</button>
          </div>
        </Modal>
      )}
    </>
  );
}
