// v0.5.3: extracted from Admin.jsx L422-514 (Knowledge + FewShots + Prompts tab JSX)
// D4 mapping: Knowledge (Knowledge + FewShots + Prompts) — 知识库三件套
// v0.5.23: 视觉重构 — Inset 8% 闭环字面文件总数 8→9 第十处扩张 + thead R-480（2 处）+ Hex 偿还
// v0.5.35: Knowledge 完整 UI — stats + drag-drop upload + 8-col 表（demo knowledge.jsx 重写）
import { useRef, useState } from 'react';
import { I, iconBtn, pillBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

// R-587/R-588 共享 thead style — brandSoft 8% + mono + 0.06em + uppercase + fontWeight 500 + T.subtext
const theadStyle = (T) => ({
  background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
  borderBottom: `1px solid ${T.border}`,
  fontSize: 11, color: T.subtext, fontFamily: T.mono,
  fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
});

// v0.5.35 FileIcon — demo knowledge.jsx L39-47 byte-equal；ext 推断类型 + PDF warn / 其他 brand 双色
function FileIcon({ T, type }) {
  const isPdf = type === 'pdf';
  return (
    <span style={{
      width: 32, height: 32, borderRadius: 8,
      background: isPdf ? `color-mix(in oklch, ${T.warn} 12%, transparent)` : `color-mix(in oklch, ${T.accent} 8%, transparent)`,
      color: isPdf ? T.warn : T.accent,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 9, fontWeight: 700, fontFamily: T.mono, letterSpacing: '0.04em',
      flexShrink: 0,
    }}>{(type || 'doc').toUpperCase()}</span>
  );
}

// v0.5.35 relative time helper（demo "2 小时前 / 昨天 / 3 天前 / 1 周前 / 2 周前 / 上月"）
function _relativeTime(iso) {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '—';
  const diff = Date.now() - t;
  const h = diff / 3600000;
  if (h < 1) return '刚刚';
  if (h < 24) return `${Math.floor(h)} 小时前`;
  const d = h / 24;
  if (d < 2) return '昨天';
  if (d < 7) return `${Math.floor(d)} 天前`;
  if (d < 14) return '1 周前';
  if (d < 30) return `${Math.floor(d / 7)} 周前`;
  return '上月';
}

export function TabKnowledge({ T, tab, knowledgeDocs, onDeleteKbDoc, onUploadKb,
                              fewShots, onEditFewShot, onDeleteFewShot,
                              prompts, setPrompts, promptsSaving, onSavePrompt }) {
  const dragRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  // v0.5.35 stats 计算
  const indexedCount = knowledgeDocs.filter(d => (d.chunk_count || 0) > 0).length;
  const lastUpdate = knowledgeDocs.length > 0
    ? _relativeTime(knowledgeDocs.map(d => d.created_at).sort().reverse()[0])
    : '—';

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f && onUploadKb) onUploadKb(f);
  };

  return (
    <>
      {tab === 'knowledge' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* v0.5.35 stats — demo knowledge.jsx L58-75 byte-equal（4-grid） */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' }}>文档数</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.text, fontFamily: T.mono, letterSpacing: '-0.02em', marginTop: 4 }}>{knowledgeDocs.length}</div>
            </div>
            <div title="后端文件大小字段对接中 (v0.5.38)" style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' }}>总大小</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.muted, fontFamily: T.mono, marginTop: 4 }}>—</div>
            </div>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' }}>索引状态</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.accent, fontFamily: T.mono, marginTop: 4 }}>{indexedCount} / {knowledgeDocs.length}</div>
            </div>
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.06em', textTransform: 'uppercase' }}>上次更新</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: T.text, marginTop: 4 }}>{lastUpdate}</div>
            </div>
          </div>

          {/* v0.5.35 drag-drop zone — demo knowledge.jsx L77-95 byte-equal */}
          <div
            ref={dragRef}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            style={{
              border: `1.5px dashed color-mix(in oklch, ${T.accent} ${dragOver ? 50 : 25}%, transparent)`,
              borderRadius: 12,
              background: `color-mix(in oklch, ${T.accent} ${dragOver ? 12 : 8}%, transparent)`,
              padding: '24px 24px',
              display: 'flex', alignItems: 'center', gap: 16,
              transition: 'all 0.2s',
            }}>
            <span style={{
              width: 44, height: 44, borderRadius: 10,
              background: T.card, color: T.accent,
              border: `1px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <I.dl width="20" height="20" style={{ transform: 'rotate(180deg)' }}/>
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>拖拽文件到这里上传</div>
              <div style={{ fontSize: 12, color: T.muted, marginTop: 2 }}>支持 .md / .pdf / .txt · 单文件 ≤ 10 MB · 上传后自动切块、向量化并加入检索</div>
            </div>
          </div>

          {/* v0.5.35 doc list — demo knowledge.jsx L98-141 重设计（4-col → 8-col 字段对齐） */}
          {knowledgeDocs.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: T.muted, background: T.card, borderRadius: 12, border: `1px solid ${T.border}`, fontSize: 13 }}>
              暂无文档 · 上方拖拽或点击右上角「上传文档」添加
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {/* v0.5.35 thead — 8 列 demo L100-105 byte-equal */}
              <div style={{ display: 'grid', gridTemplateColumns: '60px 2fr 0.8fr 0.8fr 1fr 0.7fr 1fr 70px', padding: '10px 18px', ...theadStyle(T) }}>
                <div></div><div>文档名</div><div>类型</div><div>大小</div><div>更新</div><div style={{ textAlign: 'right' }}>命中</div><div>状态</div><div></div>
              </div>
              {knowledgeDocs.map((d, i) => {
                const ext = (d.filename || '').toLowerCase().split('.').pop() || 'doc';
                const isIndexed = (d.chunk_count || 0) > 0;
                return (
                  <div key={d.id} style={{ display: 'grid', gridTemplateColumns: '60px 2fr 0.8fr 0.8fr 1fr 0.7fr 1fr 70px', padding: '12px 18px', borderBottom: i < knowledgeDocs.length - 1 ? `1px solid ${T.borderSoft}` : 'none', alignItems: 'center', fontSize: 12.5 }}>
                    <FileIcon T={T} type={ext}/>
                    <div style={{ color: T.text, fontWeight: 500, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</div>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ padding: '2px 8px', borderRadius: 4, background: `color-mix(in oklch, ${T.accent} 8%, transparent)`, color: T.accent, fontSize: 10.5, fontFamily: T.mono, textTransform: 'uppercase' }}>{ext}</span>
                    </div>
                    <div title="后端文件大小字段对接中 (v0.5.38)" style={{ color: T.muted, fontFamily: T.mono, fontSize: 11, minWidth: 0 }}>—</div>
                    <div style={{ color: T.muted, fontSize: 11.5, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{_relativeTime(d.created_at)}</div>
                    <div title={`${d.chunk_count || 0} 分块`} style={{ color: T.text, fontFamily: T.mono, fontSize: 11.5, textAlign: 'right', minWidth: 0 }}>{d.chunk_count || 0}</div>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: isIndexed ? T.success : T.warn }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }}/>
                        {isIndexed ? '已索引' : '待索引'}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
                      <button onClick={() => onDeleteKbDoc(d.id, d.name)} style={iconBtn(T)} title="删除"><I.trash/></button>
                    </div>
                  </div>
                );
              })}
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
