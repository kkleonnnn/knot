// ReportDirectory.jsx — v0.8.5 (②a) BI 左栏报表目录（文件夹树 + 报表 + 搜索）。
// admin 管理入口（新建文件夹/报表）仅当 onNewFolder/onNewReport 传入时渲染（commit 6 接 builder）。
import { useMemo, useState } from 'react';

// 报表类型图标（inline SVG，viewBox 24 / stroke 1.6，匹配 I-lib 视觉语言 R-BI-3）
function TypeIcon({ T, type }) {
  const p = type === 'dashboard'
    ? <path d="M4 13a8 8 0 0 1 16 0M12 13l4-4" />               // 仪表盘：表盘
    : <><path d="M4 7h16M4 12h16M4 17h16" /><path d="M9 4v16" /></>; // 宽表：表格
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={T.muted} strokeWidth="1.6"
         strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>{p}</svg>
  );
}

function ReportRow({ T, report, selected, onSelect }) {
  return (
    <button onClick={() => onSelect(report.id)} style={{
      display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left',
      padding: '7px 10px 7px 22px', borderRadius: 8, border: 'none', cursor: 'pointer',
      background: selected ? T.accentSoft : 'transparent',
      color: selected ? T.text : T.subtext, fontFamily: 'inherit',
    }}>
      <TypeIcon T={T} type={report.report_type} />
      <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 }}>
        {report.title}
      </span>
      {report.last_run_at && (
        <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>
          {String(report.last_run_at).slice(0, 10)}
        </span>
      )}
    </button>
  );
}

function FolderNode({ T, folder, folders, reports, selectedId, onSelect, depth }) {
  const [open, setOpen] = useState(true);
  const childFolders = folders.filter((f) => f.parent_id === folder.id);
  const childReports = reports.filter((r) => r.folder_id === folder.id);
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)} style={{
        display: 'flex', alignItems: 'center', gap: 6, width: '100%', textAlign: 'left',
        padding: '7px 10px', paddingLeft: 10 + depth * 12, borderRadius: 8, border: 'none',
        background: 'transparent', color: T.text, cursor: 'pointer', fontFamily: 'inherit',
      }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke={T.muted} strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round"
             style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .12s', flexShrink: 0 }}>
          <path d="M9 6l6 6-6 6" />
        </svg>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={T.subtext} strokeWidth="1.6"
             strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
        <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{folder.name}</span>
        <span style={{ fontSize: 11, color: T.muted }}>{childReports.length || ''}</span>
      </button>
      {open && (
        <div>
          {childFolders.map((cf) => (
            <FolderNode key={cf.id} T={T} folder={cf} folders={folders} reports={reports}
                        selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />
          ))}
          {childReports.map((r) => (
            <ReportRow key={r.id} T={T} report={r} selected={r.id === selectedId} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ReportDirectory({ T, folders = [], reports = [], selectedId, onSelect,
                                 isAdmin = false, onNewFolder, onNewReport }) {
  const [q, setQ] = useState('');
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return kw ? reports.filter((r) => (r.title || '').toLowerCase().includes(kw)) : reports;
  }, [q, reports]);

  const topFolders = folders.filter((f) => f.parent_id == null);
  const unfiled = filtered.filter((r) => r.folder_id == null);
  const canManage = isAdmin && (onNewFolder || onNewReport);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ padding: '4px 4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: T.muted, letterSpacing: '0.04em' }}>报表目录</span>
        {canManage && (
          <span style={{ display: 'flex', gap: 4 }}>
            {onNewFolder && (
              <button onClick={onNewFolder} title="新建文件夹" style={iconBtnMini(T)}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 11v4M10 13h4" />
                </svg>
              </button>
            )}
            {onNewReport && (
              <button onClick={onNewReport} title="新建报表" style={iconBtnMini(T)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
          </span>
        )}
      </div>
      <div style={{ padding: '0 4px 8px' }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索报表…"
          style={{
            width: '100%', padding: '7px 10px', borderRadius: 8, fontSize: 12.5,
            border: `1px solid ${T.border}`, background: T.inputBg, color: T.text, fontFamily: 'inherit',
          }} />
      </div>
      <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {topFolders.map((f) => (
          <FolderNode key={f.id} T={T} folder={f} folders={folders} reports={filtered}
                      selectedId={selectedId} onSelect={onSelect} depth={0} />
        ))}
        {unfiled.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div style={{ padding: '7px 10px', fontSize: 11, color: T.muted, letterSpacing: '0.04em' }}>未归档</div>
            {unfiled.map((r) => (
              <ReportRow key={r.id} T={T} report={r} selected={r.id === selectedId} onSelect={onSelect} />
            ))}
          </div>
        )}
        {!reports.length && (
          <div style={{ padding: '24px 12px', textAlign: 'center', color: T.muted, fontSize: 12 }}>
            暂无报表{isAdmin ? '，点 + 新建' : ''}。
          </div>
        )}
      </div>
    </div>
  );
}

const iconBtnMini = (T) => ({
  width: 24, height: 24, display: 'grid', placeItems: 'center', border: 'none',
  background: 'transparent', color: T.subtext, cursor: 'pointer', borderRadius: 6,
});
