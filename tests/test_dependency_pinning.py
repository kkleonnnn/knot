"""依赖钉版本哨兵 Sd1–Sd7（v0.9.14）。

**为什么这里不用 Python AST**（R-SENTINEL-AST 要求写明理由）：
被守护的对象全是**非 Python 文件** —— `Dockerfile` / `.github/workflows/ci.yml` /
`requirements.txt` / `requirements.lock` / `scripts/regen_lock.sh` ⇒ 根本不存在 Python AST。
而对 `requirements*.txt` / `.lock` 这两种**有正式语法**的文件，本模块用
**PEP 508/440 结构化 API**（`packaging.requirements` / `packaging.specifiers` /
`packaging.utils.canonicalize_name`）解析，**不手写正则**（d5）——
规范化大小写与 `-`/`_`、正确处理 extras 与 marker，都交给上游实现。

**判据锚在产出，不锚在描述**（本弧反复付学费的那条）：
· Sd5 断言的头部是 `scripts/regen_lock.sh` **生成**的，不是手写声明；
· Sd7 **真的跑一次**脚本的派生（`--print-base`），而不是读脚本文本；
· Sd3 的期望上下界**从 lock 里的实装版本派生**，不写死字面量。
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

REPO = Path(__file__).resolve().parent.parent
REQ_TXT = REPO / "requirements.txt"
REQ_LOCK = REPO / "requirements.lock"
DOCKERFILE = REPO / "Dockerfile"
PYPROJECT = REPO / "pyproject.toml"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"
REGEN = REPO / "scripts" / "regen_lock.sh"

# lock 头部必须有的六项（Sd5）—— 由 scripts/regen_lock.sh 生成
_HEADER_FIELDS = ("base-image", "--platform", "python", "platform", "machine", "pip")


# ── 解析工具 ────────────────────────────────────────────────────────────────
def _strip_comment(line: str) -> str:
    """去掉行尾注释。`requirements.txt` 里存在 `sqlglot>=30,<31  # 理由…` 这种写法。"""
    return line.split("#", 1)[0].strip()


def _direct_requirements() -> list[Requirement]:
    out = []
    for raw in REQ_TXT.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw)
        if line:
            out.append(Requirement(line))
    return out


def _lock_lines() -> list[str]:
    return [
        line.strip()
        for line in REQ_LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _lock_versions() -> dict[str, str]:
    """canonical name → 精确版本。"""
    versions = {}
    for line in _lock_lines():
        req = Requirement(line)
        spec = list(req.specifier)
        assert len(spec) == 1 and spec[0].operator == "==", (
            f"lock 行不是精确 pin: {line!r}"
        )
        versions[canonicalize_name(req.name)] = spec[0].version
    return versions


def _from_lines() -> list[str]:
    """`Dockerfile` 里所有 `FROM` 指令的镜像引用，按出现顺序。"""
    return [
        line.split()[1]
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("FROM ")
    ]


def _runtime_base_image() -> str:
    """运行 stage = **最后一个** `FROM`（多阶段构建里真正被 tag 的那个）。"""
    images = _from_lines()
    assert images, "Dockerfile 里找不到任何 FROM"
    return images[-1]


def _py_series(text: str) -> str:
    """从 `python:3.11-slim` / `>=3.11` / `"3.11"` 里取出 `3.11`。"""
    m = re.search(r"(\d+\.\d+)", text)
    assert m, f"取不出 Python 版本: {text!r}"
    return m.group(1)


# ⭐ 上界/下界阶梯（Q2 裁定 · 从实装版本**派生**期望值，不写死）
def _ladder_bounds(version: str) -> tuple[str, str]:
    """返回 (下界, 上界)：上游版本契约所能支撑的最紧那一对。

    · `1+`      → `>={major}.{minor}` / `<{major+1}`
    · `0.x`     → `>=0.{minor}`       / `<0.{minor+1}`
    · `0.0.x`   → `>=0.0.{patch}`     / `<0.0.{patch+1}`

    0.0.x 在任何层级都无稳定性承诺 ⇒ 比实测版本更宽的任何声明都是假话。
    对 0.0.x 这等于钉住 —— **那是正确的**：精确版本本来就由 lock 钉，
    spec 的界纯粹是一句真话声明。
    """
    rel = Version(version).release
    major = rel[0]
    minor = rel[1] if len(rel) > 1 else 0
    patch = rel[2] if len(rel) > 2 else 0
    if major >= 1:
        return f"{major}.{minor}", f"{major + 1}"
    if minor >= 1:
        return f"0.{minor}", f"0.{minor + 1}"
    return f"0.0.{patch}", f"0.0.{patch + 1}"


# ── Sd1 ─────────────────────────────────────────────────────────────────────
def test_Sd1_dockerfile_copies_and_consumes_lock() -> None:
    """**正向**断言：`Dockerfile` 既 COPY 了 lock，又在安装行消费它。

    F7' 实证：纯负断言（「不得再 install requirements.txt」）连**删掉整个安装步骤**
    都测不出来 ⇒ 必须正向断言两件事都在。
    """
    lines = [line.strip() for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()]
    copied = [
        line
        for line in lines
        if line.startswith("COPY ") and "requirements.lock" in line
    ]
    installs = [
        line
        for line in lines
        if line.startswith("RUN ") and "pip install" in line
    ]
    consuming = [line for line in installs if "requirements.lock" in line]

    assert copied, (
        "Dockerfile 没有把 requirements.lock COPY 进镜像 ——\n"
        "    只改安装行不改 COPY 行，构建会当场失败（F7' 实测）。"
    )
    assert installs, "Dockerfile 里找不到任何 `RUN ... pip install` —— 安装步骤被删了？"
    assert consuming, (
        "Dockerfile 的 pip install 行没有引用 requirements.lock ——\n"
        f"    实际安装行: {installs!r}\n"
        "    生产必须走 `-r requirements.txt -c requirements.lock`（roots 走 spec，精确版本走 lock）。"
    )


# ── Sd2 ─────────────────────────────────────────────────────────────────────
def test_Sd2_lock_is_exact_pins_only() -> None:
    """lock 每行必须是 `name==version`：拒 `>=` / URL / editable / extras。"""
    for line in _lock_lines():
        assert not line.startswith("-e "), f"lock 出现 editable 安装: {line!r}"
        assert "://" not in line, f"lock 出现 URL 依赖（不可复现）: {line!r}"
        req = Requirement(line)
        assert not req.extras, f"lock 行不该带 extras（应已展开为具体包）: {line!r}"
        spec = list(req.specifier)
        assert len(spec) == 1 and spec[0].operator == "==", (
            f"lock 行不是精确 pin: {line!r} —— 全树精确 pin 是 kk 2026-08-01 的拍板口径。"
        )


def test_Sd2b_locked_versions_satisfy_spec_ranges() -> None:
    """每个直接依赖的锁定版本必须落在 `requirements.txt` 的区间内。

    ⚠️ **纯字符串/结构化比对，不联网**（v3.1-B #2）：否则注入「区间外的版本」时，
    测到的是「pip 装不到」而不是「断言抓到了」。
    """
    locked = _lock_versions()
    for req in _direct_requirements():
        name = canonicalize_name(req.name)
        assert name in locked, f"{req.name} 在 lock 里缺席（Sd4 应已抓到）"
        version = locked[name]
        assert req.specifier.contains(version, prereleases=True), (
            f"{req.name}: lock 锁的是 {version}，落在 requirements.txt 的区间"
            f" `{req.specifier}` **之外** ⇒ 两个文件互相矛盾。"
        )


# ── Sd3 ─────────────────────────────────────────────────────────────────────
def test_Sd3_spec_bounds_are_the_tightest_the_upstream_contract_supports() -> None:
    """`requirements.txt` 的上下界必须 == 从实装版本派生的阶梯值（Q2）。

    期望值**派生**，不写死 ⇒ 换了实装版本，本测会直接告诉你该写什么。
    ⭐ 特别地：0.x 包的上界**不得**是 `<1.0`（那等于不设界，是一句假话）。
    """
    locked = _lock_versions()
    problems = []
    for req in _direct_requirements():
        name = canonicalize_name(req.name)
        if name not in locked:
            continue  # Sd4 负责这条
        want_low, want_high = _ladder_bounds(locked[name])
        lows = [s for s in req.specifier if s.operator == ">="]
        highs = [s for s in req.specifier if s.operator == "<"]
        if len(highs) != 1:
            problems.append(f"{req.name}: 应恰有一个 `<` 上界，实际 {len(highs)} 个")
            continue
        if len(lows) != 1:
            problems.append(f"{req.name}: 应恰有一个 `>=` 下界，实际 {len(lows)} 个")
            continue
        if highs[0].version != want_high:
            problems.append(
                f"{req.name} (实装 {locked[name]}): 上界应为 `<{want_high}`，实际 `<{highs[0].version}`"
            )
        if lows[0].version != want_low:
            problems.append(
                f"{req.name} (实装 {locked[name]}): 下界应为 `>={want_low}`，实际 `>={lows[0].version}`"
            )
    assert not problems, (
        "requirements.txt 的区间声明与实装版本不符（上下界都必须是「上游契约能支撑的最紧那个」）:\n  "
        + "\n  ".join(problems)
    )


# ── Sd4 ─────────────────────────────────────────────────────────────────────
def test_Sd4_lock_covers_every_direct_dependency() -> None:
    """lock 必须覆盖**全部**直接依赖（extras 取基名）。

    fail-open 面：漏一个 ⇒ 镜像里装不上 ⇒ **运行时 ImportError**。
    """
    locked = set(_lock_versions())
    direct = {canonicalize_name(r.name) for r in _direct_requirements()}
    missing = sorted(direct - locked)
    assert not missing, (
        f"这些直接依赖不在 requirements.lock 里: {missing}\n"
        "    ⇒ 跑 ./scripts/regen_lock.sh 重新生成。"
    )


# ── Sd5 ─────────────────────────────────────────────────────────────────────
def test_Sd5_lock_header_is_generated_and_names_the_real_base_image() -> None:
    """lock 头部六项齐全，**且 base-image 等于从 `Dockerfile` 派生的那个**。

    ⭐ Q3-①：头部由 `scripts/regen_lock.sh` **生成** ⇒ 本测验的是「那段话是派生的」，
    不是「有这么一段话」。实证：首次生成时头部打出 `machine: aarch64`（宿主是 Apple
    Silicon）**当场自证这份 lock 对生产无效** —— 手写声明抓不到这个。
    """
    header = [
        line
        for line in REQ_LOCK.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    ]
    blob = "\n".join(header)
    missing = [f for f in _HEADER_FIELDS if f not in blob]
    assert not missing, (
        f"lock 头部缺这些生成环境字段: {missing}\n"
        f"    ⇒ 头部应由 scripts/regen_lock.sh 生成；别手写。"
    )
    want = _runtime_base_image()
    assert f"base-image : {want}" in blob, (
        f"lock 头部声称的 base-image 与 Dockerfile 运行 stage 的 `{want}` 不符 ——\n"
        f"    ⇒ 这份 lock 是在错的环境里生成的（d1' 存在的全部理由）。\n"
        f"    头部实际内容:\n{blob}"
    )


# ── Sd6 ─────────────────────────────────────────────────────────────────────
def test_Sd6_python_version_is_consistent_across_every_site() -> None:
    """`requires-python` 与**全部** Python 版本声明站点一致。

    ⭐ 加项 2：站点集合**从文件派生**（不写死行号）。实测 `ci.yml` 有 **3 处**
    `python-version`（`:16 / :101 / :180`）+ `Dockerfile` 运行 stage 一处。
    **只断一处 = 看起来完整的局部守护。**
    """
    ci_versions = re.findall(
        r"python-version:\s*['\"]?(\d+\.\d+)['\"]?", CI_YML.read_text(encoding="utf-8")
    )
    # ⚠️ 先证明扫描面非空 —— 对空集做「全都一致」的断言恒真（本弧的空集陷阱）。
    assert len(ci_versions) >= 3, (
        f"ci.yml 里只找到 {len(ci_versions)} 处 python-version（实测应 ≥3）——\n"
        "    扫描面塌了，「全都一致」这个断言会在空集上恒真。"
    )

    docker_py = _py_series(_runtime_base_image())

    m = re.search(
        r'requires-python\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8")
    )
    assert m, "pyproject.toml 里找不到 requires-python"
    pyproject_py = _py_series(m.group(1))

    sites = {
        "pyproject.requires-python": pyproject_py,
        "Dockerfile 运行 stage": docker_py,
        **{f"ci.yml python-version #{i + 1}": v for i, v in enumerate(ci_versions)},
    }
    distinct = set(sites.values())
    assert len(distinct) == 1, (
        "Python 版本声明在各站点之间漂开了（3.9/3.10 从未被任何东西验过 —— F8'）:\n  "
        + "\n  ".join(f"{k} = {v}" for k, v in sites.items())
    )


# ── Sd7 ─────────────────────────────────────────────────────────────────────
def test_Sd7_regen_script_derives_base_image_from_dockerfile() -> None:
    """`scripts/regen_lock.sh` 的基础镜像必须**派生自** `Dockerfile` 运行 stage。

    ⭐ Q3-② 的加强版：处方是「比对两个字面量」；本片改成**脚本不硬编、从 Dockerfile 派生**
    ⇒ 漂开在结构上不可能。本测两条：
      ① 脚本里**没有** `python:` 镜像字面量（否则又变成两份清单）；
      ② **真的跑一次**那段派生（`--print-base`，不启动 docker），产出必须等于运行 stage 的镜像。
    ⚠️ 这里用文本扫描而非 AST：目标是 **bash 脚本**，不存在 Python AST（R-SENTINEL-AST 要求写明）。
    """
    assert REGEN.exists(), f"{REGEN} 不存在 —— d7 的「确切命令」不能只是散文"
    body = REGEN.read_text(encoding="utf-8")

    # ① 排掉注释行后，正文里不得出现 `python:<tag>` 字面量
    code = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    hardcoded = re.findall(r"python:[\w.-]+", code)
    assert not hardcoded, (
        f"regen_lock.sh 正文里硬编了镜像 {hardcoded} ——\n"
        "    ⇒ 「用哪个 Python」就又有了两份清单，会与 Dockerfile 静默漂开，\n"
        "       而 lock 会在错的环境里生成（d1' 存在的理由）。改为从 Dockerfile 派生。"
    )

    # ② 跑那段派生，看它真的产出什么
    proc = subprocess.run(
        ["bash", str(REGEN), "--print-base"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (
        f"regen_lock.sh --print-base 失败（rc={proc.returncode}）:\n"
        f"  stdout: {proc.stdout!r}\n  stderr: {proc.stderr!r}"
    )
    derived = proc.stdout.strip()
    want = _runtime_base_image()
    assert derived == want, (
        f"脚本派生出 `{derived}`，而 Dockerfile 运行 stage 是 `{want}` ——\n"
        "    ⇒ lock 会在错的基础镜像里生成。检查派生是否取到了**最后一个** FROM\n"
        f"       （本 Dockerfile 的 FROM 依次是: {_from_lines()}）。"
    )


# ── Sd8 ─────────────────────────────────────────────────────────────────────
def test_Sd8_locked_lane_scripts_are_stdlib_only() -> None:
    """locked lane 里跑的每个 `scripts/*.py` 必须**零第三方依赖**。

    ⭐ **为什么这是判据成立的前提，不是洁癖**：那些脚本跑在**它们自己要测量的那个环境**里
    （只装了生产依赖）。它 import 的任何非生产包 —— 要么让它自己崩，要么就得被装进环境里，
    而**装进去会让「集合等值」当场报「多了一个 lock 之外的包」**。
    ⇒ **测量工具不能给它测量的集合加东西。**

    ⚠️ **实测代价（本片首次上 CI 就红在这）**：
    `scripts/check_lock_closure.py` 初版 `from packaging.requirements import Requirement`
    ⇒ lane 红在 `ModuleNotFoundError: No module named 'packaging'`
    （本机有 —— `packaging` 是 pytest 的依赖）。**第三次「我本机有、CI 没有」。**

    **扫描面从 `ci.yml` 派生**（不写死脚本清单）：解析出那个 job 的全部 `run:`，
    正则取其中的 `scripts/*.py`。新增一步跑新脚本，自动进入守护范围。
    ⚠️ 用 AST 判 import（而非文本），且**白名单从 `sys.stdlib_module_names` 派生**——
    不手维护清单（R-SENTINEL-AST）。
    """
    import sys as _sys

    import yaml

    ci = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = ci.get("jobs", {})
    lane = next(
        (j for j in jobs.values() if j.get("name") == "locked runtime lane"),
        None,
    )
    assert lane is not None, (
        "ci.yml 里找不到 name 为 `locked runtime lane` 的 job ——\n"
        "    扫描面塌了，本断言会在空集上恒真。"
    )

    runs = " \n".join(
        str(step.get("run", "")) for step in lane.get("steps", []) if isinstance(step, dict)
    )
    scripts = sorted(set(re.findall(r"scripts/[\w/]+\.py", runs)))
    # ⚠️ 先证明扫描面非空 —— 否则「每个脚本都合规」在空集上恒真。
    assert scripts, (
        f"没从 locked lane 的 run: 里解析出任何 `scripts/*.py`——\n    实际 run 内容:\n{runs}"
    )

    problems = []
    for rel in scripts:
        path = REPO / rel
        assert path.exists(), f"lane 引用了不存在的脚本: {rel}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # 相对 import（level>0）不引入外部包
                mods = [] if node.level else [(node.module or "").split(".")[0]]
            else:
                continue
            for m in mods:
                if m and m not in _sys.stdlib_module_names:
                    problems.append(f"{rel}:{node.lineno} import 了非 stdlib 的 `{m}`")

    assert not problems, (
        "locked lane 的脚本 import 了第三方包 —— 它跑在只有生产依赖的环境里:\n  "
        + "\n  ".join(problems)
        + "\n  ⇒ 要么改用 stdlib 实现，要么把该包变成真正的生产依赖（想清楚再做）。\n"
        "  ⚠️ **别用「往 lane 里补装一个包」来修** —— 那会让集合等值报「多了一个 lock 之外的包」。"
    )


@pytest.mark.parametrize("path", [REQ_LOCK, REGEN])
def test_Sd_artifacts_exist(path: Path) -> None:
    """两个新产物必须存在 —— 缺了的话上面各条会以「文件不存在」的形态糊掉。"""
    assert path.exists(), f"{path.relative_to(REPO)} 不存在"
