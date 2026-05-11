// v0.5.3: extracted from Admin.jsx L422-514 (Knowledge + FewShots + Prompts tab JSX)
// D4 mapping: Knowledge (Knowledge + FewShots + Prompts) — 知识库三件套
// v0.5.23: 视觉重构 — Inset 8% 闭环字面文件总数 8→9 第十处扩张 + thead R-480（2 处）+ Hex 偿还
import { I, iconBtn, pillBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

// R-587/R-588 共享 thead style — brandSoft 8% + mono + 0.06em + uppercase + fontWeight 500 + T.subtext
const theadStyle = (T) => ({
  background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
  borderBottom: `1px solid ${T.border}`,
  fontSize: 11, color: T.subtext, fontFamily: T.mono,
  fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
});

export function TabKnowledge({ T, tab, knowledgeDocs, onDeleteKbDoc,
                              fewShots, onEditFewShot, onDeleteFewShot,
                              prompts, setPrompts, promptsSaving, onSavePrompt }) {
  return (
    <>
      {tab === 'knowledge' && (
        <div>
          <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 14, lineHeight: 1.55 }}>
            上传业务文档（PDF / Markdown / TXT），每次 SQL 查询时自动检索相关片段注入 prompt，提升生成准确度。<br/>
            需要 OpenAI 或 OpenRouter API Key 才能使用向量检索；无 Key 时自动降级为关键词匹配。
          </div>
          {knowledgeDocs.length === 0 ? (
            <div style={{ padding: '40px 24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 12, border: `1px solid ${T.border}` }}>
              暂无文档 · 点击右上角「上传文档」添加
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {/* R-587 thead R-480 闭环字面第十处扩张 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '9px 16px', ...theadStyle(T) }}>
                <div>文档名称</div><div>文件名</div><div>分块数</div><div>上传时间</div><div></div>
              </div>
              {knowledgeDocs.map((d, i) => (
                <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '1.8fr 1fr 0.8fr 0.8fr 60px', padding: '11px 16px', borderBottom: i < knowledgeDocs.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                  {/* R-589 Row 5 字段 minWidth: 0 + ellipsis 兜底 */}
                  <div style={{ color: T.text, fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.filename}</div>
                  <div style={{ color: T.subtext, fontFamily: T.mono, minWidth: 0 }}>{d.chunk_count}</div>
                  <div style={{ color: T.muted, fontSize: 11, fontFamily: T.mono, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.created_at?.slice(0, 10)}</div>
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
          <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 14, lineHeight: 1.55 }}>
            管理 SQL Agent 的 few-shot 示例。DB 为空时自动回退到内置 yaml；上传 xlsx 可批量导入（列：question / sql / type / is_active）。
          </div>
          {fewShots.length === 0 ? (
            <div style={{ padding: '40px 24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 12, border: `1px solid ${T.border}` }}>
              暂无示例 · 点击右上角「新建」或上传 xlsx
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {/* R-588 thead R-480 闭环字面本文件第二处命中 */}
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 0.8fr 0.6fr 80px', padding: '9px 16px', ...theadStyle(T) }}>
                <div>问题</div><div>SQL</div><div>类型</div><div>状态</div><div></div>
              </div>
              {fewShots.map((f, i) => (
                <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '2fr 3fr 0.8fr 0.6fr 80px', padding: '11px 16px', borderBottom: i < fewShots.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                  {/* R-590 Row 5 字段 minWidth: 0 + ellipsis 兜底 */}
                  <div style={{ color: T.text, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.question}</div>
                  <div style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.sql}</div>
                  <div style={{ color: T.subtext, fontSize: 11.5, fontFamily: T.mono, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.type || '—'}</div>
                  <div style={{ fontSize: 11.5, color: f.is_active ? T.success : T.muted, minWidth: 0 }}>{f.is_active ? '启用' : '禁用'}</div>
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
          <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 14, lineHeight: 1.55 }}>
            覆盖 3 个 Agent 的 system prompt。留空则使用内置默认（不影响现有行为）。可使用占位符：clarifier 支持 {'{tables}'} {'{history}'}；sql_planner 支持 {'{max_steps}'} {'{db_env}'} {'{schema}'} {'{business_ctx}'}；presenter 支持 {'{today}'}。
          </div>
          {[
            { key: 'clarifier',   label: 'Clarifier · 理解问题' },
            { key: 'sql_planner', label: 'SQL Planner · 生成 SQL' },
            { key: 'presenter',   label: 'Presenter · 整理洞察 + 质量检查' },
          ].map(({ key, label }) => (
            // R-592 Section radius 10→12 + padding 升级（与 v0.5.21/22 Card 一致）
            <div key={key} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '16px 20px', marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                {/* R-593 Section header — fontSize 14 + fontWeight 600 + letterSpacing -0.01em */}
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>{label}</div>
                {/* R-596 Spinner color hex 偿还 — 白色字面 → T.sendFg（R-484 sustained） */}
                <button onClick={() => onSavePrompt(key)} disabled={promptsSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
                  {promptsSaving[key] ? <><Spinner size={10} color={T.sendFg}/> 保存中</> : '保存'}
                </button>
              </div>
              {/* R-594 textarea byte-equal — minHeight 140 + T.mono + T.inputBg + radius 7 */}
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
