"""
seed_v021_b3.py — 一次性 seed：6 条 few-shot + 4 个 agent 的 prompt 覆盖（在内置基础上加业务约束）

幂等：先清掉本脚本之前 seed 的 few-shots（按 question 标记），再覆盖 prompt_templates。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bi_agent" / "core"))

import persistence  # noqa: E402

FEW_SHOTS = [
    {
        "question": "昨天注册用户数",
        "sql": "SELECT COUNT(*) AS cnt FROM users WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
        "type": "metric",
    },
    {
        "question": "最近 7 天每日 GMV 趋势",
        "sql": "SELECT DATE(pay_time) AS d, SUM(amount) AS gmv FROM orders "
               "WHERE pay_time >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) GROUP BY d ORDER BY d",
        "type": "trend",
    },
    {
        "question": "本月新用户数对比上月",
        "sql": ("SELECT "
                "SUM(CASE WHEN DATE_FORMAT(created_at,'%Y-%m')=DATE_FORMAT(CURDATE(),'%Y-%m') THEN 1 ELSE 0 END) AS this_month, "
                "SUM(CASE WHEN DATE_FORMAT(created_at,'%Y-%m')=DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH),'%Y-%m') THEN 1 ELSE 0 END) AS last_month "
                "FROM users"),
        "type": "compare",
    },
    {
        "question": "Top 10 付费用户",
        "sql": "SELECT user_id, SUM(amount) AS total FROM orders WHERE status='paid' "
               "GROUP BY user_id ORDER BY total DESC LIMIT 10",
        "type": "rank",
    },
    {
        "question": "各支付渠道占比",
        "sql": ("SELECT pay_channel, COUNT(*) AS cnt, "
                "ROUND(COUNT(*)*100.0/SUM(COUNT(*)) OVER (),2) AS pct "
                "FROM orders WHERE status='paid' GROUP BY pay_channel"),
        "type": "distribution",
    },
    {
        "question": "近 30 天注册用户的 D1 留存率",
        "sql": ("SELECT DATE(u.created_at) AS reg_day, "
                "COUNT(DISTINCT u.id) AS new_users, "
                "COUNT(DISTINCT CASE WHEN DATE(l.login_time)=DATE_ADD(DATE(u.created_at), INTERVAL 1 DAY) THEN u.id END) AS d1 "
                "FROM users u LEFT JOIN user_logins l ON l.user_id=u.id "
                "WHERE u.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) "
                "GROUP BY reg_day ORDER BY reg_day"),
        "type": "retention",
    },
]

_TAIL = (
    "\n\n## 业务约束（admin 追加）\n"
    "{rules}"
)

PROMPT_OVERRIDES = {
    "clarifier": "{__default__}" + _TAIL.format(rules=(
        "- 时间口径默认 created_at；金额单位默认元\n"
        "- 用户提到「注册」默认对应 user.created_at；「下单」默认对应 orders.created_at；「支付/付款」默认对应 orders.pay_time\n"
        "- 不要把 ≤ 今日的日期判断为未来日期"
    )),
    "sql_planner": "{__default__}" + _TAIL.format(rules=(
        "- 优先用窗口函数避免相关子查询；表别名用 t1/t2 不要用单字母 a/b\n"
        "- 占比类计算统一用 ROUND(X*100.0/SUM(X) OVER(), 2)\n"
        "- 同环比统一用 SUM(CASE WHEN ... THEN 1 ELSE 0 END) 方式落在一行"
    )),
    "validator": "{__default__}" + _TAIL.format(rules=(
        "- 数值结果若全为 0 或全为 NULL 视为 low confidence\n"
        "- 时间筛选若把 ≤ 今日的日期判定为未来导致空集，confidence=low 并在 issues 写「日期判断错误」\n"
        "- 单聚合标量结果（COUNT/SUM）非 0 即 high"
    )),
    "presenter": "{__default__}" + _TAIL.format(rules=(
        "- 洞察用动词开头，不超过 3 句\n"
        "- 数值带单位（元/人/单/%）；同比环比带正负号\n"
        "- suggested_followups 给 2 条，每条 ≤ 15 字"
    )),
}


def main():
    persistence.init_db()

    # few-shot：清掉重名再插入（幂等）
    questions = {fs["question"] for fs in FEW_SHOTS}
    existing = persistence.list_few_shots()
    for ex in existing:
        if ex["question"] in questions:
            persistence.delete_few_shot(ex["id"])
    inserted = persistence.bulk_insert_few_shots(FEW_SHOTS)
    print(f"[seed] few_shots: inserted {inserted}, total now = {len(persistence.list_few_shots())}")

    # prompt_templates：直接覆盖
    for agent, content in PROMPT_OVERRIDES.items():
        persistence.set_prompt_template(agent, content, updated_by=None)
    print(f"[seed] prompt_templates: set {len(PROMPT_OVERRIDES)} agents")
    for row in persistence.list_prompt_templates():
        print(f"  - {row['agent_name']}: {len(row['content'])} chars")


if __name__ == "__main__":
    main()
