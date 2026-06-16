import { statCardStyle, statValueStyle, statLabelStyle } from '../../Shared.jsx';

// v0.6.3.2 C5 — AdminAudit 子组件拆分（dumb presentational）
// v0.5.40 Stat 4-card grid — 真数据 from /api/admin/audit-stats（{total, today, failed, distinct_users}）
export function AuditStatGrid({ T, stats }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
      <div style={statCardStyle(T)}>
        <span style={statLabelStyle(T, 10.5)}>总记录数</span>
        <span style={statValueStyle(T)}>{stats ? stats.total.toLocaleString() : '—'}</span>
      </div>
      <div style={statCardStyle(T)}>
        <span style={statLabelStyle(T, 10.5)}>今日</span>
        <span style={statValueStyle(T)}>{stats ? stats.today.toLocaleString() : '—'}</span>
      </div>
      <div style={statCardStyle(T)}>
        <span style={statLabelStyle(T, 10.5)}>失败数</span>
        <span style={{ ...statValueStyle(T), color: stats && stats.failed > 0 ? T.warn : T.text }}>
          {stats ? stats.failed.toLocaleString() : '—'}
        </span>
      </div>
      <div style={statCardStyle(T)}>
        <span style={statLabelStyle(T, 10.5)}>涉及用户</span>
        <span style={statValueStyle(T)}>{stats ? stats.distinct_users.toLocaleString() : '—'}</span>
      </div>
    </div>
  );
}
