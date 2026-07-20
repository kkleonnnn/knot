#!/usr/bin/env python3
"""scripts/eval_corpus_propose.py — 语义激活收官：从 parser **稳定输出**重建 corpus 候选。

问题（v0.7.30 教训 + 2026-07-18 基线）：拿单条历史审计 LF 硬匹配非确定性 LLM parser → 大量假 misjudge
（parser 现在产出正确 LF 但历史期望是旧/buggy 的）。真 corpus 的 expect.logicform 该是「parser 现在
**稳定该产出**的正确 LF」，由 kk 校口径。

本工具：每题 live parse N 次 → 收 canonical → 取多数为 proposed → 标稳定度/变异/编译 → 写候选 corpus
（annotations 全 `_` 前缀，harness 忽略）。**把 kk 的 review 从「逐条写 LF」降级成「看一眼对没」**。

流程：
    python scripts/eval_corpus_propose.py --runs 3          # 从现 semantic_cases.yaml 的问题重建候选
    # → 写 tests/eval/semantic_cases.candidate.yaml（scratchpad 副本），kk 逐案确认：
    #     对 → 删 _* 注解留下；错 → 改 expect.logicform 或删案；_stability<N/N 或 _variants 多 → 重点看
    # → 确认后覆盖 tests/eval/semantic_cases.yaml → python scripts/eval_semantic_live.py --runs 3

catalog 段原样沿用（41 metric + 12 表机械可信）；只重提 cases 的 expect。
OR key 解析同 eval_semantic_live（env → DB）。跑 parser 用真 catalog metrics（DB-free 确定性 compile）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter, OrderedDict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from tests.eval._semantic_eval import (  # noqa: E402
    catalog_arg,
    catalog_metrics,
    eval_time_ctx,
    resolve_business_rules,
    resolve_eval_model,
)

_CORPUS = _REPO_ROOT / "tests/eval/semantic_cases.yaml"


def _resolve_or_key() -> tuple[str, str]:
    import os
    k = os.getenv("OPENROUTER_API_KEY", "").strip()
    if k:
        return k, "env"
    try:
        from knot.repositories.settings_repo import get_app_setting
        k = (get_app_setting("openrouter_api_key", "") or "").strip()
        if k:
            return k, "DB"
    except Exception:
        pass
    return "", "none"






async def _parse(question: str, metrics: list[dict], model: str, or_key: str, business_rules: str):
    from knot.services.semantic import parser
    res = await parser.parse_to_logicform(question, metrics, model_key=model, openrouter_api_key=or_key,
                                          business_rules=business_rules)  # 生产同参（query_steps.py:235）
    return res.get("logicform")


def _canonical(lf) -> str | None:
    """lf = parse_to_logicform 返回的 **LogicForm 对象**（非 dict）→ 直接 to_canonical_json。"""
    if lf is None:
        return None
    try:
        return lf.to_canonical_json()
    except Exception:
        return None


def _propose_one(question, metrics, cat, tc, model, or_key, runs, business_rules):
    """跑 N 次 → (proposed_lf_dict|None, stability_str, variants[list[(canon,cnt)]], compile_note, mode)。"""
    import json

    from knot.services.query_steps import _period_comparison_unrepresented
    from knot.services.semantic import compiler
    from knot.services.semantic.logicform import LogicForm

    canon_counts, refuse = Counter(), 0
    for _ in range(runs):
        lf = asyncio.run(_parse(question, metrics, model, or_key, business_rules))
        # 生产语义决策：周期对比 guard 拒识 = 回退
        if lf is not None and _period_comparison_unrepresented(question, lf, metrics):
            refuse += 1
            continue
        cj = _canonical(lf)
        if cj is None:
            refuse += 1
            continue
        canon_counts[cj] += 1

    total = runs
    if not canon_counts or refuse > total // 2:
        # 多数拒识/无 LF → 稳定回退
        return None, f"{refuse}/{total} refuse", [], "", "fallback"

    top_canon, top_n = canon_counts.most_common(1)[0]
    proposed = json.loads(top_canon)  # canonical JSON 串 → dict（corpus expect.logicform 用 dict）
    variants = [(cj, n) for cj, n in canon_counts.most_common() if cj != top_canon]
    # compile 校验 proposed（from_dict 读 dict → 编译）
    compile_note = "ok"
    try:
        compiler.compile_logicform(LogicForm.from_dict(proposed), cat, tc)
    except Exception as e:
        compile_note = f"{type(e).__name__}: {str(e)[:80]}"
    stability = f"{top_n}/{total}" + (f" (+{refuse} refuse)" if refuse else "")
    return proposed, stability, variants, compile_note, "hit"


def main() -> int:
    ap = argparse.ArgumentParser(description="从 parser 稳定输出重建 corpus 候选")
    ap.add_argument("--runs", type=int, default=3, help="每题跑几次取稳定 canonical（默认 3）")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=0, help="仅前 N 题（冒烟）")
    ap.add_argument("--out", default=str(_REPO_ROOT / "tests/eval/semantic_cases.candidate.yaml"))
    args = ap.parse_args()

    model, model_src = resolve_eval_model(args.model)
    or_key, src = _resolve_or_key()
    if not or_key:
        print("❌ 无 OpenRouter key（env OPENROUTER_API_KEY / DB app_settings 均空）", file=sys.stderr)
        return 2
    if not _CORPUS.exists():
        print(f"❌ 现语料不存在：{_CORPUS}（先跑 reconstruct 或 cp .example）", file=sys.stderr)
        return 2

    data = yaml.safe_load(_CORPUS.read_text(encoding="utf-8")) or {}
    catalog = data.get("catalog", {})
    cases = data.get("cases", [])
    if args.limit:
        cases = cases[: args.limit]
    metrics = catalog_metrics(catalog)
    cat, tc = catalog_arg(catalog), eval_time_ctx()
    import knot.repositories.metric_repo as mr
    mr.list_metrics = lambda cid=None: metrics

    # 跳垃圾问题（澄清数字回复等）
    def _junk(q):
        q = (q or "").strip()
        return len(q) <= 2 or q.isdigit()

    business_rules, br_src = resolve_business_rules(catalog)
    if business_rules and not (catalog.get("business_rules") or "").strip():
        catalog["business_rules"] = business_rules   # 写进候选 catalog 段 → corpus 自包含（生产同参）
    print(f"从 {len(cases)} 题重建候选（{args.runs} 轮/题 · 模型 {model}[{model_src}] · key {src} · rules {len(business_rules)}c[{br_src}]）——跳垃圾问题")
    out_cases, junk_n, unstable_n, bad_compile_n = [], 0, 0, 0
    for i, case in enumerate(cases, 1):
        q = (case.get("question") or "").strip()
        if _junk(q):
            junk_n += 1
            continue
        proposed, stability, variants, compile_note, mode = _propose_one(q, metrics, cat, tc, model, or_key, args.runs, business_rules)
        oc = OrderedDict()
        oc["id"] = case.get("id", f"C{i:02d}")
        oc["question"] = q
        oc["_stability"] = stability
        if mode == "hit":
            oc["_compile"] = compile_note
            if compile_note != "ok":
                bad_compile_n += 1
            if variants:
                unstable_n += 1
                oc["_variants"] = [f"{cj}  (×{n})" for cj, n in variants]
            oc["expect"] = OrderedDict([("mode", "hit"), ("logicform", proposed)])
        else:
            oc["expect"] = OrderedDict([("mode", "fallback")])
        out_cases.append(oc)
        tag = "hit" if mode == "hit" else "FALLBACK"
        flag = "" if (mode == "fallback" or (not variants and compile_note == "ok")) else "  ⚠️看"
        print(f"  [{i}/{len(cases)}] {oc['id']} {tag} {stability}「{q[:22]}」{flag}")

    doc = OrderedDict([("catalog", catalog), ("cases", out_cases)])

    class _OD(yaml.SafeDumper):
        pass
    _OD.add_representer(OrderedDict, lambda d, x: d.represent_dict(x.items()))
    header = f"""# KNOT 语义 corpus **候选** —— parser 稳定输出（{args.runs} 轮/题）· kk 逐案确认口径
