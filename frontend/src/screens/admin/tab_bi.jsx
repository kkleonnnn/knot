// tab_bi.jsx — v0.8.12 BI 设置专属 tab（目录管理 C2 / 目录权限 C4 / da-asst C5）。
// 从 BI 齿轮进设置时显示（Shell backMode==='bi' 过滤 nav）。自包含 fetch，保 Admin.jsx 精简。
// C2：目录 新建 / 重命名(行内) / 删除 / 拖拽排序（后端 folders CRUD + reorder 已就绪，require_admin）。
import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api.js';
import { toast, confirmDialog } from '../../utils.jsx';
import { PermissionMatrix } from './bi_permissions.jsx';   // v0.8.12 C4a 权限矩阵

function Panel({ T, title, desc, children }) {
  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, fontWeight: 650, color: T.text, margin: '0 0 4px' }}>{title}</h2>
      {desc && <p style={{ fontSize: 13, color: T.subtext, margin: '0 0 18px', lineHeight: 1.6 }}>{desc}</p>}
      {children}
    </div>
  );
}

// 行内可编辑目录行（重命名 blur/Enter 提交 + 拖拽手柄 + 删除）
// key 含 folder.name → 重命名/reload 后名字变则整行 remount 重置 input（避免 prop→state sync effect 反模式）。
function FolderRow({ T, folder, onRename, onDelete, dnd }) {
  const [name, setName] = useState(folder.name);
  return (
    <div draggable onDragStart={dnd.start} onDragOver={(e) => e.preventDefault()} onDrop={dnd.drop}
      style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: `1px solid ${T.border}`,
        borderRadius: 8, background: T.card, opacity: dnd.dragging ? 0.5 : 1 }}>
      <span title="拖拽排序" style={{ cursor: 'grab', color: T.muted, fontSize: 14, flexShrink: 0 }}>⠿</span>
      <input value={name} onChange={(e) => setName(e.target.value)}
        onBlur={() => { if (name.trim() && name !== folder.name) onRename(folder.id, name.trim()); else setName(folder.name); }}
        onKeyDown={(e) => { if (e.key === 'Enter') e.target.blur(); if (e.key === 'Escape') { setName(folder.name); e.target.blur(); } }}
        style={{ flex: 1, minWidth: 0, background: 'transparent', border: 'none', color: T.text, fontSize: 13, outline: 'none', fontFamily: 'inherit', padding: '2px 0' }} />
      {folder.parent_id != null && <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>子目录</span>}
      <button onClick={() => onDelete(folder.id)} title="删除目录" style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 14, flexShrink: 0 }}>×</button>
    </div>
  );
}

