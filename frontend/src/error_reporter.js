// v0.6.0.4 F-B — 前端 JS 错误自动上报
// 装在 main.jsx 入口；window.onerror + onunhandledrejection 全局捕获
//
// M-B1 throttle 算法（守护者立约）：
//   - dedupe by hash(stack first 10 lines + message)
//   - 1 个 hash 1 小时内仅上报 1 次（localStorage 持久）
//   - 全局任意 hash 1 分钟内 ≤ 5 次（内存 ring）
//   - 防爆：单页 lifetime 最多 50 次上报兜底

const STORAGE_KEY = 'knot_err_seen';     // hash → last_ts ms
const COOLDOWN_MS = 60 * 60 * 1000;      // 1h per hash
const WINDOW_MS = 60 * 1000;             // 1min global
const WINDOW_CAP = 5;                    // 全局 5/min
const LIFETIME_CAP = 50;                 // 单页 50 次兜底

const _windowTimes = [];                 // 最近 1min 上报时间戳
let _lifetimeCount = 0;

function _hashStr(s) {
  // 简单 32-bit hash（djb2）；不是密码学 hash，足够 dedupe
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return (h >>> 0).toString(36);
}

function _computeHash(message, stack) {
  const head = (stack || '').split('\n').slice(0, 10).join('\n');
  return _hashStr((message || '') + '|' + head);
}

function _shouldReport(hash) {
  if (_lifetimeCount >= LIFETIME_CAP) return false;
  // 全局 1min cap
  const now = Date.now();
  while (_windowTimes.length && now - _windowTimes[0] > WINDOW_MS) _windowTimes.shift();
  if (_windowTimes.length >= WINDOW_CAP) return false;
  // hash 1h cooldown
  try {
    const seen = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    if (seen[hash] && now - seen[hash] < COOLDOWN_MS) return false;
    seen[hash] = now;
    // 清理超过 1h 的旧 hash，控制 localStorage 大小
    for (const k of Object.keys(seen)) {
      if (now - seen[k] > COOLDOWN_MS) delete seen[k];
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
  } catch { /* localStorage 满或被禁用 — 不阻止上报 */ }
  _windowTimes.push(now);
  _lifetimeCount++;
  return true;
}

async function _post(payload) {
  try {
    const token = localStorage.getItem('cb_token');
    if (!token) return;  // 未登录不上报（POST 需 user token）
    await fetch('/api/frontend-errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
  } catch { /* 上报失败 silent — 防 reporter 自己抛错套娃 */ }
}

// v0.7.33 (B1.1): 公共上报入口 —— 复用 _computeHash/_shouldReport/_post 节流去重 pipeline（M-B1 契约）；
// window handlers + ErrorBoundary.componentDidCatch 共用。hash 输入由 caller 决定（保各路径上报 byte-equal）。
export function reportError(message, stack) {
  const hash = _computeHash(message, stack);
  if (!_shouldReport(hash)) return;
  _post({
    message: (message || 'unknown').slice(0, 2000),
    stack: (stack || '').slice(0, 10000),
    url: location.href.slice(0, 500),
    error_hash: hash,
  });
}

export function installErrorReporter() {
  if (window.__knotErrorReporterInstalled) return;
  window.__knotErrorReporterInstalled = true;

  // byte-equal：hash 输入 = raw message/stack（reportError 内 slice for post，与旧一致）
  window.addEventListener('error', (event) => {
    reportError(event.message || String(event.error?.message || 'unknown'), event.error?.stack || '');
  });

  // byte-equal：rejection 旧路径 hash 输入 = sliced message/stack → 传 sliced（double-slice no-op）
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    reportError((reason?.message || String(reason || 'unhandledrejection')).slice(0, 2000),
                (reason?.stack || '').slice(0, 10000));
  });
}
