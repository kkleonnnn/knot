# BI-Agent Eval

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

## 下一步（v0.2.3）

- LLM-as-judge：用 `expects.judge_rubric` 让另一个模型给洞察打分
- 多 agent 全链路（clarifier → sql_planner → presenter），不只测 sql_planner
- 加 baseline 模型 + 主模型对比报表
