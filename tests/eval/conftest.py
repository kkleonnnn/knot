"""tests/eval/conftest.py — pytest fixtures: 加载 cases.yaml 并把 bi_agent/core 加进 sys.path。"""
import sys
from pathlib import Path

import yaml
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "bi_agent" / "core"))

CASES_FILE = Path(__file__).parent / "cases.yaml"


def load_cases():
    with open(CASES_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


@pytest.fixture(scope="session")
def fake_schema():
    """给 LLM 看的 schema，覆盖 cases.yaml 涉及的表。"""
    return (
        "## Table users\n"
        "- id (BIGINT)\n- created_at (DATETIME) 注册时间\n- email (VARCHAR)\n\n"
        "## Table orders\n"
        "- id (BIGINT)\n- user_id (BIGINT)\n- amount (DECIMAL) 金额，单位元\n"
        "- status (VARCHAR) paid|unpaid|refunded\n- pay_channel (VARCHAR) wechat|alipay|card\n"
        "- pay_time (DATETIME) 支付时间\n- created_at (DATETIME) 下单时间\n\n"
        "## Table user_logins\n"
        "- user_id (BIGINT)\n- login_time (DATETIME)\n"
    )
