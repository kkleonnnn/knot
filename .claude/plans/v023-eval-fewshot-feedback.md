# BI-Agent v0.2.3 — Eval / Few-shot / Feedback 闭环

起点：v0.2.2.202604271400（已发朋友体验）
目标：把"翻车 case → 喂回 few-shot + eval"的闭环跑起来。

---

## 三个模板（你今天能做）

### A. Few-shot 模板（生产用）

文件：`bi_agent/few_shots.yaml` 或 admin 面板上传 xlsx

```yaml
- question: 昨天注册用户数
  sql: |
    SELECT COUNT(*) AS cnt
    FROM users
    WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)
  type: metric

- question: 最近 7 天每日 GMV 趋势
  sql: |
    SELECT DATE(pay_time) AS d, SUM(amount) AS gmv
    FROM orders
    WHERE pay_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
    GROUP BY d ORDER BY d
  type: trend
```

5 条原则：

1. question 写人话（"昨天注册多少人"，不是"统计昨日新增用户数量"）
2. SQL 必须能在真实库跑通
3. 每个 type ≥ 5 条；6 类 × 5 = 30 是下限
4. 覆盖业务独有口径（GMV 是否含退款、DAU 按 user_id 还是 session_id）
5. 不塞重复（10 条 Top X 不如 5 条 Top + 5 条占比）

type 值：metric / trend / compare / rank / distribution / retention

---

### B. Eval 模板（测试用）

文件：`tests/eval/cases.yaml`

```yaml
cases:
  - id: yesterday_signups
    question: 昨天注册用户数
    expects:
      intent: metric
      must_tables: [users]
      must_keywords:
        - "count"
        - "created_at"
      forbid_keywords:
        - "DELETE"
        - "UPDATE"
    judge_rubric: |
      insight 必须包含具体数字 + 简短结论；不超过 3 句；不含"建议"类废话
```

5 条原则：

1. 断言要松要稳 — `must_keywords: ["count"]` 而不是写完整 SQL 字符串
2. forbid_keywords 比 must_keywords 重要（红线钉死）
3. 每条 case 至少 1 条 forbid
4. case 来源 = 真实翻车记录，不是脑补
5. id 要稳（跑分对比靠 id）

**关键：eval 和 few-shot 不重叠** — eval 是考试，few-shot 是教材，重叠 = 作弊。

---

### C. Prompt 模板（admin 面板覆盖）

```
{__default__}

## 业务约束（admin 追加）
### 时间口径
- "注册" → user.created_at
- "下单" → orders.created_at
- "支付/付款" → orders.pay_time
- 所有日期判断不要把 ≤ 今日的当未来

### 金额口径
- 默认单位元
- GMV 默认含退款
- 占比类统一 ROUND(X*100.0/SUM(X) OVER(), 2)

### 口语映射
- "活跃用户" → 默认 30 天内有 login 记录
- "付费用户" → orders.status='paid' 至少 1 单
- "新用户" → 当周期内首次 created_at

### 表别名规则
- 用 t1/t2/t3，不用单字母 a/b
```

4 条原则：

1. 永远 `{__default__}` 打底，只追加不重写
2. 写"术语 → 字段"映射，不写"请仔细思考"废话
3. 越短越好，每条 1 行；超 500 字挪到 few-shot
4. 改完必须跑 eval

---

## 给朋友的体验须知

### 永久基线（每个新测试者都发）

- 这是**内部 BI 助手原型**，只能查数，不写代码、不聊天、不写文档
- 数据来自指定数据库，超出范围会瞎编/拒答 — 不是 bug
- 每次回答会显示 SQL，数字感觉错了请把 SQL 一起截图发回
- 速度：5-30 秒正常

### 反馈四件套（让他们这样发）

1. 原问题（一字不差）
2. 截图（含 SQL + 结果）
3. 一句结论：✅ 对 / ❌ 错 / 🤔 看不懂
4. 错的话给"正确答案大概是什么"

**不要发**："不太行"、"感觉不准" — 无信息量，无法 debug。

### v0.2.2 这版重点试

| 试法 | 暴露什么 |
|---|---|
| 同问题问 3 次 | 模型抖动 / few-shot 够不够 |
| 模糊问题（"看看用户情况"） | Clarifier 反问质量 |
| 代词追问（"那这些人里付费的呢"） | 多轮上下文 |
| 跨表问题（"付费用户的注册渠道分布"） | 多表关联 |
| 刁钻时间（"上上周日活"） | 时间解析 |

**不要试**：删/改/导出 — 这版没开放写。

### 反馈表（飞书/腾讯文档表头）

```
| 时间 | 问题原话 | 答案对错 | 期望答案 | 截图链接 | 备注 |
```

或微信直接发四件套，表格兜底。

---

## v0.2.3 todo（我下轮做）

- [ ] Few-shot 批量入库流程验证（admin 上传 xlsx 走通你今天写的 30 条）
- [ ] LLM-as-judge：`tests/eval/cases.yaml` 的 `judge_rubric` 启用 + 跑分报告
- [ ] Feedback API：`POST /api/messages/{id}/feedback {rating: -1|1, comment?}` + admin 面板「反馈」tab
- [ ] 翻车 case 一键导出 yaml：rating=-1 的 message 生成 case 模板，admin 审核后追加 `cases.yaml`
- [ ] 可选：产品内 `/feedback` 路由，测试者直接点踩留言

## 验收

- few-shot ≥ 30 条进 DB（你输入）
- eval ≥ 30 条 case；LLM-as-judge 平均分 ≥ 4/5
- 至少 1 个测试者用过 feedback 按钮，反馈出现在 admin 面板
- CHANGELOG + tag `v0.2.3.YYYYMMDDHHmm` + PR

## 不在本轮（拉清单到下下轮）

- Async LLM 切换（v0.2.4 候选，看 v0.2.2 火焰图）
- Dashboard / 订阅推送（v0.2.4 或 v0.3.0）
- 多租户 + 项目级 OpenRouter key（v0.3.0 重构）
- 角色分类（暂搁置，已确认）
- 甲方改 prompt（暂搁置，已确认）
