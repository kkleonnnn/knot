"""tests/test_frontend_no_eval.py — v0.8.5 (②a) R-BI-11.1 eval-free CI 门。

公式求值器 formula.js 是新安全承重面：**严禁 eval / new Function / Function() / with**
（守护者 §B；全仓当前 100% eval-free，本门守住）。扫 frontend/src 生产源（排除 .test.js*
—— 对抗测把 "eval(" 等作**字符串字面输入**喂求值器，非真调用）。

纯 stdlib（re/pathlib）→ 本机 + CI 同跑。RegExp `.exec(` 未被禁（只禁 `eval(`/`Function(`/
`with(`）→ ThinkingCard.jsx tableRe.exec 等合法用法不误红（守护者要求）。
"""
import re
from pathlib import Path

_FRONTEND_SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"

# 禁：eval( · new Function · Function( · with(  （不禁 .exec( → RegExp 合法）
_BANNED = re.compile(r"\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(|\bwith\s*\(")


def test_frontend_src_is_eval_free():
    hits: list[str] = []
    for p in sorted(_FRONTEND_SRC.rglob("*.js")) + sorted(_FRONTEND_SRC.rglob("*.jsx")):
        name = p.name
        if name.endswith((".test.js", ".test.jsx")):
            continue  # 对抗测以字符串字面喂求值器，非真调用 → 排除
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("//", "*", "/*")):
                continue  # 跳过注释行（注释里提及被禁词非执行代码；只查真代码）
            if _BANNED.search(line):
                hits.append(f"{p.relative_to(_FRONTEND_SRC)}:{lineno}: {line.strip()[:80]}")
    assert not hits, (
        "R-BI-11.1 eval-free 违规（禁 eval/new Function/Function()/with）：\n" + "\n".join(hits)
    )
