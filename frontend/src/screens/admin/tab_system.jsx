// v0.5.3: extracted from Admin.jsx L516-561 (Catalog tab JSX)
// D4 mapping: System (Catalog) — 系统与治理（Audit / Recovery 是独立页面 AdminAudit.jsx / AdminRecovery.jsx）
import { pillBtn } from '../../Shared.jsx';
import { Spinner } from '../../utils.jsx';

export function TabSystem({ T, catalog, setCatalog, catalogSaving, onSaveCatalogField, onResetCatalogField }) {
  return (
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
                <button onClick={() => onResetCatalogField(key)} style={{ ...pillBtn(T), padding: '4px 10px', fontSize: 11.5 }}>恢复默认</button>
              )}
              <button onClick={() => onSaveCatalogField(key)} disabled={catalogSaving[key]} style={{ ...pillBtn(T, true), padding: '4px 10px', fontSize: 11.5 }}>
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
  );
}
