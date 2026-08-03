"""shell 脚本卫生哨兵（v0.9.14 Stage 4 §III 守护者建议）。

═══ 为什么需要它 ═══
「**我拿到的东西 ≠ 我以为它是的东西**」这一族错，我在 v0.9.13/.14 两片里连栽四次。
其中三条难机械化（把安装报告当环境清单 / 为从未产出过的 diff 写因果 / 顺手编的分解数字），
**只有一条可以机械化，而它已经连续两片咬我**：

| 片 | 我怎么栽的 |
|---|---|
| v0.9.13 | `tar … 2>/dev/null` —— 吞掉 tar 的 stderr ⇒ 「流被截断」这个事件对我不可见 |
| v0.9.14 | `./scripts/regen_lock.sh \| tail -3` —— 管道里 `$?` 是 **`tail` 的**退出码 ⇒ 脚本**根本没跑完**，而我读成「跑过了、产物没变」，并据此写下一段错的因果 |

⇒ **按 v3.1 统摄原则**：评审的产物应当是哨兵，不是意见 ——
否则这条教训的有效期只到某一段上下文结束（而它已经证明自己会复发）。

═══ 本哨兵守什么 ═══
`set -euo pipefail` 三件缺一不可，且**必须在任何可执行语句之前**：
- `-e` 出错即停；
- `-u` 引用未设变量即报错（拼错变量名不会静默变空串）；
- **`-o pipefail`** —— 管道的退出码取**最后一个非零**而不是最后一条命令的
  ⇒ **`cmd | tail` 里 `cmd` 失败不再被 `tail` 的 0 掩盖**。这条正是上面那次事故的直接解药。

⚠️ **纪律（哨兵管不到，写在这里当唯一载体）**：
**在意退出码的命令，不得管道给 `tail` / `head` / `grep`。**
要截断输出就 `cmd > full.log 2>&1; rc=$?` 之后再看，别在管道里读 `$?`。
（`pipefail` 只在脚本内生效；我那次是在**交互命令行**上栽的，脚本哨兵覆盖不到 ——
如实说明这个边界，不假装它守住了全部。）

⚠️ **为什么用文本匹配而非 AST**（R-SENTINEL-AST 要求写明理由）：
目标是 **bash/sh 脚本**，不存在 Python AST。判据是「首个可执行行」这种**位置**性质，
不是「某处出现过某串字符」⇒ 逐行扫描 + 跳过注释/空行/shebang，是这个性质的直接表达。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
REQUIRED = "set -euo pipefail"


def _shell_scripts() -> list[Path]:
    """**git 跟踪的** `.sh`，从 `git ls-files` 派生（不硬编清单）。

    ⚠️ **初版用 `REPO.rglob("*.sh")`，在干净状态下就红了** —— 它扫进了
    `.claude/worktrees/…/`，那是**另一个 checkout**（陈旧的 v0.6.1.4 分支，不在 main 历史里），
    里面的 `start.sh` / `run-knot.sh` **不是本仓要守的文件**。
    ⇒ 参照系必须是「**本仓将要提交的东西**」= git 索引，而不是「磁盘上这棵树里有什么」。
    （与 `test_dockerignore_context.py` 同一个参照系，理由同源：那里也是拿 git 跟踪集当真相源。）
    ⚠️ 代价如实说明：新加但**未 `git add`** 的 `.sh` 不在守护范围内 —— 与那条一致，
    换成参照工作树反而会把别的 checkout 也算进来（已实测踩到）。
    """
    out = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO / line for line in out.stdout.splitlines() if line.strip()]


def _first_executable_line(text: str) -> tuple[int, str]:
    """返回 (行号, 内容)：跳过 shebang / 注释 / 空行后的第一行。"""
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        return i, line
    return 0, ""


def test_shell_scripts_start_with_euo_pipefail() -> None:
    """每个 `.sh` 的**首个可执行行**必须是 `set -euo pipefail`。

    revert-to-bad：把任一脚本改回 `set -e` ⇒ 红，并指名文件与实际内容。
    """
    scripts = _shell_scripts()
    # ⚠️ 先证明扫描面非空 —— 对空列表做「每个都合规」的断言恒真（本弧的空集陷阱）。
    assert len(scripts) >= 5, (
        f"只扫到 {len(scripts)} 个 .sh（实测应 ≥5）—— 扫描面塌了，"
        "「每个都合规」这个断言会在空集上恒真。"
    )

    problems = []
    for path in scripts:
        rel = path.relative_to(REPO)
        lineno, line = _first_executable_line(path.read_text(encoding="utf-8"))
        if line != REQUIRED:
            problems.append(f"{rel}:{lineno} 首个可执行行是 `{line}`，应为 `{REQUIRED}`")

    assert not problems, (
        "shell 脚本缺 `set -euo pipefail`（三件缺一不可，且须在任何可执行语句之前）:\n  "
        + "\n  ".join(problems)
        + "\n\n  ⇒ 为什么 `-o pipefail` 是承重的：没有它，`cmd | tail` 的退出码取的是\n"
        "     **`tail` 的**（恒 0）⇒ `cmd` 失败会被完全掩盖。v0.9.14 实测踩过：\n"
        "     `./scripts/regen_lock.sh | tail -3` 让「脚本没跑完」看起来像「跑完了」。"
    )
