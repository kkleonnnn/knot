// v0.5.3: extracted from Admin.jsx L422-514 (Knowledge + FewShots + Prompts tab JSX)
// D4 mapping: Knowledge (Knowledge + FewShots + Prompts) — 知识库三件套
import { I, iconBtn, pillBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

export function TabKnowledge({ T, tab, knowledgeDocs, onDeleteKbDoc,
                              fewShots, onEditFewShot, onDeleteFewShot,
                              prompts, setPrompts, promptsSaving, onSavePrompt }) {
  return (
    <>
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
                    <button onClick={() => onDeleteKbDoc(d.id, d.name)} style={iconBtn(T)} title="删除"><I.trash/></button>
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
                    <button onClick={() => onEditFewShot(f)} style={iconBtn(T)} title="编辑"><I.pencil/></button>
                    <button onClick={() => onDeleteFewShot(f.id)} style={iconBtn(T)} title="删除"><I.trash/></button>
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
                <button onClick={() => onSavePrompt(key)} disabled={promptsSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
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
    </>
  );
}
