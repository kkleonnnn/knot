// v0.5.3: extracted from Chat.jsx L7-37 (intent → layout 映射 + 老消息形态推断)
// v0.4.0: Clarifier 输出的 7 类 intent → 前端 layout（与后端 INTENT_TO_HINT 一一对应）
export const INTENT_TO_HINT = {
  metric: 'metric_card',
  trend: 'line',
  compare: 'bar',
  rank: 'rank_view',
  distribution: 'pie',
  retention: 'retention_matrix',
  detail: 'detail_table',
};

// v0.4.0 老消息（无 intent 字段）兼容降级：从 rows/cols 形态推断意图
export function inferIntentFromShape(rows, cols) {
  if (!rows || rows.length === 0) return 'detail';
  if (rows.length === 1) return 'metric';  // 单行（不论几列）作 metric
  if (cols.some(c => /\d{4}[-/年]/.test(String(rows[0][c])))) return 'trend';
  if (cols.length >= 4) return 'detail';
  const idLikeCols = cols.filter(c => /(_id|^id)$/i.test(c));
  if (idLikeCols.length > 0 && cols.length <= 3) return 'detail';
  return 'rank';
}

// v0.4.1 R-S4 effectiveHint 三级优先级链：
//   1. msg.display_hint  — saved_report 快照（v0.4.1 SavedReportView 注入）
//   2. INTENT_TO_HINT[msg.intent] — v0.4.0 message + 当前 mapping
//   3. INTENT_TO_HINT[inferIntentFromShape(...)] — v0.4.0 之前老消息启发式
export function resolveEffectiveHint(msg, rows, cols) {
  if (msg.display_hint) return msg.display_hint;
  if (msg.intent && INTENT_TO_HINT[msg.intent]) return INTENT_TO_HINT[msg.intent];
  return INTENT_TO_HINT[inferIntentFromShape(rows, cols)] || 'detail_table';
}
