"""tests/services/test_metric_cost_async_carriers.py — v0.7.0 C4 成本/async 不变量载体。

§9 ratify ①「成本/async 决策 + 预留」：v0.7.0 = 指标注册表（纯 DB CRUD），**无新 LLM 调用、
无新 agent_kind 成本桶** —— LogicForm 解析/编译（产生 LLM 调用 + 成本归桶）留 v0.7.1。
本 PATCH 用两个**前瞻 negative carrier** 锁定该决策（production 代码 0 改 — 纯 test）：

1. **成本预留（不早加桶）**：cost_service `_NEW_AGENT_KINDS` 维持 4 桶
   （clarifier/sql_planner/fix_sql/presenter）；v0.7.1 LogicForm 编译时才追加 semantic/logicform
   桶 + R-S8 cost_service 横跨语义+LLM 双路径归集。本守护防 v0.7.0 提前引桶（决策漂移）。

2. **async-native（0 sync LLM）**：metric 子系统（metrics.py + metric_repo.py + metric.py）纯
   CRUD，0 引 sync LLM（generate_sql/fix_sql DEPRECATED v1.0）；v0.7.1 LogicForm 解析/编译须
   async-native（a* + R-26 首行 budget gate），严禁新 sync LLM 路径。本守护锁定 v0.7.0 无回退。

纯 stdlib（ast/import/pathlib）→ 本机 + CI 同跑。
"""
import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_METRIC_FILES = (
    _REPO / "knot" / "api" / "admin" / "metrics.py",
    _REPO / "knot" / "repositories" / "metric_repo.py",
    _REPO / "knot" / "models" / "metric.py",
)
# sync LLM 符号（v0.5.5 DEPRECATED；v1.0 移除目标）— metric 子系统严禁引用
_SYNC_LLM_SYMBOLS = {"generate_sql", "fix_sql"}


# ─── carrier 1：成本桶不早加 semantic（决策预留）────────────────────

def test_cost_buckets_unchanged_no_premature_semantic_bucket():
    """v0.7.0 不引新 agent_kind 成本桶；semantic/logicform 桶留 v0.7.1 LogicForm 编译。"""
    from knot.services.cost_service import _NEW_AGENT_KINDS
    assert _NEW_AGENT_KINDS == ("clarifier", "sql_planner", "fix_sql", "presenter"), (
        f"v0.7.0 严禁改成本桶（决策预留 — semantic 桶留 v0.7.1）；实际 {_NEW_AGENT_KINDS}"
    )


# ─── carrier 2：metric 子系统 0 sync LLM（async-native 锚）──────────

def _referenced_names(path: Path) -> set[str]:
    """文件中所有 Name / Attribute 末段标识符（捕获裸调用 + import 名）。"""
    names: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def test_metric_subsystem_is_pure_crud_no_sync_llm():
    """metric 子系统 3 文件 0 引 sync LLM（generate_sql/fix_sql）— v0.7.1 编译须 async-native。"""
    for path in _METRIC_FILES:
        assert path.exists(), f"metric 子系统文件应存在：{path}"
        leaked = _referenced_names(path) & _SYNC_LLM_SYMBOLS
        assert not leaked, (
            f"async-native 守护：{path.name} 引用 sync LLM {leaked}；"
            f"v0.7.0 registry 应纯 CRUD，v0.7.1 LogicForm 编译须 async（a* + R-26 gate）"
        )
