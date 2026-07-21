// v0.8.23 — 数据源徽标「已连接」计数（纯函数，可单测；修 v0.8.21 冷启假 0 回归）。
// 从 GET /api/admin/datasources 响应算徽标数字（喂 App.jsx setSourceCount）：
//   非数组（异常响应）           → 1     （沿用原 fallback 语义）
//   online>0                     → online（暖缓存真实数，透传）
//   online===0 且存在 checking    → null  （冷启/混合未探测=未知；Chat/BI 回落 dbOk?1:0）
//   online===0 且无 checking      → 0     （暖缓存全 error / 空列表 = 真 0；诚实显「0 已连接」，不谎报）
// 背景：v0.8.21 列表探测解耦后冷启缓存空→_cached_status 全返 'checking'；旧代码把冷启 0 当确定值→
// 假「0 已连接」，而钝的 `||null` 又把暖缓存真 0 吞成 null→谎报「1」（反向假阳性）。checking-gated 两全。
export function connectedCountForBadge(ds) {
  if (!Array.isArray(ds)) return 1;
  const online = ds.filter(s => s.status === 'online').length;
  if (online > 0) return online;
  return ds.some(s => s.status === 'checking') ? null : 0;
}
