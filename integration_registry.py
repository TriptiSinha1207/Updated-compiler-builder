from __future__ import annotations
from typing import Any, Dict, List
from pydantic import BaseModel


class TriggerDescriptor(BaseModel):
    trigger_type: str  # e.g. "record_created", "record_updated", "status_changed"
    entity_event: str  # e.g. "contact", "deal", "invoice"
    description: str


class ActionDescriptor(BaseModel):
    action_id: str  # e.g. "send_slack_message", "create_lead"
    action_name: str
    description: str
    input_schema: Dict[str, Any]  # JSON schema for payload
    output_schema: Dict[str, Any]  # JSON schema for response


class Integration(BaseModel):
    id: str
    display_name: str
    auth_type: str  # "oauth2" | "api_key" | "webhook_secret" | "none"
    triggers: List[TriggerDescriptor]
    actions: List[ActionDescriptor]
    is_implemented: bool = False


class IntegrationRegistry:
    """First-class integration registry for the AppSpec."""

    REGISTRY: Dict[str, Integration] = {}

    @classmethod
    def register(cls, integration: Integration) -> None:
        cls.REGISTRY[integration.id] = integration

    @classmethod
    def get(cls, integration_id: str) -> Integration | None:
        return cls.REGISTRY.get(integration_id)

    @classmethod
    def list_all(cls) -> Dict[str, Integration]:
        return cls.REGISTRY

    @classmethod
    def validate_integration(cls, integration_id: str, action_id: str | None = None) -> bool:
        integration = cls.get(integration_id)
        if not integration:
            return False
        if action_id:
            return any(action.action_id == action_id for action in integration.actions)
        return True


# Working Integrations (5)

SLACK = Integration(
    id="slack",
    display_name="Slack",
    auth_type="oauth2",
    is_implemented=True,
    triggers=[
        TriggerDescriptor(trigger_type="record_created", entity_event="*", description="Send Slack message when any record is created"),
        TriggerDescriptor(trigger_type="record_updated", entity_event="*", description="Send Slack message when record updates"),
        TriggerDescriptor(trigger_type="status_changed", entity_event="*", description="Send Slack message on status change"),
    ],
    actions=[
        ActionDescriptor(
            action_id="send_slack_message",
            action_name="Send Message to Channel",
            description="Post a formatted message to a Slack channel",
            input_schema={"channel": "string", "text": "string", "blocks": "object"},
            output_schema={"message_ts": "string", "channel": "string"},
        ),
        ActionDescriptor(
            action_id="send_slack_dm",
            action_name="Send Direct Message",
            description="Send a direct message to a Slack user",
            input_schema={"user_id": "string", "text": "string"},
            output_schema={"message_ts": "string", "channel": "string"},
        ),
    ],
)

STRIPE = Integration(
    id="stripe",
    display_name="Stripe",
    auth_type="api_key",
    is_implemented=True,
    triggers=[
        TriggerDescriptor(trigger_type="subscription_created", entity_event="subscription", description="Subscription created"),
        TriggerDescriptor(trigger_type="payment_completed", entity_event="payment", description="Payment completed"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_customer",
            action_name="Create Customer",
            description="Create a Stripe customer",
            input_schema={"email": "string", "name": "string", "metadata": "object"},
            output_schema={"customer_id": "string", "email": "string"},
        ),
        ActionDescriptor(
            action_id="charge_customer",
            action_name="Charge Customer",
            description="Charge a customer one-time or recurring",
            input_schema={"customer_id": "string", "amount_cents": "integer", "currency": "string"},
            output_schema={"charge_id": "string", "status": "string"},
        ),
    ],
)

GMAIL = Integration(
    id="gmail",
    display_name="Gmail / Google Workspace",
    auth_type="oauth2",
    is_implemented=True,
    triggers=[
        TriggerDescriptor(trigger_type="record_event", entity_event="*", description="Trigger on record event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="send_email",
            action_name="Send Email",
            description="Send an email via Gmail",
            input_schema={"to": "string", "subject": "string", "body": "string", "html": "string"},
            output_schema={"message_id": "string", "status": "string"},
        ),
        ActionDescriptor(
            action_id="create_calendar_event",
            action_name="Create Calendar Event",
            description="Create a Google Calendar event",
            input_schema={"title": "string", "start_time": "string", "end_time": "string", "attendees": "array"},
            output_schema={"event_id": "string", "calendar_link": "string"},
        ),
    ],
)

AIRTABLE = Integration(
    id="airtable",
    display_name="Airtable",
    auth_type="api_key",
    is_implemented=True,
    triggers=[
        TriggerDescriptor(trigger_type="record_event", entity_event="*", description="Record created or updated"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_record",
            action_name="Create Record",
            description="Create a new Airtable record",
            input_schema={"table_id": "string", "fields": "object"},
            output_schema={"record_id": "string", "fields": "object"},
        ),
        ActionDescriptor(
            action_id="update_field",
            action_name="Update Field",
            description="Update a field in an Airtable record",
            input_schema={"record_id": "string", "fields": "object"},
            output_schema={"record_id": "string", "updated_fields": "array"},
        ),
    ],
)

