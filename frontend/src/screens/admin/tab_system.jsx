// v0.5.3: extracted from Admin.jsx L516-561 (Catalog tab JSX)
// D4 mapping: System (Catalog) — 系统与治理（Audit / Recovery 是独立页面 AdminAudit.jsx / AdminRecovery.jsx）
// v0.5.22: 视觉重构 — Inset 8% 闭环第九处扩张（7→8 文件）+ borderLeft 25% 第四处闭环 + 蓝色 hex 双残留偿还
import { pillBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

// R-557 Section number chip — 22×22 brandSoft 8% + T.accent + mono + fontWeight 600 + 01/02/03（v0.6 候选移入 Shared）
function NumChip({ T, num }) {
  return (
    <span style={{
      width: 22, height: 22, borderRadius: 5,
      background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
      color: T.accent,
      fontSize: 11, fontFamily: T.mono, fontWeight: 600,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      letterSpacing: '0.04em', flexShrink: 0,
    }}>{num}</span>
  );
}

// R-560/R-566/R-567 OverrideChip — hex 双残留偿还（v0.5.x 蓝色 hex 唯一残留正式清零）
function OverrideChip({ T }) {
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 999,
      background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
      color: T.accent,
      fontSize: 10.5, fontWeight: 600,
      fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.02em',
    }}>DB 覆盖中</span>
  );
}

// v0.5.29 #27 SourceTag — section 标题后的源标识（demo `<Tag tone="neutral">` byte-equal）
// neutral 风格：T.bg bg + T.subtext color + T.mono uppercase；与 brand OverrideChip 视觉分离
function SourceTag({ T, children }) {
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 4,
      background: T.bg, color: T.subtext,
      fontSize: 10.5, fontWeight: 500,
      fontFamily: T.mono, textTransform: 'uppercase', letterSpacing: '0.04em',
      border: `1px solid ${T.border}`,
    }}>{children}</span>
  );
}

export function TabSystem({ T, catalog, setCatalog, catalogSaving, onSaveCatalogField, onResetCatalogField }) {
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
          业务目录注入到 schema 检索 + 3 个 Agent prompt。优先级：DB（本面板编辑）→ 仓库 ohx_catalog.py（部署方填）→ ohx_catalog.example.py（仓库默认）。
          当前生效来源：<b style={{ color: T.text }}>{catalog.source || '...'}</b>。任一字段保存即覆盖默认；点"恢复默认"清空 DB 覆盖。
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
