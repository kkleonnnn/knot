#!/usr/bin/env python3
"""重生成路由策略快照（D9' 单命令）—— `tests/fixtures/route_policy.json`。

用法（**唯一 documented 入口**）：
    PYTHONPATH=. python3 scripts/gen_route_policy_snapshot.py

⚠️ 快照是**期望值**，必须是字面（不得由测运行期从 app 派生 —— 那是自我实现的 tautology，测永远绿）。
本脚本是**人有意执行**的动作：改了路由/守护后跑一次，把 diff 当 review 材料。
`test_route_policy.py` 失败时也会直接打印可粘贴的新块，二者等价。
"""
import json
import os
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tests"))

# 与 tests/conftest.py 同口径的最小启动 env（不落任何真实数据目录）
import tempfile  # noqa: E402

_d = tempfile.mkdtemp(prefix="knot_snapshot_")
os.environ.setdefault("SQLITE_DB_PATH", os.path.join(_d, "knot.db"))
os.environ["KNOT_SKIP_DOTENV"] = "1"
os.environ["KNOT_SKIP_STARTUP_MIGRATION"] = "1"
os.environ.setdefault("JWT_SECRET", "x" * 40)
if not os.environ.get("KNOT_MASTER_KEY"):
    from cryptography.fernet import Fernet

    os.environ["KNOT_MASTER_KEY"] = Fernet.generate_key().decode()

from tests._route_policy import build_actual_policy_map  # noqa: E402

OUT = _ROOT / "tests" / "fixtures" / "route_policy.json"


def main() -> int:
    actual = build_actual_policy_map()
    OUT.write_text(json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"✓ 写入 {OUT.relative_to(_ROOT)} —— {len(actual)} 条")
    import collections
    for policy, n in sorted(collections.Counter(actual.values()).items()):
        print(f"    {policy:24} {n}")
    print("\n⚠️ 请把 diff 当 review 材料逐条过一遍：新增/降级的策略是有意的吗？")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
