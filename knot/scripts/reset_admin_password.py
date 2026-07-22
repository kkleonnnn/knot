"""knot/scripts/reset_admin_password.py — 重置 admin 口令（v0.8.20 F7）。

首启竞态补救 / 口令遗失时用。重置后 must_change_password=1（首登须改）。

用法：
  python -m knot.scripts.reset_admin_password                                  # 随机新口令，打印一次
  KNOT_INITIAL_ADMIN_PASSWORD=<pwd> python -m knot.scripts.reset_admin_password # 指定口令
"""
import os
import secrets
import sys

import bcrypt

from knot.repositories.base import get_conn, init_db


def main() -> None:
    # v0.9.0 C2：standalone 无 middleware/ctx → 自洽建 platform.db/tenant#1（幂等）+ set tenant ctx（fail-closed get_conn）。
    from knot.core import tenant_context as _tc
    from knot.repositories import tenant_repo as _tr
    _tr.init_platform_db()
    _tr.seed_default_tenant()
    _tok = _tc.set_active_tenant(_tr.resolve_single_tenant())
    try:
        init_db()  # 幂等；确保 users 表存在
        pwd = os.environ.get("KNOT_INITIAL_ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12)
        pwd_hash = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn = get_conn()
        cur = conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=1 WHERE username='admin'",
            (pwd_hash,),
        )
        conn.commit()
        n = cur.rowcount
        conn.close()
        if n == 0:
            print("✗ 未找到 admin 账号（DB 未初始化？先启动一次服务）", file=sys.stderr)
            sys.exit(1)
        print(f"✓ admin 口令已重置：admin / {pwd}（首登须改密 must_change_password=1）")
    finally:
        _tc.reset_active_tenant(_tok)


if __name__ == "__main__":
    main()
