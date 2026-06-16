import { FilterField, inputStyleField, ghostBtnStyle, primaryBtnStyle } from '../../Shared.jsx';

// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）
// v0.5.32 Filter strip 对齐 demo audit.jsx L69-92 — 时段 dropdown + 单短标签 + 横向 flex
export function AuditFilterStrip({ T, filter, setFilter, onReset, onQuery }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '14px 18px',
      display: 'flex', alignItems: 'flex-end', gap: 12, flexWrap: 'wrap',
    }}>
      <FilterField T={T} label="时段">
        <select value={filter.sincePreset} onChange={e => setFilter({...filter, sincePreset: e.target.value})}
                style={inputStyleField(T)}>
          <option value="">全部</option>
          <option value="24h">最近 24h</option>
          <option value="7d">最近 7 天</option>
          <option value="30d">最近 30 天</option>
        </select>
      </FilterField>
      <FilterField T={T} label="用户 ID">
        <input value={filter.actor_id} onChange={e => setFilter({...filter, actor_id: e.target.value})}
               placeholder="数字 ID..." style={inputStyleField(T)}/>
      </FilterField>
      <FilterField T={T} label="动作">
        <input value={filter.action} onChange={e => setFilter({...filter, action: e.target.value})}
               placeholder="如 auth.login" style={inputStyleField(T)}/>
      </FilterField>
      <FilterField T={T} label="资源关键词">
        <input value={filter.resource_type} onChange={e => setFilter({...filter, resource_type: e.target.value})}
               placeholder="如 user / budget" style={inputStyleField(T)}/>
      </FilterField>
      <div style={{ flex: 1, minWidth: 0 }}/>
      <button onClick={onReset} style={ghostBtnStyle(T)}>重置</button>
      <button onClick={onQuery} style={primaryBtnStyle(T)}>查询</button>
    </div>
  );
}
