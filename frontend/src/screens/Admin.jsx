// v0.5.3 拆分：本主文件作"调度员 + 状态容器"；保留 AdminScreen export 名 + props（R-116 强制）。
// 子模块（screens/admin/*）：
//   tab_access.jsx     — Users + Sources（D4 mapping: Access）
//   tab_resources.jsx  — Models + API Keys + Agent Models（D4 mapping: Resources）
//   tab_knowledge.jsx  — Knowledge + FewShots + Prompts（D4 mapping: Knowledge）
//   tab_system.jsx     — Catalog（D4 mapping: System；Audit/Recovery 独立页面）
//   modals.jsx         — UserFormModal + SourceFormModal + FewShotModal
//
// D4 mapping 注：手册原议 4 文件（Access/Resources/Knowledge/System）= Stage 2 提议；
// 实际 Admin.jsx 仅 7 tabs（Budgets/Audit/Recovery 是独立页面），按内聚原则调整内部映射，
// 4 文件总数不变。
import { useState, useEffect, useRef } from 'react';
import { I, iconBtn, pillBtn } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';
import { TabAccess } from './admin/tab_access.jsx';
import { TabResources } from './admin/tab_resources.jsx';
import { TabKnowledge } from './admin/tab_knowledge.jsx';
import { TabSystem } from './admin/tab_system.jsx';
import { UserFormModal, SourceFormModal, FewShotModal } from './admin/modals.jsx';

