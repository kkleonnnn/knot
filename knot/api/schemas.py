from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


# v0.6.0.20 admin 强制改密
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# v0.6.2.0 TOTP 2FA — enroll / verify / reset 4 端点共用 schema
class TotpEnrollCompleteRequest(BaseModel):
    """enroll Step 2：用户扫码后输入 1 次 6 位动态码完成 enroll（R-PB-B1-7）。

    secret 是 Step 1 enroll-init 返回的；前端必须原样回传（KNOT 不持久化中间态）。
    """
    secret: str
    code: str  # 6-digit TOTP code


class TotpVerifyRequest(BaseModel):
    """login 后 verify 步骤：用 interim_token + 6 位码完成完整登录。"""
    interim_token: str
    code: str


class TotpResetRequest(BaseModel):
    """admin 重置 user TOTP — admin 调用，target_user_id 是被重置的 user。"""
    target_user_id: int


class CreateConversationRequest(BaseModel):
    title: str = "新对话"


class QueryRequest(BaseModel):
    question: str
    model_key: str = ""
    api_key: str = ""
    use_agent: bool = False
    upload_id: int | None = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "analyst"
    doris_host: str = ""
    doris_port: int = 9030
    doris_user: str = ""
    doris_password: str = ""
    doris_database: str = ""


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    password: str | None = None
    doris_host: str | None = None
    doris_port: int | None = None
    doris_user: str | None = None
    doris_password: str | None = None
    doris_database: str | None = None
    default_source_id: int | None = None
    is_active: int | None = None
    source_ids: list[int] | None = None


class DataSourceRequest(BaseModel):
    name: str
    description: str = ""
    # v0.6.1.4 OVERRIDE #4: db_type='http' 时 DB 字段可空字符串
    db_host: str = ""
    db_port: int = 9030
    db_user: str = ""
    db_password: str = ""
    db_database: str = ""
    db_type: str = "doris"  # doris / mysql / http
    # v0.6.1.4: HTTP 类型 — JSON 字符串
    # {"base_url","auth_header","auth_value","allowed_hosts","timeout_sec"}
    http_config: str = ""


class UpdateDataSourceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_database: str | None = None
    db_type: str | None = None
    http_config: str | None = None  # v0.6.1.4 OVERRIDE #4
    is_active: int | None = None


class AgentModelConfigRequest(BaseModel):
    clarifier: str = ""
    sql_planner: str = ""
    presenter: str = ""
