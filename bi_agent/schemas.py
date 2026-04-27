from typing import List, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateConversationRequest(BaseModel):
    title: str = "新对话"


class QueryRequest(BaseModel):
    question: str
    model_key: str = ""
    api_key: str = ""
    use_agent: bool = False
    upload_id: Optional[int] = None


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
    display_name: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    doris_host: Optional[str] = None
    doris_port: Optional[int] = None
    doris_user: Optional[str] = None
    doris_password: Optional[str] = None
    doris_database: Optional[str] = None
    default_source_id: Optional[int] = None
    is_active: Optional[int] = None
    source_ids: Optional[List[int]] = None


class DataSourceRequest(BaseModel):
    name: str
    description: str = ""
    db_host: str
    db_port: int = 9030
    db_user: str
    db_password: str
    db_database: str
    db_type: str = "doris"


class UpdateDataSourceRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    db_host: Optional[str] = None
    db_port: Optional[int] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_database: Optional[str] = None
    db_type: Optional[str] = None
    is_active: Optional[int] = None


class UpdateUserConfigRequest(BaseModel):
    api_key: Optional[str] = None
    preferred_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    openrouter_api_key: Optional[str] = None
    embedding_api_key: Optional[str] = None


class AgentModelConfigRequest(BaseModel):
    clarifier: str = ""
    sql_planner: str = ""
    presenter: str = ""
