// v0.6.0.2 F1 — MetricCard 子组件抽出（从 ResultBlock.jsx line 404-427 byte-equal）
// v0.4.0 metric intent 渲染大数字卡片（取代 chart+table）
// v0.5.6+ R-156 18 屏 0 修改自动换皮 sustained — 仅依赖 T 25 字段
export function MetricCard({ T, rows, cols, numericCols }) {
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  const valueCol = numericCols[0] || cols[0];
  const labelCol = cols.find(c => c !== valueCol);
  const value = r[valueCol];
  const display = (value === null || value === undefined)
    ? '—'
    : (typeof value === 'number' ? value.toLocaleString() : String(value));
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 22px' }}>
      {labelCol && r[labelCol] !== undefined && (
        <div style={{ fontSize: 11.5, color: T.muted, marginBottom: 6, letterSpacing: '0.04em',
                      textTransform: 'uppercase' }}>
          {labelCol}: {String(r[labelCol])}
        </div>
      )}
      <div style={{ fontSize: 48, fontWeight: 600, color: T.text, fontFamily: T.mono, lineHeight: 1.1 }}>
        {display}
      </div>
      <div style={{ fontSize: 12, color: T.muted, marginTop: 4 }}>{valueCol}</div>
    </div>
  );
}
