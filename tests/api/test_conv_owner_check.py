"""tests/api/test_conv_owner_check.py — v0.7.40 B2.1 回归守护。

_check_conv_owner 改单行 PK 查询（conversation_repo.get_conversation_owner）后，
404 语义须 byte-equal：(a) 他人 conv → 404 (b) 不存在 conv → 404 (c) 自己 conv → 放行。

依赖 `client` fixture 仅为建 tmp DB + init_db + monkeypatch SQLITE_DB_PATH；
测试直接调模块函数 _check_conv_owner + 真实 conversation_repo（走真 get_conversation_owner 查询）。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_check_conv_owner_own_conv_passes(client):
    """自己的 conv → 不 raise。"""
    from knot.api import query
    from knot.repositories import conversation_repo

    cid = conversation_repo.create_conversation(user_id=1, title="own")
    query._check_conv_owner(cid, 1)  # 不 raise 即通过


def test_check_conv_owner_foreign_conv_404(client):
    """他人的 conv → 404（owner != user_id）。"""
    from knot.api import query
    from knot.repositories import conversation_repo

    cid = conversation_repo.create_conversation(user_id=2, title="foreign")
    with pytest.raises(HTTPException) as exc:
        query._check_conv_owner(cid, 1)
    assert exc.value.status_code == 404


def test_check_conv_owner_nonexistent_conv_404(client):
    """不存在的 conv → 404（owner None != user_id），防枚举，与他人 conv 同码。"""
    from knot.api import query

    with pytest.raises(HTTPException) as exc:
        query._check_conv_owner(999999, 1)
    assert exc.value.status_code == 404
