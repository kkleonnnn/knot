"""tests/services/test_audit_service_stress.py — R-53 stress（v0.4.6 commit #3）。

1000 次连发 mutation → audit 写入 p95 < 5ms。
"""
import statistics
import time

from knot.services import audit_service


def test_R53_stress_1000_inserts_p95_under_5ms(tmp_db_path):
    """SQLite 单实例 + 同步 INSERT，1000 次连发 p95 必须 < 5ms。"""
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

    # 取 p95（statistics.quantiles n=20 的第 19 个区间结尾即 95% 分位）
    p95 = statistics.quantiles(durations, n=20)[18]
    p99 = statistics.quantiles(durations, n=100)[98]
    avg = statistics.mean(durations)
    print(f"[stress] avg={avg:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms n=1000")
    assert p95 < 5.0, f"R-53 失败：p95={p95:.3f}ms 超过 5ms 阈值"
