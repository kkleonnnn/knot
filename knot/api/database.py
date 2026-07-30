from fastapi import APIRouter, Depends

from knot.adapters.db import doris as db_connector
from knot.api.deps import get_current_user, require_tenant_admin
from knot.api.schemas import DataSourceRequest
from knot.services.engine_cache import get_user_databases, get_user_engine

router = APIRouter()


@router.get("/api/db/status")
async def db_status(user=Depends(get_current_user)):
    engine, schema = get_user_engine(user)
    if engine is None:
        return {"connected": False, "message": "未配置数据库连接", "tables": 0}
    try:
        ok, msg = db_connector.test_connection(engine)
        tables = schema.count("###") if schema else 0
        return {"connected": ok, "message": msg, "tables": tables}
    except Exception as e:
        return {"connected": False, "message": str(e)[:200], "tables": 0}


@router.get("/api/db/schema")
async def get_db_schema(user=Depends(get_current_user)):
    engine, _ = get_user_engine(user)
    if engine is None:
        return {"tables": []}
    databases = get_user_databases(user["id"])
    return {"tables": db_connector.get_schema_structured(engine, databases=databases)}


# v0.8.20 F4（SSRF）：db/test 用 db_host/db_port 建任意连接 = 内网探测面。收紧 get_current_user
# → require_tenant_admin（对齐 datasources CRUD 的 admin-only 信任级；低权 analyst 不再能盲扫内网）。
@router.post("/api/db/test")
async def test_db_connection(req: DataSourceRequest, admin=Depends(require_tenant_admin)):
    try:
        engine = db_connector.create_engine(
            req.db_host, req.db_port, req.db_user, req.db_password, req.db_database
        )
        ok, msg = db_connector.test_connection(engine)
        return {"connected": ok, "message": msg}
    except Exception as e:
        return {"connected": False, "message": str(e)[:200]}
