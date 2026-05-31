from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ValidationError
from .schemas import AppConfig, Endpoint, Table, TableColumn, ResponseSchema, SchemaField

class ValidationResult(BaseModel):
    valid: bool
    errors: List[str]
    repairs: List[str]

class ConfigValidator:
    @classmethod
    def validate(cls, config: AppConfig) -> ValidationResult:
        errors: List[str] = []
        table_names = {t.name for t in config.db.tables}
        endpoint_paths = {ep.path for ep in config.api.endpoints}
        role_set = set(config.auth.roles)

        for endpoint in config.api.endpoints:
            if endpoint.linked_entity and endpoint.linked_entity not in table_names:
                errors.append(f"Endpoint {endpoint.name} links to missing DB entity '{endpoint.linked_entity}'")
            for role in endpoint.roles_allowed:
                if role not in role_set:
                    errors.append(f"Endpoint {endpoint.name} references undefined role '{role}'")
            if endpoint.auth_required and endpoint.method == "POST" and endpoint.request_schema is None:
                errors.append(f"Endpoint {endpoint.name} lacks request schema for POST")

        for page in config.ui.pages:
            for comp in page.components:
                if comp.data_source and comp.data_source not in endpoint_paths:
                    errors.append(f"UI component {comp.id} references missing endpoint '{comp.data_source}'")

        for logic in config.logic:
            if logic.rule_type == "authorization" and "allowed_roles" in logic.details:
                for role in logic.details["allowed_roles"]:
                    if role not in role_set:
                        errors.append(f"Logic rule {logic.name} references undefined role '{role}'")

        if not errors:
            return ValidationResult(valid=True, errors=[], repairs=[])

        repairs = cls.repair(config, errors)
        if repairs:
            # re-validate after repair
            second_pass = cls.validate(config)
            return ValidationResult(valid=second_pass.valid, errors=second_pass.errors, repairs=repairs)
        return ValidationResult(valid=False, errors=errors, repairs=[])

    @classmethod
    def repair(cls, config: AppConfig, errors: List[str]) -> List[str]:
        repairs = []
        tables_by_name = {table.name: table for table in config.db.tables}
        endpoints_by_path = {endpoint.path: endpoint for endpoint in config.api.endpoints}

        for error in errors:
            if "links to missing DB entity" in error:
                missing = error.split("'")[1]
                if missing not in tables_by_name:
                    new_table = Table(name=missing, columns=[TableColumn(name="id", type="integer"), TableColumn(name="name", type="string", required=False)])
                    config.db.tables.append(new_table)
                    tables_by_name[missing] = new_table
                    repairs.append(f"Created missing DB table '{missing}'")
            if "references undefined role" in error:
                role = error.split("'")[1]
                if role not in config.auth.roles:
                    config.auth.roles.append(role)
                    repairs.append(f"Added missing auth role '{role}'")
            if "references missing endpoint" in error:
                data_source = error.split("'")[1]
                if data_source not in endpoints_by_path:
                    default_ep = Endpoint(
                        name=f"Auto generated endpoint {data_source}",
                        path=data_source,
                        method="GET",
                        description="Auto-generated endpoint to satisfy UI binding.",
                        response_schema=ResponseSchema(fields=[SchemaField(name="items", type="array")]),
                        auth_required=True,
                        roles_allowed=config.auth.roles or ["user"],
                    )
                    config.api.endpoints.append(default_ep)
                    endpoints_by_path[data_source] = default_ep
                    repairs.append(f"Added generated endpoint for UI data source '{data_source}'")
        return repairs

    @classmethod
    def load_json(cls, payload: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            parsed = json.loads(payload)
            return parsed, None
        except json.JSONDecodeError as exc:
            return None, str(exc)

    @classmethod
    def parse_config(cls, payload: str) -> Tuple[Optional[AppConfig], Optional[str]]:
        parsed, error = cls.load_json(payload)
        if error:
            return None, f"Invalid JSON payload: {error}"
        try:
            config = AppConfig.parse_obj(parsed)
            return config, None
        except ValidationError as exc:
            return None, str(exc)
