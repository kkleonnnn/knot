# KNOT Eval

YAML 驱动的 SQL 生成质量回归集。

## 目标

每次 prompt / few-shot / 模型切换，跑一次确认没退化。

## 运行

```bash
# 不烧 token：只校验 cases.yaml 结构
pytest tests/eval -v -k cases_loaded

# 全量跑（每条 case 1 次 LLM 调用，约 5 token-cents）
OPENROUTER_API_KEY=sk-or-... pytest tests/eval -v

# 切模型
OPENROUTER_API_KEY=... EVAL_MODEL=anthropic/claude-haiku-4.5 pytest tests/eval -v
```

## 加 case

编辑 `cases.yaml`，至少给：

- `id`（唯一）
- `question`（用户原问题）
- `expects.must_keywords` / `expects.must_tables` / `expects.forbid_keywords`

目标到 v0.2.3 凑齐 30 条覆盖：metric / trend / compare / rank / distribution / retention 六类。

## 语义层 parser 命中率门禁（B6.2 · v0.8.1）

把 kk 手工 runbook 三率（命中/误判/漏判）固化成可复演 eval，对标上面的 v0.4.0 intent ≥90% 门禁。
**两层**（守护者 Stage 3 LOCKED）：

- **Layer 1（key-free · 主 CI 强制）** `tests/services/semantic/test_semantic_eval_corpus.py`：corpus 良构 +
  每 hit case 期望 LogicForm **确定性编译覆盖**（0 LLM/DB）+ classify scorer 逻辑。放 tests/services/semantic/
  **而非** tests/eval（后者被 `ci.yml --ignore=tests/eval` 排除，放这才每-PR 强制）。
- **Layer 2（live LLM · opt-in）** `tests/eval/test_semantic_accuracy.py`（`@_REQUIRES_KEY`）：live
  `parse_to_logicform` → canonical 匹配 → 三率 → **assert 命中率 ≥ 0.9 AND 误判数 == 0**。

```bash
# Layer 1（无 key，主 CI 已含）
pytest tests/services/semantic/test_semantic_eval_corpus.py -v

# Layer 2（live，opt-in；eval-live.yml `pytest tests/eval` 已自动纳入）
OPENROUTER_API_KEY=sk-or-... pytest tests/eval/test_semantic_accuracy.py -v
```

**corpus**：committed `semantic_cases.example.yaml` = **假域（e-commerce）harness 自检**（设计成 parser 稳过
≥95% → Layer 2 在此 assert 本质是 harness 正确性自检）。**真准确率门 = kk 在 gitignored `semantic_cases.yaml`
（真 OHX metric/表/期望 LogicForm）上跑 Layer 2** —— 激活 `KNOT_SEMANTIC_LAYER` 的 checkpoint 依据。
部署：`cp semantic_cases.example.yaml semantic_cases.yaml` 后按真业务填（期望 LF 可复用 v0.7.44 重跑已知-good LF）。

**canonical 语义**：`LogicForm.to_canonical_json()` metrics/dimensions/filters **保序不归一** → 匹配检「parser
是否复现期望确定性 LF」**非「语义等价」**（激活门恰需此）。filters 自由文本假阴风险最高 → filter-heavy hit case
用 `expect.logicforms`（≥1 期望 LF 集合，任一命中即算对）。**数值真相类误判**出 auto-eval scope，由 kk runbook live-DB 人判段兜。

**激活 checkpoint**：`KNOT_SEMANTIC_LAYER` 仍 off；kk 在真 OHX corpus 跑 Layer 2 拿命中≥90%+误判=0，连同
B6.4/6.5/6.6 全清 → 决定开 flag。B6.2 **不自动开 flag**。

## 下一步（v0.2.3）

- LLM-as-judge：用 `expects.judge_rubric` 让另一个模型给洞察打分
- 多 agent 全链路（clarifier → sql_planner → presenter），不只测 sql_planner
- 加 baseline 模型 + 主模型对比报表
