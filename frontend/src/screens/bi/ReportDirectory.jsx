// ReportDirectory.jsx — v0.8.5 (②a) BI 左栏报表目录（文件夹树 + 报表 + 搜索）。
// admin 管理入口（新建文件夹/报表）仅当 onNewFolder/onNewReport 传入时渲染（commit 6 接 builder）。
import { useMemo, useState } from 'react';

// 报表类型图标（handoff §3）：宽表 = 表格网格图标 success 绿；图表类 = 折线趋势 青/muted。一眼区分。
function TypeIcon({ T, type }) {
  const wide = type !== 'dashboard';   // 非 dashboard（wide_table 等）= 宽表 → 绿表格
  return wide ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={T.success} strokeWidth="1.6"
         strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      <rect x="3" y="4" width="18" height="16" rx="1.5" /><path d="M3 9h18M3 14.5h18M9 4v16" />
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.6"
         strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
      <path d="M4 19V5M4 19h16M7 15l3-4 3 3 4-6" />
    </svg>
  );
}

function ReportRow({ T, report, selected, onSelect, dnd }) {
  // v0.8.5 ②a #3：选中样式 = ASK 会话项同一套（accent 8% 底 + accent 25% 四边 border + radius 6，margin 0 8px；
  // 去左侧竖条；inactive 用 transparent 1px border 防 layout shift）
  // v0.8.8 ③：admin 非搜索态可拖拽排序（同文件夹内）—— dnd 存在即启用（HTML5 draggable，R-186 无库）。
  return (
    <button onClick={() => onSelect(report.id)}
      draggable={!!dnd} onDragStart={dnd?.onStart}
      onDragOver={dnd ? (e) => e.preventDefault() : undefined} onDrop={dnd?.onDrop}
      style={{
      display: 'flex', alignItems: 'center', gap: 8, width: 'calc(100% - 16px)', textAlign: 'left',
      margin: '0 8px 1px', padding: '7px 10px', borderRadius: 6, cursor: dnd ? 'grab' : 'pointer',
      opacity: dnd && dnd.dragging ? 0.4 : 1,
      background: selected ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : 'transparent',
      border: selected ? `1px solid color-mix(in oklch, ${T.accent} 25%, transparent)` : '1px solid transparent',
      color: selected ? T.text : T.subtext, fontWeight: selected ? 500 : 400, fontFamily: 'inherit',
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

function FolderNode({ T, folder, folders, reports, selectedId, onSelect, depth, reportDnd, folderDnd }) {
  const [open, setOpen] = useState(true);
  const childFolders = folders.filter((f) => f.parent_id === folder.id);
  const childReports = reports.filter((r) => r.folder_id === folder.id);
  const fdnd = folderDnd && folderDnd(folder, folder.parent_id ?? null);   // 本文件夹拖拽（同级重排）
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)}
        draggable={!!fdnd} onDragStart={fdnd?.onStart}
        onDragOver={fdnd ? (e) => e.preventDefault() : undefined} onDrop={fdnd?.onDrop}
        style={{
        display: 'flex', alignItems: 'center', gap: 6, width: 'calc(100% - 16px)', textAlign: 'left',
        margin: '0 8px 1px', padding: '7px 10px', paddingLeft: 10 + depth * 12, borderRadius: 6,
        opacity: fdnd && fdnd.dragging ? 0.4 : 1,
        border: '1px solid transparent', background: 'transparent', color: T.text, cursor: fdnd ? 'grab' : 'pointer', fontFamily: 'inherit',
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
                        selectedId={selectedId} onSelect={onSelect} depth={depth + 1}
                        reportDnd={reportDnd} folderDnd={folderDnd} />
          ))}
          {childReports.map((r) => (
            <ReportRow key={r.id} T={T} report={r} selected={r.id === selectedId} onSelect={onSelect}
                       dnd={reportDnd && reportDnd(r, folder.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ReportDirectory({ T, folders = [], reports = [], selectedId, onSelect,
                                 isAdmin = false, onNewFolder, onNewReport,
                                 onReorderReports, onReorderFolders }) {
  const [q, setQ] = useState('');
  const [drag, setDrag] = useState(null);   // v0.8.8 ③ {kind:'report'|'folder', id, group}
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    return kw ? reports.filter((r) => (r.title || '').toLowerCase().includes(kw)) : reports;
  }, [q, reports]);

  const topFolders = folders.filter((f) => f.parent_id == null);
  const unfiled = filtered.filter((r) => r.folder_id == null);
  const canManage = isAdmin && (onNewFolder || onNewReport);

  // v0.8.8 ③ 拖拽排序：仅 admin 非搜索态（搜索过滤下重排语义不清）。同 group 内移动 → reorder 全 group 有序 id。
  const dndOn = isAdmin && !q.trim();
  const _reorder = (items, group, kind, fromId, targetId, cb) => {
    if (drag == null || drag.kind !== kind || drag.group !== group || fromId === targetId) { setDrag(null); return; }
    const ids = items.filter((x) => ((kind === 'report' ? x.folder_id : x.parent_id) ?? null) === group).map((x) => x.id);
    const from = ids.indexOf(fromId), to = ids.indexOf(targetId);
    if (from >= 0 && to >= 0) { ids.splice(to, 0, ids.splice(from, 1)[0]); cb && cb(ids); }
    setDrag(null);
  };
  const reportDnd = dndOn ? (r, group) => ({
    dragging: drag && drag.kind === 'report' && drag.id === r.id,
    onStart: () => setDrag({ kind: 'report', id: r.id, group }),
    onDrop: () => _reorder(reports, group, 'report', drag && drag.id, r.id, onReorderReports),
  }) : null;
  const folderDnd = dndOn ? (f, group) => ({
    dragging: drag && drag.kind === 'folder' && drag.id === f.id,
    onStart: () => setDrag({ kind: 'folder', id: f.id, group }),
    onDrop: () => _reorder(folders, group, 'folder', drag && drag.id, f.id, onReorderFolders),
  }) : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* #1：搜索框在上（#2：盒子度量对齐 ASK「新建对话」按钮 —— side inset / 撑满 / padding 10×14 / radius8 / 1px border）*/}
      <div style={{ padding: '0 8px 8px' }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索报表…"
          style={{
            width: '100%', padding: '10px 14px', borderRadius: 8, fontSize: 13,
            border: `1px solid ${T.border}`, background: T.inputBg, color: T.text, fontFamily: 'inherit',
          }} />
      </div>
      {/* #1：报表目录 标题行 + 管理入口移到搜索框下方 */}
      <div style={{ padding: '2px 8px 8px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
      <div className="cb-sb" style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {topFolders.map((f) => (
          <FolderNode key={f.id} T={T} folder={f} folders={folders} reports={filtered}
                      selectedId={selectedId} onSelect={onSelect} depth={0}
                      reportDnd={reportDnd} folderDnd={folderDnd} />
        ))}
        {unfiled.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '7px 10px', fontSize: 11, color: T.muted, letterSpacing: '0.04em' }}>
              {/* #3（kk）：「未归档」不好听 → 「未分组」+ 无文件夹 icon（斜杠文件夹）明示不在文件夹内 */}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.7 }}>
                <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M3 3l18 18" />
              </svg>
              未分组
            </div>
            {unfiled.map((r) => (
              <ReportRow key={r.id} T={T} report={r} selected={r.id === selectedId} onSelect={onSelect}
                         dnd={reportDnd && reportDnd(r, null)} />
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
