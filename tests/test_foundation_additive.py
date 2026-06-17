"""tests/test_foundation_additive.py — v0.6.2.3 Foundation additive-only 守护（R-PB-SH-1/3/4/8/11）。

v0.6.2.3 段 3 Shared.jsx inline helper 整合 = **自 v0.5.6 Foundation 冻结以来首次受准修改**。
R-365「Shared.jsx git-diff = 0 绝对红线」正式退役（演进非撤回，资深 2026-06-12 ack）→
升级为「既有 export byte-equal + 仅新增」的静态 + 计数 + cycle 守护。

⚠️ 机制说明（资深 2026-06-12 拍板 — 详 docs/plans/v0.6.2.3-shared-consolidation.md §8.2/§8.3）：
  守护者 Stage 3 钦定 react-test-renderer Shadow Run（运行时 deepEqual），但前端零 JS 测试栈，
  装 vitest/react-test-renderer 违反 § 抗诱惑清单「禁新 npm 依赖」。改用 KNOT 原生 Python text guard：
  断言既有顶层 decl 源码 byte-equal。**等价且更精确** —— Foundation 全部确定性渲染（无 Math.random/Date），
  故「源码 byte-equal ⟹ render 输出 deepEqual」恒成立；且直接证明 additivity 比抽查 12 export render 更强。

守护 4 维：
  R-PB-SH-1/2 additive-only：snapshot 内每个既有顶层 decl 在 live byte-equal（仅允许新增 export）
  R-PB-SH-3   buildTheme 返回 26 keys（25 设计 token + 1 dark 布尔透传；node 实测 Object.keys===26）
  R-PB-SH-4   I icon dict 54 names 契约（v0.6.4.0 UI v2 +16；原 38）
  R-PB-SH-8   cycle：Shared.jsx 0 import utils / screens / api（utils→Shared 单向，反向即循环）

baseline 快照：tests/foundation/{shared,utils}_foundation_base.jsx。
  v0.6.2.3 commit 1 冻结 = v0.6.2.3 前 main 态；
  **v0.6.4.0 UI v2 Foundation 演进 re-baseline**（资深 2026-06-17 拍 + 守护者复核）：
  设计系统 v2 sanctioned 演进 = buildTheme 3 值微调（success/successSoft/warn）+ I 38→54，
  非 additive（是 modification）→ baseline 重置为 UI v2 态，future v0.6.4.1+ 对此 additive。
  （治理依据同 v0.6.2.3 retire R-365：Foundation 守护"演进非撤回"，每次重大 Foundation 节点 re-baseline。）
"""
import re
from pathlib import Path

import pytest

_SHARED = Path("frontend/src/Shared.jsx")
_UTILS = Path("frontend/src/utils.jsx")
_SHARED_BASE = Path("tests/foundation/shared_foundation_base.jsx")
_UTILS_BASE = Path("tests/foundation/utils_foundation_base.jsx")

# 顶层声明：export? (function|const|let|var) NAME
_DECL_RE = re.compile(r"^(?:export\s+)?(?:function|const|let|var)\s+([A-Za-z_$][\w$]*)")


def _strip_for_depth(line: str) -> str:
    """移除行注释 + 字符串/模板字面量，避免其中的括号污染深度计数。"""
    line = re.sub(r"//.*$", "", line)
    line = re.sub(r"`[^`]*`", "", line)
    line = re.sub(r"'[^']*'", "", line)
    line = re.sub(r'"[^"]*"', "", line)
    return line


def _extract_decl(lines: list[str], start: int) -> tuple[str, int]:
    """从 start 行的顶层 decl 抽取完整声明文本。返回 (原始文本, 结束行 idx)。

    深度按 {} [] 计（忽略 ()）；注释/字符串先剥离。
    终止：有括号 → 深度回 0；无括号（如 fmtNum 三元）→ 行尾 ';'。
    """
    depth = 0
    opened = False
    out: list[str] = []
    i = start
    while i < len(lines):
        raw = lines[i]
        out.append(raw)
        stripped = _strip_for_depth(raw)
        for ch in stripped:
            if ch in "{[":
                depth += 1
                opened = True
            elif ch in "}]":
                depth -= 1
        if depth <= 0 and (opened or stripped.strip().endswith(";")):
            break
        i += 1
    return "\n".join(out), i


def _named_blocks(src: str) -> dict[str, str]:
    """切分顶层命名 decl → {name: 源码块}。匿名（import / IIFE / 注释）不纳入。"""
    lines = src.split("\n")
    blocks: dict[str, str] = {}
    i = 0
    while i < len(lines):
        m = _DECL_RE.match(lines[i])
        if m:
            text, end = _extract_decl(lines, i)
            blocks[m.group(1)] = text
            i = end + 1
        else:
            i += 1
    return blocks


# ─── R-PB-SH-1/2 — additive-only（既有 decl byte-equal + 仅新增）─────────────

