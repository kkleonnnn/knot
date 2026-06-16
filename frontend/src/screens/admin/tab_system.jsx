// v0.5.3: extracted from Admin.jsx L516-561 (Catalog tab JSX)
// D4 mapping: System (Catalog) — 系统与治理（Audit / Recovery 是独立页面 AdminAudit.jsx / AdminRecovery.jsx）
// v0.5.22: 视觉重构 — Inset 8% 闭环第九处扩张（7→8 文件）+ borderLeft 25% 第四处闭环 + 蓝色 hex 双残留偿还
import { useState } from 'react';
import { pillBtn, NumChip, OverrideChip, SourceTag } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

export function TabSystem({ T, catalog, setCatalog, catalogSaving, onSaveCatalogField, onResetCatalogField,
                            catalogs = [], activeCatalogId = 1, onSwitchCatalog, onCreateCatalog, onDeleteCatalog }) {
  // v0.6.2.5 段 4 (A1): 新建 catalog 名称输入（UI-local 受控态）
  const [newCatalogName, setNewCatalogName] = useState('');
  // v0.5.44 — 加第 4 section 表关系（RELATIONS）— 笛卡尔积根因解 (admin UI 替代 gitignored .py)
  const sections = [
    { num: '01', key: 'tables', title: '表目录', source: 'tables', hint: 'JSON 数组：[{db, table, topics:[], summary}]，给 schema_filter 做主题加分。', mono: true },
    { num: '02', key: 'lexicon', title: '业务词典', source: 'lexicon', hint: 'JSON 对象：{业务词: [表全名优先级]}。问题命中词 → 把列表里的表加分入选。', mono: true },
    { num: '03', key: 'business_rules', title: '业务规则', source: 'business_rules', hint: '纯文本/Markdown，注入到 Clarifier、SQL Planner、Presenter 的 system prompt。', mono: false },
    { num: '04', key: 'relations', title: '表关系', source: 'relations', hint: 'JSON 数组：[[left_table, left_col, right_table, right_col, semantics?]]。多表 JOIN ON 关联键来源，sql_planner 必读防笛卡尔积。', mono: true },
  ];

  return (
    <div>
      {/* v0.5.29 #25/26 — info icon path 改 demo byte-equal（filled dot + 更清晰 i 形）；
          borderLeft 25% 移除（资深反馈"莫名其妙的深色边边"；v0.5.22 R-481 第四处闭环局部撤回 — 仅 catalog Helper） */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '12px 14px',
        background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
        border: `1px solid ${T.border}`,
        borderRadius: 8,
        fontSize: 12, color: T.subtext, lineHeight: 1.55, marginBottom: 16,
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.8" style={{ flexShrink: 0, marginTop: 2 }}>
          <circle cx="12" cy="12" r="9"/>
          <line x1="12" y1="11" x2="12" y2="16"/>
          <circle cx="12" cy="8" r="0.6" fill={T.accent}/>
        </svg>
        <div>
          业务目录注入到 schema 检索 + 3 个 Agent prompt。优先级：DB（本面板编辑）→ 仓库 _local_catalog.py（部署方填）→ _template_catalog.py（仓库默认）。
          当前生效来源：<b style={{ color: T.text }}>{catalog.source || '...'}</b>。任一字段保存即覆盖默认；点"恢复默认"清空 DB 覆盖。
        </div>
      </div>

      {/* v0.6.2.5 段 4 (A1): 多 catalog 切换选择器 — VRP 视觉延续（Inset 8% + 25% border + SourceTag/pillBtn）*/}
      <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, marginBottom: 14, padding: '14px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>多 Catalog 切换</div>
          <SourceTag T={T}>active</SourceTag>
          <div style={{ flex: 1 }}/>
          <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>per-user 切换 · query 生效 v0.6.2.6</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {catalogs.map(c => {
            const isActive = c.id === activeCatalogId;
            return (
              <div key={c.id} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
                background: isActive ? `color-mix(in oklch, ${T.accent} 8%, transparent)` : T.inputBg,
                border: `1px solid ${isActive ? `color-mix(in oklch, ${T.accent} 25%, transparent)` : T.border}`,
                borderRadius: 8,
              }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{c.name}</span>
                <span style={{ fontSize: 10.5, color: T.muted, fontFamily: T.mono }}>#{c.id}</span>
                {c.description && <span style={{ fontSize: 11.5, color: T.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.description}</span>}
                <div style={{ flex: 1 }}/>
                {isActive
                  ? <SourceTag T={T}>当前 active</SourceTag>
                  : <button onClick={() => onSwitchCatalog(c.id)} style={{ ...pillBtn(T), padding: '4px 10px', fontSize: 11.5 }}>切换</button>}
                {c.id !== 1 && <button onClick={() => onDeleteCatalog(c.id)} style={{ ...pillBtn(T), padding: '4px 10px', fontSize: 11.5 }}>删除</button>}
              </div>
            );
          })}
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <input
            value={newCatalogName}
            onChange={e => setNewCatalogName(e.target.value)}
            placeholder="新 catalog 名称..."
            style={{ flex: 1, background: T.inputBg, color: T.text, fontSize: 12, border: `1px solid ${T.inputBorder}`, borderRadius: 7, padding: '6px 10px', outline: 'none', boxSizing: 'border-box' }}
          />
          <button onClick={() => { onCreateCatalog(newCatalogName); setNewCatalogName(''); }} style={{ ...pillBtn(T, true), padding: '6px 14px', fontSize: 11.5 }}>新建 catalog</button>
        </div>
      </div>

      {sections.map(({ num, key, title, source, hint, mono }) => (
        // R-559 Section radius 12 + padding 升级（与 v0.5.21 Card 一致）
        <div key={key} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, marginBottom: 14, overflow: 'hidden' }}>
          {/* R-558 Section header — number chip + title + source neutral tag + override chip + actions 右对齐 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px', borderBottom: `1px solid ${T.border}` }}>
            <NumChip T={T} num={num}/>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: '-0.01em' }}>{title}</div>
            {/* v0.5.29 #27 source neutral tag — demo `<Tag tone="neutral">` byte-equal */}
            <SourceTag T={T}>{source}</SourceTag>
            {catalog.overrides?.[key] && <OverrideChip T={T}/>}
            <div style={{ flex: 1 }}/>
            <div style={{ display: 'flex', gap: 8 }}>
              {catalog.overrides?.[key] && (
                <button onClick={() => onResetCatalogField(key)} style={{ ...pillBtn(T), padding: '4px 10px', fontSize: 11.5 }}>恢复默认</button>
              )}
              {/* R-564 Spinner color hex 偿还 — 白色字面 → T.sendFg（R-484 sustained） */}
              <button onClick={() => onSaveCatalogField(key)} disabled={catalogSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
                {catalogSaving[key] ? <><Spinner size={10} color={T.sendFg}/> 保存中</> : '保存'}
              </button>
            </div>
          </div>
          <div style={{ padding: '12px 18px 6px', fontSize: 11.5, color: T.muted, lineHeight: 1.55 }}>{hint}</div>
          <div style={{ padding: '0 18px 16px' }}>
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
        </div>
      ))}
    </div>
  );
}
