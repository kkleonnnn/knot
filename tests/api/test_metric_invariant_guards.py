"""tests/api/test_metric_invariant_guards.py — v0.7.0 C3 §4.5 greenfield 不变量 CI 守护。

两个 greenfield 守护（**新建非 extend** — 既有审计/加密守护无对应能力）：

1. **加密决策（存储侧 schema-scan）**：v0.7.0 metric 全字段非密（caliber = SQL 表达式 / name·display·
   aliases = 标签 / base_object·filters·dimensions·lineage = 元数据；无凭证）。守护 = metrics 表
   0 secret-pattern 列且未注册加密；未来若加机密列（如 connection_secret）→ 须注册
   `_METRIC_ENCRYPTED_COLS` + Fernet enc_v1（参 data_source_repo `_DS_ENCRYPTED_COLS`）否则红。

2. **审计每-Literal-emit**：每个 metric.* AuditAction Literal 须在 API 层有 ≥1 audit() emit
   （既有 test_audit_repo 仅前缀子集覆盖，无「每 Literal ≥1 emit」断言 → 本守护补齐）。

纯 stdlib（ast/re/sqlite3/pathlib）→ 本机 + CI 同跑（不依赖 fastapi）。
"""
import ast
import re
import sqlite3
import typing
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SCHEMA = _REPO / "knot" / "repositories" / "schema.sql"
_API_DIR = _REPO / "knot" / "api"


# ─── 守护 1：加密决策（存储侧 schema-scan）──────────────────────────

_SECRET_PAT = re.compile(
    r"(password|passwd|secret|token|api[_]?key|credential|private_key)", re.I
)
# 已注册加密的 metric 列（v0.7.0 全字段非密 → 空；未来含密列须登记 + 对应 repo Fernet 加密）
_METRIC_ENCRYPTED_COLS: tuple[str, ...] = ()


def _metric_columns() -> list[str]:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA.read_text())
    cols = [r[1] for r in conn.execute("PRAGMA table_info(metrics)").fetchall()]
    conn.close()
    return cols


def test_metrics_no_unregistered_secret_columns():
    """§4.5 加密守护：metric 非密决策 — metrics 任何 secret-pattern 列须已注册加密。"""
    cols = _metric_columns()
    assert cols, "metrics 表应存在（C1 schema）"
    unregistered = [c for c in cols if _SECRET_PAT.search(c) and c not in _METRIC_ENCRYPTED_COLS]
    assert not unregistered, (
        f"§4.5 加密守护：metric 列 {unregistered} 形似机密但未注册加密 — "
        f"非密则重命名；含密则登记 _METRIC_ENCRYPTED_COLS + Fernet enc_v1（参 _DS_ENCRYPTED_COLS）"
    )


# ─── 守护 2：审计每-Literal-emit ─────────────────────────────────────

def _metric_audit_literals() -> set[str]:
    from knot.models.audit import AuditAction
    return {a for a in typing.get_args(AuditAction) if a.startswith("metric.")}


def _api_audit_emit_actions() -> set[str]:
    """AST 扫描 knot/api/**.py 所有 audit(...action="...") 调用的 action 字面量。"""
    out: set[str] = set()
    for path in _API_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "audit":
                for kw in node.keywords:
                    if kw.arg == "action" and isinstance(kw.value, ast.Constant):
                        out.add(kw.value.value)
    return out


def test_every_metric_literal_has_audit_emit():
    """§4.5 审计守护：每个 metric.* Literal 须在 API 层有 ≥1 audit() emit。"""
    literals = _metric_audit_literals()
    assert literals == {"metric.create", "metric.update", "metric.delete"}, (
        f"metric AuditAction Literal 应为 create/update/delete 三条；实际 {literals}"
    )
    emitted = _api_audit_emit_actions()
    missing = literals - emitted
    assert not missing, f"§4.5 审计守护：metric Literal {missing} 无对应 audit() emit（每 Literal ≥1）"
