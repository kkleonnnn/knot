"""knot.api._rate_limit — v0.6.0.23 简易 in-memory rate limiter（防 brute force）。

Codex §APPENDIX D 推荐项：login endpoint rate limit 防字典攻击。
本模块提供 token-bucket 风格的 per-key 限流（默认 per IP）+ FastAPI Depends 装配。

设计取舍：
- in-memory 实现（per uvicorn worker；多 worker / 多 replica 时各自计数）
- 内测期 DAU 5-20 + 单 replica 部署完全够用
- 真正需要分布式限流时换 Redis backend（v0.7+ 评估）

红线：
- R-限-1 IP 提取必走 X-Forwarded-For first（反代场景）
- R-限-2 失败返 429 + Retry-After header（HTTP 标准）
- R-限-3 thread-safe（uvicorn 内部 thread pool 调用 sync deps 时会并发）
- R-限-4 内存有上限（自动清理过期 buckets；防内存膨胀攻击）
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

# 默认限流配置：(limit, window_sec)
# login: 10 次 / 60s / IP — 防字典攻击（admin/admin123 + v0.6.0.20 强制改密兜底）
# change_pwd: 5 次 / 60s / IP — 改密接口更严
_DEFAULT_LIMITS = {
    "login": (10, 60),
    "change_pwd": (5, 60),
}

# 内存有上限守护：单个 key bucket 最大长度 = limit + 1（自然限制）
# 全局 buckets dict 最大 key 数 = _MAX_KEYS（防 IP 喷射占内存）
_MAX_KEYS = 10000


class _Bucket:
    """thread-safe per-key 滑动窗口计数器。"""

    def __init__(self) -> None:
        self._d: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float) -> tuple[bool, float]:
        """检查 + 累加；返 (允许通过, retry_after 秒数)。"""
        now = time.time()
        with self._lock:
            # 内存上限守护（R-限-4）：超过 _MAX_KEYS 时清理最老 buckets
            if len(self._d) > _MAX_KEYS:
                # 简单清理：删除 30% 最久未活跃的 keys
                cutoff = now - window * 2
                to_del = [k for k, ts in self._d.items() if not ts or ts[-1] < cutoff]
                for k in to_del[: _MAX_KEYS // 3]:
                    self._d.pop(k, None)

            bucket = self._d[key]
            # 移除超过 window 的旧时间戳
            bucket[:] = [t for t in bucket if now - t < window]
            if len(bucket) >= limit:
                # 计算 retry-after：bucket[0] 是窗口内最老一次，等到它过期即可
                retry_after = window - (now - bucket[0])
                return False, max(retry_after, 1.0)
            bucket.append(now)
            return True, 0.0


_bucket = _Bucket()


def _client_ip(request: Request) -> str:
    """提取客户端 IP（R-限-1：反代场景 X-Forwarded-For first）。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # XFF 格式：'client, proxy1, proxy2'；取第一个为真实 client
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce(request: Request, kind: str) -> None:
    """通用限流强制；超限抛 429 + Retry-After。"""
    limit, window = _DEFAULT_LIMITS[kind]
    key = f"{kind}:{_client_ip(request)}"
    ok, retry_after = _bucket.check(key, limit, window)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail={
                "ja": "Too many attempts; please wait and retry.",
                "zh": f"操作过于频繁，请 {int(retry_after) + 1} 秒后再试",
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


# ─── FastAPI Depends 用入口 ─────────────────────────────────────────────


def rate_limit_login(request: Request) -> None:
    """登录限流：10 次/60s/IP。"""
    _enforce(request, "login")


def rate_limit_change_pwd(request: Request) -> None:
    """改密限流：5 次/60s/IP（严于登录）。"""
    _enforce(request, "change_pwd")


# ─── 测试辅助 — 重置桶（仅 tests 用） ───────────────────────────────────


def _reset_for_tests() -> None:
    """测试间清空 bucket — 仅测试调；生产路径不应触发。"""
    with _bucket._lock:
        _bucket._d.clear()
