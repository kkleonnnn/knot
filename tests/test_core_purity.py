"""tests/test_core_purity.py — T-2 资深要求：core/ 边界守护测试。

利用反射 + AST 扫描 bi_agent.core 下所有模块的 import 语句，
若发现任何 services / repositories / adapters / api / models 的痕迹，
测试**直接挂掉**。这是除 import-linter 之外的第二道防线。

为什么需要双保险：
  - import-linter 在 CI 静态扫描；本测试在 pytest 跑（开发阶段更早暴露）
  - 反射 + AST 双手段：即便 import-linter 配置被误改，本测试仍能拦住
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import pkgutil

import bi_agent.core


_FORBIDDEN_PREFIXES = (
    "bi_agent.api",
    "bi_agent.services",
    "bi_agent.repositories",
    "bi_agent.adapters",
    "bi_agent.models",  # core 与 models 同层，语义不同，禁止互相 import
)


def _collect_imports_via_ast(src_path: pathlib.Path) -> set[str]:
    """AST 扫描——比 inspect 更可靠（能抓到函数体内的 import）。"""
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
    return found


def test_core_purity_via_ast():
    """对 bi_agent.core 下所有 .py 文件做 AST 扫描，断言无业务层 import。"""
    core_dir = pathlib.Path(bi_agent.core.__file__).parent
    py_files = list(core_dir.glob("*.py"))
    assert py_files, "bi_agent.core 至少应有 __init__.py"

    violations = []
    for f in py_files:
        imports = _collect_imports_via_ast(f)
        for imp in imports:
            for prefix in _FORBIDDEN_PREFIXES:
                if imp == prefix or imp.startswith(prefix + "."):
                    violations.append(f"{f.name}: imports {imp}")

    assert not violations, (
        "core/ 包侵入业务层（违反 4 层架构 contract）：\n  - "
        + "\n  - ".join(violations)
    )


def test_core_purity_via_runtime_reflection():
    """运行时再校验：所有 core 模块的 __dict__ 中不含任何 bi_agent 业务包对象。"""
    violations = []
    for _, mod_name, _ in pkgutil.iter_modules(bi_agent.core.__path__):
        full = f"bi_agent.core.{mod_name}"
        m = importlib.import_module(full)
        for attr_name, attr_val in vars(m).items():
            if hasattr(attr_val, "__module__"):
                origin = getattr(attr_val, "__module__", "") or ""
                for prefix in _FORBIDDEN_PREFIXES:
                    if origin == prefix or origin.startswith(prefix + "."):
                        # 排除 dataclass / Protocol 自带的注解（这些不应在 core 里出现）
                        violations.append(f"{full}.{attr_name} → {origin}")

    assert not violations, (
        "core/ 模块在 runtime 持有业务层对象引用（违反 4 层架构）：\n  - "
        + "\n  - ".join(violations)
    )


def test_core_only_contains_horizontal_utilities():
    """v0.3.3 终态：core/ 应只剩横切工具（logging / date_context / errors）。
    若新增其他业务文件，本测试失败 — 强制 reviewer 思考分层归属。"""
    core_dir = pathlib.Path(bi_agent.core.__file__).parent
    expected = {"__init__.py", "logging_setup.py", "date_context.py"}
    actual = {f.name for f in core_dir.glob("*.py")}
    unexpected = actual - expected
    assert not unexpected, (
        f"core/ 出现非横切工具文件 {unexpected}；"
        f"业务模块应放 services/ / adapters/，纯数据形状放 models/"
    )
