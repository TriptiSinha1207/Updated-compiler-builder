from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator, validator

class TableColumn(BaseModel):
    name: str
    type: str
    required: bool = True
    default: Optional[Any] = None

class Table(BaseModel):
    name: str
    columns: List[TableColumn]
    primary_key: str = "id"

    @validator("name")
    def normalize_name(cls, v: str) -> str:
        return v.strip().lower()

class Relation(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relation_type: str = "one-to-many"

class DBConfig(BaseModel):
    tables: List[Table]
    relations: List[Relation] = []

    @model_validator(mode="before")
    def require_tables(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not values.get("tables"):
            raise ValueError("DB schema must include at least one table")
        return values

class UIComponent(BaseModel):
    id: str
    type: str
    props: Dict[str, Any] = {}
    data_source: Optional[str] = None

class PageConfig(BaseModel):
    name: str
    path: str
    layout: str = "default"
    components: List[UIComponent]

    @validator("path")
    def ensure_path_starts_with_slash(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

class UIConfig(BaseModel):
    pages: List[PageConfig]

class SchemaField(BaseModel):
    name: str
    type: str
    required: bool = True

class RequestSchema(BaseModel):
    fields: List[SchemaField]

class ResponseSchema(BaseModel):
    fields: List[SchemaField]

class Endpoint(BaseModel):
    name: str
    path: str
    method: str
    description: str
    request_schema: Optional[RequestSchema] = None
    response_schema: ResponseSchema
    auth_required: bool = True
    roles_allowed: List[str] = []
    linked_entity: Optional[str] = None

    @validator("method")
    def upper_method(cls, value: str) -> str:
        return value.upper()

    @validator("path")
    def normalize_path(cls, value: str) -> str:
        return value if value.startswith("/") else f"/{value}"

class APIConfig(BaseModel):
    endpoints: List[Endpoint]

    @model_validator(mode="before")
    def ensure_unique_endpoints(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        seen = set()
        for endpoint in values.get("endpoints", []):
            method = endpoint.get("method") if isinstance(endpoint, dict) else endpoint.method
            path = endpoint.get("path") if isinstance(endpoint, dict) else endpoint.path
            key = (method, path)
            if key in seen:
                raise ValueError(f"Duplicate endpoint {method} {path}")
            seen.add(key)
        return values

class PermissionRule(BaseModel):
    role: str
    actions: List[str]
    resources: List[str]

class AuthConfig(BaseModel):
    roles: List[str]
    permissions: List[PermissionRule]
    rules: Dict[str, Any] = {}

class LogicRule(BaseModel):
    name: str
    rule_type: str
    description: str
    details: Dict[str, Any]

class AppMetadata(BaseModel):
    app_name: str
    description: str
    version: str = "0.1.0"
    assumptions: List[str] = []

class AppConfig(BaseModel):
    metadata: AppMetadata
    ui: UIConfig
    api: APIConfig
    db: DBConfig
    auth: AuthConfig
    logic: List[LogicRule]


class IntegrationHook(BaseModel):
    id: str
    integration_id: str
    action_id: str
    trigger_entity: str
    trigger_event: str
    payload_template: Dict[str, Any] = {}


class WorkflowTrigger(BaseModel):
    entity: str
    event: str
    condition: Optional[str] = None


class WorkflowStub(BaseModel):
    name: str
    description: str
    trigger: WorkflowTrigger
    integration_id: str
    action_id: str
    payload: Dict[str, str]
    integration_hooks: List[IntegrationHook] = []


class AppSpec(BaseModel):
    metadata: AppMetadata
    pages: List[PageConfig]
    api_endpoints: List[Endpoint]
    auth_rules: AuthConfig
    integration_hooks: List[IntegrationHook] = []
    workflow_stubs: List[WorkflowStub] = []
    assumptions: List[str] = []
