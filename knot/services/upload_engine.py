"""knot.services.upload_engine — per-tenant 上传库(uploads.db)引擎 resolver（v0.9.2）。

替代 engine_cache 的 import 期 `_upload_engine`（值绑数据根单库 = 上传问数 SQL 的 sqlite_master 可列举
**别租户** t_* 表 + SELECT 其数据 = 跨租户上传数据混池）。uploads.db 住 `tenants/<id>/uploads.db`
（镜像 base 的 knot.db 双层解析，fail-closed）。物理迁移见 repositories/uploads_relocation.py。

MF5/R7：`db_dir` 无 UNIQUE 约束（platform_schema）→ 相对/`..` 别名可指同物理目录 → memoize 键用
**(tid, 规范化绝对路径)** + 路径在数据根内校验 + path→tid 冲突 tripwire。
路径源读 `base.SQLITE_DB_PATH`（与 knot.db 双层解析同源；测试 monkeypatch base.SQLITE_DB_PATH 即覆盖）。
"""
from __future__ import annotations

from pathlib import Path

from knot.adapters.db import doris as db_connector
from knot.core.tenant_context import TenantContextError, current_tenant
from knot.repositories import base as _base

# memoize：键 (tid, canonical_abs_path)；值 = SQLAlchemy engine。模块级 → conftest reset 须 dispose+clear。
_upload_engines: dict = {}
# 规范化绝对路径 → tid（tripwire：同物理路径被两 tid claim = db_dir 别名/配置错，fail-closed）。
_uploads_path_owner: dict = {}


def _tenant_uploads_path() -> Path:
    """当前 active tenant 的 uploads.db 路径（fail-closed：无 ctx → current_tenant() raise）。

    = `Path(base.SQLITE_DB_PATH).parent / current_tenant()["db_dir"] / "uploads.db"`（规范化）。
    校验解析路径在数据根内（防 db_dir='../x' 逃逸出租户边界）。
    """
    root = Path(_base.SQLITE_DB_PATH).parent.resolve()
    p = (root / current_tenant()["db_dir"] / "uploads.db").resolve()
    if root != p.parent and root not in p.parents:
        raise TenantContextError(f"uploads 路径逃出数据根：{p} 不在 {root} 内（db_dir 非法）")
    return p


def get_upload_engine():
    """当前 active tenant 的 uploads.db engine（memoize by (tid, abs_path)，fail-closed）。

    替代 engine_cache._upload_engine（import 期值绑数据根）。上传/问数/删除 caller 走本 resolver。
    """
    tid = current_tenant()["id"]
    path = _tenant_uploads_path()
    spath = str(path)
    owner = _uploads_path_owner.get(spath)
    if owner is not None and owner != tid:
        raise TenantContextError(
            f"uploads 路径 {path} 已属 tenant#{owner}，tenant#{tid} 不得复用（db_dir 别名冲突）"
        )
    key = (tid, spath)
    eng = _upload_engines.get(key)
    if eng is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        eng = db_connector.create_sqlite_engine(spath)
        _upload_engines[key] = eng
        _uploads_path_owner[spath] = tid
    return eng
