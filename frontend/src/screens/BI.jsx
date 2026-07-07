// BI.jsx — v0.8.5 (②a) BIScreen：BI 报表模式屏（全新 BIShell，独立 AppShell — D2/R-192）。
// 布局照 artboard：左目录 + 右区（全宽顶栏[标题 · 右上角集群] + 下方 [报表主区 | da-asst 面板]）。
// 右上角集群 = 数据源·N · 主题开关 · ASK/BI（与 AppShell 一致，问题①修）。全用 buildTheme token（VRP）。
import { useEffect, useState } from 'react';
import { I, KnotLogo, iconBtn } from '../Shared.jsx';
import { APP_VERSION } from '../version.js';
import { usePersist, Modal, ModalHeader, Input, toast } from '../utils.jsx';
import { api } from '../api.js';
import { ReportDirectory } from './bi/ReportDirectory.jsx';
import { WideTableReport } from './bi/WideTableReport.jsx';
import { DashboardReport } from './bi/DashboardReport.jsx';
import { SkillPanel } from './bi/SkillPanel.jsx';
import { ReportBuilderModal } from './bi/ReportBuilderModal.jsx';
import { ModeToggle } from './bi/ModeToggle.jsx';

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

// 操作按钮 12px line icon（handoff §4）
const ICONS = {
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
  refresh: 'M21 12a9 9 0 1 1-3-6.7M21 4v5h-5',
  csv: 'M12 3v12M8 11l4 4 4-4M5 21h14',
  excel: 'M4 4h16v16H4zM4 9h16M4 14.5h16M9.5 4v16',
  trash: 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14',
};
function ActBtn({ T, icon, label, onClick, primary, disabled, danger, title }) {
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 6, fontSize: 12.5,
        border: primary ? 'none' : `1px solid ${T.border}`, fontFamily: 'inherit', cursor: disabled ? 'default' : 'pointer',
        background: primary ? T.accent : 'transparent', color: primary ? T.sendFg : (danger ? T.warn : T.subtext), opacity: disabled ? 0.5 : 1,
      }}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[icon]} /></svg>
      {label}
    </button>
  );
}

export function BIScreen({ T, user, onToggleTheme, onNavigate, dbOk, sourceCount }) {
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [dataSources, setDataSources] = useState([]);
  const [selectedId, setSelectedId] = usePersist('cb_bi_report', null);
  const [selected, setSelected] = useState(null);
  const [skillCollapsed, setSkillCollapsed] = useState(false);
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

  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', gap: 10, padding: 10,
      background: T.bg, color: T.text, fontFamily: T.sans, fontSize: 13.5, overflow: 'hidden',
      letterSpacing: '-0.003em', lineHeight: 1.5,
    }}>
      {/* ═══ 左：报表目录（全高）═══ */}
      <aside style={{ width: 236, flexShrink: 0, background: T.sidebar, border: `1px solid ${T.border}`, borderRadius: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <div style={{ height: 56, padding: '0 16px', flexShrink: 0, display: 'flex', alignItems: 'center', borderBottom: `1px solid ${T.border}` }}>
          <KnotLogo T={T} size={20} />
          <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: T.mono, color: T.muted, letterSpacing: '0.06em' }}>v{APP_VERSION}</span>
        </div>
        <div style={{ flex: 1, minHeight: 0, padding: '8px 8px 0' }}>
          <ReportDirectory T={T} folders={folders} reports={reports} selectedId={selectedId} onSelect={setSelectedId}
            isAdmin={isAdmin} onNewReport={isAdmin ? () => setBuilder('new') : undefined}
            onNewFolder={isAdmin ? () => setFolderModal(true) : undefined} />
        </div>
        <div style={{ padding: '10px 14px', borderTop: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: T.accentSoft, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 600, color: T.accent }}>{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user && user.username}</div>
            <div style={{ fontSize: 10, color: T.muted, letterSpacing: '0.06em' }}>{((user && user.role) || '').toUpperCase()}</div>
          </div>
        </div>
      </aside>

      {/* ═══ 右区：全宽顶栏 + 下方（主区 | da-asst）═══ */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* 全宽顶栏：标题左 · 右上角集群（数据源·N · 主题 · ASK/BI）——与 AppShell 一致（问题①）*/}
        <header style={{
          height: 56, flexShrink: 0, padding: '0 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: T.content, border: `1px solid ${T.border}`, borderRadius: 14,
        }}>
          <div style={{ fontSize: 14, color: T.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selected ? selected.title : 'BI 报表'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: T.muted, fontSize: 12 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: dbOk === false ? T.warn : T.success, flexShrink: 0 }} />
              <span>数据源 · {dbOk === false ? '未连接' : (sourceCount != null ? `${sourceCount} 已连接` : '已连接')}</span>
            </span>
            <button onClick={onToggleTheme} style={{ ...iconBtn(T), width: 30, height: 30, border: `1px solid ${T.border}` }} title="切换主题">
              {T.dark ? <I.sun /> : <I.moon />}
            </button>
            <ModeToggle T={T} active="bi" onNavigate={onNavigate} />
          </div>
        </header>

        {/* 下方：报表主区 | da-asst 面板 */}
        <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 10 }}>
          <main style={{ flex: 1, minWidth: 0, background: T.content, border: `1px solid ${T.border}`, borderRadius: 14, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {selected ? (
              <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
                <div style={{ maxWidth: 1200, margin: '0 auto', padding: '22px 30px 30px' }}>
                  <div style={{ fontSize: 22, fontWeight: 600, color: T.text, marginBottom: 8 }}>{selected.title}</div>
                  <div style={{ fontFamily: T.mono, fontSize: 11.5, color: T.muted, marginBottom: 16, display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                    <span>intent · {selected.report_type === 'dashboard' ? 'compare' : 'detail'}</span>
                    <span>layout · {selected.report_type === 'dashboard' ? 'overview_grid' : 'wide_table'}</span>
                    <span>last_run · {selected.last_run_at || '—'}</span>
                    {selected.last_run_ms ? <span>{selected.last_run_ms}ms</span> : null}
                    <span style={{ color: T.warn }}>● frozen</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                    {isAdmin && <ActBtn T={T} icon="edit" label="编辑" onClick={() => setBuilder(selected)} />}
                    {isAdmin && <ActBtn T={T} icon="clock" label="定时" disabled title="调度器即将上线（②c）" />}
                    {isAdmin && <ActBtn T={T} icon="refresh" label={busy ? '刷新中…' : '重跑'} primary onClick={refresh} disabled={busy} />}
                    <ActBtn T={T} icon="csv" label="CSV" onClick={() => download(`/api/bi/reports/${selected.id}/export.csv`, `bi_report_${selected.id}.csv`)} />
                    <ActBtn T={T} icon="excel" label="Excel" onClick={() => download(`/api/bi/reports/${selected.id}/export.xlsx`, `bi_report_${selected.id}.xlsx`)} />
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
          </main>
          <SkillPanel T={T} report={selected} collapsed={skillCollapsed} onToggle={() => setSkillCollapsed((c) => !c)} />
        </div>
      </div>

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
    </div>
  );
}
