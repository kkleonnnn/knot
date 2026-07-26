#!/usr/bin/env python3
"""scripts/eval_semantic_live.py — 语义层激活门 (P1-③) turnkey 跑批 runner。

复用 tests/eval 现有 harness（load_semantic_corpus / classify / rates + test_semantic_accuracy
的 parse→周期对比 guard→compile 流），但**打印命中率/误判/逐案明细 + 多轮波动分布 + 激活门 PASS/FAIL**
（而非只 assert 的 pytest）——供 kk 在真 OHX `tests/eval/semantic_cases.yaml` 上做激活决策。

激活门（守护者 §E LOCKED）：**命中率 ≥ 90% ∧ 误判 == 0**（误判=带徽标错口径的硬安全线）。
多轮语义：flaky 主翻 hit↔fallback（抖命中率）非 hit↔误判；本 runner 取**所有轮最差**判门
（命中率门 = min(hit_rate) ≥ 0.90；误判门 = max(misjudge) == 0），守护者「先跑几轮收波动分布」的保守裁定。

用法：
    # 真 OHX 语料 + DB 里的 OR key（kk 真实部署，最常用）
    python scripts/eval_semantic_live.py --runs 3

    # 显式 env key / 指定模型 / 落 JSON 记录
    OPENROUTER_API_KEY=sk-or-... python scripts/eval_semantic_live.py --runs 5 --model anthropic/claude-haiku-4.5 --json /tmp/eval.json

OR key 解析：env OPENROUTER_API_KEY 优先 → 回退 DB app_settings.openrouter_api_key（Fernet 解密）→ 缺则报错退出。
语料解析：优先 tests/eval/semantic_cases.yaml（真 OHX，gitignored）→ 回退 .example（假域=harness 自检，会大声警告）。
本 runner 不改任何代码/DB（只读语料 + 只读 DB 取 key）；是 dev/ops 工具，不进 knot/ 包（不受分层/size 闸门约束）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

# scripts/ 不在 sys.path[0] 的父级 → 显式插入仓根，令 `import tests.eval...` 与 `import knot...` 可解析
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.eval._semantic_eval import (  # noqa: E402
    catalog_arg,
    catalog_metrics,
    classify,
    eval_time_ctx,
    load_semantic_corpus,
    rates,
    resolve_business_rules,  # 保真度：模型+rules 解析单一真相源（committed 测同用）
    resolve_eval_model,
)

_HIT_RATE_GATE = 0.90
_MISJUDGE_GATE = 0


def _resolve_or_key() -> tuple[str, str]:
    """→ (key, source)。env 优先 → DB app_settings（Fernet 解密）。缺则 ('', 'none')。"""
    import os
    env_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key, "env OPENROUTER_API_KEY"
    try:
        from knot.repositories.settings_repo import get_app_setting
        db_key = (get_app_setting("openrouter_api_key", "") or "").strip()
        if db_key:
            return db_key, "DB app_settings.openrouter_api_key"
    except Exception as e:  # DB 不可达 / 未配 —— 不致命，交调用方决定
        print(f"[warn] DB 取 OR key 失败（{e.__class__.__name__}: {e}）；仅用 env", file=sys.stderr)
    return "", "none"


def _mask(key: str) -> str:
    return f"{key[:8]}...{key[-4:]}" if len(key) > 14 else "***"


def _corpus_is_real() -> bool:
    return (Path(__file__).resolve().parent.parent / "tests/eval/semantic_cases.yaml").exists()


async def _parse_one(question: str, metrics: list[dict], model: str, or_key: str, business_rules: str):
    from knot.services.semantic import parser
    res = await parser.parse_to_logicform(question, metrics, model_key=model, openrouter_api_key=or_key,
                                          business_rules=business_rules)  # 生产同参（query_steps.py:235）
    return res.get("logicform")


def _run_once(cases, metrics, cat, tc, model, or_key, business_rules):
    """跑一轮全语料 → (rates_dict, problem_detail_list)。镜像生产 parse(+rules)→guard→compile。"""
    from knot.services.query_steps import _period_comparison_unrepresented
    from knot.services.semantic import compiler

    labels, detail = [], []
    for case in cases:
        lf = asyncio.run(_parse_one(case["question"], metrics, model, or_key, business_rules))
        compile_ok, cerr = False, ""
        if lf is not None and _period_comparison_unrepresented(case["question"], lf, metrics):
            compile_ok = False                       # B6.4 周期对比 guard 拒识 → 生产 engine=llm 回退
        elif lf is not None:
            try:
                compiler.compile_logicform(lf, cat, tc)
                compile_ok = True
            except compiler.CompileError as e:
                cerr = f"CompileError: {e}"           # 预期回退（parser 出 LF 但编译歧义/gap）
            except Exception as e:                    # 非预期（如 time_ctx 缺窗）→ 记为异常，别崩
                cerr = f"⚠️非预期 {type(e).__name__}: {e}"
        label = classify(case, lf, compile_ok)
        labels.append(label)
        if label in ("misjudge", "miss"):
            detail.append({
                "id": case.get("id", "?"), "label": label, "question": case.get("question", ""),
                "produced": lf.to_canonical_json() if lf is not None else None,
                "expect_mode": case["expect"]["mode"], "compile_err": cerr,
            })
    return rates(labels, cases), detail


def main() -> int:
    ap = argparse.ArgumentParser(description="语义层激活门 (P1-③) eval-live 跑批")
    ap.add_argument("--runs", type=int, default=1, help="跑几轮（flaky 波动分布；守护者建议 3-5）")
    ap.add_argument("--model", default=None, help="模型 key（默认 env EVAL_MODEL 或 anthropic/claude-haiku-4.5）")
    ap.add_argument("--limit", type=int, default=0, help="仅跑前 N 个 case（0=全部；快速冒烟/迭代用，非激活裁定）")
    ap.add_argument("--json", dest="json_out", default=None, help="结果落 JSON 路径（可选，留档）")
    args = ap.parse_args()

    model, model_src = resolve_eval_model(args.model)
    or_key, key_src = _resolve_or_key()
    if not or_key:
        print("❌ 未解析到 OpenRouter API key（env OPENROUTER_API_KEY 与 DB app_settings 均空）。\n"
              "   设 env：OPENROUTER_API_KEY=sk-or-... python scripts/eval_semantic_live.py\n"
              "   或确保运行环境的 knot.db 已配 openrouter_api_key。", file=sys.stderr)
        return 2

    catalog, cases = load_semantic_corpus()
    if args.limit > 0:
        cases = cases[: args.limit]
    metrics = catalog_metrics(catalog)
    cat, tc = catalog_arg(catalog), eval_time_ctx()

    # 令内部 compiler.list_metrics(catalog_id)（compiler.py:336 延迟 import）取语料 metrics —— DB-free 确定性编译
    import knot.repositories.metric_repo as mr
    mr.list_metrics = lambda cid=None: metrics  # runner 一次性进程，无需还原

    real = _corpus_is_real()
    should_hit = sum(1 for c in cases if c["expect"]["mode"] == "hit")
    print("=" * 66)
    print("KNOT 语义层 eval-live 跑批（P1-③ 激活门：命中率 ≥90% ∧ 误判 ==0）")
    print("=" * 66)
    business_rules, br_src = resolve_business_rules(catalog)
    corpus_tag = "真 OHX (semantic_cases.yaml)" if real else "⚠️ .example 假域 = harness 自检，非真准确率！"
    print(f"语料 : {corpus_tag}")
    print(f"用例 : {len(cases)}（应命中 {should_hit} / 应回退 {len(cases) - should_hit}）")
    print(f"模型 : {model}（来自 {model_src}）   OR key: {_mask(or_key)}（来自 {key_src}）")
    print(f"规则 : business_rules {len(business_rules)} chars（来自 {br_src}）")
    print(f"跑数 : {args.runs} 轮（顺序执行，每 case live parse）")
    if not real:
        print("\n⚠️  当前跑的是假域 .example —— 这只验 harness 正确性（应 ~100%），"
              "不能作激活依据！请先 cp 出 tests/eval/semantic_cases.yaml 填真 OHX。")

    run_rates, all_detail = [], []
    for i in range(1, args.runs + 1):
        r, detail = _run_once(cases, metrics, cat, tc, model, or_key, business_rules)
        run_rates.append(r)
        all_detail.append(detail)
        print(f"\n轮{i}: 命中率 {r['hit_rate']:.1%} ({r['hit']}/{r['should_hit']}) · "
              f"误判 {r['misjudge']} · 漏判 {r['miss']} · 正确回退 {r['correct_fallback']}")

    hit_rates = [r["hit_rate"] for r in run_rates]
    misjudges = [r["misjudge"] for r in run_rates]
    min_hr, max_mj = min(hit_rates), max(misjudges)

    print("\n" + "-" * 66)
    print(f"分布（{args.runs} 轮）: 命中率 min {min_hr:.1%} / mean {statistics.mean(hit_rates):.1%} / "
          f"max {max(hit_rates):.1%}   误判 max {max_mj}")

    # 曾出问题的 case 去重汇总（并集）
    seen, problems = set(), []
    for detail in all_detail:
        for d in detail:
            if d["id"] not in seen:
                seen.add(d["id"])
                problems.append(d)
    if problems:
        print(f"\n问题项（曾误判/漏判，{len(problems)} 个 case —— 修这些再复跑）：")
        for d in problems:
            print(f"  [{d['label']}] {d['id']}  「{d['question']}」（expect={d['expect_mode']}）")
            print(f"      produced: {d['produced']}")
            if d.get("compile_err"):
                print(f"      compile : {d['compile_err']}")
    else:
        print("\n✅ 无误判/漏判 case。")

    hit_pass = min_hr >= _HIT_RATE_GATE
    mj_pass = max_mj == _MISJUDGE_GATE
    print("\n" + "=" * 66)
    print("激活门裁定")
    print(f"  命中率门（所有轮 ≥{_HIT_RATE_GATE:.0%}）: {'PASS' if hit_pass else 'FAIL'}  (min {min_hr:.1%})")
    print(f"  误判门  （所有轮 =={_MISJUDGE_GATE}）    : {'PASS' if mj_pass else 'FAIL'}  (max {max_mj})")
    sampled = args.limit > 0
    overall = hit_pass and mj_pass and real and not sampled
    if overall:
        print("→ 总: ✅ PASS —— 满足激活门。可开 KNOT_SEMANTIC_LAYER=true（真域 · 建议再多跑几轮确认稳定）。")
    elif sampled:
        print(f"→ 总: ⚠️ 不作数（--limit {args.limit} 抽样，非全语料）—— 去掉 --limit 跑全量才作激活裁定。")
    elif not real:
        print("→ 总: ⚠️ 不作数（假域 .example）—— 填真 OHX semantic_cases.yaml 后复跑。")
    else:
        why = []
        if not hit_pass:
            why.append(f"命中率 {min_hr:.1%} < 90%")
        if not mj_pass:
            why.append(f"误判 {max_mj} > 0（安全线，必清零）")
        print(f"→ 总: ❌ FAIL —— {'；'.join(why)}。先修上列问题项再复跑。")
    print("=" * 66)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "corpus_real": real, "model": model, "runs": args.runs,
            "run_rates": run_rates, "min_hit_rate": min_hr, "max_misjudge": max_mj,
            "gate_pass": overall, "problems": problems,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[记录] 已写 {args.json_out}")

    return 0 if overall else 1


def _with_tenant_ctx(fn):
    """v0.9.3 R-8'：standalone CLI 无 middleware ⇒ 无 tenant ctx。

    catalog 载体自 v0.9.3 起 per-tenant，无 ctx 读 catalog 会 fail-closed raise → business_rules 静默变空
    → eval 命中率下滑会被误判成「语义层回归」（2026-07-18 假回归同型，正是立 R-STORM 的那个案例）。
    故显式 set ctx，镜像 `knot/scripts/purge_audit_log.py:97-109` 的既有先例；finally reset。
    """
    from knot.core import tenant_context as _tc
    from knot.repositories import tenant_repo as _tr
    try:
        tok = _tc.set_active_tenant(_tr.resolve_single_tenant())
    except Exception as e:
        sys.stderr.write(
            f"\n\033[91m[eval] 无法解析 tenant ctx：{e}\033[0m\n"
            "  → catalog 自 v0.9.3 起 per-tenant（fail-closed）；CLI 必须能解析租户。\n"
            "  → 请确认 data/platform.db 存在且恰有 1 个 active 租户。\n"
        )
        return 1
    try:
        return fn()
    finally:
        _tc.reset_active_tenant(tok)


if __name__ == "__main__":
    sys.exit(_with_tenant_ctx(main))
