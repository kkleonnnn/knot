import { useState, useEffect } from 'react';
import { I, LineChart } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.3: AdminRecovery — System_Recovery 趋势（R-19 已 baked into backend：过滤 legacy）
export function AdminRecoveryScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [period, setPeriod] = useState('30d');
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, [period]);

  async function load() {
    setLoading(true);
    try {
      setStats(await api.get(`/api/admin/recovery-stats?period=${period}`));
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  const sidebarContent = (
    <button onClick={() => onNavigate('chat')} style={{
      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
      padding: '9px 10px', borderRadius: 8, background: 'transparent',
      color: T.muted, border: `1px solid ${T.border}`,
      fontFamily: 'inherit', fontSize: 13, cursor: 'pointer', marginBottom: 8,
    }}>
      <I.chev style={{ transform: 'rotate(90deg)' }}/> 返回对话
    </button>
  );

  return (
    <AppShell T={T} user={user} active="admin-recovery" sidebarContent={sidebarContent}
              topbarTitle="🛡️ System Recovery 趋势" onToggleTheme={onToggleTheme}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>

          {/* 时段切换 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12.5, color: T.muted }}>时段：</span>
            {['7d', '30d', '90d'].map(p => (
              <button key={p} onClick={() => setPeriod(p)} style={{
                padding: '5px 12px', borderRadius: 5, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer',
                background: period === p ? T.accent : 'transparent',
                color: period === p ? '#fff' : T.muted,
                border: `1px solid ${period === p ? T.accent : T.border}`,
              }}>{p}</button>
            ))}
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : stats && (
            <>
              {/* 概览卡片 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <StatCard T={T} label="自纠正总次数" value={stats.total_recovery_attempts}
                          hint={`(过滤 legacy 后 ${stats.period_days}d）`}/>
                <StatCard T={T} label="覆盖消息" value={stats.total_messages}
                          hint="参与统计的非 legacy 消息"/>
                <StatCard T={T} label="自纠正率"
                          value={stats.total_messages > 0
                            ? `${(stats.total_recovery_attempts / stats.total_messages * 100).toFixed(1)}%`
                            : '—'}
                          hint="自纠正次数 / 总消息"/>
              </div>

              {/* by_day 折线 */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: 16 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: T.text, marginBottom: 8 }}>
                  📈 每日自纠正次数趋势
                </div>
                {stats.by_day.length === 0 ? (
                  <div style={{ color: T.muted, fontSize: 12, padding: 16, textAlign: 'center' }}>
                    所选时段内无数据（可能只有 legacy 历史，已被 R-19 过滤）
                  </div>
                ) : (
                  <LineChart
                    data={stats.by_day.map(d => ({ date: d.date.slice(5), count: d.count }))}
                    stroke={T.accent} fill labelColor={T.muted}
                    gridColor={T.borderSoft} width={880} height={200}
                  />
                )}
              </div>

              {/* top_users 表格 */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
                              fontSize: 13, fontWeight: 500, color: T.text }}>
                  🏆 高频自纠正用户 Top {stats.top_users.length}
                </div>
                {stats.top_users.length === 0 ? (
                  <div style={{ color: T.muted, fontSize: 12, padding: 24, textAlign: 'center' }}>
                    暂无任何用户触发自纠正
                  </div>
                ) : (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                    <thead>
                      <tr style={{ background: T.bg }}>
                        {['User', '自纠正次数', '消息数', '自纠正率'].map(c =>
                          <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted,
                                                fontWeight: 600, fontSize: 11, letterSpacing: '0.03em',
                                                textTransform: 'uppercase', borderBottom: `1px solid ${T.border}` }}>{c}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {stats.top_users.map(u => (
                        <tr key={u.user_id} style={{ borderBottom: `1px solid ${T.borderSoft}` }}>
                          <td style={cellStyle(T)}>{u.username} <span style={{ color: T.muted, fontSize: 11 }}>(id={u.user_id})</span></td>
                          <td style={{ ...cellStyle(T), fontFamily: T.mono }}>{u.count}</td>
                          <td style={{ ...cellStyle(T), fontFamily: T.mono }}>{u.msg_count}</td>
                          <td style={{ ...cellStyle(T), fontFamily: T.mono }}>
                            {u.msg_count > 0 ? `${(u.count / u.msg_count * 100).toFixed(1)}%` : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div style={{ fontSize: 11, color: T.muted, lineHeight: 1.6 }}>
                <p>📌 <b>R-19 守护</b>：本趋势已过滤 v0.4.2 之前的 legacy 历史数据（agent_kind != 'legacy'），曲线仅含 v0.4.2 起的真实自纠正数据</p>
                <p>📌 数据源：messages.recovery_attempt 列（v0.4.2 引入），含 fan-out reject + fix_sql retry</p>
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function StatCard({ T, label, value, hint }) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '14px 16px' }}>
      <div style={{ fontSize: 11, color: T.muted, marginBottom: 4, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 600, color: T.text, fontFamily: T.mono, lineHeight: 1.1 }}>{value}</div>
      <div style={{ fontSize: 11, color: T.muted, marginTop: 4 }}>{hint}</div>
    </div>
  );
}

function cellStyle(T) {
  return { padding: '8px 12px', color: T.text, whiteSpace: 'nowrap' };
}
