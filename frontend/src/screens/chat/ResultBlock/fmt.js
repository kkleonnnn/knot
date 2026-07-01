// v0.7.25 D2 — 共享值格式化（MetricCard 大数字 + TableContainer cell）
// R1 承重约定：unit='percentage' 假设**值是 0-1 小数**（÷派生费率如 fee/volume=0.000486 → ×100=0.0486%）；
//   严禁设在 caliber 已返百分数的 metric 上（×100 双缩放）—— admin UI hint + content 补录前置守。

// percentage：值 ×100 + %（R2 note：maxFractionDigits 4 是舍入移位，sub-0.0001% 极小费率仍可能舍向 0%）。
export function fmtPercent(value) {
  return (value * 100).toLocaleString(undefined, { maximumFractionDigits: 4 }) + '%';
}

// MetricCard 大数字：**非-percentage 完整 subsume 原 _fmt 逻辑 byte-equal**（守护者 R3）
//   null/undefined→'—' + number→toLocaleString() + else→String；percentage(number) → fmtPercent。
export function fmtValue(value, unit) {
  if (value === null || value === undefined) return '—';
  if (unit === 'percentage' && typeof value === 'number') return fmtPercent(value);
  return typeof value === 'number' ? value.toLocaleString() : String(value);
}
