import { useEffect, useState } from 'react';
import { I, pillBtn } from '../Shared.jsx';
import { toast } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';
import { AuditStatGrid } from './audit/AuditStatGrid.jsx';
import { AuditRetentionBar } from './audit/AuditRetentionBar.jsx';
import { AuditFilterStrip } from './audit/AuditFilterStrip.jsx';
import { AuditTable } from './audit/AuditTable.jsx';
import { AuditPagination } from './audit/AuditPagination.jsx';
import { AuditDetailDrawer } from './audit/AuditDetailDrawer.jsx';

// v0.4.6 D3：审计日志 admin 看板（who-did-what 追溯）
// R-61 强制分页：默认 50 / 上限 200（与后端一致）
// v0.5.17 视觉重构：Inset 8% 闭环第四处 (R-409) / R-313 rgba 豁免扩展 (R-415) / StatusDot inline (R-412)
// v0.6.3.2 C5：6 视觉段抽 screens/audit/ 子组件（dumb presentational）；本文件留编排层
// 守护者前瞻：不做"加载更多"无限滚；显式 page 1 / page 2 / ...

// v0.5.32 — 时段下拉 preset (demo audit.jsx L75 byte-equal — 24h/7d/30d)；映射到 since ISO 字符串
function _sinceFromPreset(preset) {
  if (!preset) return '';
  const now = new Date();
  const ms = { '24h': 24 * 3600 * 1000, '7d': 7 * 86400 * 1000, '30d': 30 * 86400 * 1000 }[preset];
  if (!ms) return '';
  return new Date(now.getTime() - ms).toISOString();
}

// v0.5.32 — 客户端 CSV 导出 helper（topbar 导出 CSV button — demo audit.jsx L64）
function exportAuditCsv(items) {
  if (!items || items.length === 0) return;
  const cols = ['created_at', 'actor_name', 'actor_role', 'actor_id', 'action', 'resource_type', 'resource_id', 'client_ip', 'success'];
  const esc = (v) => {
    if (v === null || v === undefined) return '';
    const s = String(v).replace(/"/g, '""');
    return /[",\n]/.test(s) ? `"${s}"` : s;
  };
  const csv = '﻿' + cols.join(',') + '\n' + items.map(r => cols.map(c => esc(r[c])).join(',')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  a.download = `knot-audit-${Date.now()}.csv`;
  a.click();
}

export function AdminAuditScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(50);
  // v0.5.32 — 加 sincePreset state（demo 24h/7d/30d 下拉 + 客户端转 since ISO）；resource_kw 替代 resource_type 字面（保后端字段名）
  const [filter, setFilter] = useState({ actor_id: '', action: '', resource_type: '', sincePreset: '7d' });
  const [drawerRow, setDrawerRow] = useState(null);  // 详情抽屉
  const [stats, setStats] = useState(null);  // v0.5.40 — { total, today, failed, distinct_users }
  // v0.6.0.5 F-C: 清理状态 + retention 配置
  const [purgeStatus, setPurgeStatus] = useState({ last_purge_at: null });
  const [retention, setRetention] = useState(90);
  const [purging, setPurging] = useState(false);

  // v0.6.0.14 lint sweep：page/size 切换 fetch；load 闭包内访问 setter
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [page, size]);
  // v0.5.40 — load stats once on mount
  useEffect(() => { api.get('/api/admin/audit-stats').then(setStats).catch(() => {}); }, []);
  // v0.6.0.5 F-C — 清理状态 + retention 配置一次性 fetch
  useEffect(() => {
    api.get('/api/admin/audit/purge-status').then(setPurgeStatus).catch(() => {});
    api.get('/api/admin/audit-config').then(d => setRetention(d.retention_days || 90)).catch(() => {});
  }, []);

  const triggerPurge = async () => {
    if (purging) return;
    if (!confirm('确认立即清理超过 retention 期的审计日志？此操作含自动备份。')) return;
    setPurging(true);
    try {
      const r = await api.post('/api/admin/audit/purge', {});
      toast(`已清理 ${r.deleted} 行，备份：${r.backup_path?.split('/').pop()}`);
      const s = await api.get('/api/admin/audit/purge-status');
      setPurgeStatus(s);
      const st = await api.get('/api/admin/audit-stats');
      setStats(st);
    } catch (e) { toast(`清理失败: ${e.message}`, true); }
    finally { setPurging(false); }
  };

  const saveRetention = async (days) => {
    try {
      await api.put('/api/admin/audit-config', { retention_days: days });
      setRetention(days);
      toast(`Retention 已设为 ${days} 天`);
    } catch (e) { toast(`保存失败: ${e.message}`, true); }
  };

  // 上次清理 → 相对时间（格式化器；结果传 AuditRetentionBar relPurgeText）
  const _relPurge = () => {
    if (!purgeStatus.last_purge_at) return '未清理';
    const t = new Date(purgeStatus.last_purge_at).getTime();
    if (isNaN(t)) return '未清理';
    const sec = Math.floor((Date.now() - t) / 1000);
    if (sec < 60) return `${sec}s 前`;
    if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
    if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
    return `${Math.floor(sec / 86400)} 天前`;
  };

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: size, offset: (page - 1) * size });
      // v0.5.32 — sincePreset → since ISO 字符串；其他直传
      for (const k of ['actor_id', 'action', 'resource_type']) {
        if (filter[k]) params.append(k, filter[k]);
      }
      const sinceIso = _sinceFromPreset(filter.sincePreset);
      if (sinceIso) params.append('since', sinceIso);
      const r = await api.get(`/api/admin/audit-log?${params.toString()}`);
      setItems(r.items || []);
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  // v0.5.38 — 返回对话 button 移除（Shell.jsx 全屏底部统一渲染）
  const sidebarContent = null;

  return (
    <AppShell T={T} user={user} active="admin-audit" sidebarContent={sidebarContent}
              topbarTitle="审计日志" onToggleTheme={onToggleTheme}
              topbarTrailing={
                /* v0.5.41 — 用 pillBtn(T) helper 统一 topbar button 字体/图标（与 Admin tabs 新建账号等一致）*/
                <button onClick={() => exportAuditCsv(items)} disabled={items.length === 0}
                        style={{ ...pillBtn(T), opacity: items.length === 0 ? 0.5 : 1, cursor: items.length === 0 ? 'not-allowed' : 'pointer' }}>
                  <I.dl width="13" height="13"/> 导出 CSV
                </button>
              }
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* v0.5.40 Stat 4-card grid */}
          <AuditStatGrid T={T} stats={stats}/>

          {/* v0.6.0.5 F-C — Retention 配置 + 立即清理 banner */}
          <AuditRetentionBar T={T} relPurgeText={_relPurge()} retention={retention} setRetention={setRetention}
                             purging={purging} onPurge={triggerPurge} onSaveRetention={saveRetention}/>

          {/* v0.5.32 Filter strip */}
          <AuditFilterStrip T={T} filter={filter} setFilter={setFilter}
                            onReset={() => { setFilter({ actor_id: '', action: '', resource_type: '', sincePreset: '7d' }); setPage(1); }}
                            onQuery={() => { setPage(1); load(); }}/>

          {/* R-408 Table CSS Grid 7-col */}
          <AuditTable T={T} items={items} loading={loading} onOpenDrawer={setDrawerRow}/>

          {/* v0.5.32 Pagination */}
          <AuditPagination T={T} items={items} page={page} size={size} setPage={setPage} setSize={setSize}/>
        </div>
      </div>

      <AuditDetailDrawer T={T} drawerRow={drawerRow} onClose={() => setDrawerRow(null)}/>
    </AppShell>
  );
}
