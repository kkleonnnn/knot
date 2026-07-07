// BI.jsx — v0.8.5 (②a) BIScreen：BI 报表模式屏（全新 BIShell，独立 AppShell — D2/R-BI-1/R-192）。
// 3 列：左报表目录 + 中报表主区 + 右 da-asst 占位。全用 buildTheme token（R-BI-3 VRP，fluid + anchored）。
import { useEffect, useState } from 'react';
import { KnotLogo, iconBtn } from '../Shared.jsx';
import { APP_VERSION } from '../version.js';
import { usePersist } from '../utils.jsx';
import { api } from '../api.js';
import { ReportDirectory } from './bi/ReportDirectory.jsx';
import { WideTableReport } from './bi/WideTableReport.jsx';
import { SkillPanelPlaceholder } from './bi/SkillPanelPlaceholder.jsx';

export function BIScreen({ T, user, onToggleTheme }) {
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [selectedId, setSelectedId] = usePersist('cb_bi_report', null);
  const [selected, setSelected] = useState(null);
  const [skillCollapsed, setSkillCollapsed] = useState(false);
  const isAdmin = user && user.role === 'admin';

  useEffect(() => {
    api.get('/api/bi/folders').then((f) => setFolders(Array.isArray(f) ? f : [])).catch(() => {});
    api.get('/api/bi/reports').then((r) => setReports(Array.isArray(r) ? r : [])).catch(() => {});
  }, []);

  // reset + async 取详情：同步 reset 是选择切换标准模式（同 App.jsx prefetch 约定）
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (selectedId == null) { setSelected(null); return; }
    api.get(`/api/bi/reports/${selectedId}`).then(setSelected).catch(() => setSelected(null));
  }, [selectedId]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const initials = user ? (user.display_name || user.username || '?').slice(0, 2).toUpperCase() : '?';

  return (
    <div style={{
      width: '100vw', height: '100vh', display: 'flex', gap: 10, padding: 10,
      background: T.bg, color: T.text, fontFamily: T.sans, fontSize: 13.5, overflow: 'hidden',
      letterSpacing: '-0.003em', lineHeight: 1.5,
    }}>
      {/* ═══ 左：报表目录 ═══ */}
      <aside style={{
        width: 224, flexShrink: 0, background: T.sidebar, border: `1px solid ${T.border}`,
        borderRadius: 14, overflow: 'hidden', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ height: 56, padding: '0 16px', flexShrink: 0, display: 'flex', alignItems: 'center', borderBottom: `1px solid ${T.border}` }}>
          <KnotLogo T={T} size={20} />
          <span style={{ marginLeft: 'auto', fontSize: 11, fontFamily: T.mono, color: T.muted, letterSpacing: '0.06em' }}>v{APP_VERSION}</span>
        </div>
        <div style={{ flex: 1, minHeight: 0, padding: '8px 8px 0' }}>
          <ReportDirectory T={T} folders={folders} reports={reports}
                           selectedId={selectedId} onSelect={setSelectedId} isAdmin={isAdmin} />
        </div>
        <div style={{ padding: '10px 14px', borderTop: `1px solid ${T.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: T.accentSoft, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 600, color: T.accent }}>{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12.5, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user && user.username}</div>
            <div style={{ fontSize: 10, color: T.muted, letterSpacing: '0.06em' }}>{(user && user.role || '').toUpperCase()}</div>
          </div>
        </div>
      </aside>

      {/* ═══ 中：报表主区 ═══ */}
      <main style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, paddingRight: 130 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {selected ? selected.title : 'BI 报表'}
          </span>
          <button onClick={onToggleTheme} title="切换主题" style={{ ...iconBtn(T), marginLeft: 'auto', width: 30, height: 30, border: `1px solid ${T.border}` }}>
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
    </div>
  );
}
