// bi_permissions.jsx — v0.8.12 目录/报表权限矩阵（**用户**×目录/报表 × 4 权限）。
// kk 验收返工：按用户授权（同角色不同部门看不同表）。选用户 → 其 目录/未分组报表 × 定时/编辑/导出/分享 勾选。
// admin 恒全权（不入表、不可改）。勾选即 PUT /api/bi/permissions；归档报表继承目录、未分组逐张（后端解析）。
import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api.js';
import { toast } from '../../utils.jsx';

const PERMS = [['can_schedule', '定时'], ['can_edit', '编辑'], ['can_export', '导出'], ['can_share', '分享']];
const GT = '1fr repeat(4, 62px)';

function PermRow({ T, label, sub, grant, onToggle }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: GT, alignItems: 'center', padding: '9px 12px', borderTop: `1px solid ${T.borderSoft}` }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
        {sub && <div style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono }}>{sub}</div>}
      </div>
      {PERMS.map(([p]) => (
        <div key={p} style={{ textAlign: 'center' }}>
          <input type="checkbox" checked={!!(grant && grant[p])} onChange={() => onToggle(p)}
            style={{ cursor: 'pointer', accentColor: T.accent, width: 15, height: 15 }} />
        </div>
      ))}
    </div>
  );
}

function Head({ T, children }) {
  return <div style={{ fontSize: 11.5, fontWeight: 600, color: T.subtext, margin: '18px 0 2px', padding: '0 12px' }}>{children}</div>;
}

export function PermissionMatrix({ T }) {
  const [grants, setGrants] = useState([]);
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [users, setUsers] = useState([]);
  const [uid, setUid] = useState(null);
  const reload = useCallback(() => {
    Promise.all([
      api.get('/api/bi/permissions').catch(() => []),
      api.get('/api/bi/folders').catch(() => []),
      api.get('/api/bi/reports').catch(() => []),
      api.get('/api/admin/users').catch(() => []),
    ]).then(([g, f, r, u]) => {
      setGrants(g || []); setFolders(f || []); setReports(r || []);
      const nonAdmin = (u || []).filter((x) => x.role !== 'admin');
      setUsers(nonAdmin);
      setUid((prev) => (prev != null ? prev : (nonAdmin[0] ? nonAdmin[0].id : null)));
    });
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const grantFor = (key, id) => grants.find((x) => x.user_id === uid && x[key] === id) || null;

  const toggle = async (key, id, perm) => {
    if (uid == null) return;
    const cur = grantFor(key, id);
    const body = {
      user_id: uid, folder_id: null, report_id: null,
      can_schedule: !!(cur && cur.can_schedule), can_edit: !!(cur && cur.can_edit),
      can_export: !!(cur && cur.can_export), can_share: !!(cur && cur.can_share),
    };
    body[key] = id;
    body[perm] = !body[perm];
    try { await api.put('/api/bi/permissions', body); reload(); }
    catch (e) { toast(String(e.message || e), true); }
  };

  const fld = { padding: '8px 11px', borderRadius: 8, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 13, fontFamily: 'inherit', cursor: 'pointer' };
  const ungrouped = reports.filter((r) => r.folder_id == null);
  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '0 0 4px' }}>目录访问权限</h2>
      <p style={{ fontSize: 12.5, color: T.subtext, margin: '0 0 14px', lineHeight: 1.6 }}>
        选一个用户 → 授予其 目录（内含报表继承）/ 未分组报表（逐张）的 定时 / 编辑 / 导出 / 分享 权限。admin 恒全权。
      </p>
      {users.length === 0
        ? <div style={{ fontSize: 13, color: T.muted }}>暂无非管理员用户 —— 先到「用户」新建 analyst 账号。</div>
        : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
              <span style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>用户</span>
              <select value={uid ?? ''} onChange={(e) => setUid(Number(e.target.value))} style={{ ...fld, minWidth: 200 }}>
                {users.map((u) => <option key={u.id} value={u.id}>{u.display_name || u.username}（{u.role}）</option>)}
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: GT, padding: '8px 12px', fontSize: 11, color: T.muted, fontFamily: T.mono, background: T.bg, borderRadius: 8 }}>
              <span>目标 / 权限</span>
              {PERMS.map(([p, l]) => <span key={p} style={{ textAlign: 'center' }}>{l}</span>)}
            </div>
            <Head T={T}>目录（内含报表继承）</Head>
            {folders.length === 0 ? <div style={{ padding: '9px 12px', fontSize: 12, color: T.muted }}>暂无目录</div>
              : folders.map((f) => (
                <PermRow key={`f${f.id}`} T={T} label={f.name} sub={f.parent_id != null ? '子目录' : null}
                  grant={grantFor('folder_id', f.id)} onToggle={(p) => toggle('folder_id', f.id, p)} />
              ))}
            <Head T={T}>未分组报表（逐张授权）</Head>
            {ungrouped.length === 0 ? <div style={{ padding: '9px 12px', fontSize: 12, color: T.muted }}>暂无未分组报表</div>
              : ungrouped.map((r) => (
                <PermRow key={`r${r.id}`} T={T} label={r.title} grant={grantFor('report_id', r.id)}
                  onToggle={(p) => toggle('report_id', r.id, p)} />
              ))}
          </>
        )}
    </div>
  );
}
