from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

APP_TYPES = {
    "crm": ["crm", "customer relationship", "contact"],
    "project_management": ["project", "task", "kanban", "agile"],
    "ecommerce": ["ecommerce", "shop", "store", "product", "cart"],
    "hr_tool": ["hr", "human resources", "employee", "recruitment"],
    "inventory": ["inventory", "warehouse", "stock", "supply"],
    "content_platform": ["content", "blog", "cms", "article"],
    "analytics": ["analytics", "reporting", "dashboard", "metric"],
    "custom": [],
}

INTEGRATIONS = {
    "slack": ["slack"],
    "salesforce": ["salesforce"],
    "hubspot": ["hubspot"],
    "whatsapp": ["whatsapp"],
    "gmail": ["gmail", "email", "google"],
    "notion": ["notion"],
    "airtable": ["airtable"],
    "stripe": ["stripe", "payment", "subscription"],
    "twilio": ["twilio", "sms"],
    "webhook": ["webhook"],
    "sheets": ["google sheets", "sheets"],
    "jira": ["jira"],
    "github": ["github"],
    "zapier": ["zapier"],
}

FEATURE_KEYWORDS = {
    "login": ["login", "signin", "sign in", "log in"],
    "contacts": ["contacts", "clients", "customers"],
    "dashboard": ["dashboard"],
    "payments": ["payment", "payments", "stripe", "charge", "billing"],
    "analytics": ["analytics", "reports", "metrics", "insights"],
    "role_based_access": ["role-based access", "roles", "permissions", "admin", "user access"],
    "premium_plans": ["premium", "subscription", "plan", "paid", "membership"],
    "crm": ["crm", "customer relationship management"],
    "admin": ["admin", "administrator"],
}

ROLE_KEYWORDS = {
    "admin": ["admin", "administrator"],
    "user": ["user", "member", "customer", "client"],
    "manager": ["manager", "owner", "team lead"],
}

PAGE_KEYWORDS = ["dashboard", "contacts", "login", "register", "pricing", "analytics", "settings", "profile"]
ENTITY_KEYWORDS = {
    "user": ["user", "admin", "member", "account"],
    "contact": ["contact", "client", "customer"],
    "plan": ["plan", "subscription", "premium"],
    "payment": ["payment", "invoice", "billing"],
    "deal": ["deal", "deals"],
    "task": ["task", "tasks", "todo", "ticket"],
    "property": ["property", "properties", "real estate", "listing"],
    "employee": ["employee", "staff", "worker"],
    "leave_request": ["leave request", "time off", "vacation"],
    "performance_review": ["performance review", "review"],
    "order": ["order", "orders"],
    "product": ["product", "products"],
    "supplier": ["supplier", "suppliers"],
    "inventory": ["inventory", "stock", "warehouse"],
}

class AppType(str, Enum):
    CRM = "crm"
    PROJECT_MANAGEMENT = "project_management"
    ECOMMERCE = "ecommerce"
    HR_TOOL = "hr_tool"
    INVENTORY = "inventory"
    CONTENT_PLATFORM = "content_platform"
    ANALYTICS = "analytics"
    CUSTOM = "custom"

class Intent(BaseModel):
    prompt: str
    app_type: AppType
    features: List[str]
    pages: List[str]
    entities: List[str]
    roles: List[str]
    plans: List[str]
    integrations_requested: List[str] = []
    analytics: bool = False
    payments: bool = False
    auth_required: bool = False
    assumptions: List[str] = []
    needs_clarification: bool = False
    clarification_questions: Optional[List[str]] = None

