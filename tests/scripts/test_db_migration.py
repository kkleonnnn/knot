"""tests/scripts/test_db_migration.py — v0.5.0 R-69 (idempotent) + R-76 (atomic) 守护（TDD）。

覆盖：
- R-69 4 场景幂等：no_db_yet / already_migrated / migrate / both_exist
- R-69 timestamped backup 不覆盖前次（沿袭 v0.4.5 R-46 模式）
- R-76 mock os.rename 抛错 → bak 删 + old 保留 + raise（绝不允许 DB 消失）
- R-76 mock shutil.copy2 抛错 → bak 不残留 + old 保留 + raise

Stage 3 守护者终审 §3 修订 2（DB migration 双轨 + atomic 保护）+ R-76 实现要求。
"""
import shutil
import time
from pathlib import Path

import pytest

# D-2 阶段 import 必失败（knot 包尚不存在）；D-3 git mv 后转绿。
from knot.scripts.migrate_db_rename_v050 import migrate_db_rename


def _make_dummy_db(path: Path, content: bytes = b"fake-sqlite-data"):
    path.write_bytes(content)


# ─── R-69 4 场景幂等 ─────────────────────────────────────────────────

def test_R69_no_db_yet(tmp_path):
    """场景 c：都不存在 → status='no_db_yet'，0 副作用。"""
    result = migrate_db_rename(tmp_path)
    assert result["status"] == "no_db_yet"
    assert not (tmp_path / "knot.db").exists()
    assert not (tmp_path / "bi_agent.db").exists()


def test_R69_already_migrated(tmp_path):
    """场景 b：仅 knot.db → status='already_migrated'。"""
    _make_dummy_db(tmp_path / "knot.db")
    result = migrate_db_rename(tmp_path)
    assert result["status"] == "already_migrated"
    assert (tmp_path / "knot.db").exists()


def test_R69_migrate_old_to_new(tmp_path):
    """场景 a：仅 bi_agent.db → 备份 + rename + status='migrated'。"""
    old = tmp_path / "bi_agent.db"
    new = tmp_path / "knot.db"
    _make_dummy_db(old, b"original-content")

    result = migrate_db_rename(tmp_path)
    assert result["status"] == "migrated"
    assert "backup" in result
    assert new.exists()
    assert not old.exists(), "rename 后老 db 应不存在"
    # bak 名带 v044 + timestamp（沿袭 v0.4.5 R-46 命名）
    bak = Path(result["backup"])
    assert bak.exists()
    assert ".v044-" in bak.name
    assert bak.read_bytes() == b"original-content"
    assert new.read_bytes() == b"original-content"


def test_R69_both_exist_raises(tmp_path):
    """场景 d：双 db 同时存在 → RuntimeError，绝不静默 drop。"""
    _make_dummy_db(tmp_path / "bi_agent.db")
    _make_dummy_db(tmp_path / "knot.db")
    with pytest.raises(RuntimeError, match="同时存在"):
        migrate_db_rename(tmp_path)


def test_R69_idempotent_run_three_times(tmp_path):
    """跑 3 次结果一致（场景 a 后变 b）。"""
    _make_dummy_db(tmp_path / "bi_agent.db", b"data-v1")
    r1 = migrate_db_rename(tmp_path)
    r2 = migrate_db_rename(tmp_path)
    r3 = migrate_db_rename(tmp_path)
    assert r1["status"] == "migrated"
    assert r2["status"] == "already_migrated"
    assert r3["status"] == "already_migrated"
    assert (tmp_path / "knot.db").read_bytes() == b"data-v1"


def test_R69_timestamped_backup_no_overwrite(tmp_path):
    """timestamped bak 多次执行避免覆盖前次（沿袭 v0.4.5 R-46 数据丢失教训）。"""
    old = tmp_path / "bi_agent.db"
    new = tmp_path / "knot.db"
    _make_dummy_db(old, b"v1-content")
    r1 = migrate_db_rename(tmp_path)
    bak1 = Path(r1["backup"])
    assert bak1.exists()

    # 模拟用户回滚后又再次迁移
    new.rename(old)
    _make_dummy_db(old, b"v2-content")
    time.sleep(1.1)  # 保证 timestamp 后缀不同
    r2 = migrate_db_rename(tmp_path)
    bak2 = Path(r2["backup"])
    assert bak1 != bak2, "两次 bak 路径必须不同（timestamp 后缀）"
    assert bak1.exists() and bak2.exists(), "两个 bak 都应保留"


# ─── R-76 原子性异常保护 ────────────────────────────────────────────

def test_R76_atomic_rename_failure_preserves_old_db(tmp_path, monkeypatch):
    """R-76：mock rename 抛 OSError → 老 DB 保留 + bak 删除 + 原异常上抛。"""
    old = tmp_path / "bi_agent.db"
    _make_dummy_db(old, b"precious-data")

    real_rename = Path.rename

    def _flaky_rename(self, target):
        if str(self).endswith("bi_agent.db"):
            raise OSError("simulated rename failure")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", _flaky_rename)

    with pytest.raises(OSError, match="simulated rename failure"):
        migrate_db_rename(tmp_path)

    # R-76 关键：老 DB 必须仍在 + 内容未损
    assert old.exists(), "R-76：rename 失败时老 DB 必须保留"
    assert old.read_bytes() == b"precious-data"
    assert not (tmp_path / "knot.db").exists()
    bak_files = list(tmp_path.glob("bi_agent.db.v044-*.bak"))
    assert not bak_files, "R-76：rename 失败时 bak 必须删（避免误导用户）"


def test_R76_atomic_copy_failure_preserves_old_db(tmp_path, monkeypatch):
    """R-76：mock copy2 抛 OSError → 老 DB 保留 + bak 不存在 + 原异常上抛。"""
    old = tmp_path / "bi_agent.db"
    _make_dummy_db(old, b"precious-data")

    def _flaky_copy(*args, **kwargs):
        raise OSError("simulated copy failure")

    monkeypatch.setattr(shutil, "copy2", _flaky_copy)

    with pytest.raises(OSError, match="simulated copy failure"):
        migrate_db_rename(tmp_path)

    assert old.exists()
    assert old.read_bytes() == b"precious-data"
    assert not (tmp_path / "knot.db").exists()
    bak_files = list(tmp_path.glob("bi_agent.db.v044-*.bak"))
    assert not bak_files


# ─── 独立 entrypoint dry-run（守护者修订 2 双轨）───────────────────

def test_dry_run_via_subprocess_does_not_modify_files(tmp_path):
    """守护者修订 2：独立 entrypoint 支持 --dry-run，0 副作用。"""
    import os
    import subprocess
    import sys

    _make_dummy_db(tmp_path / "bi_agent.db", b"original")

    env = os.environ.copy()
    env.setdefault("BIAGENT_MASTER_KEY", "QwlGZIGjzEryd93omq5UGR5ATZ6mTMm70NmS4o331Xk=")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "knot.scripts.migrate_db_rename_v050",
            "--dry-run",
            "--data-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, f"dry-run 应成功；stderr: {result.stderr}"
    assert (tmp_path / "bi_agent.db").read_bytes() == b"original"
    assert not (tmp_path / "knot.db").exists()
    assert not list(tmp_path.glob("*.bak")), "dry-run 不应创建 bak"
