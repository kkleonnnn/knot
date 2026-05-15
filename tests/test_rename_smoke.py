"""tests/test_rename_smoke.py — R-67 / R-70 / R-79 / R-72 综合 smoke 守护。

v0.5.0 起：包名 / 包目录 / 业务代码 / agent prompt 字面统一为 KNOT；旧 brand 0 命中。
v0.6.0 起（F5/F15 + R-PA-6 系列立约）：R-67 从"含白名单的兼容期检查"转型为
"通用无 bi_agent 字面严格守护"（详 CHANGELOG v0.6.0 撤回声明）。

R-67：knot/ 业务代码不含 bi_agent 字面（0 豁免；commit 3/4/5/6 物理清算 + 转型完成）
R-70：services/knot/ 强制 → services/agents/，不留 alias
R-72：FastAPI title=KNOT version=<current>；routes count = 77 不变
R-79：grep BI-Agent / bi-agent 字面在 agent prompt / repositories / api 0 命中

⚠️ 本文件含字面量断言（bi_agent / bi-agent / BI-Agent 是 grep 守护目标），
   用 "bi" + "_agent" 字面分割避免被 sanitize 脚本 / IDE 替换工具误改；
   本文件自身在 R-PA-6.2 EXCLUDE 自指环豁免清单内（守护工具不应违反自己的守护契约）。
"""
import subprocess
from pathlib import Path

import pytest


# ─── R-67 包名 / 目录 / 一致性 ────────────────────────────────────────

def test_R67_knot_package_dir_exists():
    """knot/ 包目录存在；bi_agent/ 旧目录必须不存在。"""
    assert Path("knot").is_dir(), "knot/ 包目录必须存在"
    assert not Path("bi" + "_agent").exists(), "bi_agent/ 旧目录必须不存在（git mv 后）"


def test_R67_pyproject_name_is_knot():
    """pyproject.toml name='knot'。"""
    src = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "knot"' in src, "pyproject.toml name 应改 'knot'"
    assert 'name = "bi' + '-agent"' not in src, "旧 name 不应保留"


def test_R67_no_bi_agent_in_knot_package_python_code():
    """v0.6.0 F5/F15 转型：grep `bi_agent` 在 knot/ 业务代码 0 命中（0 豁免）。

    v0.5.0 时此测试含白名单（BIAGENT_MASTER_KEY / bi_agent.db / .v044- 三类）;
    v0.6.0 Phase A 撤回 R-67/68/74 公开承诺 + commit 3/4 物理清算 → 白名单整组删 +
    转为严格"0 命中"守护。
    """
    if not Path("knot").is_dir():
        pytest.fail("knot/ 包目录必须存在")

    needle = "bi" + "_agent"  # 字面分割避免被 sanitize 脚本 / IDE 工具误替
    result = subprocess.run(
        ["grep", "-rn", needle, "knot/", "--include=*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"R-67 违规：knot/ 业务代码应 0 命中 bi_agent 字面；命中：\n{result.stdout}"
    )


# ─── R-70 services/knot/ 不留 alias ──────────────────────────────────

def test_R70_no_services_knot_alias():
    """grep `knot.services.knot` 在业务代码 0 命中。"""
    if not Path("knot").is_dir():
        pytest.fail("knot/ 必须存在")

    result = subprocess.run(
        [
            "grep", "-rn", "-E",
            r"from knot\.services\.knot|knot\.services\.knot",
            "knot/", "--include=*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
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

    检测目标用字面量分割构造避免被 sanitize 脚本误替。
    """
    paths = [
        "knot/services/agents/",
        "knot/repositories/",
        "knot/api/",
    ]
    paths = [p for p in paths if Path(p).is_dir()]
    if not paths:
        pytest.fail("knot/services/agents/ 等业务目录必须存在")

    # 字面量分割：'BI' + '-Agent' = 'BI-Agent'；'bi' + '-agent' = 'bi-agent'
    pattern = "BI" + "-Agent" + "|" + "bi" + "-agent"
    result = subprocess.run(
        [
            "grep", "-rn", "-E", pattern, *paths, "--include=*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return  # 0 命中是预期

    violations = [line for line in result.stdout.strip().split("\n") if line]
    assert not violations, (
        "R-79 违规：业务代码 0 命中旧 brand 字眼；命中：\n" + "\n".join(violations)
    )


# ─── R-72 FastAPI 元数据 + 路由数 ────────────────────────────────────

def test_R72_app_title_and_version():
    """FastAPI title=KNOT version=0.6.0.6（v0.5.0 R-72 守护，每 PATCH 同步）。"""
    from knot.main import app
    assert app.title == "KNOT", f"title 应改 KNOT；实际：{app.title}"
    assert app.version == "0.6.0.6", f"version 应 0.6.0.6；实际：{app.version}"


def test_R72_routes_count_unchanged():
    """路由数下限守护 ≥ 80（v0.6.0.6 F-A 起改为下限 — 守护者 P-2 临时救火）。

    历史上是 == 严格相等：v0.5.40 +3 / v0.5.42 +2 / v0.6.0.6 +3 每次都触发 4 处硬编码 drift。
    短期改 >= 防"路由蒸发"+ 允许加路由不触发 CI 红；
    长期由 v0.6.0.6 P-1/P-5 决议（动态计数 / 直接撤回守护对象）治本。
    """
    from knot.main import app
    assert len(app.routes) >= 80, f"路由数下限应 ≥ 80（防路由蒸发）；实际：{len(app.routes)}"


def test_R72_import_knot_main_succeeds():
    """`import knot.main` 不报错（最基础的 smoke）。"""
    import knot.main  # noqa: F401


def test_R67_services_agents_importable():
    """knot.services.agents.X 可 import（git mv 后路径生效）。"""
    import knot.services.agents.orchestrator  # noqa: F401
    import knot.services.agents.sql_planner  # noqa: F401
    import knot.services.agents.catalog  # noqa: F401