class IntentExtractor:
    @classmethod
    def parse(cls, prompt: str) -> Intent:
        text = prompt.strip()
        normalized = text.lower()
        features = cls._extract_features(normalized)
        pages = cls._extract_pages(normalized)
        roles = cls._extract_roles(normalized)
        plans = cls._extract_plans(normalized)
        entities = cls._extract_entities(normalized, features)
        integrations = cls._extract_integrations(normalized)
        analytics = "analytics" in normalized or "report" in normalized or "metric" in normalized
        payments = "payment" in normalized or "premium" in normalized or "plan" in normalized or "billing" in normalized
        auth_required = bool(roles or any(feature in ["login", "role_based_access"] for feature in features))
        app_type = cls._extract_app_type(normalized)
        assumptions: List[str] = []
        clarification_questions: List[str] = []
        needs_clarification = False

        if not features:
            features = ["dashboard"]
            assumptions.append("No explicit features found; defaulting to a dashboard-style app.")
        if not pages:
            pages = ["dashboard"]
            assumptions.append("No explicit pages found; adding dashboard page by default.")
        if auth_required and "login" not in features:
            features.append("login")
            assumptions.append("Role access detected; adding login flow automatically.")
        if payments and "premium_plans" not in features:
            features.append("premium_plans")
            assumptions.append("Billing keywords detected; adding premium plan support.")
        if not roles and auth_required:
            roles = ["admin", "user"]
            assumptions.append("No explicit roles provided; using default roles admin and user.")
        if "conflicting" in normalized or "contradict" in normalized or ("also" in normalized and "," in normalized):
            needs_clarification = True
            clarification_questions.append("Please clarify which domain should be prioritized or what the primary MVP should include.")
        if "build something like notion" in normalized:
            assumptions.append("Notion-like collaboration is interpreted as a workspace MVP rather than full product parity.")
        if "real-time chat" in normalized and "native mobile" in normalized:
            assumptions.append("Real-time chat and native mobile are noted as advanced features; generating a web-first MVP.")

        return Intent(
            prompt=text,
            app_type=app_type,
            features=sorted(set(features)),
            pages=sorted(set(pages)),
            entities=sorted(set(entities)),
            roles=sorted(set(roles)),
            plans=sorted(set(plans)),
            integrations_requested=sorted(set(integrations)),
            analytics=analytics,
            payments=payments,
            auth_required=auth_required,
            assumptions=assumptions,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions or None,
        )

    @classmethod
    def _extract_features(cls, text: str) -> List[str]:
        return [feature for feature, keywords in FEATURE_KEYWORDS.items() if any(keyword in text for keyword in keywords)]

    @classmethod
    def _extract_pages(cls, text: str) -> List[str]:
        page_names = [keyword for keyword in PAGE_KEYWORDS if keyword in text]
        if "login" in text and "register" not in page_names:
            page_names.append("login")
        return page_names

    @classmethod
    def _extract_roles(cls, text: str) -> List[str]:
        return [role for role, keywords in ROLE_KEYWORDS.items() if any(keyword in text for keyword in keywords)]

    @classmethod
    def _extract_plans(cls, text: str) -> List[str]:
        plans: List[str] = []
        if "premium" in text:
            plans.append("premium")
        if "free" in text:
            plans.append("free")
        if "pro" in text:
            plans.append("pro")
        return plans

    @classmethod
    def _extract_entities(cls, text: str, features: List[str]) -> List[str]:
        entities = set()
        for entity, keywords in ENTITY_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                entities.add(entity)

        if "task" in text or "tasks" in text:
            entities.add("task")
        if "deal" in text or "deals" in text:
            entities.add("deal")
        if "property" in text or "properties" in text:
            entities.add("property")
        if "order" in text or "orders" in text:
            entities.add("order")
        if "product" in text or "products" in text:
            entities.add("product")
        if "supplier" in text or "suppliers" in text:
            entities.add("supplier")
        if "leave" in text or "vacation" in text or "time off" in text:
            entities.add("leave_request")
        if "performance" in text and "review" in text:
            entities.add("performance_review")
        if "stock" in text or "inventory" in text or "warehouse" in text:
            entities.add("inventory")

        if not entities and features:
            if "contacts" in features:
                entities.add("contact")
            if "payments" in features or "premium_plans" in features:
                entities.update({"plan", "payment"})

        return sorted(entities)

    @classmethod
    def _extract_app_type(cls, text: str) -> AppType:
        for app_type, keywords in APP_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return AppType(app_type.lower())
        return AppType.CUSTOM

    @classmethod
    def _extract_integrations(cls, text: str) -> List[str]:
        return [integration for integration, keywords in INTEGRATIONS.items() if any(keyword in text for keyword in keywords)]

        page_names = []
        for keyword in PAGE_KEYWORDS:
            if keyword in text:
                page_names.append(keyword)
        if "login" in text and "register" not in page_names:
            page_names.append("login")
        return page_names

    @classmethod
    def _extract_roles(cls, text: str) -> List[str]:
        roles = []
        for role, keywords in ROLE_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                roles.append(role)
        return roles

    @classmethod
    def _extract_plans(cls, text: str) -> List[str]:
        plans = []
        if "premium" in text:
            plans.append("premium")
        if "free" in text:
            plans.append("free")
        if "pro" in text:
            plans.append("pro")
        return plans

    @classmethod
    def _extract_entities(cls, text: str, features: List[str]) -> List[str]:
        entities = set()
        if "crm" in text or "contacts" in text:
            entities.add("contact")
        if "payment" in text or "billing" in text or "premium" in text or "plan" in text:
            entities.add("plan")
            entities.add("payment")
        if "login" in text or "user" in text or "admin" in text:
            entities.add("user")
        if "analytics" in text or "dashboard" in text or "report" in text:
            entities.add("analytics")
        if not entities and features:
            for feature in features:
                if feature == "contacts":
                    entities.add("contact")
                elif feature == "premium_plans":
                    entities.add("plan")
                elif feature == "payments":
                    entities.add("payment")
        return sorted(entities)