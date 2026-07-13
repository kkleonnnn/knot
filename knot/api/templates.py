"""
templates.py — 三类模板下载（few_shots.xlsx / prompts.xlsx / knowledge.txt）
"""
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from knot.api.deps import require_admin

router = APIRouter()


def _xlsx_bytes(header: list, sample_rows: list) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for row in sample_rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@router.get("/api/templates/{kind}")
async def download_template(kind: str, admin=Depends(require_admin)):
    if kind == "few_shots":
        data = _xlsx_bytes(
            ["question", "sql", "type", "is_active"],
            [
                ["昨天的订单总数", "SELECT COUNT(*) AS cnt FROM orders WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)", "aggregation", 1],
                ["上月各品类销售额排名", "SELECT category, SUM(amount) AS gmv FROM orders WHERE created_at >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH), '%Y-%m-01') GROUP BY category ORDER BY gmv DESC", "rank", 1],
            ],
        )
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="few_shots_template.xlsx"'},
        )

    if kind == "prompts":
        data = _xlsx_bytes(
            ["agent_name", "content"],
            [
                ["clarifier", "你是数据分析助手的「问题理解专家」……（在此填入完整 system prompt，可使用 {tables} {history} 占位符）"],
                ["sql_planner", "你是 SQL Agent……（可使用 {max_steps} {db_env} {schema} {business_ctx} 占位符）"],
                ["presenter", "你是数据洞察专家……"],
            ],
        )
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="prompts_template.xlsx"'},
        )

    if kind == "metrics":
        # v0.8.13：指标注册表批量导入模板（扁平字段；JSON 高级字段 dimensions/filters/lineage 走 UI 单建）
        data = _xlsx_bytes(
            ["name", "display", "caliber", "base_object", "date_column", "unit", "aliases"],
            [
                ["gmv", "成交额 GMV", "SUM(o.pay_amount)", "orders", "sta_date", "money", "成交额,营业额"],
                ["dau", "日活跃用户", "COUNT(DISTINCT o.user_id)", "orders", "sta_date", "count", "活跃用户,日活"],
            ],
        )
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="metrics_template.xlsx"'},
        )

    if kind == "knowledge":
        sample = (
            "# 知识库文档模板\n\n"
            "把业务术语、表关系、计算口径等知识写在此文件中，每段空行分隔。\n\n"
            "示例：\n"
            "GMV = 已支付订单的 pay_amount 之和（不含退款）。\n\n"
            "活跃用户：近 30 天内有过登录或下单行为的用户。\n"
        )
        return Response(
            content=sample.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="knowledge_template.txt"'},
        )

    if kind == "catalog":
        # v0.8.13：业务目录是结构化 JSON（非表格）→ JSON 模板；上传走 PUT /api/admin/catalog 校验。
        # v0.8.13 fixup：形状严格对齐 _template_catalog.py 真实契约 —
        #   tables = {db, table, topics[], summary}（非 {table, columns, desc}）；
        #   lexicon = {业务词: [表全名优先级...]}（list[str]，非 NL 定义串 — 否则路由按字符逐一注册假 target 静默降级）；
        #   relations = [左表全名, 左列, 右表全名, 右列, 语义?, 基数?]（第 6 元素 n:1/1:1 = 跨对象聚合 gate）。
        import json
        sample = {
            "tables": [
                {"db": "ohx_ads", "table": "ads_operation_report_daily",
                 "topics": ["运营", "日报", "注册", "充值"],
                 "summary": "平台运营日报（每日一行）：sta_date + reg_user_num + active_user_num + deposit + platform_pnl"},
            ],
            "lexicon": {
                "活跃用户": ["ohx_ads.ads_operation_report_daily"],
                "充值": ["ohx_ads.ads_operation_report_daily"],
            },
            "business_rules": "口径说明：金额单位一律 USDT；日期列 sta_date。",
            "relations": [["ohx_dwd.dwd_order", "user_id", "ohx_dwd.dwd_user_reg", "user_id", "订单下单用户即注册用户", "n:1"]],
            "field_labels": {"reg_user_num": "注册用户数", "deposit": "充值金额"},
        }
        return Response(
            content=json.dumps(sample, ensure_ascii=False, indent=2).encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="catalog_template.json"'},
        )

    raise HTTPException(status_code=404, detail="未知模板类型")
