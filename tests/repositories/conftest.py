"""tests/repositories/conftest — 每条测试一个独立的 tmp SQLite 文件。

base.py 在模块 import 时把 SQLITE_DB_PATH 拷贝进自己的命名空间，所以 monkeypatch
必须直接打 base 模块（不是 config 单例）。
"""
import os
import tempfile

import pytest


@pytest.fixture()
def tmp_db_path(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db", prefix="knot_test_")
    os.close(fd)
    os.unlink(path)  # 让 init_db() 自己创建

    from knot.repositories import base as base_mod
    monkeypatch.setattr(base_mod, "SQLITE_DB_PATH", path)

    base_mod.init_db()

    yield path

    if os.path.exists(path):
        os.unlink(path)
