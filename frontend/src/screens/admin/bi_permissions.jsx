// bi_permissions.jsx — v0.8.12 C4a 目录/报表权限矩阵（角色×目录/报表 × 4 权限）。
// admin 恒全权（不入表、不可改）；当前唯一可授非-admin 角色 = analyst。勾选即 PUT /api/bi/permissions（全 0 = 撤销/删行）。
// 归档报表继承所属目录授权；未分组报表逐张授权（后端 RBAC 解析）。
import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api.js';
import { toast } from '../../utils.jsx';

const PERMS = [['can_schedule', '定时'], ['can_edit', '编辑'], ['can_export', '导出'], ['can_share', '分享']];
const ROLE = 'analyst';
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
  const reload = useCallback(() => {
    Promise.all([
      api.get('/api/bi/permissions').catch(() => []),
      api.get('/api/bi/folders').catch(() => []),
      api.get('/api/bi/reports').catch(() => []),
    ]).then(([g, f, r]) => { setGrants(g || []); setFolders(f || []); setReports(r || []); });
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const grantFor = (key, id) => grants.find((x) => x.role === ROLE && x[key] === id) || null;

  const toggle = async (key, id, perm) => {
    const cur = grantFor(key, id);
    const body = {
      role: ROLE, folder_id: null, report_id: null,
      can_schedule: !!(cur && cur.can_schedule), can_edit: !!(cur && cur.can_edit),
      can_export: !!(cur && cur.can_export), can_share: !!(cur && cur.can_share),
    };
    body[key] = id;
    body[perm] = !body[perm];   // flip 该权限
    try { await api.put('/api/bi/permissions', body); reload(); }
    catch (e) { toast(String(e.message || e), true); }
  };

  const ungrouped = reports.filter((r) => r.folder_id == null);
  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '0 0 4px' }}>目录访问权限</h2>
      <p style={{ fontSize: 12.5, color: T.subtext, margin: '0 0 6px', lineHeight: 1.6 }}>
        按 <b style={{ color: T.text }}>analyst</b> 角色 × 目录（内含报表继承）/ 未分组报表（逐张）授予 定时 / 编辑 / 导出 / 分享 权限。
      </p>
      <p style={{ fontSize: 11.5, color: T.muted, margin: '0 0 8px' }}>admin 恒全权（不可改）；勾掉全部即撤销授权。</p>
      {/* 表头 */}
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
    </div>
  );
}
