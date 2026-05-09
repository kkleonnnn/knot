"""tests/eval/conftest.py — pytest fixtures: 加载用例与 fake_schema。

v0.2.4 隐私分层：
  - cases.yaml / fake_schema.txt           : 真实业务（.gitignore，本地填）
  - cases.example.yaml / fake_schema.example.txt: 通用模板（仓库内提交）

加载顺序：先尝试真实文件；缺失则回退 .example。

v0.3.0：knot 已 pip install -e；不再需要 sys.path hack。
"""
from pathlib import Path

import yaml
import pytest

HERE = Path(__file__).parent


def _pick(real: str, example: str) -> Path:
    for name in (real, example):
        p = HERE / name
        if p.exists():
            return p
    return HERE / example  # 最后兜底，用 example 路径让上层报清晰错误


def load_cases():
    p = _pick("cases.yaml", "cases.example.yaml")
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("cases", [])


def _load_schema() -> str:
    p = _pick("fake_schema.txt", "fake_schema.example.txt")
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def fake_schema():
    return _load_schema()
