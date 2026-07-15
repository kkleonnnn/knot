"""knot/services/agents/da_asst.py — v0.8.10 §5（③ 提前落地）只读报表解读助手 da-asst。

BI 右栏「数据分析」的后端：基于报表**冻结快照**（last_run_rows_json）一问一答解读报表。
- **只读**：不跑新 SQL、不写库、不改报表（对应前端「仅解读 · 不改写报表」）。
- 复用异步 LLM 链路 `_allm`（R-26 budget gate + R-30 领域异常透传 + R-32 agent_kind='da_asst' 分桶）。
- 报表数据视为**不可信内容**（prompt-injection 护栏写进 system）。
- 默认模型 `DEFAULT_MODEL`（OR-only）；admin 可后续为 agent_kind='da_asst' 配 per_call 预算。

⚠️ v1 非流式（一次返完整 answer）。v0.8.18 ③：system prompt 已 .md 化（knot/prompts/da_asst.md，
   6 只读/安全铁律 + da-asst 7 应答原则）+ 纳入 prompt_service seed → admin 可覆盖（对齐 3-agent）。
"""
from __future__ import annotations

import json
import pathlib

_PROMPT_DIR = pathlib.Path(__file__).resolve().parents[2] / "prompts"


def _load_default_prompt(name: str) -> str:
    """v0.8.18 ③：读 knot/prompts/{name}.md 作默认 system prompt（镜像 presenter._load_default_prompt）。
    缺失/异常 → 空串（fail-soft；上层 prompt_service.get_prompt 走 DB 兜底）。"""
    try:
        return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8").rstrip("\n")
    except OSError:
        return ""


# v0.8.18 ③：da-asst 真嵌入 —— 6 只读/安全铁律（含 #3 报表数据不可信 prompt-injection 护栏、#1 只读）
# + da-asst 7 应答原则，落 knot/prompts/da_asst.md（vendor 自 da-asst repo commit b8543a1 决策应答原则，
# 详 NOTICE）。纳入 prompt_service._DEFAULT_PROMPT_AGENTS → seed DB + admin 可覆盖（对齐 3-agent）。
_DA_ASST_SYS = _load_default_prompt("da_asst")

_MAX_ROWS_PER_BLOCK = 30      # 每组件 / 报表级快照喂给 LLM 的行数上限（控 token）
_MAX_CONTEXT_CHARS = 16000    # 全上下文硬顶（30 tile × 30 行宽表 → 输入 token 失控；per_call 预算按 max_tokens 估
                              # 仅覆盖输出，不覆盖输入 → 此处兜输入侧成本上限，超则截断 + 标注）
_MAX_QUESTION_CHARS = 2000    # 单条提问上限
_MAX_HISTORY_TURNS = 12       # 保留最近 N 轮
_MAX_HISTORY_CHARS = 4000     # 单条历史长度上限


def _rows_of(raw) -> list:
    """安全解析冻结快照 JSON 串 → list（非法/非 list → []）。"""
    try:
        rows = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return []
    return rows if isinstance(rows, list) else []


def _snap_line(head: str, rows: list) -> str:
    sample = json.dumps(rows[:_MAX_ROWS_PER_BLOCK], ensure_ascii=False, default=str)
    more = (f"（共 {len(rows)} 行，示前 {_MAX_ROWS_PER_BLOCK} 行）"
            if len(rows) > _MAX_ROWS_PER_BLOCK else f"（共 {len(rows)} 行）")
    return f"{head}{more}：{sample}"


def _context_block(report: dict) -> str:
    """报表标题 + 各 tile（dashboard/tabbed）或报表级（wide_table）冻结快照 → 上下文文本。"""
    lines = [f"报表标题：{report.get('title') or '(未命名)'}"]
    tiles = report.get("tiles")
    if isinstance(tiles, list) and tiles:
        for t in tiles:
            head = f"\n【组件】{t.get('title') or '(未命名)'}（类型 {t.get('tile_type') or '?'}）"
            err = t.get("last_run_error")
            rows = _rows_of(t.get("last_run_rows_json"))
            if err:
                lines.append(f"{head}：查询出错 {err}")
            elif not rows:
                lines.append(f"{head}：暂无数据（未刷新）")
            else:
                lines.append(_snap_line(head, rows))
    else:
        rows = _rows_of(report.get("last_run_rows_json"))
        lines.append("\n【报表数据】暂无数据（未刷新）" if not rows else _snap_line("\n【报表数据】", rows))
    block = "\n".join(lines)
    if len(block) > _MAX_CONTEXT_CHARS:      # 输入侧成本硬顶（per_call 预算不覆盖输入 → 此处截断）
        block = block[:_MAX_CONTEXT_CHARS] + "\n…（数据过长已截断，仅供概览）"
    return block


def _clean_history(history) -> list:
    """只保留 {role∈(user,assistant), content:非空 str}；截轮数 + 单条长度（防越界烧 token）。"""
    out = []
    for h in (history or [])[-_MAX_HISTORY_TURNS:]:
        if not isinstance(h, dict):
            continue
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content[:_MAX_HISTORY_CHARS]})
    return out


async def arun_da_asst(report: dict, question: str, history=None, model_key: str = "") -> dict:
    """报表解读一问一答（async）。返 {answer, input_tokens, output_tokens, cost_usd}。

    KnotError（budget/auth/network）由 `_allm` 抛出后**透传**给 api 层翻译（R-30）；本函数不吞。
    """
    # R-106 方案 1：延迟 import 主文件 helpers（与 presenter/clarifier 同模式）
    from knot.config import DEFAULT_MODEL
    from knot.repositories.settings_repo import get_agent_model_config
    from knot.services import prompt_service
    from knot.services.agents.orchestrator import _allm, _resolve

    # v0.8.18 ③：DB 覆盖 / .md 默认（admin 可编辑）；报表数据仍**追加在 system 之后** → injection 边界不变（B-4）
    sys_prompt = prompt_service.get_prompt("da_asst", _DA_ASST_SYS)
    system = sys_prompt + "\n\n===== 报表数据 =====\n" + _context_block(report)
    messages = _clean_history(history) + [
        {"role": "user", "content": (question or "").strip()[:_MAX_QUESTION_CHARS]},
    ]

    # v0.8.12 返工：da-asst = 一等分析引擎，模型走 agent_model_config['da_asst']（「API & 模型」配的第 4 槽）；
    # 用平台 OR key（同其它 agent，不单独填 key）。留空 → DEFAULT_MODEL。
    # ⚠️ 必须传非空 model：_resolve("") 落 generic 分支不查 DB OR key → OR-only 100% 502。
    da_model = get_agent_model_config().get("da_asst") or ""
    model_key, key, cfg = _resolve(model_key or da_model or DEFAULT_MODEL)
    text, it, ot, cost = await _allm(
        model_key, key, cfg, system, messages, max_tokens=700, agent_kind="da_asst",
    )
    return {"answer": (text or "").strip(), "input_tokens": it,
            "output_tokens": ot, "cost_usd": cost}
