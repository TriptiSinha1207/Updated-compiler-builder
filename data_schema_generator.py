from __future__ import annotations
from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field


class FieldSchema(BaseModel):
    name: str
    type: str  # "string" | "integer" | "boolean" | "datetime" | "json" | "text"
    nullable: bool = False
    is_relation: bool = False
    is_primary: bool = False
    is_unique: bool = False
    relation_type: str | None = None  # "hasMany" | "belongsTo" | "hasOne"
    relation_target: str | None = None
    foreign_key: str | None = None


class RelationSchema(BaseModel):
    type: str  # "hasMany" | "belongsTo" | "hasOne"
    source_entity: str
    target_entity: str
    foreign_key: str
    on_delete: str = "cascade"  # "cascade" | "restrict" | "set_null"


class EntitySchema(BaseModel):
    name: str
    table_name: str  # snake_case
    fields: List[FieldSchema]
    relations: List[RelationSchema] = Field(default_factory=list)

    def get_primary_key(self) -> str:
        for field in self.fields:
            if field.is_primary:
                return field.name
        return "id"

    def has_tenant_id(self) -> bool:
        return any(f.name == "tenant_id" for f in self.fields)


class DataSchema(BaseModel):
    entities: List[EntitySchema]
    relations: List[RelationSchema] = Field(default_factory=list)

    def get_entity(self, name: str) -> EntitySchema | None:
        return next((e for e in self.entities if e.name.lower() == name.lower()), None)

    def get_all_entity_names(self) -> Set[str]:
        return {e.name for e in self.entities}


class DataSchemaGenerator:
    """Generate DataSchema from AppIntent with tenantId on every entity."""

    CORE_ENTITIES = {
        "user": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="email", type="string", is_unique=True),
            FieldSchema(name="password_hash", type="string"),
            FieldSchema(name="role", type="string"),
            FieldSchema(name="plan", type="string", nullable=True),
            FieldSchema(name="created_at", type="datetime"),
            FieldSchema(name="updated_at", type="datetime"),
        ],
        "contact": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="first_name", type="string"),
            FieldSchema(name="last_name", type="string", nullable=True),
            FieldSchema(name="email", type="string"),
            FieldSchema(name="phone", type="string", nullable=True),
            FieldSchema(name="company", type="string", nullable=True),
            FieldSchema(name="owner_id", type="integer", is_relation=True, relation_type="belongsTo", relation_target="user"),
            FieldSchema(name="created_at", type="datetime"),
        ],
        "payment": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="user_id", type="integer", is_relation=True, relation_type="belongsTo", relation_target="user"),
            FieldSchema(name="plan_id", type="integer", is_relation=True, relation_type="belongsTo", relation_target="plan"),
            FieldSchema(name="amount_cents", type="integer"),
            FieldSchema(name="currency", type="string", nullable=True),
            FieldSchema(name="status", type="string"),
            FieldSchema(name="stripe_charge_id", type="string", nullable=True),
            FieldSchema(name="created_at", type="datetime"),
        ],
        "plan": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="name", type="string"),
            FieldSchema(name="price_cents", type="integer"),
            FieldSchema(name="features", type="json", nullable=True),
            FieldSchema(name="created_at", type="datetime"),
        ],
        "analytics": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="metric_name", type="string"),
            FieldSchema(name="metric_value", type="text"),
            FieldSchema(name="entity_type", type="string", nullable=True),
            FieldSchema(name="created_at", type="datetime"),
        ],
        "task": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="title", type="string"),
            FieldSchema(name="description", type="text", nullable=True),
            FieldSchema(name="status", type="string"),
            FieldSchema(name="priority", type="string", nullable=True),
            FieldSchema(name="assigned_to", type="integer", is_relation=True, relation_type="belongsTo", relation_target="user", nullable=True),
            FieldSchema(name="created_at", type="datetime"),
        ],
        "product": [
            FieldSchema(name="id", type="integer", is_primary=True),
            FieldSchema(name="tenant_id", type="string", is_relation=True),
            FieldSchema(name="name", type="string"),
            FieldSchema(name="description", type="text", nullable=True),
            FieldSchema(name="price_cents", type="integer"),
            FieldSchema(name="inventory_count", type="integer"),
            FieldSchema(name="created_at", type="datetime"),
        ],
    }

    @classmethod
    def generate(cls, intent: Any) -> DataSchema:
        entities: List[EntitySchema] = []
        entity_names = set(intent.entities) | {"user"}  # user always included

        for entity_name in entity_names:
            schema = cls.CORE_ENTITIES.get(entity_name)
            if schema:
                entity = EntitySchema(
                    name=entity_name,  # Keep lowercase for consistency
                    table_name=entity_name.lower(),
                    fields=schema.copy(),
                )
                if not entity.has_tenant_id():
                    entity.fields.insert(1, FieldSchema(name="tenant_id", type="string", is_relation=True))
                entities.append(entity)
            else:
                entity = EntitySchema(
                    name=entity_name,  # Keep lowercase
                    table_name=entity_name.lower(),
                    fields=[
                        FieldSchema(name="id", type="integer", is_primary=True),
                        FieldSchema(name="tenant_id", type="string", is_relation=True),
                        FieldSchema(name="name", type="string"),
                        FieldSchema(name="created_at", type="datetime"),
                    ],
                )
                entities.append(entity)

        relations = cls._generate_relations(entities)
        return DataSchema(entities=entities, relations=relations)

    @classmethod
    def _generate_relations(cls, entities: List[EntitySchema]) -> List[RelationSchema]:
        relations: List[RelationSchema] = []
        entity_names = {e.name.lower() for e in entities}

        for entity in entities:
            for field in entity.fields:
                if field.is_relation and field.relation_target and field.relation_type == "belongsTo":
                    target_lower = field.relation_target.lower()
                    if target_lower in entity_names:
                        relations.append(
                            RelationSchema(
                                type="belongsTo",
                                source_entity=entity.name,
                                target_entity=field.relation_target.lower(),  # Use lowercase
                                foreign_key=field.name,
                                on_delete="cascade",
                            )
                        )

        return relations
