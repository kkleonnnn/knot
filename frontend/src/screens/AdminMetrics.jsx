import { useState, useEffect } from 'react';
import { KpiCard } from '../Shared.jsx';
import { toast, Spinner } from '../utils.jsx';
import { AppShell } from '../Shell.jsx';
import { api } from '../api.js';

// v0.6.1.0 — AdminMetrics 内测健康指标屏（path A 第三步）
// 4 KPI 卡片：一次成功率 / 澄清率 / P95 latency / 总成本
// 复用 v0.5.19 KpiCard + PeriodTab + TagChip pattern（v0.6.x Shared 移植承诺加强）

const PERIOD_LABELS = { '7d': 'last 7 days', '30d': 'last 30 days', '90d': 'last 90 days' };

function PeriodTab({ T, label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      height: 30, padding: '0 12px',
      background: active ? T.accent : 'transparent',
      color: active ? T.sendFg : T.subtext,
      border: `1px solid ${active ? T.accent : T.border}`,
      borderRadius: 8, fontSize: 12.5, fontFamily: 'inherit',
      fontWeight: 500, letterSpacing: '-0.005em', cursor: 'pointer',
      boxShadow: active ? `0 2px 8px color-mix(in oklch, ${T.accent} 20%, transparent)` : 'none',
    }}>{label}</button>
  );
}

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

const fmtPct = (rate) => `${(rate * 100).toFixed(1)}`;
const fmtCost = (usd) => usd < 0.01 ? usd.toFixed(4) : usd.toFixed(2);
const fmtMs = (ms) => ms == null ? '—' : (ms >= 1000 ? `${(ms / 1000).toFixed(1)}` : `${ms}`);
const unitMs = (ms) => ms == null ? '' : (ms >= 1000 ? 's' : 'ms');

export function AdminMetricsScreen({ T, user, onToggleTheme, onNavigate, onLogout }) {
  const [period, setPeriod] = useState('7d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  /* eslint-disable react-hooks/immutability, react-hooks/exhaustive-deps */
  useEffect(() => { load(); }, [period]);
  /* eslint-enable react-hooks/immutability, react-hooks/exhaustive-deps */

  async function load() {
    setLoading(true);
    try {
      setData(await api.get(`/api/admin/metrics?period=${period}`));
    } catch (e) {
      toast(`加载失败: ${e.message}`, true);
    } finally {
      setLoading(false);
    }
  }

  // brandSoft 8% 全站铁律 (v0.5.19 R-480 字面 byte-equal 第七处扩展)
  const insetBg = `color-mix(in oklch, ${T.accent} 8%, transparent)`;
  const insetBorder = `color-mix(in oklch, ${T.accent} 25%, transparent)`;

  // R-481 borderLeft 3px 25% 第四处闭环（与 SavedReports / AdminBudgets / AdminRecovery 字面一致）
  const rulesBorderLeft = `3px solid ${insetBorder}`;

  const rules = [
    { tag: 'success', body: '一次成功率 = presenter 输出 & recovery_attempt=0 的消息数 / 所有 sql_planner 消息（一次跑通无需重试）' },
    { tag: 'clarify', body: '澄清率 = clarifier 终态消息数 / 总消息数（高于 20% 说明用户问题模糊或 prompt 调优空间）' },
    { tag: 'latency', body: 'P95 latency = 95% 请求在此时间内返回（端到端含 LLM + SQL 执行；v0.6.1.0 起新消息开始记录）' },
    { tag: 'cost',    body: '成本 = 期内所有非 legacy 消息的 cost_usd 总和（4 桶 agent_kind 分桶聚合）' },
  ];

  return (
    <AppShell T={T} user={user} active="admin-metrics"
              onToggleTheme={onToggleTheme} onNavigate={onNavigate} onLogout={onLogout}
              topbarTitle="内测指标">
      <div style={{ padding: '24px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>

        {/* 顶栏 — 时段切换 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {['7d', '30d', '90d'].map(p => (
              <PeriodTab key={p} T={T} label={PERIOD_LABELS[p]}
                         active={period === p} onClick={() => setPeriod(p)}/>
            ))}
          </div>
          {data && <TagChip T={T}>{data.total_messages} messages · {PERIOD_LABELS[period]}</TagChip>}
        </div>

        {/* 4 KPI 卡片 grid */}
        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: T.muted }}><Spinner/></div>
        ) : data ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
            <KpiCard T={T} label="一次成功率"
                     value={data.first_try_success.denominator === 0 ? '—' : fmtPct(data.first_try_success.rate)}
                     unit={data.first_try_success.denominator === 0 ? '' : '%'}
                     hint={`${data.first_try_success.numerator} / ${data.first_try_success.denominator} sql_planner`}
                     accent/>
            <KpiCard T={T} label="澄清率"
                     value={data.clarification.denominator === 0 ? '—' : fmtPct(data.clarification.rate)}
                     unit={data.clarification.denominator === 0 ? '' : '%'}
                     hint={`${data.clarification.numerator} / ${data.clarification.denominator} messages`}/>
            <KpiCard T={T} label="P95 latency"
                     value={fmtMs(data.latency_ms.p95)}
                     unit={unitMs(data.latency_ms.p95)}
                     hint={data.latency_ms.sample_size === 0
                       ? '尚无有 latency 数据的消息（v0.6.1.0 起开始记录）'
                       : `P50=${fmtMs(data.latency_ms.p50)}${unitMs(data.latency_ms.p50)} · P99=${fmtMs(data.latency_ms.p99)}${unitMs(data.latency_ms.p99)} · n=${data.latency_ms.sample_size}`}/>
            <KpiCard T={T} label="总成本"
                     value={`$${fmtCost(data.cost_usd.total)}`}
                     hint={`平均 $${fmtCost(data.cost_usd.avg_per_message)} / message`}/>
          </div>
        ) : (
          <div style={{ padding: 40, color: T.muted, textAlign: 'center' }}>尚无数据</div>
        )}

        {/* 指标定义说明 — brandSoft inset + borderLeft 3px 25% */}
        <div style={{
          background: insetBg, border: `1px solid ${insetBorder}`,
          borderLeft: rulesBorderLeft, borderRadius: 8,
          padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <TagChip T={T}>指标定义</TagChip>
          </div>
          {rules.map((r, i) => (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', fontSize: 12.5, lineHeight: 1.55, color: T.text }}>
              <TagChip T={T}>{r.tag}</TagChip>
              <div style={{ flex: 1, minWidth: 0 }}>{r.body}</div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
