"""
templates.py — 三类模板下载（few_shots.xlsx / prompts.xlsx / knowledge.txt）
"""
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from bi_agent.api.deps import require_admin

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

    raise HTTPException(status_code=404, detail="未知模板类型")