#
# 每案注解（`_` 前缀，harness 忽略，review 完删）：
#   _stability = parser N 次里多数形出现次数（N/N = 完全稳定；<N 或有 refuse = 看）
#   _compile   = proposed LF 确定性编译（ok / 错 = parser 稳定产出但编译不了，真 gap）
#   _variants  = 不稳时的其他形（parser 抖动，判哪个对；可能要 expect.logicforms 集合容忍）
#
# review：对 → 删 _* 留下 · 错 → 改 expect.logicform 或删案 · fallback 案确认该退 · ⚠️看 的重点核。
# 确认后覆盖 tests/eval/semantic_cases.yaml → python scripts/eval_semantic_live.py --runs 3。
# 统计：{len(out_cases)} 案（跳 {junk_n} 垃圾）· {unstable_n} 不稳 · {bad_compile_n} 编译不过。

"""
    Path(args.out).write_text(header + yaml.dump(doc, Dumper=_OD, allow_unicode=True, sort_keys=False, width=200),
                              encoding="utf-8")
    print(f"\n✅ 候选写入 {args.out}")
    print(f"   {len(out_cases)} 案（跳 {junk_n} 垃圾）· {unstable_n} 不稳(_variants)· {bad_compile_n} 编译不过 · 余为稳定 hit")
    print("   → 逐案确认口径后覆盖 tests/eval/semantic_cases.yaml，再跑 eval_semantic_live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
