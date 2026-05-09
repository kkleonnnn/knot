"""models 包是叶子节点 — 任何 import 不得出现 knot 内部其他子包。"""
import pkgutil

import knot.models


def test_all_model_modules_importable():
    """所有 models/*.py 都必须能裸 import 成功（无依赖业务层）。"""
    for _, mod_name, _ in pkgutil.iter_modules(knot.models.__path__):
        full = f"knot.models.{mod_name}"
        __import__(full)


def test_models_dont_import_business_layers():
    """运行时再次 verify（import-linter 在 CI 已锁，本测试是兜底）。"""
    import importlib
    forbidden_prefixes = (
        "knot.core", "knot.config", "knot.routers",
        "knot.repositories", "knot.services", "knot.adapters",
    )
    for _, mod_name, _ in pkgutil.iter_modules(knot.models.__path__):
        full = f"knot.models.{mod_name}"
        m = importlib.import_module(full)
        # check the module's namespace for any forbidden absolute imports
        # (this is rough; import-linter does the real job)
        src_path = m.__file__
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        for forbid in forbidden_prefixes:
            assert forbid not in src, f"{full} contains forbidden import: {forbid}"
