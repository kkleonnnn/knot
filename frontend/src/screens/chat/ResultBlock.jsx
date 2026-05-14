// v0.6.0.2 — ResultBlock 主文件瘦身（449 → ~250 行 / v0.5.14 R-341 承诺偿还）
// 6 子组件抽出到 chat/ResultBlock/* — 主文件仅 layout 调度 + intent 分支 + import
// v0.5.13/14/15 字面分流体系 sustained — R-227.5/R-227.5.1/R-302.5/R-323/R-325/R-327
import { useState } from 'react';
import { I, iconBtn } from '../../Shared.jsx';
import { toast } from '../../utils.jsx';
import { api } from '../../api.js';
import { resolveEffectiveHint } from './intent_helpers.js';
import { MetricCard } from './ResultBlock/MetricCard.jsx';
import { InsightCard } from './ResultBlock/InsightCard.jsx';
import { BudgetBanner } from './ResultBlock/BudgetBanner.jsx';
import { ErrorBanner } from './ResultBlock/ErrorBanner.jsx';
import { TokenMeter } from './ResultBlock/TokenMeter.jsx';
import { TableContainer } from './ResultBlock/TableContainer.jsx';

// SVG path helper（不依赖 Shared.jsx 36 names — 局部 inline；agent_costs chips + bookmark 用）
const SvgPath = ({ d, size = 14, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor"
       strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);

// 主文件残留 RB_SVG —  bookmark（收藏按钮）+ agent_costs chip icons
// 拆分后子组件各自含独立 path 字面 — 主文件保留这 5 个
const RB_SVG = {
  bookmark:     'M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z',
  bulb:         'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9V15h7v-1.1A6 6 0 0 0 12 3z',
  magnify:      'M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0zM15.5 15.5L20 20',
  wrench:       'M14.7 6.3a4 4 0 1 1-5.4 5.4l-5.6 5.6 1.4 1.4 5.6-5.6a4 4 0 0 1 5.4-5.4l-2.8 2.8 1.4 1.4 2.8-2.8z',
  bars:         'M3 20h18M6 11h3v9h-3zM11 6h3v14h-3zM16 14h3v6h-3z',
};

// v0.5.31 #38 — agent_costs chip icons 对齐 demo thinking.jsx L199-202（bulb/magnify/bars byte-equal）
const AGENT_KIND_EMOJI = {
  clarifier:   RB_SVG.bulb,
  sql_planner: RB_SVG.magnify,
  fix_sql:     RB_SVG.wrench,
  presenter:   RB_SVG.bars,
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

  const handleBudgetDismiss = () => {
    try { sessionStorage.setItem(dismissKey, '1'); } catch {}
    setBudgetDismissed(true);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {showBudgetBanner && (
        <BudgetBanner T={T} budget_status={budget_status} budget_meta={budget_meta} onDismiss={handleBudgetDismiss}/>
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
              {/* v0.5.31 #39 — 收藏按钮 bookmark（demo thinking.jsx L82 byte-equal）；
                  fill 双态保留（pinned T.accent / 非 pinned 'none' 描边） */}
              <SvgPath d={RB_SVG.bookmark} size={15} fill={pinned ? T.accent : 'none'}/>
            </button>
          )}
        </div>
      )}

      {/* v0.4.4 ErrorBanner：error_kind 已知时走富视觉；R-302.5 emoji 业务豁免（icon 字段保留） */}
      {error && showErrorBanner && (
        <ErrorBanner T={T} error={error} error_kind={error_kind} user_message={user_message}
                     is_retryable={is_retryable} onRetry={onRetry} question={msg.question}/>
      )}
      {error && !showErrorBanner && (
        <div style={{ padding: '8px 12px', background: T.accentSoft, borderRadius: 6, color: T.accent, fontSize: 12.5 }}>{error}</div>
      )}

      {rows && rows.length > 0 && isMetric && (
        <MetricCard T={T} rows={rows} cols={cols} numericCols={numericCols}/>
      )}

      {rows && rows.length > 0 && !isMetric && (
        <TableContainer
          T={T} rows={rows} cols={cols} labelCols={labelCols} numericCols={numericCols}
          chartable={chartable} isMetric={isMetric} isDetail={isDetail} isRetention={isRetention}
          showChart={showChart} chartData={chartData} pieData={pieData}
          chartType={chartType} setChartType={setChartType} activeType={activeType}
          isDateLike={isDateLike} msg={msg} onDownload={onDownload} exportMessageCsv={exportMessageCsv}
        />
      )}

      <InsightCard T={T} insight={insight}/>

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
                <SvgPath d="M9 18l6-6-6-6" size={11}/>
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

      <TokenMeter T={T} input_tokens={input_tokens} output_tokens={output_tokens}
                  cost_usd={cost_usd} confidence={confidence} recovery_attempt={recovery_attempt}/>

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
