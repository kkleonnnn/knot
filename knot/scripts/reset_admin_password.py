"""knot/scripts/reset_admin_password.py — 重置某个租户的 admin 口令（v0.8.20 F7 · v0.9.15 强制 `--tenant`）。

首启竞态补救 / 口令遗失时用。重置后 `must_change_password=1`（首登须改）。

用法（`--tenant` **必填**）：
  python -m knot.scripts.reset_admin_password --tenant <slug|id>
  KNOT_INITIAL_ADMIN_PASSWORD=<pwd> python -m knot.scripts.reset_admin_password --tenant <slug|id>

═══ ⛔ v0.9.15：`--tenant` 为什么是**必填**而不是「可选 + 回退唯一 active 租户」═══

**这条是一次真实事故换来的**（Stage 4 守护者 #1 + 我的破坏性验证）：
本脚本此前**完全没有参数解析** ⇒ 有人按 v0.9.15 开通端点 409 消息的指引执行
`… --tenant <slug>`，那个 flag 被 **argparse 不存在而静默吞掉**，脚本照常跑
`resolve_single_tenant()` ⇒ **重置了「唯一 active 租户」（= 起源租户 / 部署方自己）的 admin 口令**，
并打印 `✓ 已重置`。**运维看不出任何异常。**

⭐ **这比「报 `unrecognized arguments`」糟得多**：不是命令失败，是**动作静默作用在错误的对象上**。
⇒ 修法必须是**强制**：
  · **破坏性工具不得有默认目标。** 缺 `--tenant` 即拒绝执行（非 0 退出、零写入）。
  · ⛔ **严禁**做成「可选，缺省回退唯一 active 租户」—— 同一个事故会**原样复发**，
    而那个回退形态正是本仓 v0.9.4 记过的坑（登录 `company` 可选 ⇒ lift 后 fail-open）。
  · **写之前先把目标说出来**（id + slug）—— 事故的核心是「动作发生了而对象没被说出来」；
    这就是本仓「消息挂在事情真的发生的那一行」用在 CLI 上的形态。

⚠️ **口令经 stdout 交付，本脚本无法约束下游**（守护者登记的机制观察）：
任何自动捕获脚本输出的地方（CI 日志 / 终端记录 / checkpoint 工具 / 对话转录）都会**留存它**。
这与 v0.9.15 d3「口令只在响应体返回一次 + `Cache-Control: no-store`」同族，
但 CLI 这条**没有** `no-store` 之类的边界可用 ⇒ 只能显式告警（见末尾输出）。
"""
import argparse
import os
import secrets
import sys

import bcrypt

from knot.repositories.base import get_conn, init_db
from knot.services import cli_audit


def _resolve_target(spec: str) -> dict:
    """把 `--tenant` 的值解析成租户行（接受 slug 或数字 id）。

    ⚠️ 用 `get_tenant*`（**不过滤 status**）而不是 `resolve_*`：本脚本的正当用途之一
    就是给一个**刚开通、还是 `suspended`** 的租户重置口令 —— 而 `resolve_*` 看不见它们
    （那正是 v0.9.15 Stage 4 守护者指出「这个恢复路径到不了 suspended 租户」的根因）。
    """
    from knot.repositories import tenant_repo as _tr

    row = _tr.get_tenant(int(spec)) if spec.isdigit() else _tr.get_tenant_by_slug(spec)
    if row is None:
        print(
            f"✗ 找不到租户 {spec!r}（按 {'id' if spec.isdigit() else 'slug'} 查）。\n"
            "  ⇒ 用 `GET /api/platform/tenants` 列出现有租户；**不要**靠 `ls data/tenants/` 猜"
            "（`db_dir` 是服务端生成的不透明随机串，刻意不可辨识）。",
            file=sys.stderr,
        )
        sys.exit(2)
    return row


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="重置指定租户的 admin 口令（--tenant 必填 —— 破坏性工具不得有默认目标）",
    )
    ap.add_argument(
        "--tenant",
        required=True,          # ⛔ 必填：缺省即拒绝（见模块 docstring 的事故记录）
        metavar="<slug|id>",
        help="目标租户的 slug 或数字 id。**必填** —— 缺它本脚本拒绝执行，不回退任何默认目标。",
    )
    args = ap.parse_args(argv)

    from knot.core import tenant_context as _tc
    from knot.repositories import tenant_repo as _tr

    _tr.init_platform_db()      # 幂等：只保证平台库形状；⚠️ **不再** seed_default_tenant（那会隐式造租户）
    target = _resolve_target(args.tenant)

    # ⭐ 写之前先把目标说出来 —— 事故的核心是「动作发生了而对象没被说出来」
    print(
        f"→ 将重置租户 id={target['id']} slug={target['slug']!r} "
        f"（status={target['status']}）的 admin 口令"
    )

    _tok = _tc.set_active_tenant(target)
    try:
        init_db()  # 幂等；确保 users 表存在
        pwd = os.environ.get("KNOT_INITIAL_ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12)
        pwd_hash = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn = get_conn()
        cur = conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=1 WHERE username='admin'",
            (pwd_hash,),
        )
        n = cur.rowcount
        if n:
            # ⭐ **审计与动作同连接、同事务、单次 commit**（`BL-v0915-3`）——
            #   「做了但没记」/「记了但没做」结构上不存在。**这条是真实事件换来的**：
            #   v0.9.15 那次重置在系统里查无此事 ⇒ 事后无从对账。
            #   为什么不走 `audit_service.log`、为什么 detail 不含凭据：见 `services/cli_audit` docstring。
            uid = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()["id"]
            cli_audit.record_password_reset(conn, tenant=target, user_id=uid)
        conn.commit()
        conn.close()
        if n == 0:
            print(
                f"✗ 租户 id={target['id']} 的库里未找到 admin 账号（库未初始化？）",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            f"✓ 租户 id={target['id']} slug={target['slug']!r} 的 admin 口令已重置："
            f"admin / {pwd}（首登须改密 must_change_password=1）"
        )
        print(
            "⚠️ 上面这行含明文口令，且**本脚本无法约束下游** —— "
            "CI 日志 / 终端记录 / 自动捕获输出的工具都会留存它。用完请尽快登录改密。",
            file=sys.stderr,
        )
    finally:
        _tc.reset_active_tenant(_tok)   # ⭐ 异常路径也必须 reset（v0.9.15 §1.3 同一范式）


if __name__ == "__main__":
    main()
