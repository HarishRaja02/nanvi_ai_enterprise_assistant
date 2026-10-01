"""Centralized Intent and Action Registry — Milestone 6.

Defines the single source of truth for conversational and UI action intents,
their required permissions, risk levels (low / medium / high requiring confirmation),
parameter schemas, and executable query templates.

Conforms strictly to Section 6.4 of docs/NANVI_SPEC.md.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Sequence
from pydantic import BaseModel, Field

from backend.security.authorization.abac import UserAttributes
from backend.security.authorization.rbac import Role


class RiskLevel(str, Enum):
    LOW = "low"          # Safe read-only / exploratory actions; proceed without prompting
    MEDIUM = "medium"    # State-changing or filtered queries
    HIGH = "high"        # Irreversible side effects (sending email, modifying data, approvals)


class IntentDefinition(BaseModel):
    intent_id: str
    label: str
    description: str
    category: str  # "finance" | "crm" | "invoices" | "team" | "email" | "search" | "report"
    risk_level: RiskLevel = RiskLevel.LOW
    required_roles: list[str] = Field(default_factory=list)  # Empty means all authenticated users
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    query_template: str
    icon: str = "arrow-right"
    variant: str = "secondary"

    def can_user_access(self, user: UserAttributes) -> bool:
        """Check if user has sufficient role permissions to trigger this intent."""
        if not self.required_roles:
            return True
        user_role_names = {r.value if hasattr(r, "value") else str(r) for r in user.roles}
        return bool(user_role_names.intersection(self.required_roles))

    def resolve_query(self, parameters: dict[str, Any] | None = None) -> str:
        """Interpolate parameters into the query template to form a concrete orchestration query."""
        params = parameters or {}
        try:
            return self.query_template.format(**params)
        except KeyError:
            # Fallback if optional params are missing
            return self.query_template


class IntentRegistry:
    """Singleton repository for all enterprise action intents."""

    def __init__(self) -> None:
        self._intents: dict[str, IntentDefinition] = {}
        self._register_default_intents()

    def register(self, intent: IntentDefinition) -> None:
        self._intents[intent.intent_id] = intent

    def get(self, intent_id: str) -> IntentDefinition | None:
        return self._intents.get(intent_id)

    def list_intents(self) -> list[IntentDefinition]:
        return list(self._intents.values())

    def can_execute(self, user: UserAttributes, intent_id: str) -> bool:
        intent = self.get(intent_id)
        if not intent:
            return False
        return intent.can_user_access(user)

    def resolve_query(self, intent_id: str, parameters: dict[str, Any] | None = None) -> str:
        intent = self.get(intent_id)
        if not intent:
            # Fallback to cleaning the intent string as a natural prompt
            return intent_id.replace("_", " ")
        return intent.resolve_query(parameters)

    def get_actions_for_context(
        self,
        user: UserAttributes,
        suggested_intents: Sequence[str] = (),
        capability: str = "",
        active_entity: str = "",
        limit: int = 3,
    ) -> list[IntentDefinition]:
        """Return permitted, contextually relevant action intents for the user."""
        matched: list[IntentDefinition] = []

        # 1. First prioritize explicitly suggested intents from the response planner
        for intent_id in suggested_intents:
            intent = self.get(intent_id)
            if intent and intent.can_user_access(user) and intent not in matched:
                matched.append(intent)

        # 2. If space remains, add category-relevant intents
        if len(matched) < limit:
            category_map = {
                "knowledge": "search",
                "database": "finance",
                "email": "email",
                "report": "report",
            }
            target_cat = category_map.get(capability.lower(), "")
            for intent in self._intents.values():
                if len(matched) >= limit:
                    break
                if intent not in matched and intent.can_user_access(user):
                    if target_cat and intent.category == target_cat:
                        matched.append(intent)

        # 3. Fallback to generic safe search/detail actions
        if len(matched) < limit:
            for fallback_id in ("show_more_detail", "verify_sources", "export_summary"):
                intent = self.get(fallback_id)
                if intent and intent not in matched and intent.can_user_access(user):
                    matched.append(intent)
                if len(matched) >= limit:
                    break

        return matched[:limit]

    def _register_default_intents(self) -> None:
        """Populate the enterprise standard intents."""
        defaults = [
            # ── Finance & Performance ──────────────────────────────────────────
            IntentDefinition(
                intent_id="compare_previous_quarter",
                label="Compare with Last Quarter",
                description="Compare revenue and key financial metrics against the previous fiscal quarter.",
                category="finance",
                risk_level=RiskLevel.LOW,
                required_roles=["CEO", "Finance", "Manager"],
                query_template="Compare financial performance and revenue with the previous quarter.",
                icon="bar-chart",
                variant="primary",
            ),
            IntentDefinition(
                intent_id="revenue_drivers",
                label="Show Revenue Drivers",
                description="Breakdown key product lines and enterprise contracts driving revenue.",
                category="finance",
                risk_level=RiskLevel.LOW,
                required_roles=["CEO", "Finance", "Manager"],
                query_template="Show me the primary revenue drivers and breakdown.",
                icon="trending-up",
            ),
            IntentDefinition(
                intent_id="top_customers",
                label="Top Customers",
                description="List top enterprise customers ranked by total spend and volume.",
                category="finance",
                risk_level=RiskLevel.LOW,
                required_roles=["CEO", "Finance", "Manager"],
                query_template="Show the top enterprise customers by revenue and transaction volume.",
                icon="users",
            ),

            # ── CRM & Accounts ────────────────────────────────────────────────
            IntentDefinition(
                intent_id="customer_invoices",
                label="View Invoices",
                description="Retrieve all active and historical invoices for the account.",
                category="crm",
                risk_level=RiskLevel.LOW,
                required_roles=["CEO", "Finance", "Manager"],
                query_template="Show invoices and payment records for this account.",
                icon="file-text",
            ),
            IntentDefinition(
                intent_id="contact_details",
                label="Contact Details",
                description="Display authorized phone, email, and address info.",
                category="crm",
                risk_level=RiskLevel.LOW,
                query_template="What are the contact details for this account?",
                icon="phone",
            ),
            IntentDefinition(
                intent_id="compare_accounts",
                label="Compare Accounts",
                description="Compare performance across peer client accounts.",
                category="crm",
                risk_level=RiskLevel.LOW,
                required_roles=["CEO", "Finance"],
                query_template="Compare this account with similar client accounts.",
                icon="layers",
            ),

            # ── Invoices & Billing ────────────────────────────────────────────
            IntentDefinition(
                intent_id="download_invoice",
                label="Download Invoice",
                description="Prepare and export invoice file for download.",
                category="invoices",
                risk_level=RiskLevel.LOW,
                query_template="Download and export the active invoice.",
                icon="download",
            ),
            IntentDefinition(
                intent_id="view_line_items",
                label="View Line Items",
                description="Show itemized breakdown of products and services billed.",
                category="invoices",
                risk_level=RiskLevel.LOW,
                query_template="Display the itemized line items on this invoice.",
                icon="list",
            ),
            IntentDefinition(
                intent_id="payment_status",
                label="Payment Status",
                description="Check transaction clearance and overdue status.",
                category="invoices",
                risk_level=RiskLevel.LOW,
                query_template="What is the current payment clearance status?",
                icon="check-circle",
            ),

            # ── HR & Team ─────────────────────────────────────────────────────
            IntentDefinition(
                intent_id="view_org_chart",
                label="View Org Chart",
                description="Display managerial reporting hierarchy.",
                category="team",
                risk_level=RiskLevel.LOW,
                query_template="Show the organizational reporting chart for this team.",
                icon="network",
            ),
            IntentDefinition(
                intent_id="contact_info",
                label="Contact Info",
                description="Display enterprise directory contact information.",
                category="team",
                risk_level=RiskLevel.LOW,
                query_template="What is the contact information for this team member?",
                icon="mail",
            ),
            IntentDefinition(
                intent_id="team_projects",
                label="Team Projects",
                description="Show current active project allocations.",
                category="team",
                risk_level=RiskLevel.LOW,
                query_template="List the active projects assigned to this team.",
                icon="briefcase",
            ),

            # ── Email & Communications ────────────────────────────────────────
            IntentDefinition(
                intent_id="review_draft",
                label="Review Draft",
                description="Preview generated email draft before sending.",
                category="email",
                risk_level=RiskLevel.LOW,
                query_template="Show me the full draft of the email.",
                icon="edit-3",
            ),
            IntentDefinition(
                intent_id="send_confirmation",
                label="Confirm & Send Email",
                description="High-risk action: Send outbound email. Requires explicit user confirmation.",
                category="email",
                risk_level=RiskLevel.HIGH,
                query_template="Send the confirmed email draft now.",
                icon="send",
                variant="primary",
            ),
            IntentDefinition(
                intent_id="send_email",
                label="Send Email",
                description="High-risk action: Send outbound email. Requires explicit user confirmation.",
                category="email",
                risk_level=RiskLevel.HIGH,
                required_roles=["CEO", "Manager", "Finance"],
                query_template="Send email to {recipient} with subject {subject}.",
                icon="send",
                variant="primary",
            ),
            IntentDefinition(
                intent_id="find_replies",
                label="Find Replies",
                description="Search for subsequent replies in the email thread.",
                category="email",
                risk_level=RiskLevel.LOW,
                query_template="Find any recent replies or follow-up emails in this thread.",
                icon="message-square",
            ),

            # ── General Exploration & Verification ────────────────────────────
            IntentDefinition(
                intent_id="show_more_detail",
                label="Show More Detail",
                description="Expand on the verified figures with full context.",
                category="search",
                risk_level=RiskLevel.LOW,
                query_template="Tell me more details about this result.",
                icon="plus-circle",
            ),
            IntentDefinition(
                intent_id="verify_sources",
                label="Verify Sources",
                description="Inspect the verified citations and documents.",
                category="search",
                risk_level=RiskLevel.LOW,
                query_template="Show the verified document sources and citations used for this answer.",
                icon="shield-check",
            ),
            IntentDefinition(
                intent_id="export_summary",
                label="Export Summary",
                description="Export structured summary of current answer.",
                category="report",
                risk_level=RiskLevel.LOW,
                query_template="Export a structured summary report of this information.",
                icon="download",
            ),
            IntentDefinition(
                intent_id="search_again",
                label="Search Again",
                description="Run an expanded search across authorized files.",
                category="search",
                risk_level=RiskLevel.LOW,
                query_template="Search authorized records again with broader criteria.",
                icon="search",
            ),
            IntentDefinition(
                intent_id="browse_documents",
                label="Browse Documents",
                description="Open company document repository browser.",
                category="search",
                risk_level=RiskLevel.LOW,
                query_template="Browse company files and uploaded documentation.",
                icon="folder-open",
            ),
        ]

        for item in defaults:
            self.register(item)


# Global singleton instance
intent_registry = IntentRegistry()
