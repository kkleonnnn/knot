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

// v0.8.10 BI 仪表盘大数值（基准 §5）：kind='money' → ¥ + 万/亿（≥1亿 保 1-2 位小数、≥1万 <100万带1位否则整数千分位）；
//   'percentage' → ×100+%；否则（'count'）→ 千分位。非数原样。
export function fmtBig(value, kind = 'count') {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (kind === 'percentage') return fmtPercent(n);
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (kind === 'money') {
    if (abs >= 1e8) return `${sign}¥${(abs / 1e8).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })}亿`;
    if (abs >= 1e4) {
      const wan = abs / 1e4;
      return `${sign}¥${wan < 100 ? wan.toLocaleString(undefined, { maximumFractionDigits: 1 }) : Math.round(wan).toLocaleString()}万`;
    }
    return `${sign}¥${abs.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });   // count 千分位
}
