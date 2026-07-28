"""tests/services/test_audit_service_stress.py — R-53 stress（v0.4.6 commit #3）。

1000 次连发 mutation → audit 写入 p95 守护。阈值演进：
- v0.4.6 立 5ms → v0.5.x 观测 GH ubuntu-latest 共享 runner p95 飘 8-12ms（本地 macOS ~1ms）→ 放 15ms。
- 2026-07-27（riding v0.9.3）：绝对 15ms 在 runner 负载高峰仍假红 —— PR#256 `77d6378`（0 生产码）
  两 run 均 p95=139ms，整 run 9m15s/10m55s vs 正常 ~6m（整机慢 50%+），本地 1 passed/1.26s，
  0 改动重跑即绿。改「同 run 裸 INSERT 基准相对比较 + 15ms 绝对下限」：
  阈值 = max(15ms, 裸 sqlite3 connect+WAL+INSERT+commit 周期 p95 × 10)。
  - 本地 / 健康 runner：基准 p95 远小于 1.5ms → 下限 15ms 生效，守护力度与原绝对阈值等同（不降）。
  - 高负载 runner：基准同倍膨胀 → 阈值随整机负载水位抬升；audit 层相对裸 INSERT 的额外开销
    （真回归形态：多余查询 / 表扫描 / 锁竞争，健康比值 ~1-2×）仍被 10× 比值兜住。
"""
import os
import sqlite3
import statistics
import time

from knot.services import audit_service

# 绝对下限：本地 / 健康 runner 上生效，与旧版纯绝对阈值守护力度等同
_ABS_FLOOR_MS = 15.0
# audit 写入 p95 不得超过同 run 裸 INSERT 周期 p95 的倍数（只放过整机负载，不放过 audit 层回归）
_BASELINE_FACTOR = 10.0
_BASELINE_N = 200


def _p95(durations: list[float]) -> float:
    # statistics.quantiles n=20 的第 19 个区间结尾即 95% 分位
    return statistics.quantiles(durations, n=20)[18]


def _baseline_insert_p95_ms(db_dir: str) -> float:
    """同 run 负载基准：裸 sqlite3「connect + WAL + INSERT + commit + close」周期 p95。

    镜像 base.get_conn + audit_repo.insert 的每次调用 I/O 模式（逐次开关连接 + 逐条 commit），
    不含 audit 层任何代码 —— 量化的是当前机器 / runner 的负载水位，不是被测物。
    """
    path = os.path.join(db_dir, "r53_baseline.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.close()
    durations: list[float] = []
    for i in range(_BASELINE_N):
        t0 = time.perf_counter()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("INSERT INTO t (v) VALUES (?)", (f'{{"i": {i}, "field": "value"}}',))
        conn.commit()
        conn.close()
        durations.append((time.perf_counter() - t0) * 1000.0)
    return _p95(durations)


def test_R53_stress_1000_inserts_p95_load_aware(tmp_db_path):
    """1000 次连发 audit 写入 p95 < max(15ms, 同 run 裸 INSERT p95 × 10)。"""
    db_dir = os.path.dirname(tmp_db_path)
    baseline_before = _baseline_insert_p95_ms(db_dir)

    actor = {"id": 1, "username": "admin", "role": "admin"}
    durations: list[float] = []
    for i in range(1000):
        t0 = time.perf_counter()
        audit_service.log(
            actor=actor,
            action="user.update",
            resource_type="user",
            resource_id=i,
            detail={"i": i, "field": "value"},
        )
        durations.append((time.perf_counter() - t0) * 1000.0)  # ms

    # 基准取压测段前后两窗口较高者：防负载在压测中途起落导致阈值失真
    baseline = max(baseline_before, _baseline_insert_p95_ms(db_dir))
    threshold = max(_ABS_FLOOR_MS, baseline * _BASELINE_FACTOR)

    p95 = _p95(durations)
    p99 = statistics.quantiles(durations, n=100)[98]
    avg = statistics.mean(durations)
    print(
        f"[stress] avg={avg:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms n=1000 "
        f"baseline_p95={baseline:.3f}ms threshold={threshold:.3f}ms"
    )
    assert p95 < threshold, (
        f"R-53 失败：p95={p95:.3f}ms 超过阈值 {threshold:.3f}ms"
        f"（= max({_ABS_FLOOR_MS:g}ms 下限, 裸 INSERT 基准 {baseline:.3f}ms × {_BASELINE_FACTOR:g})）"
    )
