from __future__ import annotations
from typing import List, Dict, Optional
from .intent import Intent
from .schemas import (
    AppConfig,
    AppMetadata,
    AuthConfig,
    APIConfig,
    DBConfig,
    LogicRule,
    PageConfig,
    PermissionRule,
    RequestSchema,
    ResponseSchema,
    SchemaField,
    Table,
    TableColumn,
    UIComponent,
    UIConfig,
    Endpoint,
    Relation,
)

class DesignGenerator:
    @classmethod
    def create(cls, intent: Intent) -> AppConfig:
        metadata = AppMetadata(
            app_name="Your App on Your Way",
            description=f"Generated application from prompt: {intent.prompt}",
            assumptions=intent.assumptions,
        )
        db = DBConfig(tables=cls._generate_tables(intent), relations=cls._generate_relations(intent))
        api = APIConfig(endpoints=cls._generate_endpoints(intent, db.tables))
        ui = UIConfig(pages=cls._generate_pages(intent, api.endpoints))
        auth = AuthConfig(roles=cls._generate_roles(intent), permissions=cls._generate_permissions(intent), rules=cls._generate_auth_rules(intent))
        logic = cls._generate_logic(intent)
        return AppConfig(metadata=metadata, ui=ui, api=api, db=db, auth=auth, logic=logic)

    @classmethod
    def _generate_tables(cls, intent: Intent) -> List[Table]:
        tables = []
        table_map = {
            "user": [
                TableColumn(name="id", type="integer"),
                TableColumn(name="email", type="string"),
                TableColumn(name="password_hash", type="string"),
                TableColumn(name="role", type="string"),
                TableColumn(name="plan", type="string", required=False),
            ],
            "contact": [
                TableColumn(name="id", type="integer"),
                TableColumn(name="first_name", type="string"),
                TableColumn(name="last_name", type="string", required=False),
                TableColumn(name="email", type="string"),
                TableColumn(name="company", type="string", required=False),
                TableColumn(name="owner_id", type="integer"),
            ],
            "plan": [
                TableColumn(name="id", type="integer"),
                TableColumn(name="name", type="string"),
                TableColumn(name="price_cents", type="integer"),
                TableColumn(name="features", type="string", required=False),
            ],
            "payment": [
                TableColumn(name="id", type="integer"),
                TableColumn(name="user_id", type="integer"),
                TableColumn(name="plan_id", type="integer"),
                TableColumn(name="amount_cents", type="integer"),
                TableColumn(name="status", type="string"),
            ],
            "analytics": [
                TableColumn(name="id", type="integer"),
                TableColumn(name="name", type="string"),
                TableColumn(name="value", type="string"),
            ],
        }
        for entity in sorted(set(intent.entities + ["user"])):
            schema = table_map.get(entity, [TableColumn(name="id", type="integer")])
            tables.append(Table(name=entity, columns=schema, primary_key="id"))
        return tables

    @classmethod
    def _generate_relations(cls, intent: Intent) -> List[Relation]:
        relations: List[Relation] = []
        if "contact" in intent.entities:
            relations.append(
                Relation(
                    source_table="contact",
                    source_column="owner_id",
                    target_table="user",
                    target_column="id",
                )
            )
        if "payment" in intent.entities:
            relations.append(
                Relation(
                    source_table="payment",
                    source_column="user_id",
                    target_table="user",
                    target_column="id",
                )
            )
            relations.append(
                Relation(
                    source_table="payment",
                    source_column="plan_id",
                    target_table="plan",
                    target_column="id",
                )
            )
        return relations

    @classmethod
    def _collection_path(cls, entity: str) -> str:
        return f"/{entity}" if entity.endswith("s") else f"/{entity}s"

    @classmethod
    def _generate_endpoints(cls, intent: Intent, tables: List[Table]) -> List[Endpoint]:
        endpoints: List[Endpoint] = []
        seen = set()
        def try_add(endpoint: Endpoint) -> None:
            key = (endpoint.method, endpoint.path)
            if key not in seen:
                seen.add(key)
                endpoints.append(endpoint)

        for table in tables:
            if table.name == "analytics" and not intent.analytics:
                continue
            for endpoint in cls._crud_for_table(table, intent.roles):
                try_add(endpoint)
        if intent.auth_required:
            try_add(cls._login_endpoint(intent.roles))
        if intent.payments:
            try_add(cls._payment_list_endpoint(intent.roles))
        if intent.analytics:
            try_add(cls._analytics_endpoint(intent.roles))
        return endpoints

    @classmethod
    def _crud_for_table(cls, table: Table, roles: List[str]) -> List[Endpoint]:
        entity = table.name
        name = entity.capitalize()
        roles_allowed = roles or ["user", "admin"]
        collection_path = cls._collection_path(entity)
        create_fields = [SchemaField(name=col.name, type=col.type, required=col.required) for col in table.columns if col.name != table.primary_key]
        return [
            Endpoint(
                name=f"List {name}",
                path=collection_path,
                method="GET",
                description=f"List all {entity}s.",
                response_schema=ResponseSchema(fields=[SchemaField(name="items", type="array")]),
                auth_required=True,
                roles_allowed=roles_allowed,
                linked_entity=entity,
            ),
            Endpoint(
                name=f"Create {name}",
                path=collection_path,
                method="POST",
                description=f"Create a new {entity}.",
                request_schema=RequestSchema(fields=create_fields),
                response_schema=ResponseSchema(fields=[SchemaField(name="id", type="integer")]),
                auth_required=True,
                roles_allowed=roles_allowed,
                linked_entity=entity,
            ),
            Endpoint(
                name=f"Get {name}",
                path=f"{collection_path}/<id>",
                method="GET",
                description=f"Retrieve a single {entity} by id.",
                response_schema=ResponseSchema(fields=[SchemaField(name="item", type="object")]),
                auth_required=True,
                roles_allowed=roles_allowed,
                linked_entity=entity,
            ),
        ]

    @classmethod
    def _login_endpoint(cls, roles: List[str]) -> Endpoint:
        return Endpoint(
            name="Login",
            path="/auth/login",
            method="POST",
            description="Authenticate a user and return a session token.",
            request_schema=RequestSchema(fields=[SchemaField(name="email", type="string"), SchemaField(name="password", type="string")]),
            response_schema=ResponseSchema(fields=[SchemaField(name="token", type="string"), SchemaField(name="role", type="string")]),
            auth_required=False,
            roles_allowed=roles or ["user", "admin"],
            linked_entity="user",
        )

    @classmethod
    def _payment_list_endpoint(cls, roles: List[str]) -> Endpoint:
        return Endpoint(
            name="List Payments",
            path="/payments",
            method="GET",
            description="Retrieve payment history.",
            response_schema=ResponseSchema(fields=[SchemaField(name="items", type="array")]),
            auth_required=True,
            roles_allowed=roles or ["user", "admin"],
            linked_entity="payment",
        )

    @classmethod
    def _analytics_endpoint(cls, roles: List[str]) -> Endpoint:
        return Endpoint(
            name="Analytics Summary",
            path="/analytics/summary",
            method="GET",
            description="Get aggregated analytics metrics.",
            response_schema=ResponseSchema(fields=[SchemaField(name="report", type="object")]),
            auth_required=True,
            roles_allowed=roles or ["admin"],
            linked_entity="analytics",
        )

    @classmethod
    def _generate_pages(cls, intent: Intent, endpoints: List[Endpoint]) -> List[PageConfig]:
        pages = []
        pages.append(PageConfig(
            name="Home",
            path="/",
            layout="hero",
            components=[UIComponent(id="home-welcome", type="text", props={"text": "Welcome to Your App on Your Way"})],
        ))
        if intent.auth_required:
            pages.append(PageConfig(
                name="Login",
                path="/login",
                layout="auth",
                components=[UIComponent(id="login-form", type="form", props={"action": "/auth/login", "fields": ["email", "password"]})],
            ))
        for page_name in sorted(set(intent.pages)):
            if page_name == "login" and intent.auth_required:
                continue
            components = cls._page_components(page_name, endpoints)
            matching_endpoints = [ep for ep in endpoints if page_name in ep.path or page_name in ep.name.lower()]
            for ep in matching_endpoints[:2]:
                components.append(UIComponent(id=f"{page_name}-{ep.name.lower().replace(' ', '-')}", type="table", data_source=ep.path, props={"endpoint": ep.path}))
            pages.append(PageConfig(name=page_name.capitalize(), path=f"/{page_name}", components=components))
        return pages

    @classmethod
    def _page_components(cls, page_name: str, endpoints: List[Endpoint]) -> List[UIComponent]:
        components: List[UIComponent] = []
        title = page_name.capitalize()
        if page_name == "dashboard":
            components.append(UIComponent(id="dashboard-summary", type="panel", props={"title": "Dashboard Overview", "subtitle": "Business health at a glance."}))
            components.append(UIComponent(id="dashboard-analytics", type="table", data_source="/analytics/summary", props={"title": "Analytics Summary"}))
        elif page_name == "contacts":
            components.append(UIComponent(id="contacts-panel", type="panel", props={"title": "Contacts"}))
            components.append(UIComponent(id="contacts-table", type="table", data_source="/contacts", props={"title": "Contact list"}))
            components.append(UIComponent(id="contacts-form", type="form", props={"title": "Add contact", "action": "/contacts", "fields": ["first_name", "last_name", "email", "company", "owner_id"]}))
        elif page_name == "analytics":
            components.append(UIComponent(id="analytics-panel", type="panel", props={"title": "Analytics Insights", "subtitle": "Key performance indicators."}))
            components.append(UIComponent(id="analytics-summary", type="table", data_source="/analytics/summary", props={"title": "Analytics report"}))
        else:
            components.append(UIComponent(id=f"{page_name}-panel", type="panel", props={"title": title}))
        return components

    @classmethod
    def _generate_roles(cls, intent: Intent) -> List[str]:
        if intent.roles:
            return intent.roles
        return ["admin", "user"]

    @classmethod
    def _generate_permissions(cls, intent: Intent) -> List[PermissionRule]:
        permissions: List[PermissionRule] = []
        roles = intent.roles or ["admin", "user"]
        resources = []
        for entity in sorted(set(intent.entities or ["contact"])):
            resources.append(entity)
            resources.append(entity + "s")
        if intent.payments:
            resources.append("payment")
            resources.append("payments")
        if intent.analytics:
            resources.append("analytics")
        for role in roles:
            actions = ["read", "write", "update"]
            if role == "user":
                actions = ["read", "write"]
            permissions.append(PermissionRule(role=role, actions=actions, resources=resources))
        return permissions

    @classmethod
    def _generate_auth_rules(cls, intent: Intent) -> Dict[str, Any]:
        rules = {}
        if intent.payments:
            rules["premium_gate"] = {"required_plan": "premium", "message": "Premium plan required for this feature."}
        if intent.analytics:
            rules["analytics_only"] = {"roles": ["admin"], "message": "Analytics access restricted to admins."}
        return rules

    @classmethod
    def _generate_logic(cls, intent: Intent) -> List[LogicRule]:
        logic = []
        if intent.payments:
            logic.append(LogicRule(
                name="premium gating",
                rule_type="access_control",
                description="Protect premium features behind a paid plan.",
                details={"required_plan": "premium"},
            ))
        if intent.analytics:
            logic.append(LogicRule(
                name="analytics admin only",
                rule_type="authorization",
                description="Allow only admin users to request analytics data.",
                details={"allowed_roles": ["admin"]},
            ))
        return logic
