// v0.5.13/14 (C5+) ResultBlock 偿还 + 视觉重构 — R-227.5.1/R-286/R-302.5 字面分流体系
import { useState } from 'react';
import { I, iconBtn, LineChart, BarChart, PieChart } from '../../Shared.jsx';
import { toast } from '../../utils.jsx';
import { api } from '../../api.js';
import { resolveEffectiveHint } from './intent_helpers.js';

// SVG path helper（不依赖 Shared.jsx 36 names — 局部 inline）
const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

const RB_SVG = {
  sparkle:      'M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z',
  search:       'M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0M20 20l-3.5-3.5',
  wrench:       'M14.7 6.3a4 4 0 1 1-5.4 5.4l-5.6 5.6 1.4 1.4 5.6-5.6a4 4 0 0 1 5.4-5.4l-2.8 2.8 1.4 1.4 2.8-2.8z',
  chart:        'M3 20h18M4 16l5-6 4 3 7-8',
  star:         'M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z',
  shield:       'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  triangle:     'M12 3L2 21h20L12 3zM12 10v6M12 18v.01',
  // v0.5.31 #38/#39 — demo thinking.jsx 字面 byte-equal（agent_costs chip icons + 收藏按钮）
  bookmark:     'M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z',
  bulb:         'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9V15h7v-1.1A6 6 0 0 0 12 3z',
  magnify:      'M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0zM15.5 15.5L20 20',
  bars:         'M3 20h18M6 11h3v9h-3zM11 6h3v14h-3zM16 14h3v6h-3z',
  info:         'M12 12m-10 0a10 10 0 1 0 20 0a10 10 0 1 0 -20 0M12 8v4M12 16h.01',
  chevronRight: 'M9 18l6-6-6-6',
  arrowUp:      'M12 19V5M5 12l7-7 7 7',
  arrowDown:    'M12 5v14M19 12l-7 7-7-7',
};

// v0.5.31 #38 — agent_costs chip icons 对齐 demo thinking.jsx L199-202（bulb/magnify/bars byte-equal）
const AGENT_KIND_EMOJI = {
  clarifier:   RB_SVG.bulb,
  sql_planner: RB_SVG.magnify,
  fix_sql:     RB_SVG.wrench,
  presenter:   RB_SVG.bars,
};

const ERROR_KIND_ICONS = {
  budget_exceeded: '🛑', config_missing: '🔧', llm_failed: '🤖',
  sql_invalid: '🚫', sql_exec_failed: '⚠️', data_unavailable: '📡', unknown: '❌',
};
const ERROR_KIND_TITLES = {
  budget_exceeded: '预算超限', config_missing: '配置缺失', llm_failed: 'AI 服务异常',
  sql_invalid: 'SQL 不合规', sql_exec_failed: 'SQL 执行失败',
  data_unavailable: '数据源不可用', unknown: '系统错误',
};

const getErrorKindMeta = (T, kind) => {
  const isCritical = kind === 'budget_exceeded' || kind === 'sql_invalid' || kind === 'unknown';
  const baseColor = isCritical ? T.accent : T.warn;
  return {
    icon: ERROR_KIND_ICONS[kind] || ERROR_KIND_ICONS.unknown,
    title: ERROR_KIND_TITLES[kind] || ERROR_KIND_TITLES.unknown,
    color: baseColor,
    bg: `color-mix(in oklch, ${baseColor} 13%, transparent)`,
  };
};

