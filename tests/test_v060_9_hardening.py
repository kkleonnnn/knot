"""tests/test_v060_9_hardening.py — v0.6.0.9 守护：UI 默认问题 + presenter meta-query + CI 精简。

F1: ChatEmpty.jsx 默认问题文案修改 byte-equal
F2: presenter.md 含 "元数据查询特例" 段（防 LLM 行为 regression）
F3: ci.yml 仅含 1 个 boot smoke variant（删 only-biagent / both-same / neither）
"""
from __future__ import annotations

from pathlib import Path


def test_F1_chat_empty_default_questions_updated():
    """v0.6.0.9 F1：ChatEmpty.jsx 2 个默认问题已切到合约 / 平台总盈亏。"""
    src = Path("frontend/src/screens/chat/ChatEmpty.jsx").read_text(encoding="utf-8")
    # 新文案应在
    assert "今天的合约交易总量是多少？" in src, "F1 违规：缺合约交易问题"
    assert "最近 7 天每日平台总盈亏趋势" in src, "F1 违规：缺平台总盈亏趋势问题"
    # 旧文案应删
    assert "今天的订单总量是多少？" not in src, "F1 违规：旧'订单总量'文案未删"
    assert "每日 GMV 趋势" not in src, "F1 违规：旧'GMV 趋势'文案未删"


def test_F2_presenter_prompt_has_meta_query_rule():
    """v0.6.0.9 F2：presenter.md 含 meta-query 识别段，防 LLM 把 list_tables 文本判 '空集'。"""
    src = Path("knot/prompts/presenter.md").read_text(encoding="utf-8")
    assert "元数据查询特例" in src, "F2 违规：缺 meta-query 段标题"
    assert "list_tables" in src, "F2 违规：缺 list_tables 关键字"
    assert "SELECT" in src and "DESCRIBE" in src, (
        "F2 违规：缺 SQL 关键字白名单（SELECT/WITH/SHOW/DESCRIBE）"
    )


def test_F3_ci_yml_boot_smoke_single_variant():
    """v0.6.0.9 F3：ci.yml boot smoke 矩阵从 4 → 1 variants（删 only-biagent / both-same / neither）。

    历史 matrix YAML 项已删除（注释中的描述性引用保留）—— 仅校验实际 matrix item 行。
    """
    src = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    # 保留：only-knot
    assert "only-knot" in src, "F3 违规：only-knot boot smoke 应保留"
    # 删除：matrix entries（描述性注释行 # 开头不算）
    for name in ("only-biagent", "both-same", "neither"):
        matrix_line = f'{{ name: "{name}"'
        assert matrix_line not in src, f"F3 违规：matrix item '{name}' 应删（守护对象失效 13 MINOR 0 命中）"
