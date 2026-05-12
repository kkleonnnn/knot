import { useState, useEffect } from 'react';
import { I, LineChart } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.4.3: AdminRecovery — System_Recovery 趋势（R-19 已 baked into backend：过滤 legacy）
// v0.5.19 视觉重构：Inset 8% 闭环第六处铁律加冕 (R-480) / borderLeft 25% 第三处闭环 (R-481)
// admin 顶层屏三部曲收官 (v0.5.17 Audit + v0.5.18 Budgets + v0.5.19 Recovery)

const PERIOD_LABELS = { '7d': 'last 7 days', '30d': 'last 30 days', '90d': 'last 90 days' };

// R-473/R-491 KpiCard inline helper — transition color 0.2s 动效（v0.6 候选移入 Shared）
function KpiCard({ T, label, value, unit, hint, accent }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: '18px 20px',
      display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0,
    }}>
      <div style={{ fontSize: 12, color: T.muted, letterSpacing: '0.01em' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <div style={{
          fontSize: 34, fontWeight: 700, letterSpacing: '-0.02em',
          color: accent ? T.accent : T.text,
          fontFamily: T.sans, lineHeight: 1.05,
          transition: 'color 0.2s',
        }}>{value}</div>
        {unit && <div style={{ fontSize: 14, color: T.muted, fontWeight: 500 }}>{unit}</div>}
      </div>
      <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, letterSpacing: '0.02em' }}>{hint}</div>
    </div>
  );
}

// R-472/R-492 PeriodTab inline helper — active box-shadow color-mix 20% 选中浮起感（v0.6 候选移入 Shared）
function PeriodTab({ T, label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      height: 30, padding: '0 14px',
      background: active ? T.accent : 'transparent',
      color: active ? T.sendFg : T.muted,
      border: `1px solid ${active ? T.accent : T.border}`,
      borderRadius: 6, fontSize: 12, fontFamily: T.mono,
      fontWeight: 500, cursor: 'pointer',
      boxShadow: active ? `0 2px 8px color-mix(in oklch, ${T.accent} 20%, transparent)` : 'none',
    }}>{label}</button>
  );
}

