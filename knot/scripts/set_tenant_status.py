"""knot/scripts/set_tenant_status.py — 改一家公司的服务状态（active / suspended）· v0.9.20 P-c。

用法（**两个参数都必填**）：
  python -m knot.scripts.set_tenant_status --tenant <slug|id> --status active
  python -m knot.scripts.set_tenant_status --tenant <slug|id> --status suspended
  python -m knot.scripts.set_tenant_status --tenant <slug|id> --status suspended --dry-run

═══ 为什么要有这个工具 ═══

lift R-T-GATE 之后，「把某家公司改成 active」= **让第二家真的进来** = 整个平台影响面最大的动作。
而在本工具之前它**没有任何代码路径** —— 只能运维直接 `sqlite3 UPDATE`
⇒ **不留痕**，而 v0.9.8 专门为平台变更建的审计写口 `tenant_repo.update_tenant`
（审计 INSERT 与动作**同连接、同事务、单次 commit** ⇒ 不存在「做了但没记」）**零调用方**。

⇒ 本工具的承重职责只有一条：**让这个动作走那个写口。**

═══ ⛔ 破坏性工具不得有默认目标（v0.9.15 一次真实事故换来的纪律）═══

`--tenant` 与 `--status` **都必填、都无默认值**，缺任一即拒绝执行（非 0 退出 + **零写入**）。
⚠️ 尤其 `--status` **不给默认** —— 「默认激活」正是最危险的那个默认。
⚠️ 写之前**先把目标说出来**（id + slug + 当前状态）：v0.9.15 事故的核心不是命令失败，
   而是**动作静默作用在错误的对象上**而运维看不出异常。

═══ ⚠️ 本工具今天能做什么、不能做什么（诚实边界）═══

**能**：把非起源租户 active → suspended（**这正是 lift 的回退路径**：出问题时先降到 1 active 再换镜像）。
**不能**：激活非起源租户 —— `update_tenant` 里有一道**临时代偿门**挡着，
        因为仍有 3 条能力是「租户盲」的（详见下方 `_gate_blockers` 与 tenant_repo 里那道门的注释）。
**无意义**：改起源租户 —— 它恒为 active 且不允许被停用（tenant_repo 另一道守卫）。

⚠️ 运维直接 `sqlite3 UPDATE` 仍绕过本工具与那两道门 ⇒
   只声称「**经本工具的**状态变更被审计」，**不声称**「所有状态变更都被审计」。
"""
import argparse
import sys

from knot.repositories import tenant_repo

#: 摘掉代偿门之前必须先域化的能力 —— **与 `tenant_repo` 里那道门的清单是同一份事实**。
#: ⚠️ 刻意在这里**复述**而不是 import 一份共享常量：那道门抛的是 `ValueError`，
#:    本工具需要在**调用写口之前**就把它们说出来（见 §「一次报全」）。
#:    两处漂开的风险由 `tests/test_file_catalog_owner_gate.py::test_rtgate_compensating_gate_still_blocks_activation`
#:    兜住 —— 它断言门的消息里含这三条的关键词。
_GATE_BLOCKERS = (
    "SQL 数据源出网**零 allowlist**（该租户 admin 可让服务端连部署方内网任意 host:port）",
    "LLM API key 回退到**进程 env**（该租户不填 key 就花部署方的账、以部署方账号出境）",
    "新租户 admin 行**预填部署方内网 DB 坐标**",
)


def _allowlist_columns() -> tuple[str, ...]:
    """**派生**出「必须配好才能激活」的 allowlist 列名 —— 严禁硬编。

    ⚠️ 硬编两个名字 ⇒ **第三份 allowlist 落地时本预检静默漏检**
    （v0.9.18 `_REDACTED_IN_AUDIT` 的原话：「只补第二个名字的话，第三份来时会原样重演，
    且没有任何东西会提醒你」）。
    与 `knot/scripts/show_tenant_allowlists._managed_columns()` 同一派生口径。
    """
    return tuple(f for f in tenant_repo._MUTABLE_TENANT_FIELDS if f.startswith("allowed_"))