export function ResultBlock({ T, msg, onCopy, onDownload, onFollowup, onPin, onRetry }) {
  const [sqlOpen, setSqlOpen] = useState(false);
  const [chartType, setChartType] = useState('auto');
  const [pinned, setPinned] = useState(!!msg.is_pinned);
  const { sql, rows, explanation, confidence, error, input_tokens, output_tokens, cost_usd, retry_count, query_time_ms,
          insight, suggested_followups, is_clarification, intent,
          agent_costs, recovery_attempt,
          budget_status, budget_meta,
          error_kind, user_message, is_retryable } = msg;  // v0.4.2 分桶 + 自纠正 / v0.4.3 预算告警 / v0.4.4 错误翻译

  if (is_clarification) {
    return (
      <div style={{ background: T.card, border: `1px solid color-mix(in oklch, ${T.accent} 19%, transparent)`, borderRadius: 10, padding: '14px 16px' }}>
        <div style={{ fontSize: 13, color: T.accent, fontWeight: 500, marginBottom: 4 }}>需要澄清</div>
        <div style={{ fontSize: 13.5, color: T.text, lineHeight: 1.65 }}>{explanation}</div>
        {(input_tokens > 0 || output_tokens > 0) && (
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: T.muted, fontFamily: T.mono, marginTop: 8 }}>
            <span>↑ {input_tokens?.toLocaleString()} tok</span>
            <span>↓ {output_tokens?.toLocaleString()} tok</span>
            {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
          </div>
        )}
      </div>
    );
  }

  if (error && !sql) {
    return (
      <div style={{ background: T.accentSoft, border: `1px solid color-mix(in oklch, ${T.accent} 19%, transparent)`, borderRadius: 10, padding: '13px 16px', color: T.accent, fontSize: 13 }}>
        {error}
      </div>
    );
  }

  const cols = rows && rows.length > 0 ? Object.keys(rows[0]) : [];
  const isNumericCol = (col) => rows && rows.some(r => typeof r[col] === 'number' && r[col] !== null);
  const numericCols = cols.filter(isNumericCol);
  const labelCols = cols.filter(c => !isNumericCol(c));
  const chartable = labelCols.length >= 1 && numericCols.length >= 1 && rows && rows.length >= 2;

  // v0.4.1 R-S4 三级优先级链：display_hint > INTENT_TO_HINT[intent] > inferIntentFromShape
  const layoutHint = resolveEffectiveHint(msg, rows, cols);
  const isMetric = layoutHint === 'metric_card';
  const isDetail = layoutHint === 'detail_table';
  const isRetention = layoutHint === 'retention_matrix';

  const isDateLike = chartable && rows.some(r => /\d{4}[-/年]\d/.test(String(r[labelCols[0]] || '')));
  const intentDefaultType = ({ line: 'line', bar: 'bar', pie: 'pie', rank_view: 'bar' })[layoutHint] || null;
  const autoType = (() => {
    if (intentDefaultType) return intentDefaultType;
    if (!chartable) return 'bar';
    if (isDateLike || rows.length > 12) return 'line';
    if (numericCols.length === 1 && rows.length <= 10) return 'pie';
    return 'bar';
  })();

  const activeType = chartType === 'auto' ? autoType : chartType;
  const showChart = chartable && !isMetric && !isDetail && !isRetention;

  const chartData = chartable
    ? (isDateLike ? [...rows].sort((a, b) => String(a[labelCols[0]]).localeCompare(String(b[labelCols[0]]))) : rows)
        .slice(0, 50).map(r => {
          const pt = { [labelCols[0]]: r[labelCols[0]] };
          numericCols.forEach(c => { pt[c] = r[c]; });
          return pt;
        })
    : [];
  const pieData = chartable
    ? rows.slice(0, 8).map(r => ({ [labelCols[0]]: r[labelCols[0]], [numericCols[0]]: r[numericCols[0]] }))
    : [];

  const chartBtns = [
    { id: 'line', label: '折线' },
    { id: 'bar',  label: '柱状' },
    { id: 'pie',  label: '饼图' },
  ];

  // v0.4.1 ⭐ 收藏按钮（仅当有 sql + msg.id 是真实数字 + 非 saved_report 内嵌渲染）
  const canPin = !!(sql && Number.isInteger(msg.id) && !msg.is_saved_report);

  const handlePin = async () => {
    if (!canPin || pinned || !onPin) return;
    const r = await onPin(msg.id);
    if (r && r.ok) setPinned(true);
  };

  // v0.4.3 R-20 预算 banner（sessionStorage 降噪）
  const yearMonth = new Date().toISOString().slice(0, 7).replace('-', '');  // 'YYYYMM'
  const dismissKey = `budget_warn_${msg.user_id || 'self'}_${yearMonth}`;
  const [budgetDismissed, setBudgetDismissed] = useState(
    () => typeof sessionStorage !== 'undefined' && sessionStorage.getItem(dismissKey) === '1'
  );
  // v0.4.4 R-28：ErrorBanner > BudgetBanner 优先级；budget_exceeded 错误时不再重复显示 BudgetBanner
  const showErrorBanner = !!(error && error_kind);
  const showBudgetBanner = budget_status && budget_status !== 'ok' && !budgetDismissed && budget_meta
                            && !(showErrorBanner && error_kind === 'budget_exceeded');

  // v0.4.4 错误 kind → 视觉映射 (Q1 helper function;R-294 7 kind icon/title byte-equal)
  const errMeta = getErrorKindMeta(T, error_kind);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* v0.4.3 R-20 预算告警 banner（每 user × 月份 sessionStorage 降噪）;R-304 emoji → svg */}
      {showBudgetBanner && (
        <div style={{
          padding: '10px 14px', borderRadius: 8,
          background: budget_status === 'block'
            ? T.accentSoft
            : `color-mix(in oklch, ${T.warn} 13%, transparent)`,
          border: `1px solid ${budget_status === 'block' ? T.accent : T.warn}`,
          color: budget_status === 'block' ? T.accent : T.warn,
          fontSize: 12.5, display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <SvgPath d={budget_status === 'block' ? RB_SVG.shield : RB_SVG.triangle} size={16}/>
          <span style={{ flex: 1 }}>
            {budget_status === 'block' ? '预算已达硬阈值（block）' : '预算告警'}：
            本月已用 <strong>{budget_meta.percentage}%</strong> 配额（${budget_meta.current?.toFixed(4)} / ${budget_meta.threshold?.toFixed(2)} {budget_meta.budget_type}）
          </span>
          <button onClick={() => {
            try { sessionStorage.setItem(dismissKey, '1'); } catch {}
            setBudgetDismissed(true);
          }} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11,
            border: '1px solid currentColor', background: 'transparent', color: 'inherit',
            cursor: 'pointer', fontFamily: 'inherit',
          }}>本会话不再提醒</button>
        </div>
      )}

      {(canPin || explanation) && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          {explanation && (
            <div style={{ flex: 1, fontSize: 13.5, color: T.text, lineHeight: 1.65 }}>{explanation}</div>
          )}
          {canPin && (
            <button onClick={handlePin} disabled={pinned} title={pinned ? '已收藏' : '收藏到报表'}
              style={{
                ...iconBtn(T),
                color: pinned ? T.accent : T.muted,
                cursor: pinned ? 'default' : 'pointer',
              }}>
              {/* v0.5.31 #39 — 收藏按钮 star → bookmark（demo thinking.jsx L82 byte-equal）；
                  fill 双态保留（pinned T.accent / 非 pinned 'none' 描边） */}
              <SvgPath d={RB_SVG.bookmark} size={15} fill={pinned ? T.accent : 'none'}/>
            </button>
          )}
        </div>
      )}
      {/* v0.4.4 ErrorBanner：error_kind 已知时走富视觉；R-302.5 emoji 业务豁免（icon 字段保留） */}
      {error && showErrorBanner && (
        <div style={{
          padding: '10px 14px', borderRadius: 8,
          background: errMeta.bg, border: `1px solid ${errMeta.color}`,
          color: errMeta.color, fontSize: 12.5,
          display: 'flex', alignItems: 'flex-start', gap: 10,
        }}>
          <span style={{ fontSize: 16, lineHeight: 1.2 }}>{errMeta.icon}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 500, marginBottom: 2 }}>{errMeta.title}</div>
            <div style={{ opacity: 0.9 }}>{user_message || error}</div>
          </div>
          {is_retryable && onRetry && (
            <button onClick={() => onRetry(msg.question)} style={{
              padding: '4px 10px', borderRadius: 5, fontSize: 11,
              border: '1px solid currentColor', background: 'transparent', color: 'inherit',
              cursor: 'pointer', fontFamily: 'inherit', flexShrink: 0,
            }}>重试</button>
          )}
        </div>
      )}
      {error && !showErrorBanner && (
        <div style={{ padding: '8px 12px', background: T.accentSoft, borderRadius: 6, color: T.accent, fontSize: 12.5 }}>{error}</div>
      )}

      {rows && rows.length > 0 && isMetric && (
        <MetricCard T={T} rows={rows} cols={cols} numericCols={numericCols}/>
      )}

      {rows && rows.length > 0 && !isMetric && (
        <>
          {showChart && (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 12px 10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 11, color: T.muted, fontFamily: T.mono }}>{labelCols[0]} · {numericCols[0]}</span>
                <div style={{ display: 'flex', gap: 3 }}>
                  {chartBtns.map(btn => (
                    <button key={btn.id} onClick={() => setChartType(btn.id)} style={{
                      padding: '3px 9px', borderRadius: 5, fontSize: 11, fontFamily: 'inherit', cursor: 'pointer',
                      background: activeType === btn.id ? T.accent : 'transparent',
                      color: activeType === btn.id ? T.sendFg : T.muted,
                      border: `1px solid ${activeType === btn.id ? T.accent : T.border}`,
                      transition: 'all .15s',
                    }}>{btn.label}</button>
                  ))}
                </div>
              </div>
              {activeType === 'line' && <LineChart data={chartData} stroke={T.accent} fill labelColor={T.muted} gridColor={T.borderSoft} width={640} height={190}/>}
              {activeType === 'bar'  && <BarChart  data={chartData} color={T.accent} labelColor={T.muted} gridColor={T.borderSoft} width={640} height={210}/>}
              {activeType === 'pie'  && <PieChart  data={pieData} width={640} height={210} labelColor={T.muted}/>}
            </div>
          )}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>{rows.length} 行 · {cols.length} 列</span>
              {isDetail && msg.id
                ? <button onClick={() => exportMessageCsv(msg.id)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="导出 CSV"><I.dl/></button>
                : <button onClick={() => onDownload(rows, msg.question)} style={{ ...iconBtn(T), gap: 4, fontSize: 11 }} title="下载 CSV"><I.dl/></button>}
            </div>
            <div className="cb-sb" style={{ overflowX: 'auto', maxHeight: 280 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                <thead>
                  {/* v0.5.38 全站表头底色 brandSoft 8% → T.bg gray（资深反馈"底色改成灰色"；与 admin 屏一致）*/}
                  <tr style={{ background: T.bg }}>
                    {cols.map(c => <th key={c} style={{ padding: '8px 12px', textAlign: 'left', color: T.muted, fontFamily: T.mono, fontWeight: 500, fontSize: 11, letterSpacing: '0.06em', textTransform: 'uppercase', borderBottom: `1px solid ${T.border}`, whiteSpace: 'nowrap' }}>{c}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 100).map((row, ri) => (
                    <tr key={ri} style={{ borderBottom: ri < rows.length - 1 ? `1px solid ${T.borderSoft}` : 'none' }}>
                      {cols.map(c => <td key={c} style={{ padding: '8px 12px', color: T.text, whiteSpace: 'nowrap', fontFamily: typeof row[c] === 'number' ? T.mono : 'inherit' }}>{row[c] === null || row[c] === undefined ? <span style={{ color: T.muted }}>—</span> : String(row[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {insight && (
        <div style={{
          background: `color-mix(in oklch, ${T.accent} 8%, transparent)`,
          border: `1px solid color-mix(in oklch, ${T.accent} 25%, transparent)`,
          borderRadius: 10, padding: '12px 14px',
          display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
          <span style={{ marginTop: 1, color: T.accent, flexShrink: 0 }}>
            <SvgPath d={RB_SVG.info} size={14}/>
          </span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, fontFamily: T.mono, color: T.accent, fontWeight: 600,
                          letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 4 }}>OBSERVATION</div>
            <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>{insight}</div>
          </div>
        </div>
      )}

      {suggested_followups && suggested_followups.length > 0 && onFollowup && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {suggested_followups.map((q, i) => (
            <button key={i} onClick={() => onFollowup && onFollowup(q)} style={{
              height: 28, padding: '0 12px',
              background: T.content, border: `1px solid ${T.border}`, borderRadius: 14,
              fontSize: 12, color: T.text, cursor: 'pointer', fontFamily: 'inherit',
              display: 'inline-flex', alignItems: 'center', gap: 8, lineHeight: 1,
            }}>
              <span style={{ color: T.accent, display: 'inline-flex', flexShrink: 0 }}>
                <SvgPath d={RB_SVG.chevronRight} size={11}/>
              </span>
              {q}
            </button>
          ))}
        </div>
      )}

      {sql && (
        <div style={{ background: T.codeBg, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
          <div onClick={() => setSqlOpen(!sqlOpen)} style={{
            cursor: 'pointer', padding: '9px 14px', display: 'flex', alignItems: 'center', gap: 8,
            color: T.subtext, fontSize: 12.5,
          }}>
            <I.sql/>
            <span style={{ fontFamily: T.mono, color: T.text }}>{'<>'}</span>
            <span>查看 SQL</span>
            <span style={{ flex: 1, textAlign: 'right', color: T.muted, fontSize: 11, fontFamily: T.mono }}>
              {query_time_ms ? `${query_time_ms}ms` : ''}
              {retry_count > 0 ? ` · ${retry_count}次重试` : ''}
            </span>
            <I.chev style={{ transform: sqlOpen ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}/>
          </div>
          {sqlOpen && (
            <div style={{ position: 'relative', borderTop: `1px solid ${T.border}` }}>
              <button onClick={() => onCopy(sql)} style={{ ...iconBtn(T), position: 'absolute', top: 8, right: 8 }} title="复制"><I.copy/></button>
              <pre style={{ margin: 0, padding: '10px 16px 14px', fontFamily: T.mono, fontSize: 12, lineHeight: 1.65, color: T.codeText, overflowX: 'auto', paddingRight: 40 }}>{sql}</pre>
            </div>
          )}
        </div>
      )}

      {(input_tokens > 0 || output_tokens > 0) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 11, fontFamily: T.mono, color: T.muted, paddingLeft: 2, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <SvgPath d={RB_SVG.arrowUp} size={10}/> {input_tokens?.toLocaleString()} tok
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <SvgPath d={RB_SVG.arrowDown} size={10}/> {output_tokens?.toLocaleString()} tok
          </span>
          {cost_usd > 0 && <span>$ {cost_usd?.toFixed(5)}</span>}
          {confidence && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                           color: confidence === 'high' ? T.success : confidence === 'medium' ? T.warn : T.accent }}>
              <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'currentColor' }}/>
              {confidence}
            </span>
          )}
          {recovery_attempt > 0 && (
            <span title="自纠正次数（fan-out reject + fix_sql retry）"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: T.warn }}>
              ↻ {recovery_attempt}
            </span>
          )}
        </div>
      )}

      {/* v0.4.2 per-agent cost 分桶 chip（R-302 emoji → svg；R-301 hex 兜底 → T.bg） */}
      {agent_costs && Object.values(agent_costs).some(b => b && (b.cost > 0 || b.tokens > 0)) && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 10.5, fontFamily: T.mono }}>
          {Object.entries(agent_costs)
            .filter(([_, b]) => b && (b.cost > 0 || b.tokens > 0))
            .map(([kind, b]) => (
              <span key={kind} title={`${kind}: $${b.cost?.toFixed(5) || 0} / ${b.tokens || 0} tok`}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      height: 24, padding: '0 10px',
                      background: T.bg, border: `1px solid ${T.border}`, borderRadius: 999,
                      fontSize: 11, fontFamily: T.mono, color: T.muted,
                    }}>
                {AGENT_KIND_EMOJI[kind] && (
                  <span style={{ color: T.accent, display: 'inline-flex' }}>
                    <SvgPath d={AGENT_KIND_EMOJI[kind]} size={11}/>
                  </span>
                )}
                {kind}: ${b.cost?.toFixed(5) || '0.00000'}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}

// v0.4.0: metric intent 渲染大数字卡片（取代 chart+table）
function MetricCard({ T, rows, cols, numericCols }) {
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

// v0.4.0: detail intent 服务端 CSV 导出（utf-8-sig BOM, Excel 直开）
async function exportMessageCsv(messageId) {
  try {
    const r = await fetch(`/api/messages/${messageId}/export.csv`, {
      headers: { Authorization: `Bearer ${api._token()}` },
    });
    if (!r.ok) {
      toast(`导出失败: ${r.status}`, true);
      return;
    }
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `export_msg${messageId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (e) {
    toast(`导出失败: ${e.message}`, true);
  }
}
