"""tests/api/test_budget_config_audit.py — v0.6.5.9 回归守护。

v0.6→v0.7 整体审核（v0.4 远古守护者）发现：admin.py budget-config PUT 端点的
audit() 调用参数错位（裸字符串 "budget.config_update" 塞进 actor 位 + 2 个多余
位置参 → `audit(request, actor, **kwargs)` 必然 TypeError）。因 set_app_setting
先执行，端点崩在审计前 → 500 + settings 半写入 + 0 审计留痕。

修复（v0.6.5.9）：正确 kwargs 形式 audit(request, admin, action="config.budget_update",
resource_type="budget", ...) + AuditAction Literal 补 config.budget_update。
"""
from knot.repositories import audit_repo


def _last_action(prefix: str):
    for r in audit_repo.list_filtered(page=1, size=200):
        if r["action"].startswith(prefix):
            return r
    return None


def test_budget_config_put_succeeds_and_audits(client, auth_headers):
    """回归：PUT budget-config 不再 TypeError 崩溃 → 200 + 落一条 config.budget_update 审计。"""
    r = client.put("/api/admin/budget-config", headers=auth_headers, json={
        "monthly_token_cap": 1_000_000,
        "per_conv_token_cap": 50_000,
        "warn_pct": 80,
        "default_model": "anthropic/claude-haiku-4.5",
        "rate_limit_per_min": 30,
    })
    assert r.status_code == 200, f"budget-config PUT 应 200（修复前 TypeError→500）；实际 {r.status_code}: {r.text}"

    rec = _last_action("config.budget_update")
    assert rec is not None, "budget-config 更新须落一条 config.budget_update 审计（修复前 0 审计）"
    assert rec["resource_type"] == "budget"
