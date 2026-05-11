"""tests/test_rename_smoke.py — v0.5.0 R-67 / R-70 / R-79 / R-72 综合 smoke 守护（TDD）。

R-67：包名 / 包目录 / DB 文件名一致；新代码不存在 bi_agent 字符串（白名单除外）
R-70：services/knot/ 强制 → services/agents/，不留 alias
R-72：FastAPI title=KNOT version=0.5.0；routes count = 72 不变
R-79：grep BI-Agent / bi-agent 字面量在 agent prompt / repositories / api 0 命中

⚠️ 本文件含字面量断言（bi_agent / bi-agent / BI-Agent 是 grep 守护目标），
   _v050_rename.py 必须 SKIP 本文件。
"""
import subprocess
from pathlib import Path

import pytest


# ─── R-67 包名 / 目录 / 一致性 ────────────────────────────────────────

def test_R67_knot_package_dir_exists():
    """knot/ 包目录存在；bi_agent/ 旧目录必须不存在。"""
    assert Path("knot").is_dir(), "knot/ 包目录必须存在"
    assert not Path("bi_agent").exists(), "bi_agent/ 旧目录必须不存在（git mv 后）"


def test_R67_pyproject_name_is_knot():
    """pyproject.toml name='knot'。"""
    src = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "knot"' in src, "pyproject.toml name 应改 'knot'"
    assert 'name = "bi-agent"' not in src, "旧 name 不应保留"


def test_R67_no_bi_agent_in_knot_package_python_code():
    """grep `bi_agent` 在 knot/ 业务代码 0 命中（除白名单）。

    白名单：
    - BIAGENT_MASTER_KEY 字面量（env 兼容代码）
    - bi_agent.db / bi_agent.db.v044 字面量（DB migration 检测代码）
    - _v050_rename.py（一次性 PATCH 脚本含 token 字面量；D-5 删除）
    """
    if not Path("knot").is_dir():
        pytest.fail("knot/ 包目录必须存在（D-3 后）")

    needle = "bi" + "_agent"  # 字面量分割避免被脚本误替
    result = subprocess.run(
        [
            "grep", "-rn", needle, "knot/",
            "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return  # 0 命中

    whitelist_keywords = [
        "BIAGENT_MASTER_KEY",   # env 兼容字面量
        "bi" + "_agent.db",      # DB migration 检测字面量
        ".v044-",               # bak 命名字面量
    ]
    violations = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        if not any(kw in line for kw in whitelist_keywords):
            violations.append(line)
    assert not violations, (
        "R-67 违规：knot/ 内 bi_agent 字眼不在白名单：\n" + "\n".join(violations)
    )


# ─── R-70 services/knot/ 不留 alias ──────────────────────────────────

def test_R70_no_services_knot_alias():
    """grep `knot.services.knot` 在业务代码 0 命中。

    白名单（豁免）：
    - knot/scripts/_v050_rename.py（一次性脚本 token 字面量；D-5 删除）
    - tests/test_rename_smoke.py（本文件 R-70 / R-79 测试 docstring 含目标字面量）
    - tests/scripts/test_v050_rename.py（脚本守护测试，含目标字面量）
    """
    if not Path("knot").is_dir():
        pytest.fail("knot/ 必须存在（D-3 后）")

    result = subprocess.run(
        [
            "grep", "-rn", "-E",
            r"from knot\.services\.knot|knot\.services\.knot",
            "knot/", "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"R-70：knot/ 业务代码 knot.services.knot 应 0 命中；命中：\n{result.stdout}"
    )


def test_R70_services_agents_dir_with_known_files():
    """knot/services/agents/ 目录存在且含已知文件（git mv 后）。"""
    base = Path("knot/services/agents")
    assert base.is_dir(), f"{base} 必须存在"
    expected = ["__init__.py", "orchestrator.py", "sql_planner.py", "catalog.py"]
    for f in expected:
        assert (base / f).exists(), f"{base / f} 必须存在（git mv 应保留）"


# ─── R-79 brand 字面量守护 ────────────────────────────────────────────

def test_R79_no_old_brand_literal_in_business_code():
    """R-79：grep 旧 brand 字面量在 agent prompt / repositories / api 0 命中。

    业务代码中 brand 字眼必须全替换为 KNOT 或品牌中性表述（agent system prompt /
    错误消息文案 / 用户可见 banner / repositories prompts）。

    检测目标用字面量分割构造避免被 _v050_rename.py 误替。
    """
    paths = [
        "knot/services/agents/",
        "knot/repositories/",
        "knot/api/",
    ]
    paths = [p for p in paths if Path(p).is_dir()]
    if not paths:
        pytest.fail("knot/services/agents/ 等业务目录必须存在（D-3 后）")

    # 字面量分割：'BI' + '-Agent' = 'BI-Agent'；'bi' + '-agent' = 'bi-agent'
    pattern = "BI" + "-Agent" + "|" + "bi" + "-agent"
    result = subprocess.run(
        [
            "grep", "-rn", "-E", pattern, *paths, "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return  # 0 命中是预期

    violations = [line for line in result.stdout.strip().split("\n") if line]
    assert not violations, (
        "R-79 违规：业务代码 0 命中旧 brand 字眼；命中：\n" + "\n".join(violations)
    )


# ─── R-72 FastAPI 元数据 + 路由数 ────────────────────────────────────

def test_R72_app_title_and_version():
    """FastAPI title=KNOT version=0.5.10（v0.5.0 R-72 守护，每 PATCH 同步）。"""
    from knot.main import app
    assert app.title == "KNOT", f"title 应改 KNOT；实际：{app.title}"
    assert app.version == "0.5.10", f"version 应 0.5.10；实际：{app.version}"


def test_R72_routes_count_unchanged():
    """路由数 = 72 不变（v0.4.6 锚点；本 PATCH 不增减路由）。"""
    from knot.main import app
    assert len(app.routes) == 72, f"路由数应仍为 72；实际：{len(app.routes)}"


def test_R72_import_knot_main_succeeds():
    """`import knot.main` 不报错（最基础的 smoke）。"""
    import knot.main  # noqa: F401


def test_R67_services_agents_importable():
    """knot.services.agents.X 可 import（git mv 后路径生效）。"""
    import knot.services.agents.orchestrator  # noqa: F401
    import knot.services.agents.sql_planner  # noqa: F401
    import knot.services.agents.catalog  # noqa: F401
