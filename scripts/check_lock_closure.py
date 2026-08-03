#!/usr/bin/env python3
"""`requirements.lock` 的两个运行期判据（v0.9.14 · CI locked-runtime lane 用）。

    --mode closure       ② 集合等值：`pip freeze` 与 lock **逐条**相等
    --mode still-locked   ⑤ lock 里每个包的当前安装版本**仍**等于 lock（允许环境有额外包）

⭐ **为什么这两条不是同一件事，也都不是冗余**（Stage 3 Q1 加层）：
  · `-c requirements.lock`（constraints）只**限制**版本、**不强制安装** ——
    某个传递依赖若从 lock 里漏了，pip 会**自由解析**它 ⇒ **constraints 本身证明不了闭合**；
    `closure` 才是把 constraints 变成**闭合**的那一步。
  · `still-locked` 管的是另一件事：装完 dev 依赖之后，生产依赖有没有被顶掉。
    若被顶掉，后面那次全量跑的就**不是 lock 那套** ⇒ R8 的证明作废。
    机制上 `-c requirements.lock` 已挡住，本模式是**对该机制结果的断言**
    （本仓纪律：不要只声称机制生效，要断言它的结果）。

⭐ **为什么用 `pip freeze` 而不是 `importlib.metadata`**：
lock 本身就是**容器内 `pip freeze` 的产物**（见 `scripts/regen_lock.sh`）⇒ 用同一个工具测量，
才是 like-for-like。换成 `importlib.metadata` 会把 `pip`/`setuptools`/`wheel` 也列出来，
逼我维护一份排除清单 —— 而那正是本仓反复吃过瘪的「会漂的清单」。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "requirements.lock"


def _lock_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in LOCK.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        spec = list(req.specifier)
        if len(spec) != 1 or spec[0].operator != "==":
            sys.exit(f"⛔ lock 行不是精确 pin: {line!r}")
        out[canonicalize_name(req.name)] = spec[0].version
    return out


def _frozen_map() -> dict[str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=True,
    )
    out: dict[str, str] = {}
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-e "):
            continue
        if "==" not in line:
            # `pkg @ file:///...` 这类直接引用 —— 不可复现，必须让它显形而不是被跳过
            out[canonicalize_name(line.split("@")[0].strip())] = f"<非 ==: {line}>"
            continue
        name, version = line.split("==", 1)
        out[canonicalize_name(name)] = version.strip()
    return out


def _closure() -> int:
    lock, frozen = _lock_map(), _frozen_map()
    # ⚠️ 先证明扫描面非空 —— 对空集做「两边相等」的断言恒真
    if not lock or not frozen:
        print(f"⛔ 扫描面为空（lock {len(lock)} / freeze {len(frozen)}）—— 判据不成立")
        return 2

    extra = sorted(set(frozen) - set(lock))
    missing = sorted(set(lock) - set(frozen))
    mismatch = sorted(
        (n, lock[n], frozen[n]) for n in set(lock) & set(frozen) if lock[n] != frozen[n]
    )

    if not (extra or missing or mismatch):
        print(f"✅ 集合等值：{len(lock)} 个包逐条相等（闭合成立）")
        return 0

    print("⛔ 环境与 requirements.lock **不等值** —— 闭合不成立：")
    if extra:
        print(
            f"  · lock 之外被拉进来的 {len(extra)} 个: "
            + ", ".join(f"{n}=={frozen[n]}" for n in extra)
        )
        print("    ⇒ 说明 constraints 没能覆盖某条传递依赖（constraints 只限制、不强制安装）。")
    if missing:
        print(f"  · lock 里有而环境里缺席的 {len(missing)} 个: {', '.join(missing)}")
    for n, want, got in mismatch:
        print(f"  · {n}: lock={want} 实装={got}")
    print("\n  ⇒ 处置：跑 ./scripts/regen_lock.sh 重新生成 lock（有意升级），或查为何解析偏离。")
    return 1


def _still_locked() -> int:
    lock, frozen = _lock_map(), _frozen_map()
    if not lock or not frozen:
        print(f"⛔ 扫描面为空（lock {len(lock)} / freeze {len(frozen)}）—— 判据不成立")
        return 2

    moved = sorted(
        (n, lock[n], frozen[n]) for n in lock if n in frozen and lock[n] != frozen[n]
    )
    gone = sorted(n for n in lock if n not in frozen)
    if not (moved or gone):
        print(f"✅ {len(lock)} 个锁定版本在装完 dev 依赖后**仍然成立**")
        return 0

    print("⛔ 装 dev 依赖把生产依赖顶掉了 —— 后面那次全量跑的就不是 lock 那套：")
    for n, want, got in moved:
        print(f"  · {n}: lock={want} 现在={got}")
    for n in gone:
        print(f"  · {n}: 被卸载了")
    print("\n  ⇒ 处置：检查 requirements-dev.txt 是否与生产依赖冲突（安装时已带 -c requirements.lock）。")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("closure", "still-locked"), required=True)
    args = ap.parse_args()
    return _closure() if args.mode == "closure" else _still_locked()


if __name__ == "__main__":
    sys.exit(main())