@pytest.mark.parametrize(
    "live_path, base_path",
    [(_SHARED, _SHARED_BASE), (_UTILS, _UTILS_BASE)],
    ids=["Shared.jsx", "utils.jsx"],
)
def test_foundation_additive_only(live_path: Path, base_path: Path):
    """既有顶层命名 decl 必须在 live byte-equal 出现；仅允许新增 export（R-365 退役替代契约）。"""
    assert live_path.exists(), f"{live_path} 必须存在"
    assert base_path.exists(), f"baseline 快照 {base_path} 必须存在（commit 1 冻结）"

    base_blocks = _named_blocks(base_path.read_text(encoding="utf-8"))
    live_blocks = _named_blocks(live_path.read_text(encoding="utf-8"))

    missing = [n for n in base_blocks if n not in live_blocks]
    assert not missing, (
        f"R-PB-SH-2 违规：{live_path.name} 删除了既有顶层 decl（严禁，仅允许新增）：{missing}"
    )

    drifted = [n for n in base_blocks if live_blocks.get(n) != base_blocks[n]]
    assert not drifted, (
        f"R-PB-SH-1 违规：{live_path.name} 既有 decl 源码漂移（非 byte-equal）：{drifted}\n"
        f"   → Foundation 既有 export 严禁改动；仅允许 additive 新增 export。"
    )


# ─── R-PB-SH-3 — buildTheme 26 keys（25 设计 token + dark）─────────────────

def test_R_PB_SH_3_buildtheme_26_keys():
    """buildTheme 返回对象 = 26 个 runtime key（25 设计 token + 1 dark 布尔透传）。

    资深 2026-06-12 口径锁定：node 实测 Object.keys(buildTheme(true)).length===26。
    CLAUDE.md/header「25 字段」= 25 设计 token（正确，不含 dark）。
    """
    blocks = _named_blocks(_SHARED.read_text(encoding="utf-8"))
    assert "buildTheme" in blocks, "Shared.jsx 必须含 buildTheme"
    body = blocks["buildTheme"]
    # return 对象顶层键：4 空格缩进的 `key:` 或 `key,`（shorthand dark,）
    keys = re.findall(r"^    ([A-Za-z_$][\w$]*)\s*[:,]", body, re.MULTILINE)
    assert len(keys) == 26, (
        f"R-PB-SH-3 违规：buildTheme 应 26 keys（25 token + dark），实际 {len(keys)}：{keys}"
    )
    assert "dark" in keys, "buildTheme 必须含 dark 透传字段（line 55 shorthand）"


# ─── R-PB-SH-4 — I icon dict 54 names（v0.6.4.0 UI v2 +16）─────────────────

def test_R_PB_SH_4_icon_dict_54_names():
    """I icon dict = 54 names 契约（v0.6.0.3 加 thumbsUp/Down=38；v0.6.4.0 UI v2 +16=54）。"""
    blocks = _named_blocks(_SHARED.read_text(encoding="utf-8"))
    assert "I" in blocks, "Shared.jsx 必须含 I icon dict"
    body = blocks["I"]
    # icon 键：2 空格缩进的 `name:`（注释行 `  //` 不匹配）
    names = re.findall(r"^  ([A-Za-z_$][\w$]*):\s*\(", body, re.MULTILINE)
    assert len(names) == 54, (
        f"R-PB-SH-4 违规：I icon dict 应 54 names（v0.6.4.0 UI v2），实际 {len(names)}：{names}"
    )


# ─── R-PB-SH-8 — cycle 守护（Shared 0 import utils/screens/api）────────────

def test_R_PB_SH_8_no_reverse_dependency():
    """Shared.jsx 严禁 import utils.jsx / screens/* / api（utils→Shared 单向，反向即循环）。"""
    src = _SHARED.read_text(encoding="utf-8")
    imports = re.findall(r"^import\b.*$", src, re.MULTILINE)
    forbidden = [
        ln for ln in imports
        if re.search(r"utils|/screens/|['\"./]+api(['\"./]|$)", ln)
    ]
    assert not forbidden, (
        f"R-PB-SH-8 违规：Shared.jsx 出现反向依赖（会造 Shared→utils 循环）：{forbidden}"
    )


# ─── 自校验 — 抽取器健全性（防守护本身失灵静默放过）──────────────────────

def test_extractor_self_check():
    """抽取器必须能从 baseline 抽出已知 Foundation decl（防 regex 失灵 → 守护静默放过）。"""
    base = _named_blocks(_SHARED_BASE.read_text(encoding="utf-8"))
    expected = {
        "I", "buildTheme", "iconBtn", "pillBtn", "CHART_COLORS",
        "EC_TOOLTIP", "fmtNum",
        "LineChart", "BarChart", "PieChart", "TypingDots",
        "KnotMark", "KnotWordmark", "KnotLogo",
    }
    found = expected & set(base)
    assert found == expected, (
        f"抽取器自校验失败：baseline 应含全部 Foundation decl，缺失 {expected - set(base)}"
    )
