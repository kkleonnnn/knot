// tab_bi.jsx — v0.8.12 BI 设置专属 tab（目录管理 C2 / 目录权限 C4 / da-asst C5）。
// 从 BI 齿轮进设置时显示（Shell backMode==='bi' 过滤 nav）。自包含 fetch，保 Admin.jsx 精简。
// C2：目录 新建 / 重命名(行内) / 删除 / 拖拽排序（后端 folders CRUD + reorder 已就绪，require_admin）。
import { useState, useEffect, useCallback } from 'react';
import { api } from '../../api.js';
import { toast } from '../../utils.jsx';
import { PermissionMatrix } from './bi_permissions.jsx';   // v0.8.12 C4a 权限矩阵

function Panel({ T, title, desc, children }) {
  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '0 0 4px' }}>{title}</h2>
      {desc && <p style={{ fontSize: 12.5, color: T.subtext, margin: '0 0 18px', lineHeight: 1.6 }}>{desc}</p>}
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
      {folder.parent_id != null && <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>子目录</span>}
      <button onClick={() => onDelete(folder.id)} title="删除目录" style={{ border: 'none', background: 'transparent', color: T.muted, cursor: 'pointer', fontSize: 15, flexShrink: 0 }}>×</button>
    </div>
  );
}

function DirectoryManager({ T }) {
  const [folders, setFolders] = useState([]);
  const [newName, setNewName] = useState('');
  const [newParent, setNewParent] = useState('');
  const [drag, setDrag] = useState(null);
  const reload = useCallback(() => { api.get('/api/bi/folders').then((f) => setFolders(f || [])).catch(() => {}); }, []);
  useEffect(() => { reload(); }, [reload]);

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
    if (!confirm('删除该目录？内含报表将移到「未分组」、子目录升为顶层。')) return;
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
    <Panel T={T} title="报表目录管理" desc="BI 报表目录的新建 / 重命名（点名字直接改）/ 删除 / 拖拽排序。">
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
    </Panel>
  );
}

function DaAsstSettings({ T }) {
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    api.get('/api/bi/da-asst').then((d) => { setApiKey(d.api_key || ''); setModel(d.model || ''); }).catch(() => {});
  }, []);
  const save = async () => {
    setSaving(true);
    // key 未编辑（mask 占位 ••）→ 后端 should_update_secret 保留原值；明文才更新
    try { await api.put('/api/bi/da-asst', { api_key: apiKey, model }); toast('已保存'); }
    catch (e) { toast(String(e.message || e), true); }
    finally { setSaving(false); }
  };
  const fld = { width: '100%', padding: '9px 11px', borderRadius: 8, border: `1px solid ${T.inputBorder}`, background: T.inputBg, color: T.text, fontSize: 13, fontFamily: 'inherit', outline: 'none' };
  const lbl = { fontSize: 12, color: T.subtext, fontWeight: 500, margin: '16px 0 6px' };
  return (
    <Panel T={T} title="da-asst 数据分析助手" desc="BI 报表解读的模型驱动。两项均可留空 → 复用平台 OpenRouter key + 默认模型（当前行为）。">
      <div style={lbl}>模型（可选）</div>
      <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="留空 = 平台默认（anthropic/claude-haiku-4.5）；可填任意 OpenRouter 模型 key" style={fld} />
      <div style={lbl}>专属 API Key（可选）</div>
      <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="留空 = 复用平台 OpenRouter key" autoComplete="off" style={{ ...fld, fontFamily: T.mono }} />
      <p style={{ fontSize: 11, color: T.muted, margin: '8px 0 0' }}>Key 加密存储、回显打码；不改则保留原值。</p>
      <button onClick={save} disabled={saving} style={{ marginTop: 18, padding: '9px 20px', borderRadius: 8, border: 'none', background: T.accent, color: T.sendFg, fontSize: 13, fontWeight: 500, cursor: saving ? 'default' : 'pointer', opacity: saving ? 0.6 : 1, fontFamily: 'inherit' }}>
        {saving ? '保存中…' : '保存'}
      </button>
    </Panel>
  );
}

export function TabBI({ T, tab }) {
  if (tab === 'bi-directory') return <DirectoryManager T={T} />;
  if (tab === 'bi-permissions') return <PermissionMatrix T={T} />;
  return <DaAsstSettings T={T} />;
}
