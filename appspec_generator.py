from __future__ import annotations
from typing import Any, Dict, List
from .data_schema_generator import DataSchema, EntitySchema
from .integration_registry import IntegrationRegistry
from .schemas import (
    AppMetadata,
    AppSpec,
    AuthConfig,
    Endpoint,
    RequestSchema,
    PageConfig,
    PermissionRule,
    ResponseSchema,
    SchemaField,
    UIComponent,
    IntegrationHook,
    WorkflowStub,
    WorkflowTrigger,
)


class AppSpecGenerator:
    """Generate AppSpec from DataSchema (Stage 3)."""

    @classmethod
    def generate(cls, data_schema: DataSchema, intent: Any) -> AppSpec:
        metadata = AppMetadata(
            app_name=getattr(intent, "app_name", "Generated App"),
            description=f"Generated from: {intent.prompt}" if hasattr(intent, "prompt") else "Generated App",
            assumptions=getattr(intent, "assumptions", []),
        )

        pages = cls._generate_pages(data_schema, intent)
        api_endpoints = cls._generate_api_endpoints(data_schema, intent)
        auth_rules = cls._generate_auth_rules(data_schema, intent)
        integration_hooks = cls._generate_integration_hooks(data_schema, intent)
        workflow_stubs = cls._generate_workflow_stubs(data_schema, intent, integration_hooks)

        return AppSpec(
            metadata=metadata,
            pages=pages,
            api_endpoints=api_endpoints,
            auth_rules=auth_rules,
            integration_hooks=integration_hooks,
            workflow_stubs=workflow_stubs,
            assumptions=getattr(intent, "assumptions", []),
        )

    @classmethod
    def _generate_pages(cls, schema: DataSchema, intent: Any) -> List[PageConfig]:
        pages: List[PageConfig] = []
        pages.append(PageConfig(
            name="Home",
            path="/",
            layout="dashboard",
            components=[UIComponent(id="home-hero", type="panel", props={"title": "Welcome"})],
        ))

        for entity in schema.entities:
            table_name_plural = entity.table_name + "s" if not entity.table_name.endswith("s") else entity.table_name
            entity_path = f"/{table_name_plural}"

            components = [
                UIComponent(id=f"{entity.table_name}-table", type="table", data_source=entity_path),
                UIComponent(id=f"{entity.table_name}-form", type="form", props={"entity": entity.name}),
            ]

            pages.append(PageConfig(
                name=entity.name.capitalize(),
                path=entity_path,
                layout="list",
                components=components,
            ))

        return pages

    @classmethod
    def _generate_api_endpoints(cls, schema: DataSchema, intent: Any) -> List[Endpoint]:
        endpoints: List[Endpoint] = []

        for entity in schema.entities:
            table_name_plural = entity.table_name + "s" if not entity.table_name.endswith("s") else entity.table_name
            collection_path = f"/{table_name_plural}"

            create_fields = [
                SchemaField(name=field.name, type=field.type, required=not field.nullable)
                for field in entity.fields
                if not field.is_primary
            ]

            endpoints.extend([
                Endpoint(
                    name=f"List {entity.name}",
                    path=collection_path,
                    method="GET",
                    description=f"List all {entity.table_name}s",
                    response_schema=ResponseSchema(fields=[SchemaField(name="items", type="array")]),
                    auth_required=True,
                    roles_allowed=["admin", "user"],
                    linked_entity=entity.name,
                ),
                Endpoint(
                    name=f"Create {entity.name}",
                    path=collection_path,
                    method="POST",
                    description=f"Create a new {entity.name}",
                    request_schema=RequestSchema(fields=create_fields),
                    response_schema=ResponseSchema(fields=[SchemaField(name="id", type="integer")]),
                    auth_required=True,
                    roles_allowed=["admin", "user"],
                    linked_entity=entity.name,
                ),
                Endpoint(
                    name=f"Get {entity.name}",
                    path=f"{collection_path}/<id>",
                    method="GET",
                    description=f"Get a single {entity.name} by id",
                    response_schema=ResponseSchema(fields=[SchemaField(name="item", type="object")]),
                    auth_required=True,
                    roles_allowed=["admin", "user"],
                    linked_entity=entity.name,
                ),
            ])

        return endpoints

    @classmethod
    def _generate_auth_rules(cls, schema: DataSchema, intent: Any) -> AuthConfig:
        roles = getattr(intent, "roles", None) or ["admin", "user"]
        resources = [entity.table_name for entity in schema.entities]

        permissions = [
            PermissionRule(role="admin", actions=["read", "write", "delete"], resources=resources),
            PermissionRule(role="user", actions=["read", "write"], resources=resources),
        ]

        return AuthConfig(roles=roles, permissions=permissions)

    @classmethod
    def _generate_integration_hooks(cls, schema: DataSchema, intent: Any) -> List[IntegrationHook]:
        hooks: List[IntegrationHook] = []
        integrations = getattr(intent, "integrations_requested", [])

        for idx, integration_id in enumerate(integrations):
            integration = IntegrationRegistry.get(integration_id)
            if not integration or not integration.actions:
                continue

            action_id = integration.actions[0].action_id
            for entity in schema.entities:
                hook = IntegrationHook(
                    id=f"{integration_id}_{entity.table_name}_{idx}",
                    integration_id=integration_id,
                    action_id=action_id,
                    trigger_entity=entity.name,
                    trigger_event="record_created",
                    payload_template={"entity_id": "<id>", "entity_name": entity.name},
                )
                hooks.append(hook)
                break  # One hook per integration for simplicity

        return hooks

    @classmethod
    def _generate_workflow_stubs(cls, schema: DataSchema, intent: Any, hooks: List[IntegrationHook]) -> List[WorkflowStub]:
        stubs: List[WorkflowStub] = []
        entity_map = {entity.name.lower(): entity for entity in schema.entities}

        for hook in hooks:
            trigger = cls._build_trigger(intent.prompt, hook.trigger_entity)
            payload = cls._build_payload(entity_map.get(hook.trigger_entity.lower()), hook.integration_id, hook.action_id)
            stub = WorkflowStub(
                name=f"Notify {hook.integration_id} on {hook.trigger_entity} {trigger.event}",
                description=f"Trigger {hook.integration_id} when {hook.trigger_entity} {trigger.event.replace('_', ' ')}.",
                trigger=trigger,
                integration_id=hook.integration_id,
                action_id=hook.action_id,
                payload=payload,
                integration_hooks=[hook],
            )
            stubs.append(stub)

        return stubs

    @classmethod
    def _build_trigger(cls, prompt: str, entity_name: str) -> WorkflowTrigger:
        normalized = prompt.lower()
        entity_label = entity_name.capitalize()
        if "closes" in normalized or "closed" in normalized or "when a deal closes" in normalized:
            return WorkflowTrigger(entity=entity_label, event="status_changed", condition="status === 'closed'")
        if "overdue" in normalized or "due date" in normalized or "past due" in normalized:
            return WorkflowTrigger(entity=entity_label, event="status_changed", condition="status === 'overdue'")
        if "approved" in normalized or "approval" in normalized or "leave is approved" in normalized:
            return WorkflowTrigger(entity=entity_label, event="status_changed", condition="status === 'approved'")
        if "low stock" in normalized or "stock below" in normalized or "out of stock" in normalized:
            return WorkflowTrigger(entity=entity_label, event="status_changed", condition="quantity <= 0")
        if "payment" in normalized or "subscription" in normalized:
            return WorkflowTrigger(entity=entity_label, event="created")
        if "confirmation" in normalized or "notify" in normalized:
            return WorkflowTrigger(entity=entity_label, event="created")
        return WorkflowTrigger(entity=entity_label, event="created")

    @classmethod
    def _build_payload(cls, entity: EntitySchema | None, integration_id: str, action_id: str) -> Dict[str, str]:
        if not entity:
            return {"entity_id": "<id>", "entity_name": "<name>"}

        integration = IntegrationRegistry.get(integration_id)
        action_schema = {}
        if integration:
            action = next((a for a in integration.actions if a.action_id == action_id), None)
            if action:
                action_schema = action.input_schema

        if action_schema:
            payload = {}
            sample_fields = [field.name for field in entity.fields if field.name != "id"]
            for idx, key in enumerate(action_schema.keys()):
                payload[key] = f"<{entity.name}.{sample_fields[idx] if idx < len(sample_fields) else 'id'}>"
            return payload

        return {"entity_id": f"<{entity.name}.id>", "entity_name": entity.name}
