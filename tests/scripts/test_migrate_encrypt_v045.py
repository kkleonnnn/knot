"""tests/scripts/test_migrate_encrypt_v045.py — v0.4.5 commit #3 守护测试（TDD）。

覆盖：
- R-36 幂等：见 enc_v1: 跳过；多次运行结果一致
- R-41 独立 entrypoint：grep main.py / base.py 零命中
- R-46 自动 bak（dry-run 不创建；timestamp 后缀避免覆盖；master key 缺失先 fail）
- R-46-Tx 每表单事务（中断单表回滚；其他表不受影响）
- dry-run 0 副作用（DB SHA256 一致）
"""
import hashlib
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from knot.core.crypto import ENC_PREFIX, encrypt
from knot.core.crypto.fernet import get_crypto_adapter
from knot.repositories import data_source_repo, settings_repo, user_repo


def _db_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _seed_legacy_plaintext(db_path: str):
    """模拟 v0.4.4 老 DB：直接走 sqlite3 写明文，绕过 repo 加密 wrap。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, api_key, "
        "openrouter_api_key, embedding_api_key, doris_password) "
        "VALUES ('legacy1', 'h', 'analyst', 'sk-old', 'or-old', 'em-old', 'doris-old')"
    )
    conn.execute(
        "INSERT INTO data_sources (user_id, name, db_host, db_port, db_user, db_password, db_database) "
        "VALUES (NULL, 'ds-legacy', 'h', 9030, 'u', 'ds-old-pw', 'db')"
    )
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('openrouter_api_key', 'global-or-plain')"
    )
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('default_model', 'claude-haiku')"
    )
    conn.commit()
    conn.close()


# ─── R-36 幂等 ─────────────────────────────────────────────────────────

def test_migrate_encrypts_all_targets(tmp_db_path):
    """全覆盖 — 老明文跑迁移后全部带 enc_v1: 前缀。

    ⚠️ v0.9.11 口径变更：落点从硬编 7 处改为**派生 11 处**（+totp_secret / http_config
    / lark_app_secret / telegram_bot_token）；本测的 seed 只覆盖其中 6 个字段，故仍用 >= 断言。
    「恰好 11」由 test_Sa3_targets_cover_full_sensitive_set 精确守。
    """
    _seed_legacy_plaintext(tmp_db_path)
    from knot.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=False)
    assert stats["rows_scanned"] >= 3  # 至少 1 user + 1 ds + 1 sensitive setting
    assert stats["fields_encrypted"] >= 3

    conn = sqlite3.connect(tmp_db_path)
    for col in ("api_key", "openrouter_api_key", "embedding_api_key", "doris_password"):
        v = conn.execute(f"SELECT {col} FROM users WHERE username='legacy1'").fetchone()[0]
        assert v.startswith(ENC_PREFIX), f"users.{col} 应已加密"
    ds_pw = conn.execute("SELECT db_password FROM data_sources WHERE name='ds-legacy'").fetchone()[0]
    assert ds_pw.startswith(ENC_PREFIX)
    or_v = conn.execute("SELECT value FROM app_settings WHERE key='openrouter_api_key'").fetchone()[0]
    assert or_v.startswith(ENC_PREFIX)
    # 非白名单 default_model 不应加密
    dm = conn.execute("SELECT value FROM app_settings WHERE key='default_model'").fetchone()[0]
    assert not dm.startswith(ENC_PREFIX)
    conn.close()


def test_R36_migrate_idempotent_run_twice_noop(tmp_db_path):
    """R-36：跑两次第二次 encrypted=0；DB content 不变（防"看似 noop 实际重新加密"）。"""
    _seed_legacy_plaintext(tmp_db_path)
    from knot.scripts import migrate_encrypt_v045
    migrate_encrypt_v045.migrate(dry_run=False)
    sha_after_first = _db_sha256(tmp_db_path)

    stats2 = migrate_encrypt_v045.migrate(dry_run=False)
    assert stats2["fields_encrypted"] == 0, "R-36：第二次跑应零加密"
    sha_after_second = _db_sha256(tmp_db_path)
    assert sha_after_first == sha_after_second, "R-36：DB content 不应变（无重复加密）"


def test_migrate_skips_already_encrypted_row(tmp_db_path):
    """混合行：已加密 + 老明文同时存在，迁移只动老明文。"""
    user_repo.create_user("new", "h", "N", "analyst", "h", 9030, "u", "fresh-pw", "db")  # 已加密
    _seed_legacy_plaintext(tmp_db_path)  # 老明文

    from knot.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=False)

    # legacy1 老明文应被加密；new 用户的 fresh-pw 已加密 → skipped
    assert stats["fields_encrypted"] >= 3
    # 验证 new 用户 doris_password 通过 repo 解密仍是 fresh-pw（未被二次加密）
    new_user = user_repo.get_user_by_username("new")
    assert new_user["doris_password"] == "fresh-pw"


# ─── dry-run 0 副作用 ────────────────────────────────────────────────

def test_migrate_dry_run_does_not_write(tmp_db_path):
    _seed_legacy_plaintext(tmp_db_path)
    sha_before = _db_sha256(tmp_db_path)

    from knot.scripts import migrate_encrypt_v045
    stats = migrate_encrypt_v045.migrate(dry_run=True)

    sha_after = _db_sha256(tmp_db_path)
    assert sha_before == sha_after, "dry-run DB 不应被写"
    # dry-run 应统计 would_encrypt 数量
    assert stats["fields_encrypted"] >= 3, "dry-run 仍应统计 would-encrypt 数"

    # 守护者提示：dry-run 不创建 bak
    db_dir = Path(tmp_db_path).parent
    bak_files = list(db_dir.glob(f"{Path(tmp_db_path).name}*.bak"))
    assert not bak_files, "dry-run 严禁创建 .bak"


# ─── R-46 自动备份 ───────────────────────────────────────────────────

def test_R46_migrate_creates_backup_before_write(tmp_db_path):
    """R-46：写第一个 UPDATE 之前生成 bak；bak 的**逻辑内容** = 迁移前的库。

    ⚠️⚠️ **v0.9.11 oracle 重写（本测原来的绿是「因为错误的理由」—— v3.1-B #8）**：
    原断言是 `sha256(bak) == sha256(db)`，即要求**逐字节文件拷贝**。
    而「WAL 模式下逐字节拷主文件」**恰恰就是那个缺陷本身**（未 checkpoint 的已提交数据不在主文件里）
    ⇒ **这条测在祝福缺陷**：任何改用 SQLite backup API 的正确实现都会被它判红。
    ⇒ 处置**不是删**（「备份得能用来回滚」这个断言仍值钱），是**换 oracle**：
       比**逻辑内容**（迁移前的明文值都在 bak 里、且没被加密），不比字节。

    ⚠️ **与 `test_Sa1_...` 的分工（Stage 4 note · 实测过，别只照描述理解）**：
    本测**是内容级**的（断言迁移前的明文原值在 bak 里），但它 seed 的数据在连接关闭后**已被
    checkpoint 进主文件** ⇒ **`shutil.copy2` 也拷得到** ⇒ **本测在 copy2 回归下会通过**。
    **实测**：把备份退回 `copy2` ⇒ `1 failed, 14 passed`，红的**只有 Sa1**。
    ⇒ **WAL-safe 这条性质唯一的守护者是 Sa1；删掉 Sa1，本测单独会祝福一个 copy2 备份。**
    """
    _seed_legacy_plaintext(tmp_db_path)

    from knot.scripts import migrate_encrypt_v045
    bak_path = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]

    assert bak_path is not None
    assert Path(bak_path).exists(), "bak 必须生成"
    assert ".v044" in bak_path, "bak 命名带版本号便于回溯"

    # 内容级 oracle：bak 里是**迁移前**的样子（明文原值），源库里已是密文
    b = sqlite3.connect(f"file:{bak_path}?mode=ro", uri=True)
    assert b.execute("PRAGMA quick_check").fetchone()[0] == "ok", "bak 必须是完好的库"
    bak_pw = b.execute("SELECT doris_password FROM users WHERE username='legacy1'").fetchone()[0]
    bak_or = b.execute("SELECT value FROM app_settings WHERE key='openrouter_api_key'").fetchone()[0]
    b.close()
    assert bak_pw == "doris-old", f"bak 应保留迁移前的明文原值；实际 {bak_pw!r}"
    assert bak_or == "global-or-plain", f"bak 应保留迁移前的明文原值；实际 {bak_or!r}"

    live = sqlite3.connect(tmp_db_path)
    now_pw = live.execute("SELECT doris_password FROM users WHERE username='legacy1'").fetchone()[0]
    live.close()
    assert now_pw.startswith(ENC_PREFIX), "源库应已加密（证明 bak 确实是**写之前**的快照）"

    # a1' 备份权限收窄 0600（里面是未加密之前的明文凭据）
    assert oct(os.stat(bak_path).st_mode & 0o777) == "0o600", (
        f"bak 权限应 0600；实际 {oct(os.stat(bak_path).st_mode & 0o777)}"
    )


def test_R46_bak_timestamped_does_not_overwrite_previous(tmp_db_path):
    """守护者提示：多次跑应用 timestamp 后缀，不覆盖前一次 bak（数据丢失教训）。"""
    _seed_legacy_plaintext(tmp_db_path)

    from knot.scripts import migrate_encrypt_v045
    bak1 = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]
    # 故意改 DB 模拟"第一次 bak 后又有变更"
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('post1', 'h', 'analyst')")
    conn.commit()
    conn.close()
    # 解开"已加密"使第二次跑还有事可做（确实有新明文）— 通过新加用户绕开 already-encrypted 跳过
    _seed_legacy_plaintext_more(tmp_db_path)

    bak2 = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]

    assert bak1 != bak2, "两次 bak 路径必须不同（timestamp 后缀）"
    assert Path(bak1).exists() and Path(bak2).exists(), "两个 bak 都应保留"


def _seed_legacy_plaintext_more(db_path: str):
    """补一些老明文，确保第二次迁移有事可做。"""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO users (username, password_hash, role, api_key) "
        "VALUES ('legacy2', 'h', 'analyst', 'sk-second-batch')"
    )
    conn.commit()
    conn.close()


# ─── R-46-Tx 每表单事务 ──────────────────────────────────────────────

def test_R46_Tx_per_table_transaction_rollback_on_error(tmp_db_path, monkeypatch):
    """R-46-Tx：mock encrypt 在处理 data_sources 时抛 ValueError →
    data_sources 全表回滚；users 表（已先处理）应保持加密；app_settings（之后）应跳过。"""
    _seed_legacy_plaintext(tmp_db_path)

    from knot.scripts import migrate_encrypt_v045

    call_count = {"n": 0}
    real_encrypt = migrate_encrypt_v045.encrypt

    def _flaky_encrypt(s):
        call_count["n"] += 1
        # users 4 列已加密后；进入 data_sources 抛错
        if "ds-old-pw" in s:
            raise ValueError("simulated mid-table failure")
        return real_encrypt(s)

    monkeypatch.setattr(migrate_encrypt_v045, "encrypt", _flaky_encrypt)

    with pytest.raises(ValueError):
        migrate_encrypt_v045.migrate(dry_run=False)

    conn = sqlite3.connect(tmp_db_path)
    # users 表已 commit → 应已加密
    api = conn.execute("SELECT api_key FROM users WHERE username='legacy1'").fetchone()[0]
    assert api.startswith(ENC_PREFIX), "users 表先处理且已 commit，应保持加密"
    # data_sources 表 rollback → 仍是明文
    ds_pw = conn.execute("SELECT db_password FROM data_sources WHERE name='ds-legacy'").fetchone()[0]
    assert ds_pw == "ds-old-pw", "data_sources 表中失败应整表回滚"
    conn.close()


# ─── R-41 独立 entrypoint ────────────────────────────────────────────

def test_R41_migrate_not_called_in_main_or_base():
    """R-41：grep 守护 — main.py / base.py 不得引用 migrate_encrypt。"""
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "migrate_encrypt", "knot/main.py", "knot/repositories/base.py"],
        capture_output=True, text=True,
        check=False,
    )
    assert result.returncode != 0, f"R-41：startup hook 不应引用 migrate；命中：{result.stdout}"


# ─── 守护者提示：master key 缺失先 fail，不创建 bak ───────────────────

def test_R46_no_master_key_fails_before_backup(tmp_db_path, monkeypatch):
    """守护者提示：master key 缺失立即 fail，不创建 bak（避免浪费磁盘 / 误导）。"""
    monkeypatch.delenv("KNOT_MASTER_KEY", raising=False)
    get_crypto_adapter.cache_clear()

    from knot.core.crypto.fernet import CryptoConfigError
    from knot.scripts import migrate_encrypt_v045
    with pytest.raises(CryptoConfigError):
        migrate_encrypt_v045.migrate(dry_run=False)

    # 关键：不应创建 bak
    db_dir = Path(tmp_db_path).parent
    bak_files = list(db_dir.glob(f"{Path(tmp_db_path).name}*.bak"))
    assert not bak_files, "master key 缺失时严禁先创建 bak"


# ═══ v0.9.11 硬化哨兵 Sa1–Sa6（Stage 2 Codex R2/R3/R5/R6/R8 + Stage 3 守护者）═══

def _logical_dump(path: str) -> str:
    """整库**逻辑转储**（WAL-safe 的「内容逐字节」比较基准）。

    ⚠️ **为什么不比主文件字节**：租户库是 WAL 模式，写入先落 `-wal`
    ⇒ 主文件字节可以「没变」而数据其实已被改写 ⇒ 那个 oracle **表示不了要排除的事件**（v3.1-B #2）。
    而 `PRAGMA wal_checkpoint` 本身会重排页 ⇒ checkpoint 后再比字节又会**假红**。
    ⇒ 正解是比 `iterdump()` —— 完整、WAL-safe、且逐字符可比。
    """
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return "\n".join(c.iterdump())
    finally:
        c.close()


def test_Sa1_backup_is_wal_safe_includes_uncheckpointed_commits(tmp_db_path):
    """a1/R3 —— 备份必须含**已提交但未 checkpoint**的数据（WAL 模式下的真实形态）。

    revert-to-bad：把 `_make_backup` 里的 `_backup_db_atomic` 换回 `shutil.copy2` ⇒ 本测转红。
    ⭐ **实测「唯一抓住」**：该 revert 下全文件 `1 failed, 14 passed` —— **只有本测红**。
    `test_R46_migrate_creates_backup_before_write` 虽然也是内容级的，但它的数据已被 checkpoint
    进主文件 ⇒ copy2 也拷得到 ⇒ **它通过**。
    ⇒ **本测是 WAL-safe 这条性质的唯一守护者，删它则无人再守**（Stage 4 note：两处 docstring 互引）。
    """
    _seed_legacy_plaintext(tmp_db_path)
    live = sqlite3.connect(tmp_db_path)          # 保持开着 = 服务在跑，末连接不关则不 checkpoint
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("INSERT INTO users (username, password_hash, role, api_key) "
                 "VALUES ('wal-only', 'h', 'analyst', 'sk-wal-only')")
    live.commit()
    try:
        # ⭐ v3.1-B #2：先证明**注入真的产生了要测的条件** —— 否则本测是空跑
        probe = tmp_db_path + ".copy2probe"
        shutil.copy2(tmp_db_path, probe)
        p = sqlite3.connect(f"file:{probe}?mode=ro", uri=True)
        in_main_file = p.execute(
            "SELECT COUNT(*) FROM users WHERE username='wal-only'").fetchone()[0]
        p.close()
        os.unlink(probe)
        assert in_main_file == 0, (
            "注入前提不成立：该行已经在主文件里了（WAL 已被 checkpoint）"
            " ⇒ 本测无法区分 copy2 与 backup API，等于空跑"
        )

        from knot.scripts import migrate_encrypt_v045
        bak = migrate_encrypt_v045.migrate(dry_run=False)["backup_path"]

        b = sqlite3.connect(f"file:{bak}?mode=ro", uri=True)
        try:
            n = b.execute("SELECT COUNT(*) FROM users WHERE username='wal-only'").fetchone()[0]
        finally:
            b.close()
        assert n == 1, (
            "备份丢了已提交但未 checkpoint 的行 —— 备份不是 WAL-safe。\n"
            "    这正是 v0.4.5 起 `shutil.copy2` 的缺陷：只拷主文件，而 WAL 里的已提交数据不在其中，\n"
            "    且 `PRAGMA quick_check` 仍报 ok ⇒ 无法察觉。修：走 sqlite backup API。"
        )
    finally:
        live.close()


def test_Sa2_wrong_master_key_preflight_zero_writes_zero_backup(tmp_db_path, monkeypatch):
    """a2/R2 —— 换一把**格式合法的错 key** ⇒ preflight 拦下，**零写入 + 零备份**。

    这条守的是**不可逆**路径：否则旧密文被前缀跳过、新明文用新 key 加密，脚本 exit 0，
    而没有任何一把 key 能解全库；运维丢掉旧 key 后凭据永久不可恢复。
    ⭐ 「零写入」按**内容逐字符**比（`iterdump`），不是比行数 ——
       **行数相同而值被改写，正是本测最需要排除的事件**（守护者点名）。
    """
    from cryptography.fernet import Fernet

    from knot.scripts import migrate_encrypt_v045
    _seed_legacy_plaintext(tmp_db_path)
    migrate_encrypt_v045.migrate(dry_run=False)          # 用 key A 加密
    for f in Path(tmp_db_path).parent.glob(f"{Path(tmp_db_path).name}*.bak"):
        f.unlink()                                        # 清掉第一次的 bak，便于断「零备份」

    _seed_legacy_plaintext_more(tmp_db_path)              # 留一条新明文 ⇒ 脚本确实有事可做
    before = _logical_dump(tmp_db_path)

    monkeypatch.setenv("KNOT_MASTER_KEY", Fernet.generate_key().decode())   # key B：格式合法但不对
    get_crypto_adapter.cache_clear()

    # ⚠️ **刻意不用 `pytest.raises` 包住** —— 那会让「抛没抛」成为检查真属性的前置门：
    #    摘掉 preflight 后测试停在 DID NOT RAISE，而**零写入 / 零备份这两条根本不执行**
    #    ⇒ revert 证明不了它们有效（v0.9.6「消息永不显示」的同族形态，本片实跑撞到）。
    #    真正的安全属性是「零写入 + 零备份」，抛异常只是它的实现方式之一。
    raised = None
    try:
        migrate_encrypt_v045.migrate(dry_run=False)
    except Exception as e:   # 捕 Exception 而非 RuntimeError：「零写入」必须**无论怎么失败**都成立
        raised = e

    assert _logical_dump(tmp_db_path) == before, (
        "❌ 错 key 下发生了写入 —— 这就是**双 key 混库**：旧密文被前缀跳过、新明文用新 key 加密，\n"
        "    ⇒ 没有任何一把 key 能解全库，且**不可逆**（运维丢掉旧 key 后凭据永久不可恢复）。"
    )
    assert not list(Path(tmp_db_path).parent.glob(f"{Path(tmp_db_path).name}*.bak")), (
        "❌ 错 key 下建了备份 —— 那份备份就是磁盘上一份**新的明文凭据副本**，\n"
        "    正是本次事故响应正在清理的那个危害。preflight 必须在建备份**之前**。"
    )
    assert raised is not None and "preflight" in str(raised), (
        f"❌ 错 key 应被 preflight 拦下并给出可操作的说明；实际 raised={raised!r}"
    )


def test_Sa3_targets_cover_full_sensitive_set(tmp_db_path):
    """a7/R6 —— 迁移覆盖面 **== 三个真相源的并集**（v0.9.11 前是 7/11，漏 4 个后增列）。

    revert-to-bad：把 `_derive_targets` 换回硬编清单 ⇒ 本测红。
    """
    import re

    from knot.repositories.data_source_repo import _DS_ENCRYPTED_COLS
    from knot.repositories.settings_repo import _SENSITIVE_KEYS
    from knot.repositories.user_repo import _USER_ENCRYPTED_COLS
    from knot.scripts.migrate_encrypt_v045 import _derive_targets

    truth = ({("users", c) for c in _USER_ENCRYPTED_COLS}
             | {("data_sources", c) for c in _DS_ENCRYPTED_COLS}
             | {("app_settings", k) for k in _SENSITIVE_KEYS})
    covered = set()
    for table, _id, cols, where in _derive_targets():
        if table == "app_settings":
            covered |= {(table, m) for m in re.findall(r"'([^']+)'", where or "")}
        else:
            covered |= {(table, c) for c in cols}
    assert covered == truth, (
        f"迁移覆盖面 ≠ 敏感落点全集。漏扫：{sorted(truth - covered)}；多扫：{sorted(covered - truth)}\n"
        "    v0.9.11 前实测 7/11 —— 漏 users.totp_secret / data_sources.http_config /\n"
        "    app_settings.lark_app_secret / .telegram_bot_token（全是 v0.4.5 之后新增的）。"
    )


def test_Sa4_targets_are_deterministically_ordered(tmp_db_path):
    """a4/R6 —— 表序与列序**确定** ⇒ 同一注入点必给同一失败位置 ⇒ **事故可复现**。

    `settings_repo._SENSITIVE_KEYS` 实测是 `frozenset`（无序已坐实）；不排序则每次跑顺序可变。
    """
    import re

    from knot.scripts.migrate_encrypt_v045 import _derive_targets

    # ⚠️ **不要用「同进程连跑 N 次结果相同」当判据 —— 那是空 oracle**（本片自捉）：
    #    `frozenset` 的迭代顺序在**同一进程内是稳定的**（哈希随机化按进程一次性生效）
    #    ⇒ 就算把 `sorted()` 全摘掉，连跑 5 次也必然相同 ⇒ 判据表示不了要排除的事件（v3.1-B #2）。
    #    真正保证跨进程确定性的性质是「**有序**」本身，所以直接断言有序。
    for table, _id, cols, where in _derive_targets():
        assert cols == sorted(cols), f"{table} 列序未排序：{cols}"
        if where:
            keys = re.findall(r"'([^']+)'", where)
            assert keys == sorted(keys), (
                f"{table} 的 WHERE key 列表未排序：{keys}\n"
                "    它来自 `_SENSITIVE_KEYS`（frozenset，无序）⇒ 不排序则**跨进程**迁移顺序可变\n"
                "    ⇒ 失败位置每次不同 ⇒ **事故不可复现**。"
            )


def test_Sa5_stale_schema_raises_explicitly_and_does_not_write(tmp_db_path):
    """a5/R8 —— 旧库缺敏感列 ⇒ **显式报错**，不静默跳过、不代跑 schema 迁移、不建备份。

    静默跳过会让「11/11 覆盖」在旧库上**变成谎言**。
    """
    from knot.scripts import migrate_encrypt_v045
    _seed_legacy_plaintext(tmp_db_path)
    conn = sqlite3.connect(tmp_db_path)
    conn.execute("ALTER TABLE users DROP COLUMN totp_secret")   # 模拟 v0.6.2 之前的旧库
    conn.commit()
    conn.close()
    before = _logical_dump(tmp_db_path)

    raised = None   # 同 Sa2：安全属性（零写入/零备份）不得以「抛没抛」为前置门
    try:
        migrate_encrypt_v045.migrate(dry_run=False)
    except Exception as e:   # 摘掉 schema 校验后是裸 sqlite3.OperationalError —— 也要走到下面两条
        raised = e

    assert _logical_dump(tmp_db_path) == before, "❌ schema 不就绪时发生了写入"
    assert not list(Path(tmp_db_path).parent.glob(f"{Path(tmp_db_path).name}*.bak")), \
        "❌ schema 不就绪时建了备份"
    assert raised is not None and "schema 比代码旧" in str(raised), (
        f"❌ 缺列时必须**显式报错**（静默跳过会让「11/11 覆盖」在旧库上变成谎言）；实际 raised={raised!r}"
    )


def test_Sa6_refuses_to_claim_success_when_plaintext_remains(tmp_db_path, monkeypatch):
    """a3 —— 跑完**在同一次运行内**核实不变量；仍有明文则 raise，**不许声称成功**。

    这正是 2026-05-09 事故的根因：脚本「声称完成」与「核实完成」是分开的
    ⇒ 它建了备份、一个字节没写、返回成功，三个月无人察觉。
    """
    from knot.scripts import migrate_encrypt_v045
    _seed_legacy_plaintext(tmp_db_path)
    monkeypatch.setattr(migrate_encrypt_v045, "encrypt", lambda s: s)   # 加密变恒等 = 什么也没干

    try:
        stats = migrate_encrypt_v045.migrate(dry_run=False)
    except RuntimeError as e:
        assert "拒绝声称成功" in str(e), f"应是后置校验拒绝声称成功；实际：{e}"
    else:
        pytest.fail(
            "❌ 脚本**声称成功**而不变量并未建立（返回 " + repr(stats) + "）。\n"
            "    这正是 2026-05-09 事故的形状：建了备份、一个字节没写、返回成功，三个月无人察觉。\n"
            "    ⇒ 「声称完成」与「核实完成」必须在**同一次运行内**。"
        )
