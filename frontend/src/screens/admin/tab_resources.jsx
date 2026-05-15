// v0.5.3: extracted from Admin.jsx L345-420 (Models tab — API Keys + Agent Models + Models Table)
// D4 mapping: Resources (Models) — 资源（Budgets 是独立页面 AdminBudgets.jsx）
// v0.5.21: 视觉重构 — Inset 8% 闭环字面第八处扩展（文件总数 6→7）+ thead R-480 + KeyInput mono trailing + Hex 偿还
import { I, iconBtn, pillBtn } from '../../Shared.jsx';
import { Input, Spinner } from '../../utils.jsx';

export function TabResources({ T, models, apiKeys, setApiKeys, apiKeysSaving, onSaveApiKeys,
                              agentCfg, setAgentCfg, agentSaving, onSaveAgentCfg,
                              onToggleModel, onSetDefaultModel, onSyncOrCatalog, orSyncing }) {
  // R-529 KeyInput trailing mono uppercase helper — "已填写"/"未填写" 工业感
  const trailingChip = (value) => (
    <span style={{
      fontSize: 10,
      color: value ? T.success : T.muted,
      fontFamily: T.mono,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
    }}>{value ? '已填写' : '未填写'}</span>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* R-527/R-528 API Keys Card — padding 16→20 + radius 10→12 + header 14/600/-0.01em + desc 1.55 */}
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px 22px' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: '-0.01em', marginBottom: 4 }}>API Key（应用级）</div>
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.55 }}>所有用户共用 · OpenRouter 用于 LLM、Embedding 用于知识库向量检索（默认 text-embedding-3-small，未填则降级关键词匹配）</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <Input T={T} label="OpenRouter API Key" value={apiKeys.openrouter_api_key}
                 onChange={v => setApiKeys(s => ({ ...s, openrouter_api_key: v }))}
                 type="password" placeholder="sk-or-v1-…" mono
                 trailing={trailingChip(apiKeys.openrouter_api_key)}/>
          <Input T={T} label="Embedding API Key" value={apiKeys.embedding_api_key}
                 onChange={v => setApiKeys(s => ({ ...s, embedding_api_key: v }))}
                 type="password" placeholder="sk-…（OpenAI / 兼容端点）" mono
                 trailing={trailingChip(apiKeys.embedding_api_key)}/>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
          {/* R-536 Spinner color hex 偿还 — 白色字面 → T.sendFg（R-484 sustained） */}
          <button onClick={onSaveApiKeys} disabled={apiKeysSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
            {apiKeysSaving ? <><Spinner size={11} color={T.sendFg}/> 保存中…</> : '保存 Key'}
          </button>
        </div>
      </div>

      {/* R-530 Agent Allocation Card — padding/radius 升级 + 3-col grid 120/1fr/90px */}
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px 22px' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: '-0.01em', marginBottom: 4 }}>3 个 Agent 模型分配</div>
        <div style={{ fontSize: 12, color: T.muted, marginBottom: 14, lineHeight: 1.55 }}>为每个 agent 指定模型，留空则跟随系统默认（DEFAULT_MODEL）</div>
        {[
          { key: 'clarifier',   label: '理解问题',   hint: '推荐轻量' },
          { key: 'sql_planner', label: '生成 SQL',   hint: '推荐最强' },
          { key: 'presenter',   label: '整理洞察 + 质量检查', hint: '推荐中等' },
        ].map(({ key, label, hint }) => (
          // v0.5.41 — label 列 120 → 160 防 "整理洞察 + 质量检查" 换行；select 列 flex 1（resp 压缩）；hint 列 80 收紧
          <div key={key} style={{ display: 'grid', gridTemplateColumns: '160px 1fr 80px', gap: 12, alignItems: 'center', marginBottom: 10 }}>
            <span style={{ fontSize: 13, color: T.text, fontWeight: 500, whiteSpace: 'nowrap' }}>{label}</span>
            <select value={agentCfg[key] || ''} onChange={e => setAgentCfg(p => ({ ...p, [key]: e.target.value }))}
              style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '6px 10px', fontSize: 12, color: T.text, fontFamily: T.sans, cursor: 'pointer', outline: 'none' }}>
              <option value="">默认</option>
              {models.filter(m => m.enabled !== false).map(m => (
                <option key={m.model_id} value={m.model_id}>{m.name} · {m.provider}</option>
              ))}
            </select>
            {/* D4 plain span hint byte-equal — 管理端指导文案可读性优先；不引入 TagChip */}
            <span style={{ fontSize: 11, color: T.muted, textAlign: 'right' }}>{hint}</span>
          </div>
        ))}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
          {/* R-536 Spinner color hex 偿还 — 白色字面 → T.sendFg */}
          <button onClick={onSaveAgentCfg} disabled={agentSaving} style={{ ...pillBtn(T, true), padding: '6px 14px' }}>
            {agentSaving ? <><Spinner size={11} color={T.sendFg}/> 保存中…</> : '保存 Agent 配置'}
          </button>
        </div>
      </div>

      {/* v0.6.0.6 F-D-6 — 从 OpenRouter 同步 catalog 按钮（数据自治原则；不影响业务路径） */}
      {onSyncOrCatalog && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onSyncOrCatalog} disabled={orSyncing}
                  title="拉取 OpenRouter live API 写入 model_catalog_live 缓存表（参考用，不影响业务路径）"
                  style={{ ...pillBtn(T, false), padding: '5px 12px', fontSize: 12 }}>
            {orSyncing ? <><Spinner size={11} color={T.accent}/> 同步中…</> : <><I.refresh width="12" height="12"/> 从 OpenRouter 同步</>}
          </button>
        </div>
      )}

      {/* v0.5.38 thead bg brandSoft 8% → T.bg gray + color T.subtext → T.muted（资深反馈"底色改成灰色 + 字体统一"）*/}
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.8fr 0.7fr 100px',
          padding: '9px 16px',
          background: T.bg,
          fontSize: 11, color: T.muted, fontFamily: T.mono,
          fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
          borderBottom: `1px solid ${T.border}`,
        }}>
          <div>名称</div><div>提供方</div><div>Model ID</div><div>单价(入/出)</div><div>上下文</div><div>状态</div><div></div>
        </div>
        {models.map((m, i) => (
          <div key={m.id} style={{ display: 'grid', gridTemplateColumns: '1.5fr 0.7fr 1.4fr 1fr 0.8fr 0.7fr 100px', padding: '11px 16px', borderBottom: i < models.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5, opacity: m.enabled ? 1 : 0.55 }}>
            <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <span style={{ color: T.text, fontWeight: 500 }}>{m.name}</span>
              {/* R-534 默认 chip 保 T.accentSoft byte-equal（D6 保守） */}
              {m.is_default ? <span style={{ marginLeft: 6, fontSize: 9.5, padding: '1px 5px', borderRadius: 3, background: T.accentSoft, color: T.accent, fontWeight: 600 }}>默认</span> : null}
            </div>
            <div style={{ color: T.subtext, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.provider}</div>
            {/* R-546 Model ID Mono 守护 — 技术元数据识别度 */}
            <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.model_id}</div>
            {/* R-549 价格业务标签 $ 单位保留 byte-equal */}
            <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>${m.input_price}/{m.output_price}</div>
            {/* v0.6.0.6 F-D-5 上下文列：智能 K/M 显示；direct provider 无 max_context 时显 — */}
            <div style={{ color: T.subtext, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {m.max_context
                ? (m.max_context >= 1000000 ? `${(m.max_context / 1000000).toFixed(m.max_context % 1000000 === 0 ? 0 : 1)}M`
                                            : `${Math.round(m.max_context / 1024)}K`)
                : '—'}
            </div>
            {/* R-535 状态文字 byte-equal */}
            <div style={{ fontSize: 11.5, color: m.enabled ? T.success : T.muted, minWidth: 0 }}>{m.enabled ? '启用' : '禁用'}</div>
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
