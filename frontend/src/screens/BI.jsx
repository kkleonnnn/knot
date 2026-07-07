// BI.jsx — v0.8.5 (②a) BIScreen：BI 报表模式屏（全新 BIShell，独立 AppShell — D2/R-BI-1/R-192）。
// 3 列：左报表目录 + 中报表主区 + 右 da-asst 占位。全用 buildTheme token（R-BI-3 VRP，fluid + anchored）。
import { useEffect, useState } from 'react';
import { KnotLogo, iconBtn } from '../Shared.jsx';
import { APP_VERSION } from '../version.js';
import { usePersist, Modal, ModalHeader, Input, toast } from '../utils.jsx';
import { api } from '../api.js';
import { ReportDirectory } from './bi/ReportDirectory.jsx';
import { WideTableReport } from './bi/WideTableReport.jsx';
import { SkillPanelPlaceholder } from './bi/SkillPanelPlaceholder.jsx';
import { ReportBuilderModal } from './bi/ReportBuilderModal.jsx';

// 认证下载（export 端点走 Bearer；window.open 不带 header → fetch blob 触发下载）
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

export function BIScreen({ T, user, onToggleTheme }) {
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [dataSources, setDataSources] = useState([]);
  const [selectedId, setSelectedId] = usePersist('cb_bi_report', null);
  const [selected, setSelected] = useState(null);
  const [skillCollapsed, setSkillCollapsed] = useState(false);
  const [builder, setBuilder] = useState(null);       // null | 'new' | report(edit)
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
    try {
      await api.del(`/api/bi/reports/${selected.id}`);
      toast('已删除'); setSelectedId(null); loadLists();
    } catch (e) { toast(`删除失败：${e.message || e}`, true); }
  };
  const saveFolder = async () => {
    if (!folderName.trim()) return;
    try { await api.post('/api/bi/folders', { name: folderName.trim() }); toast('已建文件夹'); setFolderName(''); setFolderModal(false); loadLists(); }
    catch (e) { toast(`建文件夹失败：${e.message || e}`, true); }
  };

  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';
  const actBtn = (active) => ({
    display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 11px', borderRadius: 7, fontSize: 12,
    border: `1px solid ${T.border}`, background: 'transparent', color: active ? T.subtext : T.muted,
    cursor: active ? 'pointer' : 'default', fontFamily: 'inherit', opacity: active ? 1 : 0.5,
  });

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', gap: 10, padding: 10,
      background: T.bg, color: T.text, fontFamily: T.sans, fontSize: 13.5, overflow: 'hidden',
      letterSpacing: '-0.003em', lineHeight: 1.5,
    }}>
      {/* ═══ 左：报表目录 ═══ */}
      <aside style={{ width: 224, flexShrink: 0, background: T.sidebar, border: `1px solid ${T.border}`, borderRadius: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
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

      {/* ═══ 中：报表主区 ═══ */}
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ minHeight: 48, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', paddingRight: 130 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginRight: 'auto' }}>
            {selected ? selected.title : 'BI 报表'}
          </span>
          {selected && isAdmin && (
            <>
              <button onClick={() => setBuilder(selected)} style={actBtn(true)}>编辑</button>
              <button title="调度器即将上线（②c）" style={actBtn(false)} disabled>定时</button>
              <button onClick={refresh} style={actBtn(true)} disabled={busy}>{busy ? '刷新中…' : '重跑'}</button>
            </>
          )}
          {selected && (
            <>
              <button onClick={() => download(`/api/bi/reports/${selected.id}/export.csv`, `bi_report_${selected.id}.csv`)} style={actBtn(true)}>CSV</button>
              <button onClick={() => download(`/api/bi/reports/${selected.id}/export.xlsx`, `bi_report_${selected.id}.xlsx`)} style={actBtn(true)}>Excel</button>
            </>
          )}
          {selected && isAdmin && <button onClick={del} style={{ ...actBtn(true), color: T.warn }}>删除</button>}
          <button onClick={onToggleTheme} title="切换主题" style={{ ...iconBtn(T), width: 30, height: 30, border: `1px solid ${T.border}` }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" /></svg>
          </button>
        </div>
        <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          {selected ? (
            <>
              <div style={{ fontFamily: T.mono, fontSize: 11, color: T.muted, marginBottom: 12, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <span>type · {selected.report_type}</span>
                <span>last_run · {selected.last_run_at || '—'}</span>
                {selected.last_run_ms ? <span>{selected.last_run_ms}ms</span> : null}
                <span style={{ color: T.warn }}>● frozen</span>
              </div>
              <WideTableReport T={T} report={selected} />
            </>
          ) : (
            <div style={{ display: 'grid', placeItems: 'center', height: '100%', color: T.muted, fontSize: 13 }}>
              选择左侧报表查看{isAdmin ? '，或点 + 新建报表' : '（报表由管理员创建）'}。
            </div>
          )}
        </div>
      </main>

      {/* ═══ 右：da-asst 占位 ═══ */}
      <SkillPanelPlaceholder T={T} collapsed={skillCollapsed} onToggle={() => setSkillCollapsed((c) => !c)} />

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