// R-447 TagChip inline helper — uppercase mono brandSoft 12%（局部内嵌）
function TagChip({ T, children }) {
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 4,
      background: `color-mix(in oklch, ${T.accent} 12%, transparent)`,
      color: T.accent,
      fontSize: 11, fontWeight: 500, fontFamily: T.mono,
      flexShrink: 0, textTransform: 'uppercase', letterSpacing: '0.02em',
    }}>{children}</span>
  );
}

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

  // v0.5.38 — 返回对话 button 移除（Shell.jsx 全屏底部统一渲染）
  const sidebarContent = null;

  // R-447 Rules note 2 条 — brandSoft inset + R-481 borderLeft 3px 25%
  const rules = [
    { tag: 'R-19', body: '本趋势已过滤 v0.4.2 之前的 legacy 历史数据（agent_kind != \'legacy\'），曲线仅含 v0.4.2 起的真实自纠正数据' },
    { tag: '数据源', body: 'messages.recovery_attempt 列（v0.4.2 引入），含 fan-out reject + fix_sql retry' },
  ];

  // v0.5.38 — PeriodTab 字体统一（fontFamily inherit T.sans + fontSize 12.5 + 与 Audit CSV button 一致风格）
  const periodTabs = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, fontFamily: 'inherit', color: T.muted }}>
      <span style={{ marginRight: 4 }}>时段</span>
      {['7d', '30d', '90d'].map(p => (
        <PeriodTab key={p} T={T} label={p} active={period === p} onClick={() => setPeriod(p)}/>
      ))}
    </div>
  );

  return (
    <AppShell T={T} user={user} active="admin-recovery" sidebarContent={sidebarContent}
              topbarTitle="System Recovery 趋势" onToggleTheme={onToggleTheme}
              topbarTrailing={periodTabs}
              onNavigate={onNavigate} onLogout={onLogout}>
      <div style={{ padding: '20px 28px 24px', overflowY: 'auto', flex: 1 }} className="cb-sb">
        {/* v0.5.33 — maxWidth 960 → 1200（与 demo recovery.jsx chartW 1140 接近）；删除原 inline period tabs（已移至 topbar） */}
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spinner size={24} color={T.accent}/></div>
          ) : stats && (
            <>
              {/* R-473 KPI 3 cards grid — auto-fit R-394 sustained + R-491 transition */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                <KpiCard T={T} label="自纠正总次数"
                         value={stats.total_recovery_attempts}
                         hint={`过滤 legacy 后 ${stats.period_days}d`}/>
                <KpiCard T={T} label="覆盖消息数"
                         value={stats.total_messages}
                         hint="参与统计的非 legacy 消息"/>
                {/* R-474 第 3 卡 accent — T.accent + fontWeight 700 + 34px */}
                <KpiCard T={T} label="自纠正率"
                         value={stats.total_messages > 0
                           ? (stats.total_recovery_attempts / stats.total_messages * 100).toFixed(1)
                           : '—'}
                         unit={stats.total_messages > 0 ? '%' : null}
                         hint="自纠正次数 / 总消息"
                         accent/>
              </div>

              {/* R-475 Chart card — svg chart icon header + Q1 动态 Tag chip + R-476 LineChart byte-equal + R-494 height=280 */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: '16px 18px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={T.accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 17 9 11 13 15 21 7"/>
                    <polyline points="14 7 21 7 21 14"/>
                  </svg>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>每日自纠正次数趋势</div>
                  <div style={{ flex: 1 }}/>
                  <TagChip T={T}>{PERIOD_LABELS[period]}</TagChip>
                </div>
                {stats.by_day.length === 0 ? (
                  <div style={{ color: T.muted, fontSize: 12, padding: 16, textAlign: 'center' }}>
                    所选时段内无数据（可能只有 legacy 历史，已被 R-19 过滤）
                  </div>
                ) : (
                  <LineChart
                    data={stats.by_day.map(d => ({ date: d.date.slice(5), count: d.count }))}
                    stroke={T.accent} fill labelColor={T.muted}
                    gridColor={T.borderSoft} width={1100} height={240}
                  />
                )}
              </div>

              {/* R-477 Top user table — HTML 全删 → CSS Grid 5-col */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
                {/* R-478 Top user header — Q2 VRP 局部例外 inline trophy svg + Tag chip */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '14px 18px', borderBottom: `1px solid ${T.border}` }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" style={{ color: T.accent, flexShrink: 0 }}>
                    <circle cx="12" cy="8" r="6"/>
                    <path d="M8.21 13.89L7 23l5-3 5 3-1.21-9.12"/>
                  </svg>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>高频自纠正用户</div>
                  <TagChip T={T}>top {stats.top_users.length}</TagChip>
                </div>
                {stats.top_users.length === 0 ? (
                  <div style={{ color: T.muted, fontSize: 12, padding: 24, textAlign: 'center' }}>
                    暂无任何用户触发自纠正
                  </div>
                ) : (
                  <>
                    {/* v0.5.38 thead bg brandSoft 8% → T.bg gray + color T.subtext → T.muted（资深反馈"底色改成灰色 + 字体统一"）*/}
                    <div style={{
                      display: 'grid', gridTemplateColumns: '64px 1.4fr 1fr 1fr 1fr',
                      padding: '8px 18px',
                      background: T.bg,
                      borderBottom: `1px solid ${T.border}`,
                      fontSize: 11, color: T.muted, fontFamily: T.mono,
                      fontWeight: 500, letterSpacing: '0.06em', textTransform: 'uppercase',
                    }}>
                      <span>#</span><span>User</span><span>自纠正次数</span><span>消息数</span><span>自纠正率</span>
                    </div>
                    {stats.top_users.map((u, i) => {
                      // R-493 NaN 守护 — msg_count === 0 边界
                      const rate = u.msg_count ? ((u.count / u.msg_count) * 100).toFixed(1) + '%' : '0.0%';
                      return (
                        <div key={u.user_id} style={{
                          display: 'grid', gridTemplateColumns: '64px 1.4fr 1fr 1fr 1fr',
                          padding: '11px 18px', alignItems: 'center', fontSize: 12.5,
                          borderBottom: i === stats.top_users.length - 1 ? 'none' : `1px solid ${T.borderSoft}`,
                        }}>
                          {/* R-479 rank # mono T.accent fontWeight 600 */}
                          <span style={{ fontFamily: T.mono, color: T.accent, fontWeight: 600 }}>{String(i + 1).padStart(2, '0')}</span>
                          {/* R-479 Avatar 22 brandSoft 8% (R-480 闭环本文件第二处命中) + username + id mono muted */}
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0, overflow: 'hidden' }}>
                            <span style={{
                              width: 22, height: 22, borderRadius: '50%',
                              background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
                              color: T.accent, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 10.5, fontWeight: 600, flexShrink: 0,
                            }}>{(u.username || 'U').charAt(0).toUpperCase()}</span>
                            <span style={{ fontWeight: 500, color: T.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.username}</span>
                            <span style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, flexShrink: 0 }}>id={u.user_id}</span>
                          </span>
                          <span style={{ fontFamily: T.mono, color: T.text }}>{u.count}</span>
                          <span style={{ fontFamily: T.mono, color: T.text }}>{u.msg_count}</span>
                          {/* R-493 rate NaN 守护 + accent color 强调 */}
                          <span style={{ fontFamily: T.mono, color: T.accent, fontWeight: 600 }}>{rate}</span>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>

              {/* v0.5.33 — Rules note 改 demo recovery.jsx L161-172 byte-equal：删 brandSoft 8% bg + borderLeft 3px → 2px brandSoftBorder（更 subtle，对齐资深"深色边边"反馈方向） */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                {rules.map((n, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '10px 14px',
                    borderLeft: `2px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
                    fontSize: 12, color: T.subtext, lineHeight: 1.55,
                  }}>
                    <TagChip T={T}>{n.tag}</TagChip>
                    <span>{n.body}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