def _activation_preflight(row: dict) -> list[str]:
    """激活前必须成立的条件；返回**未满足**的项（空 = 通过）。

    ⚠️ **判据锚在「库里真的建出了什么」，不是「目录在不在」** —— `get_conn()` 会
    「缺目录就建、缺文件就建」⇒ 判「`db_dir` 目录存在」**恒真**，是个空判据。
    ⇒ 改判「该租户库里 `users` 表存在**且有 admin 行**」。
    """
    missing: list[str] = []

    for col in _allowlist_columns():
        if row.get(col) is None:
            missing.append(
                f"`{col}` **未配置（NULL）** —— 三态里 NULL 对非起源租户**没有回退** "
                f"⇒ 该租户相关出网会全部静默拒绝，而那与 bug 不可区分。"
                f"（要「禁止出网」请显式写空串 `''`，那是另一种语义。）"
            )

    from knot.core import tenant_context as _tc
    tok = _tc.set_active_tenant(row)
    try:
        from knot.repositories.base import get_conn
        conn = get_conn()
        try:
            has_users = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            n_admin = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin'"
            ).fetchone()[0] if has_users else 0
        finally:
            conn.close()
    finally:
        _tc.reset_active_tenant(tok)

    if not has_users:
        missing.append("该租户库里**没有 `users` 表** —— 库还没初始化（首次登录会 500）。")
    elif n_admin == 0:
        missing.append("该租户库里**没有 admin 用户** —— 没人能登进去。")

    return missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="改一家公司的服务状态（active / suspended）。两个参数都必填。",
    )
    ap.add_argument("--tenant", required=True, help="目标租户的 slug 或 id（**必填，无默认**）")
    ap.add_argument("--status", required=True, choices=("active", "suspended"),
                    help="目标状态（**必填，无默认** —— 「默认激活」是最危险的默认）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将要发生什么，**零写入**")
    args = ap.parse_args(argv)

    # ⚠️ 先断言平台库**真的存在** —— `get_platform_conn` 用 `sqlite3.connect`，
    #    路径写错会**新建一个空库**，然后「找不到该租户」，而运维会以为是租户没了。
    plat = tenant_repo._platform_db_path()
    if not plat.exists():
        print(f"⛔ 平台库不存在：{plat}\n"
              f"   （若这个路径看着不对，检查 SQLITE_DB_PATH / KNOT_DATA_DIR）", file=sys.stderr)
        return 2
    print(f"平台库：{plat}")

    # ⚠️ 用 `get_*` 不是 `resolve_*` —— 本文件的命名约定：`get_*` 原样取行、**不过滤 status**；
    #    `resolve_*` 只返「可服务」的。本工具的目标**通常正是 suspended 的那些**
    #    ⇒ 用 `resolve_*` 会把它们看成「不存在」。
    row = (tenant_repo.get_tenant(int(args.tenant)) if str(args.tenant).isdigit()
           else tenant_repo.get_tenant_by_slug(args.tenant))
    if row is None:
        print(f"⛔ 找不到租户 {args.tenant!r} —— **零写入**，未做任何改动。", file=sys.stderr)
        return 3

    # ⭐ 写之前先把目标说出来（v0.9.15 纪律）
    print(f"目标：id={row['id']} slug={row['slug']!r} name={row['name']!r} "
          f"当前状态={row['status']!r} → 目标状态={args.status!r}")

    if row["status"] == args.status:
        print(f"✓ 无需改动 —— 它**本来就是** {args.status!r}。（未写入、未记审计）")
        return 0

    # ── 激活：把**所有**阻塞项一次报全（别让运维一轮一轮试）────────────────
    if args.status == "active":
        blockers = [f"[代偿门] {b}" for b in _GATE_BLOCKERS]
        blockers += [f"[预检] {m}" for m in _activation_preflight(row)]
        print("\n⛔ **拒绝激活** —— 下列各项都要先解决：", file=sys.stderr)
        for i, b in enumerate(blockers, 1):
            print(f"  {i}. {b}", file=sys.stderr)
        print(
            "\n⇒ [代偿门] 那几条清完后，删掉 `tenant_repo.update_tenant` 里那道门"
            "（注释里写了摘除条件）即可激活。\n"
            "⇒ [预检] 那几条是这一家自己的配置问题，现在就能改。\n"
            "⚠️ **零写入**，未做任何改动。",
            file=sys.stderr,
        )
        return 4

    # ── 停用（今天唯一真能落地的操作，也是 lift 的回退路径）──────────────
    if args.dry_run:
        print(f"[dry-run] 将把 id={row['id']} ({row['slug']!r}) 从 "
              f"{row['status']!r} 改为 {args.status!r} —— **本次零写入**。")
        return 0

    if row["status"] == "active":
        print("\n⚠️ 停用一家正在服务的公司 —— 它的用户会**立刻**无法登录/无法访问。")

    # ⚠️ 带上 actor / source —— 审计要能看出「**谁经什么路径**改的」。
    #    actor 用 `cli:set_tenant_status`（与 cli_audit 的 `cli:<显式传入>` 口径一致）：
    #    运维在库外执行、**没有租户内身份**，编一个用户名比留空更糟。
    ok = tenant_repo.update_tenant(
        row["id"], status=args.status,
        actor="cli:set_tenant_status", source="cli",
    )
    if not ok:
        # update_tenant 对「没有可改字段 / 行不存在」返 False、**不抛、零审计**
        print("⛔ 写口返回 False —— **未改动、未记审计**。请核对目标是否存在。", file=sys.stderr)
        return 5

    print(f"✓ 已改为 {args.status!r}（已记入 platform_audit，与动作同一事务）")
    print("⚠️ 提醒：定时报表调度是**逐租户**触发的（`/api/bi/scheduler/tick` 的 `tenant` 必填）"
          " —— 状态变了记得同步调度配置，否则该公司的定时报表会**不运行且零报错**。")
    return 0


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