function DirectoryManager({ T }) {
  const [folders, setFolders] = useState([]);
  const [reports, setReports] = useState([]);
  const [newName, setNewName] = useState('');
  const [newParent, setNewParent] = useState('');
  const [drag, setDrag] = useState(null);
  const reload = useCallback(() => {
    Promise.all([api.get('/api/bi/folders').catch(() => []), api.get('/api/bi/reports').catch(() => [])])
      .then(([f, r]) => { setFolders(f || []); setReports(r || []); });
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const move = async (reportId, folderId) => {
    try { await api.put(`/api/bi/reports/${reportId}`, { folder_id: folderId ? Number(folderId) : null }); reload(); }
    catch (e) { toast(String(e.message || e), true); }
  };

  const create = async () => {
    const name = newName.trim();
    if (!name) { toast('目录名必填', true); return; }
    try {
      await api.post('/api/bi/folders', { name, parent_id: newParent ? Number(newParent) : null });
      setNewName(''); setNewParent(''); reload(); toast('已新建目录');
    } catch (e) { toast(String(e.message || e), true); }
  };
  const rename = async (id, name) => {
    try { await api.put(`/api/bi/folders/${id}`, { name }); reload(); }
    catch (e) { toast(String(e.message || e), true); reload(); }
  };
  const del = async (id) => {
    if (!await confirmDialog('删除该目录？内含报表将移到「未分组」、子目录升为顶层。')) return;
    try { await api.del(`/api/bi/folders/${id}`); reload(); toast('已删除'); }
    catch (e) { toast(String(e.message || e), true); }
  };
  const reorder = async (from, to) => {
    if (from == null || from === to) return;
    const next = [...folders];
    const [m] = next.splice(from, 1);
    next.splice(to, 0, m);
    setFolders(next);   // 乐观更新
    try { await api.put('/api/bi/reorder/folders', { ordered_ids: next.map((f) => f.id) }); }
    catch (e) { toast(String(e.message || e), true); reload(); }
  };

  const fld = { padding: '8px 11px', borderRadius: 8, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 13, fontFamily: 'inherit', outline: 'none' };
  return (
    <Panel T={T} title="报表目录管理" desc="目录的新建 / 重命名（点名字直接改）/ 删除 / 拖拽排序；下方把报表归入目录（或移出到未分组）。">
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="新目录名称"
          onKeyDown={(e) => { if (e.key === 'Enter') create(); }} style={{ ...fld, flex: 1 }} />
        <select value={newParent} onChange={(e) => setNewParent(e.target.value)} style={{ ...fld, width: 160, cursor: 'pointer' }}>
          <option value="">（顶层目录）</option>
          {folders.filter((f) => f.parent_id == null).map((f) => <option key={f.id} value={f.id}>归入：{f.name}</option>)}
        </select>
        <button onClick={create} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit' }}>新建</button>
      </div>
      {folders.length === 0
        ? <div style={{ fontSize: 13, color: T.muted }}>暂无目录，点上方「新建」添加。</div>
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {folders.map((f, i) => (
              <FolderRow key={`${f.id}:${f.name}`} T={T} folder={f} onRename={rename} onDelete={del}
                dnd={{ dragging: drag === i, start: () => setDrag(i), drop: () => { reorder(drag, i); setDrag(null); } }} />
            ))}
          </div>
        )}

      {/* 报表归入：每张报表选归属目录（PUT folder_id；未分组 = 移出目录） */}
      <div style={{ fontSize: 13, color: T.subtext, fontWeight: 500, margin: '24px 0 8px' }}>报表归入目录</div>
      {reports.length === 0
        ? <div style={{ fontSize: 12, color: T.muted }}>暂无报表。</div>
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {reports.map((r) => (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: `1px solid ${T.border}`, borderRadius: 8 }}>
                <span style={{ flex: 1, minWidth: 0, fontSize: 13, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.title}</span>
                <select value={r.folder_id ?? ''} onChange={(e) => move(r.id, e.target.value)}
                  style={{ ...fld, width: 180, cursor: 'pointer', flexShrink: 0 }}>
                  <option value="">未分组</option>
                  {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </div>
            ))}
          </div>
        )}
    </Panel>
  );
}

