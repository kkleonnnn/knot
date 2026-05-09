"""knot/api/_secret.py — API 边界 mask helper（v0.4.5 R-39）。

守护者强调：mask 是「展示给用户看」的视图层加工，应在 api boundary 做；
**严禁**在 services / repositories 层做 mask（会污染领域模型）。

3 个工具函数：
- `mask_secret(s)` — 明文 → 「•••••••• + last4」（短于 4 字符全 mask）
- `is_mask_placeholder(s)` — 检测前端误回传的 mask 字符串
- `should_update_secret(new, old)` — 四种输入分类（缺失 / 空 / mask 占位 / 新值）
"""
from __future__ import annotations

# 8 个 U+2022（BULLET）— Stage 3 §9.5 锁定的 mask 占位前缀
_MASK_PREFIX = "•" * 8


def mask_secret(s: str | None) -> str:
    """敏感串展示版本：

    - None / "" → ""（避免误导未配置）
    - 长度 ≤ 4 → 「••••」（不暴露 last4）
    - 否则 → 「•••••••• + last4」
    """
    if not s:
        return ""
    if len(s) <= 4:
        return "••••"
    return _MASK_PREFIX + s[-4:]


def is_mask_placeholder(s: str | None) -> bool:
    """前端可能把 GET 的 masked 值原样回传 PATCH — 见前 8 个 U+2022 视为占位。"""
    return isinstance(s, str) and s.startswith(_MASK_PREFIX)


def should_update_secret(new: str | None, old: str) -> tuple[bool, str]:
    """PATCH 路由用：四种输入分类 → (是否更新, 最终值)

    | 输入 | 行为 |
    |---|---|
    | None（字段缺失） | 不更新 |
    | "" 空白 | 保留原值 |
    | mask 占位（••••••••...） | 保留原值（误回传兜底） |
    | 新明文 | 更新 |
    """
    if new is None:
        return False, old
    if new == "":
        return False, old
    if is_mask_placeholder(new):
        return False, old
    return True, new
