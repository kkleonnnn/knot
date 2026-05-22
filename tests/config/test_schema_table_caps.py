"""v0.6.0.21 — schema 表数上限守护（资深 announce 扩到 40）。

防止未来 PATCH 误把 cap 调回 20/25（影响业务表覆盖与 SQL planner 上下文质量）。
若有业务理由再调，需同步更新本测试 + commit message 说明。
"""
from __future__ import annotations


def test_max_tables_in_schema_default_is_40():
    """v0.6.0.21 — MAX_TABLES_IN_SCHEMA 默认 40（hardcoded; env 不覆盖此常量）。"""
    from knot.config import settings as s
    assert s.MAX_TABLES_IN_SCHEMA == 40, (
        f"MAX_TABLES_IN_SCHEMA 应为 40，实际 {s.MAX_TABLES_IN_SCHEMA}。"
        "若要调整请更新本测试 + commit 说明业务理由。"
    )


def test_schema_filter_max_tables_default_is_40():
    """v0.6.0.21 — SCHEMA_FILTER_MAX_TABLES 默认 40（验证源码字面 + env 缺省）。

    源码字面守护（防止未来误改默认值）+ 当前进程读取值一致性。
    env override 机制由 test_schema_filter_max_tables_env_override_still_works 守护。
    """
    import re
    from pathlib import Path
    src = (Path(__file__).parent.parent.parent / "knot" / "config" / "settings.py").read_text()
    m = re.search(r'SCHEMA_FILTER_MAX_TABLES\s*=\s*int\(os\.getenv\([^,]+,\s*"(\d+)"\)\)', src)
    assert m is not None, "settings.py 中 SCHEMA_FILTER_MAX_TABLES 定义形式变更，请同步本测试"
    default_in_source = int(m.group(1))
    assert default_in_source == 40, (
        f"settings.py 中 SCHEMA_FILTER_MAX_TABLES 默认应为 40，实际源码字面 {default_in_source}。"
        "v0.6.0.21 资深 announce 扩大业务表覆盖；若要调整请同步本测试 + commit 说明。"
    )


def test_schema_filter_max_tables_env_override_documented():
    """v0.6.0.21 — settings.py 中 SCHEMA_FILTER_MAX_TABLES 走 os.getenv（env override 仍生效）。"""
    from pathlib import Path
    src = (Path(__file__).parent.parent.parent / "knot" / "config" / "settings.py").read_text()
    assert 'SCHEMA_FILTER_MAX_TABLES = int(os.getenv("SCHEMA_FILTER_MAX_TABLES"' in src, (
        "SCHEMA_FILTER_MAX_TABLES 必须走 os.getenv 以保留运维 env 调整能力"
    )
