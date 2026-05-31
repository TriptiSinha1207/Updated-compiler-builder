from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class RepairLog(BaseModel):
    strategy: str  # "structural" | "field" | "consistency"
    error_input: str
    error_message: str
    outcome: str  # "repaired" | "escalated" | "failed"
    details: Dict[str, Any]


class RepairEngine:
    """Targeted fix strategies before escalation.

    Three minimum repair strategies:
    1. Structural repair — malformed or truncated JSON
    2. Field repair — missing or wrongly typed field
    3. Consistency repair — broken cross-layer reference
    """

    def __init__(self) -> None:
        self.logs: List[RepairLog] = []

    def repair_json(self, malformed_json: str) -> tuple[Optional[Dict[str, Any]], Optional[RepairLog]]:
        """Try to extract and repair malformed JSON."""
        log_entry = RepairLog(
            strategy="structural",
            error_input=malformed_json[:200],
            error_message="Malformed JSON",
            outcome="failed",
            details={},
        )

        # Try extracting valid JSON substring
        for start_idx in range(len(malformed_json)):
            for end_idx in range(len(malformed_json), start_idx, -1):
                try:
                    candidate = malformed_json[start_idx:end_idx]
                    parsed = json.loads(candidate)
                    log_entry.outcome = "repaired"
                    log_entry.details = {"extracted_from": start_idx, "extracted_to": end_idx}
                    self.logs.append(log_entry)
                    return parsed, log_entry
                except json.JSONDecodeError:
                    continue

        self.logs.append(log_entry)
        return None, log_entry

    def repair_missing_fields(self, data: Dict[str, Any], required_fields: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[RepairLog]]:
        """Fill missing required fields with typed defaults."""
        log_entry = RepairLog(
            strategy="field",
            error_input=json.dumps(data)[:200],
            error_message="Missing required fields",
            outcome="repaired",
            details={},
        )

        filled_count = 0
        for field_name, field_type in required_fields.items():
            if field_name not in data:
                if field_type == "string":
                    data[field_name] = ""
                elif field_type == "integer":
                    data[field_name] = 0
                elif field_type == "boolean":
                    data[field_name] = False
                elif field_type == "array":
                    data[field_name] = []
                elif field_type == "object":
                    data[field_name] = {}
                else:
                    data[field_name] = None
                filled_count += 1

        log_entry.details = {"filled_count": filled_count, "fields": list(required_fields.keys())}
        self.logs.append(log_entry)
        return data, log_entry

    def repair_entity_reference(
        self, data: Dict[str, Any], entity_key: str, valid_entities: List[str]
    ) -> tuple[Dict[str, Any], Optional[RepairLog]]:
        """Repair broken entity references."""
        log_entry = RepairLog(
            strategy="consistency",
            error_input=json.dumps(data)[:200],
            error_message=f"Invalid entity reference in {entity_key}",
            outcome="failed",
            details={"entity_key": entity_key, "valid_entities": valid_entities},
        )

        if entity_key not in data:
            self.logs.append(log_entry)
            return data, log_entry

        ref_entity = data[entity_key]
        if isinstance(ref_entity, str):
            if ref_entity.lower() not in [e.lower() for e in valid_entities]:
                if valid_entities:
                    data[entity_key] = valid_entities[0]
                    log_entry.outcome = "repaired"
                    log_entry.details["repaired_to"] = valid_entities[0]
                    log_entry.details["original"] = ref_entity

        self.logs.append(log_entry)
        return data, log_entry

    def repair_page_api_consistency(self, pages: List[Dict[str, Any]], endpoints: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Optional[RepairLog]]:
        """Ensure every page has a corresponding API endpoint."""
        log_entry = RepairLog(
            strategy="consistency",
            error_input="pages and endpoints check",
            error_message="Page-API consistency check",
            outcome="repaired",
            details={"pages": len(pages), "endpoints_before": len(endpoints)},
        )

        endpoint_paths = {ep.get("path") for ep in endpoints}
        created_endpoints = 0

        for page in pages:
            page_path = page.get("path", "/")
            if page_path not in endpoint_paths:
                entity_name = page.get("entity", page.get("name", "data")).lower()
                endpoints.append({
                    "name": f"Get {page.get('name')}",
                    "path": page_path,
                    "method": "GET",
                    "description": f"Auto-generated endpoint for {page.get('name')}",
                    "linked_entity": entity_name,
                })
                endpoint_paths.add(page_path)
                created_endpoints += 1

        log_entry.details["endpoints_after"] = len(endpoints)
        log_entry.details["created_endpoints"] = created_endpoints
        self.logs.append(log_entry)
        return pages, log_entry

    def get_logs(self) -> List[RepairLog]:
        return self.logs

    def clear_logs(self) -> None:
        self.logs = []
