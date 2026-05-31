from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ValidationError
from .schemas import AppSpec
from .data_schema_generator import DataSchema
from .integration_registry import IntegrationRegistry
from .repair_engine import RepairEngine, RepairLog


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str]
    repairs: List[str]
    repair_logs: List[RepairLog]


class SpecValidator:
    """Comprehensive validation with repair engine integration."""

    def __init__(self) -> None:
        self.repair_engine = RepairEngine()

    def validate_appspec(self, spec: AppSpec) -> ValidationResult:
        """Validate complete AppSpec with all cross-layer checks."""
        errors = self._collect_appspec_errors(spec)

        repairs: List[str] = []
        if errors:
            repairs = self._attempt_repairs(errors, spec)
            if repairs:
                errors = self._collect_appspec_errors(spec)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            repairs=repairs,
            repair_logs=self.repair_engine.get_logs(),
        )

    def _collect_appspec_errors(self, spec: AppSpec) -> List[str]:
        errors: List[str] = []

        # 1. Page-API consistency only for pages that depend on data sources
        endpoint_paths = {ep.path for ep in spec.api_endpoints}
        for page in spec.pages:
            page_sources = [comp.data_source for comp in page.components if comp.data_source]
            if page_sources and page.path not in endpoint_paths:
                errors.append(f"Page '{page.name}' ({page.path}) has no corresponding API endpoint")

        # 2. Auth rules check
        role_set = set(spec.auth_rules.roles)
        for endpoint in spec.api_endpoints:
            for role in endpoint.roles_allowed:
                if role not in role_set:
                    errors.append(f"Endpoint {endpoint.name} references undefined role '{role}'")

        # 3. Integration hook validation
        for hook in spec.integration_hooks:
            if not IntegrationRegistry.validate_integration(hook.integration_id, hook.action_id):
                errors.append(f"Integration hook '{hook.id}' references invalid integration '{hook.integration_id}' or action '{hook.action_id}'")

        # 4. Workflow stub entity validation
        entity_names = {entity.lower() for entity in {*(page.name for page in spec.pages), *(ep.linked_entity or '' for ep in spec.api_endpoints)}}
        for stub in spec.workflow_stubs:
            trigger_entity = stub.trigger.entity if hasattr(stub.trigger, 'entity') else getattr(stub, 'trigger_entity', None)
            if trigger_entity and trigger_entity.lower() not in entity_names:
                errors.append(f"Workflow stub '{stub.name}' references non-existent entity '{trigger_entity}'")
            if not IntegrationRegistry.validate_integration(stub.integration_id, stub.action_id):
                errors.append(f"Workflow stub '{stub.name}' references invalid integration '{stub.integration_id}' or action '{stub.action_id}'")

        return errors

    def validate_data_schema(self, schema: DataSchema) -> ValidationResult:
        """Validate DataSchema for consistency."""
        errors: List[str] = []

        entity_names = schema.get_all_entity_names()

        # 1. Every entity must have tenantId
        for entity in schema.entities:
            if not entity.has_tenant_id():
                errors.append(f"Entity '{entity.name}' missing required 'tenant_id' field")

        # 2. Relations must reference valid entities
        for relation in schema.relations:
            if relation.source_entity not in entity_names:
                errors.append(f"Relation has invalid source entity '{relation.source_entity}'")
            if relation.target_entity not in entity_names:
                errors.append(f"Relation has invalid target entity '{relation.target_entity}'")

        # 3. Field relations must have valid targets
        for entity in schema.entities:
            for field in entity.fields:
                if field.is_relation and field.relation_target:
                    if field.relation_target not in entity_names:
                        errors.append(f"Field '{field.name}' in entity '{entity.name}' references invalid target '{field.relation_target}'")

        if not errors:
            return ValidationResult(valid=True, errors=[], repairs=[], repair_logs=[])

        return ValidationResult(valid=False, errors=errors, repairs=[], repair_logs=self.repair_engine.get_logs())

    def _attempt_repairs(self, errors: List[str], spec: AppSpec) -> List[str]:
        """Apply targeted repair strategies."""
        repairs: List[str] = []

        for error in errors:
            if "has no corresponding API endpoint" in error:
                page_path = error.split("'")[1]
                from .schemas import Endpoint, ResponseSchema, SchemaField
                endpoint = Endpoint(
                    name=f"Auto-generated for {page_path}",
                    path=page_path,
                    method="GET",
                    description="Auto-generated to satisfy page-API consistency",
                    response_schema=ResponseSchema(fields=[SchemaField(name="items", type="array")]),
                    auth_required=True,
                    roles_allowed=spec.auth_rules.roles or ["user"],
                )
                spec.api_endpoints.append(endpoint)
                repairs.append(f"Added endpoint for page '{page_path}'")

            elif "references undefined role" in error:
                role = error.split("'")[1]
                if role not in spec.auth_rules.roles:
                    spec.auth_rules.roles.append(role)
                    repairs.append(f"Added missing role '{role}'")

            elif "references invalid integration" in error:
                hook_id = error.split("'")[1]
                for hook in spec.integration_hooks:
                    if hook.id == hook_id:
                        spec.integration_hooks.remove(hook)
                        repairs.append(f"Removed invalid integration hook '{hook_id}'")
                        break

            elif "references non-existent entity" in error:
                repairs.append(f"Consistency issue noted: {error}")

        return repairs

    @classmethod
    def load_json(cls, payload: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            parsed = json.loads(payload)
            return parsed, None
        except json.JSONDecodeError as exc:
            return None, str(exc)

    @classmethod
    def parse_spec(cls, payload: str) -> Tuple[Optional[AppSpec], Optional[str]]:
        parsed, error = cls.load_json(payload)
        if error:
            return None, f"Invalid JSON payload: {error}"
        try:
            spec = AppSpec.parse_obj(parsed)
            return spec, None
        except ValidationError as exc:
            return None, str(exc)