WEBHOOK = Integration(
    id="webhook",
    display_name="Webhook (Generic)",
    auth_type="webhook_secret",
    is_implemented=True,
    triggers=[
        TriggerDescriptor(trigger_type="any_event", entity_event="*", description="Any trigger"),
    ],
    actions=[
        ActionDescriptor(
            action_id="post_webhook",
            action_name="POST to URL",
            description="Send a POST request with HMAC signature",
            input_schema={"url": "string", "payload": "object", "headers": "object"},
            output_schema={"status_code": "integer", "response": "object"},
        ),
    ],
)

# Stubbed Integrations (10)

SALESFORCE = Integration(
    id="salesforce",
    display_name="Salesforce",
    auth_type="oauth2",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="crm_entity_synced", entity_event="contact", description="Sync contact to Salesforce"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_lead",
            action_name="Create Lead",
            description="Create a Salesforce Lead",
            input_schema={"first_name": "string", "last_name": "string", "email": "string"},
            output_schema={"lead_id": "string"},
        ),
    ],
)

HUBSPOT = Integration(
    id="hubspot",
    display_name="HubSpot",
    auth_type="api_key",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="contact_event", entity_event="contact", description="Contact event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_contact",
            action_name="Create Contact",
            description="Create a HubSpot contact",
            input_schema={"email": "string", "first_name": "string", "last_name": "string"},
            output_schema={"contact_id": "string"},
        ),
    ],
)

WHATSAPP = Integration(
    id="whatsapp",
    display_name="WhatsApp (via Twilio)",
    auth_type="api_key",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="user_action", entity_event="*", description="User action in app"),
    ],
    actions=[
        ActionDescriptor(
            action_id="send_template_message",
            action_name="Send Template Message",
            description="Send a WhatsApp template message",
            input_schema={"phone": "string", "template_id": "string", "parameters": "array"},
            output_schema={"message_id": "string", "status": "string"},
        ),
    ],
)

NOTION = Integration(
    id="notion",
    display_name="Notion",
    auth_type="api_key",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="data_change", entity_event="*", description="Data change event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_page",
            action_name="Create Page",
            description="Create a Notion page",
            input_schema={"parent_id": "string", "title": "string", "properties": "object"},
            output_schema={"page_id": "string"},
        ),
    ],
)

TWILIO = Integration(
    id="twilio",
    display_name="Twilio SMS",
    auth_type="api_key",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="user_action", entity_event="*", description="User action or status change"),
    ],
    actions=[
        ActionDescriptor(
            action_id="send_sms",
            action_name="Send SMS",
            description="Send an SMS notification",
            input_schema={"to": "string", "message": "string"},
            output_schema={"sid": "string", "status": "string"},
        ),
    ],
)

SHEETS = Integration(
    id="sheets",
    display_name="Google Sheets",
    auth_type="oauth2",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="data_export", entity_event="*", description="Data export event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="append_row",
            action_name="Append Row",
            description="Append a row to a Google Sheet",
            input_schema={"sheet_id": "string", "values": "array"},
            output_schema={"range": "string"},
        ),
    ],
)

JIRA = Integration(
    id="jira",
    display_name="Jira",
    auth_type="oauth2",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="task_event", entity_event="task", description="Task/issue event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_issue",
            action_name="Create Issue",
            description="Create a Jira issue",
            input_schema={"project_key": "string", "summary": "string", "description": "string"},
            output_schema={"issue_key": "string", "issue_id": "string"},
        ),
    ],
)

GITHUB = Integration(
    id="github",
    display_name="GitHub",
    auth_type="oauth2",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="dev_workflow_trigger", entity_event="*", description="Dev workflow trigger"),
    ],
    actions=[
        ActionDescriptor(
            action_id="create_issue",
            action_name="Create Issue",
            description="Create a GitHub issue",
            input_schema={"repo": "string", "title": "string", "body": "string"},
            output_schema={"issue_number": "integer", "issue_url": "string"},
        ),
    ],
)

ZAPIER = Integration(
    id="zapier",
    display_name="Zapier",
    auth_type="webhook_secret",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="any_trigger", entity_event="*", description="Any trigger"),
    ],
    actions=[
        ActionDescriptor(
            action_id="send_to_zapier",
            action_name="Send to Zapier",
            description="Send structured payload to Zapier webhook",
            input_schema={"webhook_url": "string", "payload": "object"},
            output_schema={"accepted": "boolean"},
        ),
    ],
)

GOOGLE_AI = Integration(
    id="google_ai",
    display_name="Google AI",
    auth_type="api_key",
    is_implemented=False,
    triggers=[
        TriggerDescriptor(trigger_type="data_event", entity_event="*", description="Data event"),
    ],
    actions=[
        ActionDescriptor(
            action_id="generate_content",
            action_name="Generate Content",
            description="Generate content using Google AI",
            input_schema={"prompt": "string", "model": "string"},
            output_schema={"content": "string", "safety_ratings": "array"},
        ),
    ],
)

# Register all integrations
for integration in [SLACK, STRIPE, GMAIL, AIRTABLE, WEBHOOK, SALESFORCE, HUBSPOT, WHATSAPP, NOTION, TWILIO, SHEETS, JIRA, GITHUB, ZAPIER, GOOGLE_AI]:
    IntegrationRegistry.register(integration)
