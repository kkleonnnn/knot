"""tests/repositories/conftest — 每条测试一个独立的 tmp SQLite 文件。

base.py 在模块 import 时把 SQLITE_DB_PATH 拷贝进自己的命名空间，所以 monkeypatch
必须直接打 base 模块（不是 config 单例）。
"""
import os
import tempfile

import pytest


@pytest.fixture()
def tmp_db_path(monkeypatch):
    # v0.9.0 C2 双层布局：mkdtemp 目录 + anchor=dir/knot.db；tenant#1 db_dir='.' → anchor 本身
    # （mkstemp 随机文件名与 db_dir='.'+'/knot.db' 冲突 — 手册 iv#6）。base + tenant_repo 各拷 SQLITE_DB_PATH
    # → 分别 monkeypatch。tenant ctx 由 tests/conftest.py autouse 提供（静态 tenant#1 db_dir='.'）。
    d = tempfile.mkdtemp(prefix="knot_test_")
    anchor = os.path.join(d, "knot.db")

    from knot.repositories import base as base_mod
    from knot.repositories import tenant_repo as _tr
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", anchor)
    monkeypatch.setattr(_tr, "SQLITE_DB_PATH", anchor)
    _tr.init_platform_db()               # 供基于 tmp_db_path 的 TestClient fixture（middleware resolve_single_tenant）
    _tr.seed_default_tenant(db_dir=".")

    base_mod.init_db()

    yield anchor

    import shutil
    shutil.rmtree(d, ignore_errors=True)