export function AdminScreen({ T, user, onToggleTheme, onNavigate, onLogout, screen: screenProp, initialTab = 'users' }) {
  const [tab, setTab] = useState(initialTab);
  const [users, setUsers] = useState([]);
  const [sources, setSources] = useState([]);
  const [models, setModels] = useState([]);
  const [knowledgeDocs, setKnowledgeDocs] = useState([]);
  const [stats, setStats] = useState({});
  const [modal, setModal] = useState(null);
  const [kbUploading, setKbUploading] = useState(false);
  const kbFileRef = useRef(null);
  // 批次 2 新增
  const [apiKeys, setApiKeys] = useState({ openrouter_api_key: '', embedding_api_key: '' });
  // v0.4.5 R-39：记录 GET 返回的 masked 值；保存时若 input 仍等于此值 → 不发送该字段
  const [apiKeysLoaded, setApiKeysLoaded] = useState({ openrouter_api_key: '', embedding_api_key: '' });
  const [apiKeysSaving, setApiKeysSaving] = useState(false);
  const [agentCfg, setAgentCfg] = useState({ clarifier: '', sql_planner: '', presenter: '' });
  const [agentSaving, setAgentSaving] = useState(false);
  const [fewShots, setFewShots] = useState([]);
  const [fsUploading, setFsUploading] = useState(false);
  const fsFileRef = useRef(null);
  const [prompts, setPrompts] = useState({ clarifier: '', sql_planner: '', presenter: '' });
  const [promptsSaving, setPromptsSaving] = useState({});
  const [pmUploading, setPmUploading] = useState(false);
  const pmFileRef = useRef(null);
  // v0.2.5: catalog tab; v0.5.44 加 relations 字段
  const [catalog, setCatalog] = useState({
    tables: '', lexicon: '', business_rules: '', relations: '',
    source: '', defaults: { tables: [], lexicon: {}, business_rules: '', relations: [], source: '' },
    overrides: { tables: false, lexicon: false, business_rules: false, relations: false },
  });
  const [catalogSaving, setCatalogSaving] = useState({});

  useEffect(() => { setTab(initialTab); }, [initialTab]);
  useEffect(() => { loadAll(); }, [tab]);

  const loadAll = async () => {
    try {
      if (tab === 'users') { const [d, s] = await Promise.all([api.get('/api/admin/users'), api.get('/api/admin/datasources')]); setUsers(d); setSources(s); }
      if (tab === 'sources') { const d = await api.get('/api/admin/datasources'); setSources(d); }
      if (tab === 'models') {
        const [d, ks, ac] = await Promise.all([
          api.get('/api/admin/models'),
          api.get('/api/admin/api-keys').catch(() => ({})),
          api.get('/api/admin/agent-models').catch(() => ({})),
        ]);
        setModels(d);
        // v0.4.5 R-39：apiKeys 与 apiKeysLoaded 同步初始化
        const loaded = { openrouter_api_key: ks.openrouter_api_key || '', embedding_api_key: ks.embedding_api_key || '' };
        setApiKeys(loaded);
        setApiKeysLoaded(loaded);
        setAgentCfg({ clarifier: ac.clarifier || '', sql_planner: ac.sql_planner || '', presenter: ac.presenter || '' });
      }
      if (tab === 'knowledge') { const d = await api.get('/api/knowledge'); setKnowledgeDocs(d); }
      if (tab === 'fewshots') { const d = await api.get('/api/few-shots').catch(() => []); setFewShots(d || []); }
      if (tab === 'prompts') {
        const ps = { clarifier: '', sql_planner: '', presenter: '' };
        const all = await Promise.all(Object.keys(ps).map(k =>
          api.get(`/api/prompts/${k}`).then(r => [k, r.content || '']).catch(() => [k, ''])
        ));
        for (const [k, v] of all) ps[k] = v;
        setPrompts(ps);
      }
      if (tab === 'catalog') {
        const d = await api.get('/api/admin/catalog').catch(() => null);
        if (d) {
          setCatalog({
            tables: JSON.stringify(d.current.tables || [], null, 2),
            lexicon: JSON.stringify(d.current.lexicon || {}, null, 2),
            business_rules: d.current.business_rules || '',
            relations: JSON.stringify(d.current.relations || [], null, 2),  // v0.5.44
            source: d.source || '',
            defaults: d.defaults || { tables: [], lexicon: {}, business_rules: '', relations: [], source: '' },
            overrides: d.db_overrides || { tables: false, lexicon: false, business_rules: false, relations: false },
          });
        }
      }
      const s = await api.get('/api/admin/stats'); setStats(s);
    } catch {}
  };

  const handleKbUpload = async (file) => {
    setKbUploading(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const r = await fetch('/api/knowledge/upload', {
        method: 'POST', headers: { Authorization: `Bearer ${api._token()}` }, body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      toast(`已上传「${d.name}」· ${d.chunk_count} 块${d.embedded_count < d.chunk_count ? '（部分未 embedding，将使用关键词检索）' : ''}`);
      loadAll();
    } catch (e) { toast(`上传失败: ${e.message}`, true); }
    finally { setKbUploading(false); }
  };

  const deleteKbDoc = async (id, name) => {
    if (!confirm(`删除「${name}」？`)) return;
    try { await api.del(`/api/knowledge/${id}`); loadAll(); toast('已删除'); }
    catch (e) { toast(String(e), true); }
  };

  const deleteUser = async (id) => {
    if (!confirm('停用该账号？')) return;
    try { await api.del(`/api/admin/users/${id}`); loadAll(); toast('已停用'); } catch (e) { toast(String(e), true); }
  };
  const deleteSrc = async (id) => {
    if (!confirm('删除该数据源？')) return;
    try { await api.del(`/api/admin/datasources/${id}`); loadAll(); toast('已删除'); } catch (e) { toast(String(e), true); }
  };
  const toggleModel = async (key) => {
    try { await api.post(`/api/admin/models/${key}/toggle`); loadAll(); } catch (e) { toast(String(e), true); }
  };
  const setDefaultModel = async (key) => {
    try { await api.post(`/api/admin/models/${key}/default`); loadAll(); toast('已设为默认'); } catch (e) { toast(String(e), true); }
  };

  const saveApiKeys = async () => {
    setApiKeysSaving(true);
    // v0.4.5 R-39：仅发送被编辑过的字段（input 值 !== 加载时的 masked 值）；
    // 同时跳过 mask 占位（• U+2022 开头）兜底前端误回传。
    const payload = {};
    for (const k of ['openrouter_api_key', 'embedding_api_key']) {
      const v = apiKeys[k];
      if (v === apiKeysLoaded[k]) continue;       // 未编辑
      if (typeof v === 'string' && v.startsWith('••••••••')) continue;  // mask 占位
      payload[k] = v;
    }
    try {
      await api.put('/api/admin/api-keys', payload);
      toast(Object.keys(payload).length === 0 ? '无更改' : 'API Key 已保存');
      // 重新加载以拿到新的 masked 值
      const ks = await api.get('/api/admin/api-keys').catch(() => ({}));
      const loaded = { openrouter_api_key: ks.openrouter_api_key || '', embedding_api_key: ks.embedding_api_key || '' };
      setApiKeys(loaded); setApiKeysLoaded(loaded);
    }
    catch (e) { toast(String(e), true); }
    finally { setApiKeysSaving(false); }
  };

  const saveAgentCfg = async () => {
    setAgentSaving(true);
    try { await api.put('/api/admin/agent-models', agentCfg); toast('Agent 模型配置已保存'); }
    catch (e) { toast(String(e), true); }
    finally { setAgentSaving(false); }
  };

  const downloadTemplate = (kind, filename) => {
    const url = `/api/templates/${kind}`;
    fetch(url, { headers: { Authorization: `Bearer ${api._token()}` } })
      .then(r => r.ok ? r.blob() : Promise.reject(new Error('下载失败')))
      .then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = filename;
        document.body.appendChild(a); a.click(); a.remove();
      })
      .catch(e => toast(String(e), true));
  };

  const uploadFewShots = async (file) => {
    setFsUploading(true);
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch('/api/few-shots/upload', {
        method: 'POST', headers: { Authorization: `Bearer ${api._token()}` }, body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      toast(`已导入 ${d.inserted} 条`);
      loadAll();
    } catch (e) { toast(`上传失败: ${e.message}`, true); }
    finally { setFsUploading(false); }
  };

  const deleteFewShot = async (id) => {
    if (!confirm('删除该示例？')) return;
    try { await api.del(`/api/few-shots/${id}`); loadAll(); toast('已删除'); }
    catch (e) { toast(String(e), true); }
  };

  const savePrompt = async (agent) => {
    setPromptsSaving(s => ({ ...s, [agent]: true }));
    try { await api.put(`/api/prompts/${agent}`, { content: prompts[agent] }); toast(`${agent} prompt 已保存`); }
    catch (e) { toast(String(e), true); }
    finally { setPromptsSaving(s => ({ ...s, [agent]: false })); }
  };

  const uploadPrompts = async (file) => {
    setPmUploading(true);
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch('/api/prompts/upload', {
        method: 'POST', headers: { Authorization: `Bearer ${api._token()}` }, body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const d = await r.json();
      toast(`已更新 ${d.updated} 个 agent 模板`);
      loadAll();
    } catch (e) { toast(`上传失败: ${e.message}`, true); }
    finally { setPmUploading(false); }
  };

  const saveCatalogField = async (field) => {
    setCatalogSaving(s => ({ ...s, [field]: true }));
    try {
      let value;
      if (field === 'business_rules') {
        value = catalog.business_rules;
      } else {
        // v0.5.44 — relations 默认空数组（与 tables 同）
        const defaultEmpty = (field === 'tables' || field === 'relations') ? '[]' : '{}';
        try {
          value = JSON.parse(catalog[field] || defaultEmpty);
        } catch (e) {
          toast(`${field} 不是合法 JSON: ${e.message}`, true);
          return;
        }
        if (field === 'tables' && !Array.isArray(value)) { toast('tables 必须是数组', true); return; }
        if (field === 'lexicon' && (typeof value !== 'object' || Array.isArray(value))) { toast('lexicon 必须是对象', true); return; }
        if (field === 'relations') {
          if (!Array.isArray(value)) { toast('relations 必须是数组', true); return; }
          for (const r of value) {
            if (!Array.isArray(r) || r.length < 4) { toast('relations 每项必须 ≥4 元素 [left_t, left_c, right_t, right_c, semantics?]', true); return; }
          }
        }
      }
      const r = await api.put('/api/admin/catalog', { [field]: value });
      toast(`已保存（生效来源：${r.source}）`);
      loadAll();
    } catch (e) { toast(String(e), true); }
    finally { setCatalogSaving(s => ({ ...s, [field]: false })); }
  };

  const resetCatalogField = async (field) => {
    if (!confirm(`清空 DB 覆盖，回退到默认（${field}）？`)) return;
    try {
      const r = await api.post('/api/admin/catalog/reset', { fields: [field] });
      toast(`${field} 已恢复默认（来源：${r.source}）`);
      loadAll();
    } catch (e) { toast(String(e), true); }
  };

  const TAB_TITLES = { users: '用户', sources: '数据源', models: 'API & 模型', knowledge: '知识库', fewshots: 'Few-shot 示例', prompts: 'Prompt 模板', catalog: '业务目录' };

  const roleChip = (role) => {
    const map = { admin: ['#FF4B4B', 'rgba(255,75,75,0.12)'], analyst: ['#2B7FFF', 'rgba(43,127,255,0.12)'] };
    const [c, bg] = map[role] || [T.muted, T.hover];
    return <span style={{ fontSize: 10.5, padding: '2px 7px', borderRadius: 999, background: bg, color: c, fontWeight: 600 }}>{role}</span>;
  };

  return (
    <AppShell T={T} user={user} active={screenProp || `admin-${tab}`} topbarTitle={TAB_TITLES[tab] || '管理员'}
              showConnectionPill={false}
              topbarTrailing={
                tab === 'users' ? <button onClick={() => setModal({ type: 'user' })} style={{ ...pillBtn(T, true), padding: '6px 12px' }}><I.plus width="13" height="13"/> 新建账号</button>
                : tab === 'sources' ? <button onClick={() => setModal({ type: 'source' })} style={{ ...pillBtn(T, true), padding: '6px 12px' }}><I.plus width="13" height="13"/> 添加数据源</button>
                : tab === 'knowledge' ? (
                  <>
                    <button onClick={() => downloadTemplate('knowledge', 'knowledge_template.txt')} style={{ ...pillBtn(T), padding: '6px 12px' }}>
                      下载模板
                    </button>
                    <input ref={kbFileRef} type="file" accept=".pdf,.md,.markdown,.txt" style={{ display: 'none' }}
                      onChange={e => { const f = e.target.files?.[0]; if (f) handleKbUpload(f); e.target.value = ''; }}/>
                    <button onClick={() => kbFileRef.current?.click()} disabled={kbUploading}
                      style={{ ...pillBtn(T, true), padding: '6px 12px' }}>
                      {kbUploading ? <><Spinner size={11} color="#fff"/> 处理中…</> : <><I.plus width="13" height="13"/> 上传文档</>}
                    </button>
                  </>
                )
                : tab === 'fewshots' ? (
                  <>
                    <button onClick={() => downloadTemplate('few_shots', 'few_shots_template.xlsx')} style={{ ...pillBtn(T), padding: '6px 12px' }}>下载模板</button>
                    <input ref={fsFileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                      onChange={e => { const f = e.target.files?.[0]; if (f) uploadFewShots(f); e.target.value = ''; }}/>
                    <button onClick={() => fsFileRef.current?.click()} disabled={fsUploading}
                      style={{ ...pillBtn(T, true), padding: '6px 12px' }}>
                      {fsUploading ? <><Spinner size={11} color="#fff"/> 上传中…</> : <><I.plus width="13" height="13"/> 上传 xlsx</>}
                    </button>
                    <button onClick={() => setModal({ type: 'fewshot' })} style={{ ...pillBtn(T), padding: '6px 12px' }}><I.plus width="13" height="13"/> 新建</button>
                  </>
                )
                : tab === 'prompts' ? (
                  <>
                    <button onClick={() => downloadTemplate('prompts', 'prompts_template.xlsx')} style={{ ...pillBtn(T), padding: '6px 12px' }}>下载模板</button>
                    <input ref={pmFileRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                      onChange={e => { const f = e.target.files?.[0]; if (f) uploadPrompts(f); e.target.value = ''; }}/>
                    <button onClick={() => pmFileRef.current?.click()} disabled={pmUploading}
                      style={{ ...pillBtn(T, true), padding: '6px 12px' }}>
                      {pmUploading ? <><Spinner size={11} color="#fff"/> 上传中…</> : <><I.plus width="13" height="13"/> 上传 xlsx</>}
                    </button>
                  </>
                )
                : null
              }
              onToggleTheme={onToggleTheme} onNewChat={() => {}} onNavigate={onNavigate} onLogout={onLogout}>
      <div className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>

        {(tab === 'users' || tab === 'sources') && (
          <TabAccess T={T} tab={tab} users={users} sources={sources}
                     onEditUser={(u) => setModal({ type: 'user', data: u })}
                     onDeleteUser={deleteUser}
                     onEditSource={(s) => setModal({ type: 'source', data: s })}
                     onDeleteSource={deleteSrc}
                     roleChip={roleChip}/>
        )}

        {tab === 'models' && (
          <TabResources T={T} models={models}
                        apiKeys={apiKeys} setApiKeys={setApiKeys}
                        apiKeysSaving={apiKeysSaving} onSaveApiKeys={saveApiKeys}
                        agentCfg={agentCfg} setAgentCfg={setAgentCfg}
                        agentSaving={agentSaving} onSaveAgentCfg={saveAgentCfg}
                        onToggleModel={toggleModel} onSetDefaultModel={setDefaultModel}/>
        )}

        {(tab === 'knowledge' || tab === 'fewshots' || tab === 'prompts') && (
          <TabKnowledge T={T} tab={tab}
                        knowledgeDocs={knowledgeDocs} onDeleteKbDoc={deleteKbDoc} onUploadKb={handleKbUpload}
                        fewShots={fewShots}
                        onEditFewShot={(f) => setModal({ type: 'fewshot', data: f })}
                        onDeleteFewShot={deleteFewShot}
                        prompts={prompts} setPrompts={setPrompts}
                        promptsSaving={promptsSaving} onSavePrompt={savePrompt}/>
        )}

        {tab === 'catalog' && (
          <TabSystem T={T} catalog={catalog} setCatalog={setCatalog}
                     catalogSaving={catalogSaving}
                     onSaveCatalogField={saveCatalogField}
                     onResetCatalogField={resetCatalogField}/>
        )}
      </div>

      {modal?.type === 'user' && <UserFormModal T={T} data={modal.data} sources={sources} onClose={() => setModal(null)} onSave={loadAll}/>}
      {modal?.type === 'source' && <SourceFormModal T={T} data={modal.data} onClose={() => setModal(null)} onSave={loadAll}/>}
      {modal?.type === 'fewshot' && <FewShotModal T={T} data={modal.data} onClose={() => setModal(null)} onSave={loadAll}/>}
    </AppShell>
  );
}
