// v0.6.0.2 F1 — MetricCard 子组件抽出（从 ResultBlock.jsx line 404-427 byte-equal）
// v0.4.0 metric intent 渲染大数字卡片（取代 chart+table）
// v0.5.6+ R-156 18 屏 0 修改自动换皮 sustained — 仅依赖 T 25 字段
// v0.6.2.2 A5：复合 metric（numericCols.length > 1）→ 多 stat 网格（R-461 设计语言）
//   R-PB-A5-1：单值路径（numericCols.length <= 1）byte-equal sustained — 下方 _SingleMetric 与
//              v0.6.0.2 抽出版完全一致（仅包一层 dispatch，单值分支代码 0 改）

// 数值格式化（单值 + 多值共用）
function _fmt(value) {
  return (value === null || value === undefined)
    ? '—'
    : (typeof value === 'number' ? value.toLocaleString() : String(value));
}

export function MetricCard({ T, rows, cols, numericCols }) {
  if (!rows || rows.length === 0) return null;
  // v0.6.2.2 A5：复合 metric 多值网格 dispatch（R-PB-A5-1 单值路径不变）
  if (numericCols.length > 1) {
    return <_MultiStatGrid T={T} rows={rows} cols={cols} numericCols={numericCols}/>;
  }
  return <_SingleMetric T={T} rows={rows} cols={cols} numericCols={numericCols}/>;
}

// R-PB-A5-1：单值大数字卡片 — 与 v0.6.0.2 抽出版 byte-equal（_fmt 抽共用不改逻辑）
function _SingleMetric({ T, rows, cols, numericCols }) {
  const r = rows[0];
  const valueCol = numericCols[0] || cols[0];
  const labelCol = cols.find(c => c !== valueCol);
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 22px' }}>
      {labelCol && r[labelCol] !== undefined && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6, letterSpacing: '0.04em',
                      textTransform: 'uppercase' }}>
          {labelCol}: {String(r[labelCol])}
        </div>
      )}
      <div style={{ fontSize: 48, fontWeight: 600, color: T.text, fontFamily: T.mono, lineHeight: 1.1 }}>
        {_fmt(r[valueCol])}
      </div>
      <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{valueCol}</div>
    </div>
  );
}

// v0.6.2.2 A5：复合 metric N stat 网格（v0.5.18 R-461 4-stat grid 设计语言复用）
// NRP-A5-1：auto-fit minmax(160px,1fr) 自适应 — 列数过多自然换行多行（>6 列不拥挤）
// label 用 SQL 列名/别名（中文友好度依赖 F2/F3 sql_planner prompt 中文别名 AS）
function _MultiStatGrid({ T, rows, cols, numericCols }) {
  const r = rows[0];
  const labelCol = cols.find(c => !numericCols.includes(c));  // 非数值列作行级 label（如有）
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 22px' }}>
      {labelCol && r[labelCol] !== undefined && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 14, letterSpacing: '0.04em',
                      textTransform: 'uppercase' }}>
          {labelCol}: {String(r[labelCol])}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
        {numericCols.map(c => (
          <div key={c}>
            <div style={{ fontSize: 28, fontWeight: 600, color: T.text, fontFamily: T.mono, lineHeight: 1.15 }}>
              {_fmt(r[c])}
            </div>
            <div style={{ fontSize: 11.5, color: T.muted, marginTop: 4, letterSpacing: '0.04em',
                          textTransform: 'uppercase' }}>{c}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
