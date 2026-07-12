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

// v0.8.10/8.11 BI 仪表盘大数值（基准 §5 + kk 迭代）：
//   金额类（kind='money' 或有 unit）→ 万/亿 压缩 + **恒 2 位小数**（无则 .00，point 4）。**不带 ¥**（kk：币种一律 USDT，
//     由 UnitBadge / unit 后缀承载，见 DashboardWidgets.unitMarker）。非 bare 且有 unit → 追加后缀（如 116.21万USDT）；
//     bare / 无 unit → 只返数字（标记由 badge 渲染）。
//   count → **整数千分位**（用户数等）；percentage → ×100+%（fmtPercent，不动）。非数原样。
export function fmtBig(value, kind = 'count', unit = '', bare = false) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (kind === 'percentage') return fmtPercent(n);
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (kind === 'money' || unit) {
    const d2 = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    const suf = bare ? '' : (unit || '');            // 无 ¥；unit 后缀仅非 bare
    const scale = abs >= 1e8 ? [1e8, '亿'] : abs >= 1e4 ? [1e4, '万'] : [1, ''];
    return `${sign}${(abs / scale[0]).toLocaleString(undefined, d2)}${scale[1]}${suf}`;
  }
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });   // count → 整数
}
