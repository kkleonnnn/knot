import { useState, useEffect, useRef } from 'react';
import { I, iconBtn, pillBtn } from '../Shared.jsx';
import { toast, Modal, ModalHeader, Input, Select, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

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
  // v0.2.5: catalog tab
  const [catalog, setCatalog] = useState({
    tables: '', lexicon: '', business_rules: '',
    source: '', defaults: { tables: [], lexicon: {}, business_rules: '', source: '' },
    overrides: { tables: false, lexicon: false, business_rules: false },
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
            source: d.source || '',
            defaults: d.defaults || { tables: [], lexicon: {}, business_rules: '', source: '' },
            overrides: d.db_overrides || { tables: false, lexicon: false, business_rules: false },
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
        try {
          value = JSON.parse(catalog[field] || (field === 'tables' ? '[]' : '{}'));
        } catch (e) {
          toast(`${field} 不是合法 JSON: ${e.message}`, true);
          return;
        }
        if (field === 'tables' && !Array.isArray(value)) { toast('tables 必须是数组', true); return; }
        if (field === 'lexicon' && (typeof value !== 'object' || Array.isArray(value))) { toast('lexicon 必须是对象', true); return; }
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

        {tab === 'users' && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
              <div>用户</div><div>账号</div><div>角色</div><div>状态</div><div></div>
            </div>
            {users.map((u, i) => (
              <div key={u.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr 0.8fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < users.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <div style={{ width: 26, height: 26, borderRadius: '50%', background: `linear-gradient(135deg, ${T.accent}, #ff7a3a)`, color: '#fff', display: 'grid', placeItems: 'center', fontSize: 10.5, fontWeight: 600, flexShrink: 0 }}>
                    {(u.display_name || u.username || '?').slice(0, 1).toUpperCase()}
                  </div>
                  <span style={{ color: T.text, fontWeight: 500 }}>{u.display_name || u.username}</span>
                </div>
                <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11.5 }}>{u.username}</div>
                <div>{roleChip(u.role)}</div>
                <div style={{ fontSize: 11.5, color: u.is_active ? T.success : T.muted }}>{u.is_active ? '正常' : '已停用'}</div>
                <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                  <button onClick={() => setModal({ type: 'user', data: u })} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                  <button onClick={() => deleteUser(u.id)} style={iconBtn(T)} title="停用"><I.trash/></button>
                </div>
              </div>
            ))}
            {users.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无用户</div>}
          </div>
        )}

        {tab === 'sources' && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
              <div>名称</div><div>类型</div><div>主机</div><div>状态</div><div></div>
            </div>
            {sources.map((s, i) => (
              <div key={s.id} style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1.6fr 0.8fr 80px', padding: '11px 16px', borderBottom: i < sources.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                <div style={{ color: T.text, fontWeight: 500, fontFamily: T.mono }}>{s.name}</div>
                <div style={{ color: T.subtext }}>{s.db_type || 'doris'}</div>
                <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.db_host}:{s.db_port}/{s.db_database}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: s.status === 'online' ? T.success : T.warn }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: s.status === 'online' ? T.success : T.warn }}/>
                  <span style={{ fontSize: 11.5 }}>{s.status === 'online' ? '正常' : '异常'}</span>
                </div>
                <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                  <button onClick={() => setModal({ type: 'source', data: s })} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                  <button onClick={() => deleteSrc(s.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
                </div>
              </div>
            ))}
            {sources.length === 0 && <div style={{ padding: '24px', textAlign: 'center', color: T.muted }}>暂无数据源</div>}
          </div>
        )}

        {tab === 'models' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* API Keys */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '16px 20px' }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>API Key（应用级）</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>所有用户共用 · OpenRouter 用于 LLM、Embedding 用于知识库向量检索（默认 text-embedding-3-small，未填则降级关键词匹配）</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Input T={T} label="OpenRouter API Key" value={apiKeys.openrouter_api_key}
                       onChange={v => setApiKeys(s => ({ ...s, openrouter_api_key: v }))}
                       type="password" placeholder="sk-or-v1-…" mono
                       trailing={<span style={{ fontSize: 11, color: apiKeys.openrouter_api_key ? T.success : T.muted }}>{apiKeys.openrouter_api_key ? '已填写' : '未填写'}</span>}/>
                <Input T={T} label="Embedding API Key" value={apiKeys.embedding_api_key}
                       onChange={v => setApiKeys(s => ({ ...s, embedding_api_key: v }))}
                       type="password" placeholder="sk-…（OpenAI / 兼容端点）" mono
                       trailing={<span style={{ fontSize: 11, color: apiKeys.embedding_api_key ? T.success : T.muted }}>{apiKeys.embedding_api_key ? '已填写' : '未填写'}</span>}/>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button onClick={saveApiKeys} disabled={apiKeysSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
                  {apiKeysSaving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存 Key'}
                </button>
              </div>
            </div>

            {/* 4-Agent Model Assignment */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '16px 20px' }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>3 个 Agent 模型分配</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 14 }}>为每个 agent 指定模型，留空则跟随系统默认（DEFAULT_MODEL）</div>
              {[
                { key: 'clarifier',   label: '理解问题',   hint: '推荐轻量' },
                { key: 'sql_planner', label: '生成 SQL',   hint: '推荐最强' },
                { key: 'presenter',   label: '整理洞察 + 质量检查', hint: '推荐中等' },
              ].map(({ key, label, hint }) => (
                <div key={key} style={{ display: 'grid', gridTemplateColumns: '120px 1fr 80px', gap: 10, alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 12.5, color: T.text, fontWeight: 500 }}>{label}</span>
                  <select value={agentCfg[key] || ''} onChange={e => setAgentCfg(p => ({ ...p, [key]: e.target.value }))}
                    style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '6px 10px', fontSize: 12, color: T.text, fontFamily: T.sans, cursor: 'pointer', outline: 'none' }}>
                    <option value="">默认</option>
                    {models.filter(m => m.enabled !== false).map(m => (
                      <option key={m.model_id} value={m.model_id}>{m.name} · {m.provider}</option>
                    ))}
                  </select>
                  <span style={{ fontSize: 11, color: T.muted, textAlign: 'right' }}>{hint}</span>
                </div>
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                <button onClick={saveAgentCfg} disabled={agentSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
                  {agentSaving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存 Agent 配置'}
                </button>
              </div>
            </div>

            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.7fr 100px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                <div>名称</div><div>提供方</div><div>Model ID</div><div>单价(入/出)</div><div>状态</div><div></div>
              </div>
              {models.map((m, i) => (
                <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.7fr 100px', padding: '11px 16px', borderBottom: i < models.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5, opacity: m.enabled ? 1 : 0.55 }}>
                  <div>
                    <span style={{ color: T.text, fontWeight: 500 }}>{m.name}</span>
                    {m.is_default ? <span style={{ marginLeft: 6, fontSize: 9.5, padding: '1px 5px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>默认</span> : null}
                  </div>
                  <div style={{ color: T.subtext }}>{m.provider}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.model_id}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11 }}>${m.input_price}/{m.output_price}</div>
                  <div>
                    <span style={{ fontSize: 11.5, color: m.enabled ? T.success : T.muted }}>{m.enabled ? '启用' : '禁用'}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                    <button onClick={() => setDefaultModel(m.id)} style={iconBtn(T)} title="设为默认"><I.check/></button>
                    <button onClick={() => toggleModel(m.id)} style={iconBtn(T)} title="启用/禁用"><I.zap/></button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'knowledge' && (
          <div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.6 }}>
              上传业务文档（PDF / Markdown / TXT），每次 SQL 查询时自动检索相关片段注入 prompt，提升生成准确度。<br/>
              需要 OpenAI 或 OpenRouter API Key 才能使用向量检索；无 Key 时自动降级为关键词匹配。
            </div>
            {knowledgeDocs.length === 0 ? (
              <div style={{ padding: '40px 24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 10, border: `1px solid ${T.border}` }}>
                暂无文档 · 点击右上角「上传文档」添加
              </div>
            ) : (
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                  <div>文档名称</div><div>文件名</div><div>分块数</div><div>上传时间</div><div></div>
                </div>
                {knowledgeDocs.map((d, i) => (
                  <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '11px 16px', borderBottom: i < knowledgeDocs.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                    <div style={{ color: T.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</div>
                    <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</div>
                    <div style={{ color: T.subtext, fontFamily: T.mono }}>{d.chunk_count}</div>
                    <div style={{ color: T.muted, fontSize: 11 }}>{d.created_at?.slice(0, 10)}</div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => deleteKbDoc(d.id, d.name)} style={iconBtn(T)} title="删除"><I.trash/></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {tab === 'fewshots' && (
          <div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.6 }}>
              管理 SQL Agent 的 few-shot 示例。DB 为空时自动回退到内置 yaml；上传 xlsx 可批量导入（列：question / sql / type / is_active）。
            </div>
            {fewShots.length === 0 ? (
              <div style={{ padding: '40px 24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 10, border: `1px solid ${T.border}` }}>
                暂无示例 · 点击右上角「新建」或上传 xlsx
              </div>
            ) : (
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 0.8fr 0.6fr 80px', padding: '9px 16px', background: T.bg, fontSize: 11, color: T.muted, fontWeight: 600, letterSpacing: '0.03em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>
                  <div>问题</div><div>SQL</div><div>类型</div><div>状态</div><div></div>
                </div>
                {fewShots.map((f, i) => (
                  <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 0.8fr 0.6fr 80px', padding: '11px 16px', borderBottom: i < fewShots.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                    <div style={{ color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.question}</div>
                    <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.sql}</div>
                    <div style={{ color: T.subtext, fontSize: 11.5 }}>{f.type || '—'}</div>
                    <div style={{ fontSize: 11.5, color: f.is_active ? T.success : T.muted }}>{f.is_active ? '启用' : '禁用'}</div>
                    <div style={{ display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
                      <button onClick={() => setModal({ type: 'fewshot', data: f })} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                      <button onClick={() => deleteFewShot(f.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === 'prompts' && (
          <div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.6 }}>
              覆盖 3 个 Agent 的 system prompt。留空则使用内置默认（不影响现有行为）。可使用占位符：clarifier 支持 {'{tables}'} {'{history}'}；sql_planner 支持 {'{max_steps}'} {'{db_env}'} {'{schema}'} {'{business_ctx}'}；presenter 支持 {'{today}'}。
            </div>
            {[
              { key: 'clarifier',   label: 'Clarifier · 理解问题' },
              { key: 'sql_planner', label: 'SQL Planner · 生成 SQL' },
              { key: 'presenter',   label: 'Presenter · 整理洞察 + 质量检查' },
            ].map(({ key, label }) => (
              <div key={key} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 18px', marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <div style={{ fontSize: 12.5, color: T.text, fontWeight: 600 }}>{label}</div>
                  <button onClick={() => savePrompt(key)} disabled={promptsSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
                    {promptsSaving[key] ? <><Spinner size={10} color="#fff"/> 保存中</> : '保存'}
                  </button>
                </div>
                <textarea
                  value={prompts[key]}
                  onChange={e => setPrompts(p => ({ ...p, [key]: e.target.value }))}
                  placeholder="留空使用内置默认 prompt"
                  style={{
                    width: '100%', minHeight: 140, resize: 'vertical',
                    background: T.inputBg, color: T.text, fontFamily: T.mono, fontSize: 12,
                    border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '8px 10px',
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>
            ))}
          </div>
        )}

        {tab === 'catalog' && (
          <div>
            <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.7 }}>
              业务目录注入到 schema 检索 + 3 个 Agent prompt。优先级：DB（本面板编辑）→ 仓库 ohx_catalog.py（部署方填）→ ohx_catalog.example.py（仓库默认）。
              当前生效来源：<b style={{ color: T.text }}>{catalog.source || '...'}</b>。任一字段保存即覆盖默认；点"恢复默认"清空 DB 覆盖。
            </div>

            {[
              { key: 'tables', label: '① 表目录 (TABLES)', hint: 'JSON 数组：[{db, table, topics:[], summary}]，给 schema_filter 做主题加分。', mono: true },
              { key: 'lexicon', label: '② 业务词典 (LEXICON)', hint: 'JSON 对象：{业务词: [表全名优先级]}。问题命中词 → 把列表里的表加分入选。', mono: true },
              { key: 'business_rules', label: '③ 业务规则 (BUSINESS_RULES)', hint: '纯文本/Markdown，注入到 Clarifier、SQL Planner、Presenter 的 system prompt。', mono: false },
            ].map(({ key, label, hint, mono }) => (
              <div key={key} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 18px', marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <div style={{ fontSize: 12.5, color: T.text, fontWeight: 600 }}>
                    {label}
                    {catalog.overrides?.[key] && (
                      <span style={{ marginLeft: 8, fontSize: 10.5, padding: '2px 7px', borderRadius: 999, background: 'rgba(43,127,255,0.12)', color: '#2B7FFF', fontWeight: 600 }}>DB 覆盖中</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    {catalog.overrides?.[key] && (
                      <button onClick={() => resetCatalogField(key)} style={{ ...pillBtn(T), padding: '4px 10px', fontSize: 11.5 }}>恢复默认</button>
                    )}
                    <button onClick={() => saveCatalogField(key)} disabled={catalogSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
                      {catalogSaving[key] ? <><Spinner size={10} color="#fff"/> 保存中</> : '保存'}
                    </button>
                  </div>
                </div>
                <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 8 }}>{hint}</div>
                <textarea
                  value={catalog[key]}
                  onChange={e => setCatalog(c => ({ ...c, [key]: e.target.value }))}
                  placeholder={`留空保存 = 清空 DB 覆盖（回退默认）`}
                  spellCheck={false}
                  style={{
                    width: '100%', minHeight: key === 'business_rules' ? 220 : 180, resize: 'vertical',
                    background: T.inputBg, color: T.text, fontFamily: mono ? T.mono : 'inherit', fontSize: 12,
                    border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '8px 10px',
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {modal?.type === 'user' && <UserFormModal T={T} data={modal.data} sources={sources} onClose={() => setModal(null)} onSave={loadAll}/>}
      {modal?.type === 'source' && <SourceFormModal T={T} data={modal.data} onClose={() => setModal(null)} onSave={loadAll}/>}
      {modal?.type === 'fewshot' && <FewShotModal T={T} data={modal.data} onClose={() => setModal(null)} onSave={loadAll}/>}
    </AppShell>
  );
}

function UserFormModal({ T, data, sources, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    username: data?.username || '',
    password: '',
    display_name: data?.display_name || '',
    role: data?.role || 'analyst',
    source_ids: new Set(data?.source_ids?.map(Number) || []),
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const toggleSource = (id) => {
    const next = new Set(form.source_ids);
    next.has(id) ? next.delete(id) : next.add(id);
    set('source_ids', next);
  };

  const submit = async () => {
    if (!isEdit && (!form.username.trim() || !form.password)) { toast('账号和密码必填', true); return; }
    setLoading(true);
    try {
      const source_ids = [...form.source_ids];
      if (isEdit) {
        const up = { source_ids };
        if (form.display_name) up.display_name = form.display_name;
        if (form.role) up.role = form.role;
        if (form.password) up.password = form.password;
        await api.put(`/api/admin/users/${data.id}`, up);
      } else {
        const body = { username: form.username, password: form.password, display_name: form.display_name, role: form.role };
        await api.post('/api/admin/users', body);
        const users = await api.get('/api/admin/users');
        const created = users.find(u => u.username === form.username);
        if (created && source_ids.length) await api.put(`/api/admin/users/${created.id}`, { source_ids });
      }
      toast(isEdit ? '已更新' : '已创建');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={500}>
      <ModalHeader T={T} title={isEdit ? '编辑账号' : '新建账号'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="账号" value={form.username} onChange={v => set('username', v)} required={!isEdit} placeholder="username"/>
        <Input T={T} label={isEdit ? '新密码（留空不修改）' : '密码'} value={form.password} onChange={v => set('password', v)} type="password" required={!isEdit} placeholder="••••••••"/>
        <Input T={T} label="显示名称" value={form.display_name} onChange={v => set('display_name', v)} placeholder="张三" optional/>
        <Select T={T} label="角色" value={form.role} onChange={v => set('role', v)} options={[{ value: 'analyst', label: 'analyst — 分析师' }, { value: 'admin', label: 'admin — 管理员' }]}/>
        <div style={{ height: 1, background: T.border, margin: '12px 0' }}/>
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 8 }}>数据源（可多选，查询时自动合并表结构）</div>
        {(sources || []).length === 0
          ? <div style={{ fontSize: 12, color: T.muted }}>暂无数据源，请先在「数据源」标签页创建</div>
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(sources || []).map(s => {
                const checked = form.source_ids.has(s.id);
                return (
                  <label key={s.id} onClick={() => toggleSource(s.id)} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                    borderRadius: 7, cursor: 'pointer',
                    background: checked ? T.accentSoft : T.content,
                    border: `1px solid ${checked ? T.accent : T.border}`,
                  }}>
                    <span style={{ width: 15, height: 15, borderRadius: 3, flexShrink: 0, border: `1.5px solid ${checked ? T.accent : T.border}`, background: checked ? T.accent : 'transparent', display: 'grid', placeItems: 'center' }}>
                      {checked && <span style={{ color: '#fff', fontSize: 10, fontWeight: 700 }}>✓</span>}
                    </span>
                    <span style={{ fontSize: 13, color: T.text, flex: 1 }}>{s.name}</span>
                    <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{s.db_database}</span>
                  </label>
                );
              })}
            </div>
        }
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color="#fff"/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}

function SourceFormModal({ T, data, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    name: data?.name || '',
    description: data?.description || '',
    db_host: data?.db_host || '',
    db_port: data?.db_port || 9030,
    db_user: data?.db_user || '',
    db_password: '',
    db_database: data?.db_database || '',
    db_type: data?.db_type || 'doris',
  });
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const testConn = async () => {
    setTesting(true); setTestResult(null);
    try {
      const d = await api.post('/api/db/test', form);
      setTestResult(d);
    } catch (e) { setTestResult({ connected: false, message: String(e) }); }
    finally { setTesting(false); }
  };

  const submit = async () => {
    if (!form.name.trim() || !form.db_host.trim()) { toast('名称和主机必填', true); return; }
    setLoading(true);
    try {
      const body = { ...form, db_port: Number(form.db_port) };
      if (isEdit) await api.put(`/api/admin/datasources/${data.id}`, body);
      else await api.post('/api/admin/datasources', body);
      toast(isEdit ? '已更新' : '已添加');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={480}>
      <ModalHeader T={T} title={isEdit ? '编辑数据源' : '添加数据源'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="名称" value={form.name} onChange={v => set('name', v)} required placeholder="trading_core"/>
        <Input T={T} label="说明" value={form.description} onChange={v => set('description', v)} optional placeholder="交易核心库"/>
        <Select T={T} label="数据库类型" value={form.db_type} onChange={v => set('db_type', v)} options={[{ value: 'doris', label: 'Apache Doris' }, { value: 'mysql', label: 'MySQL' }, { value: 'clickhouse', label: 'ClickHouse' }]}/>
        <Input T={T} label="Host" value={form.db_host} onChange={v => set('db_host', v)} required placeholder="127.0.0.1" mono/>
        <Input T={T} label="Port" value={String(form.db_port)} onChange={v => set('db_port', v)} required placeholder="9030" mono/>
        <Input T={T} label="User" value={form.db_user} onChange={v => set('db_user', v)} required placeholder="root" mono/>
        <Input T={T} label="Password" value={form.db_password} onChange={v => set('db_password', v)} type="password" placeholder={isEdit ? '留空不修改' : '••••••••'} optional={isEdit}/>
        <Input T={T} label="Database" value={form.db_database} onChange={v => set('db_database', v)} required placeholder="mydb 或 ohx_ods,ohx_dwd" mono/>
        <div style={{ fontSize: 11.5, color: T.muted, marginTop: -6 }}>多个库用英文逗号分隔，查询时可跨库使用 库名.表名</div>
        {testResult && (
          <div style={{ padding: '8px 12px', borderRadius: 6, background: testResult.connected ? T.successSoft : T.accentSoft, color: testResult.connected ? T.success : T.accent, fontSize: 12.5, marginBottom: 12 }}>
            {testResult.connected ? '✓ ' : '✗ '}{testResult.message}
          </div>
        )}
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={testConn} disabled={testing} style={pillBtn(T)}>
          {testing ? <><Spinner size={11}/> 测试中…</> : <><I.wifi/> 测试连接</>}
        </button>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color="#fff"/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}


function FewShotModal({ T, data, onClose, onSave }) {
  const isEdit = !!data;
  const [form, setForm] = useState({
    question: data?.question || '',
    sql: data?.sql || '',
    type: data?.type || '',
    is_active: data?.is_active ?? 1,
  });
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.question.trim() || !form.sql.trim()) { toast('question / sql 必填', true); return; }
    setLoading(true);
    try {
      if (isEdit) await api.put(`/api/few-shots/${data.id}`, form);
      else await api.post('/api/few-shots', form);
      toast(isEdit ? '已更新' : '已创建');
      onSave(); onClose();
    } catch (e) { toast(String(e), true); }
    finally { setLoading(false); }
  };

  return (
    <Modal T={T} onClose={onClose} width={560}>
      <ModalHeader T={T} title={isEdit ? '编辑 Few-shot' : '新建 Few-shot'} onClose={onClose}/>
      <div style={{ padding: '16px 20px', maxHeight: '70vh', overflowY: 'auto' }} className="cb-sb">
        <Input T={T} label="问题" value={form.question} onChange={v => set('question', v)} required placeholder="昨天的订单总数"/>
        <div style={{ fontSize: 12, color: T.subtext, marginBottom: 4 }}>SQL</div>
        <textarea value={form.sql} onChange={e => set('sql', e.target.value)} placeholder="SELECT ..."
          style={{ width: '100%', minHeight: 120, resize: 'vertical', background: T.inputBg, color: T.text,
                   fontFamily: T.mono, fontSize: 12, border: `1px solid ${T.inputBorder}`, borderRadius: 7,
                   padding: '8px 10px', outline: 'none', boxSizing: 'border-box', marginBottom: 12 }}/>
        <Input T={T} label="类型 type" value={form.type} onChange={v => set('type', v)} optional
               placeholder="aggregation · rank · join · …"/>
        <Select T={T} label="状态" value={String(form.is_active)} onChange={v => set('is_active', Number(v))}
                options={[{ value: '1', label: '启用' }, { value: '0', label: '禁用' }]}/>
      </div>
      <div style={{ padding: '12px 20px', borderTop: `1px solid ${T.border}`, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button onClick={onClose} style={pillBtn(T)}>取消</button>
        <button onClick={submit} disabled={loading} style={pillBtn(T, true)}>
          {loading ? <Spinner size={12} color="#fff"/> : '保存'}
        </button>
      </div>
    </Modal>
  );
}