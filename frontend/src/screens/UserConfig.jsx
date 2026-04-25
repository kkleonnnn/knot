import { useState, useEffect } from 'react';
import { pillBtn } from '../Shared.jsx';
import { toast, Input, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

export function UserConfigScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({ api_key: '', preferred_model: '', openrouter_api_key: '', embedding_api_key: '' });
  const [saving, setSaving] = useState(false);
  const [customModelDraft, setCustomModelDraft] = useState('');
  const [agentCfg, setAgentCfg] = useState({ clarifier: '', sql_planner: '', validator: '', presenter: '' });
  const [agentSaving, setAgentSaving] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  useEffect(() => {
    Promise.all([api.get('/api/user/config'), api.get('/api/user/agent-models')]).then(([d, ac]) => {
      setConfig(d);
      setForm({ api_key: d.api_key || '', preferred_model: d.preferred_model || '', openrouter_api_key: d.openrouter_api_key || '', embedding_api_key: d.embedding_api_key || '' });
      setCustomModelDraft(d.preferred_model?.includes('/') ? d.preferred_model : '');
      setAgentCfg(ac);
    }).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const body = {};
      if (form.api_key !== config?.api_key) body.api_key = form.api_key;
      if (form.preferred_model !== config?.preferred_model) body.preferred_model = form.preferred_model;
      if (form.openrouter_api_key !== config?.openrouter_api_key) body.openrouter_api_key = form.openrouter_api_key;
      if (form.embedding_api_key !== config?.embedding_api_key) body.embedding_api_key = form.embedding_api_key;
      if (Object.keys(body).length) await api.put('/api/user/config', body);
      setConfig(prev => ({ ...prev, ...body }));
      toast('已保存');
    } catch (e) { toast(String(e), true); }
    finally { setSaving(false); }
  };

  const saveAgentCfg = async () => {
    setAgentSaving(true);
    try { await api.put('/api/user/agent-models', agentCfg); toast('多Agent配置已保存'); }
    catch (e) { toast(String(e), true); }
    finally { setAgentSaving(false); }
  };

  const models = config?.models || [];

  const cardStyle = { background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '18px 20px', marginBottom: 16 };

  return (
    <AppShell T={T} user={user} active="user-config" topbarTitle="API & 模型"
              showConnectionPill={false}
              topbarTrailing={
                <button onClick={save} disabled={saving} style={pillBtn(T, true)}>
                  {saving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存更改'}
                </button>
              }
              onToggleTheme={onToggleTheme} onNewChat={() => {}} onNavigate={onNavigate} onLogout={onLogout}>
      <div className="cb-sb" style={{ flex: 1, overflowY: 'auto', padding: '22px 28px' }}>

        {config && (
          <div style={{ ...cardStyle, marginBottom: 16 }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 12 }}>本月用量</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {[
                { l: '总 Tokens', v: (config.monthly_tokens || 0).toLocaleString() },
                { l: '总花费',   v: `$${(config.monthly_cost_usd || 0).toFixed(4)}` },
                { l: '平均响应', v: config.avg_response_ms ? `${config.avg_response_ms}ms` : '—' },
              ].map((k, i) => (
                <div key={i} style={{ background: T.bg, border: `1px solid ${T.borderSoft}`, borderRadius: 7, padding: '10px 12px' }}>
                  <div style={{ fontSize: 11, color: T.muted }}>{k.l}</div>
                  <div style={{ fontSize: 18, fontFamily: T.mono, color: T.text, marginTop: 2, fontWeight: 500 }}>{k.v}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 0 }}>
          {/* API Key */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>API Key 自定义</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>支持 Anthropic / OpenAI / Google / DeepSeek 等直连</div>
            <Input T={T} label="API Key" value={form.api_key} onChange={v => set('api_key', v)}
                   type="password" placeholder="sk-ant-api03-…" mono
                   trailing={<span style={{ fontSize: 11, color: form.api_key ? T.success : T.muted }}>{form.api_key ? '已填写' : '未填写'}</span>}/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4, marginBottom: 10 }}>留空则使用系统全局 Key</div>
            <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6 }}>热门模型快选（设为默认）</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
              {[
                { id: 'claude-opus-4-7',   label: 'Claude Opus 4.7' },
                { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
                { id: 'claude-haiku-4-5',  label: 'Claude Haiku 4.5' },
                { id: 'gpt-4o',            label: 'GPT-4o' },
                { id: 'gpt-4o-mini',       label: 'GPT-4o Mini' },
                { id: 'gemini-2.0-flash',  label: 'Gemini 2.0 Flash' },
                { id: 'deepseek-chat',     label: 'DeepSeek Chat' },
              ].map(({ id, label }) => {
                const active = form.preferred_model === id;
                return (
                  <button key={id} onClick={() => { set('preferred_model', active ? '' : id); setCustomModelDraft(''); }}
                          style={{ padding: '3px 9px', borderRadius: 12, fontSize: 11.5, cursor: 'pointer',
                                   background: active ? T.accent : T.chipBg, color: active ? '#fff' : T.text,
                                   border: `1px solid ${active ? T.accent : T.border}` }}>
                    {label}
                  </button>
                );
              })}
            </div>
            <Input T={T} label="自定义模型 ID"
                   value={form.preferred_model && !form.preferred_model.includes('/') ? form.preferred_model : ''}
                   onChange={v => { set('preferred_model', v); setCustomModelDraft(''); }}
                   placeholder="claude-sonnet-4-6 · gpt-4o · …" mono/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>填写后将作为默认模型</div>
          </div>

          {/* OpenRouter */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>OpenRouter 接入</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>通过一个 Key 接入 OpenAI / Anthropic / Google 等 200+ 模型</div>
            <Input T={T} label="OpenRouter API Key" value={form.openrouter_api_key} onChange={v => set('openrouter_api_key', v)}
                   type="password" placeholder="sk-or-v1-…" mono
                   trailing={<span style={{ fontSize: 11, color: form.openrouter_api_key ? T.success : T.muted }}>{form.openrouter_api_key ? '已填写' : '未填写'}</span>}/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4, marginBottom: 10 }}>前往 openrouter.ai/keys 创建</div>
            <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6 }}>热门模型快选（设为默认）</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
              {[
                { id: 'openai/gpt-4o',                      label: 'GPT-4o' },
                { id: 'openai/gpt-4o-mini',                 label: 'GPT-4o Mini' },
                { id: 'anthropic/claude-sonnet-4-5',        label: 'Claude Sonnet 4.5' },
                { id: 'google/gemini-2.0-flash-001',        label: 'Gemini 2.0 Flash' },
                { id: 'deepseek/deepseek-chat-v3-0324',     label: 'DeepSeek V3' },
                { id: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
                { id: 'qwen/qwen-2.5-72b-instruct',        label: 'Qwen 2.5 72B' },
                { id: 'mistralai/mistral-large-2411',       label: 'Mistral Large' },
              ].map(({ id, label }) => {
                const active = form.preferred_model === id;
                return (
                  <button key={id} onClick={() => { const v = active ? '' : id; set('preferred_model', v); setCustomModelDraft(v); }}
                          style={{ padding: '3px 9px', borderRadius: 12, fontSize: 11.5, cursor: 'pointer',
                                   background: active ? T.accent : T.chipBg, color: active ? '#fff' : T.text,
                                   border: `1px solid ${active ? T.accent : T.border}` }}>
                    {label}
                  </button>
                );
              })}
            </div>
            <Input T={T} label="自定义模型 ID"
                   value={customModelDraft}
                   onChange={v => { setCustomModelDraft(v); set('preferred_model', v); }}
                   placeholder="openai/gpt-4o · anthropic/claude-opus-4-5 · …" mono/>
            <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>格式：厂商/模型名 · 见 openrouter.ai/models</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          {/* 直连模型 */}
          <div style={cardStyle}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>直连模型</div>
            <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>管理员配置的可选模型 · 选择后作为默认</div>
            {form.preferred_model && form.preferred_model.includes('/') && (
              <div style={{ padding: '7px 10px', borderRadius: 6, background: T.accentSoft, border: `1px solid ${T.accent}`, fontSize: 11.5, color: T.accent, marginBottom: 10 }}>
                当前已选 OpenRouter 模型：<strong>{form.preferred_model}</strong>
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {models.map(m => {
                const mid = m.model_id || m.id;
                const active = !form.preferred_model?.includes('/') && (form.preferred_model === mid || (!form.preferred_model && m.is_default));
                return (
                  <label key={mid} onClick={() => { set('preferred_model', mid); setCustomModelDraft(''); }} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                    background: active ? T.accentSoft : T.bg,
                    border: `1px solid ${active ? T.accent : T.borderSoft}`,
                    borderRadius: 7, cursor: 'pointer',
                  }}>
                    <span style={{ width: 14, height: 14, borderRadius: '50%', flexShrink: 0, border: `1.5px solid ${active ? T.accent : T.border}`, display: 'grid', placeItems: 'center', background: active ? T.accent : 'transparent' }}>
                      {active && <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#fff' }}/>}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, color: T.text, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                        {m.name}
                        <span style={{ fontSize: 10, padding: '1px 4px', borderRadius: 3, background: T.chipBg, color: T.muted }}>{m.provider}</span>
                        {m.is_default && <span style={{ fontSize: 10, padding: '1px 4px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>默认</span>}
                      </div>
                    </div>
                    <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>${m.input_price}/{m.output_price}</span>
                  </label>
                );
              })}
              {models.length === 0 && <div style={{ color: T.muted, fontSize: 12, padding: '12px 0' }}>暂无可用模型</div>}
            </div>
          </div>

          {/* Embedding + 多Agent */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0, minWidth: 0 }}>
            <div style={cardStyle}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>Embedding API Key</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 12 }}>用于知识库向量检索 · 填 OpenAI Key · 留空降级为关键词匹配</div>
              <Input T={T} label="Embedding API Key" value={form.embedding_api_key} onChange={v => set('embedding_api_key', v)}
                     type="password" placeholder="sk-…" mono
                     trailing={<span style={{ fontSize: 11, color: form.embedding_api_key ? T.success : T.muted }}>{form.embedding_api_key ? '已填写' : '未填写'}</span>}/>
              <div style={{ fontSize: 11, color: T.muted, marginTop: -4 }}>OpenRouter Key 可替代</div>
            </div>

            <div style={{ ...cardStyle, marginBottom: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: T.text, marginBottom: 2 }}>多 Agent 分配</div>
              <div style={{ fontSize: 11, color: T.muted, marginBottom: 14 }}>
                为每个 Agent 指定模型，留空则跟随默认模型。优先使用你配置的 API Key。
              </div>
              {[
                { key: 'clarifier',   label: '理解问题',  hint: '推荐轻量模型' },
                { key: 'sql_planner', label: '生成 SQL',  hint: '推荐最强模型' },
                { key: 'validator',   label: '验证结果',  hint: '推荐轻量模型' },
                { key: 'presenter',   label: '整理洞察',  hint: '推荐中等模型' },
              ].map(({ key, label, hint }) => (
                <div key={key} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: T.subtext, fontWeight: 500 }}>{label}</span>
                    <span style={{ fontSize: 10.5, color: T.muted }}>{hint}</span>
                  </div>
                  <select value={agentCfg[key] || ''} onChange={e => setAgentCfg(p => ({ ...p, [key]: e.target.value }))}
                    style={{ width: '100%', background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '6px 10px', fontSize: 12, color: T.text, fontFamily: T.sans, cursor: 'pointer', outline: 'none' }}>
                    <option value="">默认（跟随用户模型）</option>
                    {models.filter(m => m.enabled !== false).map(m => (
                      <option key={m.model_id} value={m.model_id}>{m.name} · {m.provider}</option>
                    ))}
                  </select>
                </div>
              ))}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                <button onClick={saveAgentCfg} disabled={agentSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
                  {agentSaving ? <><Spinner size={11} color="#fff"/> 保存中…</> : '保存配置'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
