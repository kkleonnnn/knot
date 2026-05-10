// v0.5.3: extracted from Admin.jsx L345-420 (Models tab — API Keys + Agent Models + Models Table)
// D4 mapping: Resources (Models) — 资源（Budgets 是独立页面 AdminBudgets.jsx）
import { I, iconBtn, pillBtn } from '../../Shared.jsx';
import { Input, Spinner } from '../../utils.jsx';

export function TabResources({ T, models, apiKeys, setApiKeys, apiKeysSaving, onSaveApiKeys,
                              agentCfg, setAgentCfg, agentSaving, onSaveAgentCfg,
                              onToggleModel, onSetDefaultModel }) {
  return (
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
          <button onClick={onSaveApiKeys} disabled={apiKeysSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
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
          <button onClick={onSaveAgentCfg} disabled={agentSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
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
              <button onClick={() => onSetDefaultModel(m.id)} style={iconBtn(T)} title="设为默认"><I.check/></button>
              <button onClick={() => onToggleModel(m.id)} style={iconBtn(T)} title="启用/禁用"><I.zap/></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