// v0.8.15 分享设置：IM 凭据（mask GET / should_update PUT，后端 admin/share.py）+ 投递目标白名单 CRUD。
function ShareConfig({ T }) {
  const [cfg, setCfg] = useState(null);   // {lark_app_id, lark_app_secret(masked), lark_region, telegram_bot_token(masked)}
  const [saving, setSaving] = useState(false);
  const [targets, setTargets] = useState([]);
  const [nt, setNt] = useState({ name: '', platform: 'tg', chat_id: '', region: 'feishu' });
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    api.get('/api/admin/share/config').then(setCfg).catch((e) => toast(`加载失败：${e.message || e}`, true));
    api.get('/api/admin/share/targets').then((d) => setTargets(Array.isArray(d) ? d : [])).catch(() => setTargets([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const fld = { width: '100%', height: 38, padding: '0 12px', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 8, color: T.text, fontSize: 13, fontFamily: T.sans, outline: 'none', boxSizing: 'border-box' };
  const primaryBtn = (on = true) => ({ padding: '8px 16px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500, fontFamily: 'inherit', cursor: on ? 'pointer' : 'default', opacity: on ? 1 : 0.6 });
  const setF = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const saveCfg = async () => {
    setSaving(true);
    try { await api.put('/api/admin/share/config', cfg); toast('已保存 IM 凭据'); load(); }
    catch (e) { toast(`保存失败：${e.message || e}`, true); } finally { setSaving(false); }
  };
  const addTarget = async () => {
    if (!nt.name.trim() || !nt.chat_id.trim()) { toast('名称 + chat_id 必填', true); return; }
    setAdding(true);
    try {
      await api.post('/api/admin/share/targets', { name: nt.name.trim(), platform: nt.platform, chat_id: nt.chat_id.trim(), region: nt.platform === 'lark' ? nt.region : null });
      toast('已添加投递目标'); setNt({ name: '', platform: 'tg', chat_id: '', region: 'feishu' }); load();
    } catch (e) { toast(`添加失败：${e.message || e}`, true); } finally { setAdding(false); }
  };
  const delTarget = async (t) => {
    if (!await confirmDialog(`删除投递目标「${t.name}」？`)) return;
    try { await api.del(`/api/admin/share/targets/${t.id}`); toast('已删除'); load(); }
    catch (e) { toast(String(e), true); }
  };

  if (!cfg) return <Panel T={T} title="分享"><div style={{ fontSize: 13, color: T.muted }}>加载中…</div></Panel>;

  return (
    <Panel T={T} title="分享" desc="配置 Lark / Telegram 投递凭据 + 投递目标白名单。用户分享报表快照时从白名单里选目标（不直接填 chat_id）。凭据加密存储、GET 只回掩码。">
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '16px 18px', marginBottom: 18 }}>
        <div style={{ fontSize: 13.5, fontWeight: 650, color: T.text, marginBottom: 12 }}>IM 凭据</div>
        <div style={{ display: 'grid', gridTemplateColumns: '132px 1fr', gap: '10px 14px', alignItems: 'center' }}>
          <label style={{ fontSize: 12.5, color: T.subtext }}>Telegram bot token</label>
          <input type="password" value={cfg.telegram_bot_token || ''} onChange={(e) => setF('telegram_bot_token', e.target.value)} placeholder="123456:ABC-..." style={{ ...fld, fontFamily: T.mono }} />
          <label style={{ fontSize: 12.5, color: T.subtext }}>Lark app_id</label>
          <input value={cfg.lark_app_id || ''} onChange={(e) => setF('lark_app_id', e.target.value)} placeholder="cli_..." style={{ ...fld, fontFamily: T.mono }} />
          <label style={{ fontSize: 12.5, color: T.subtext }}>Lark app_secret</label>
          <input type="password" value={cfg.lark_app_secret || ''} onChange={(e) => setF('lark_app_secret', e.target.value)} placeholder="••••••••" style={{ ...fld, fontFamily: T.mono }} />
          <label style={{ fontSize: 12.5, color: T.subtext }}>Lark region</label>
          <select value={cfg.lark_region || 'feishu'} onChange={(e) => setF('lark_region', e.target.value)} style={{ ...fld, cursor: 'pointer' }}>
            <option value="feishu">飞书 (open.feishu.cn)</option>
            <option value="lark">Lark 国际 (open.larksuite.com)</option>
          </select>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
          <button onClick={saveCfg} disabled={saving} style={primaryBtn(!saving)}>{saving ? '保存中…' : '保存凭据'}</button>
        </div>
      </div>

      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '16px 18px' }}>
        <div style={{ fontSize: 13.5, fontWeight: 650, color: T.text, marginBottom: 12 }}>投递目标白名单</div>
        {targets.length === 0
          ? <div style={{ fontSize: 12.5, color: T.muted, marginBottom: 14 }}>暂无目标 —— 下方添加。</div>
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
              {targets.map((t) => (
                <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', border: `1px solid ${T.border}`, borderRadius: 8 }}>
                  <span style={{ flex: 1, fontSize: 13, color: T.text }}>{t.name}</span>
                  <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono }}>{t.platform === 'tg' ? 'Telegram' : 'Lark'}{t.region ? `·${t.region}` : ''}</span>
                  <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.chat_id}</span>
                  <button onClick={() => delTarget(t)} title="删除" style={{ background: 'transparent', border: 'none', color: T.muted, cursor: 'pointer', fontSize: 17, lineHeight: 1, padding: '0 2px' }}>×</button>
                </div>
              ))}
            </div>}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 116px 1fr auto', gap: 8, alignItems: 'center' }}>
          <input value={nt.name} onChange={(e) => setNt({ ...nt, name: e.target.value })} placeholder="名称（如 运营大群）" style={fld} />
          <select value={nt.platform} onChange={(e) => setNt({ ...nt, platform: e.target.value })} style={{ ...fld, cursor: 'pointer' }}>
            <option value="tg">Telegram</option><option value="lark">Lark</option>
          </select>
          <input value={nt.chat_id} onChange={(e) => setNt({ ...nt, chat_id: e.target.value })} placeholder="chat_id" style={{ ...fld, fontFamily: T.mono }} />
          <button onClick={addTarget} disabled={adding} style={primaryBtn(!adding)}>添加</button>
        </div>
        {nt.platform === 'lark' && (
          <select value={nt.region} onChange={(e) => setNt({ ...nt, region: e.target.value })} style={{ ...fld, width: 240, marginTop: 8, cursor: 'pointer' }}>
            <option value="feishu">飞书 (open.feishu.cn)</option><option value="lark">Lark 国际 (open.larksuite.com)</option>
          </select>
        )}
      </div>
    </Panel>
  );
}

export function TabBI({ T, tab }) {
  // v0.8.12 返工：da-asst 独立设置 tab 移除 —— da-asst 模型并入「API & 模型」的 Agent 分配（第 4 槽）。
  if (tab === 'bi-directory') return <DirectoryManager T={T} />;
  if (tab === 'bi-share') return <ShareConfig T={T} />;   // v0.8.15 分享设置
  return <PermissionMatrix T={T} />;   // bi-permissions
}
