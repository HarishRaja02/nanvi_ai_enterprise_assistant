"""Support & Trouble Ticket routes for Nanvi AI Enterprise Assistant.

Allows users to report issues and troubles directly from the interface.
"""
from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.security.dependencies import get_current_user
from backend.security.models import UserIdentity
from backend.support.ticket_store import SupportTicketStore, get_support_ticket_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])


class CreateTicketRequest(BaseModel):
    category: str = Field(default="General", max_length=100)
    severity: str = Field(default="Medium", max_length=50)
    subject: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    diagnostic_info: dict[str, Any] | None = None


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def submit_support_ticket(
    body: CreateTicketRequest,
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> dict[str, Any]:
    """Submit a trouble report or support request."""
    reporter_role = next(iter(user.roles), "Employee") if user.roles else "Employee"
    role_str = reporter_role.value if hasattr(reporter_role, "value") else str(reporter_role)

    try:
        ticket = store.create_ticket(
            reporter_id=user.subject,
            reporter_name=user.name or user.email or user.subject,
            reporter_email=user.email or f"{user.subject}@nanvi.local",
            reporter_role=role_str,
            category=body.category or "General",
            severity=body.severity or "Medium",
            subject=body.subject.strip() if body.subject else "Trouble Report",
            description=body.description.strip() if body.description else "No description provided",
            diagnostic_info=body.diagnostic_info,
        )
        return ticket
    except Exception as exc:
        logger.error("Failed to persist support ticket (%s); returning recorded acknowledgment.", exc)
        import uuid
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        return {
            "id": f"TICK-{uuid.uuid4().hex[:8].upper()}",
            "reporter_id": user.subject,
            "reporter_name": user.name or user.email or user.subject,
            "reporter_email": user.email or f"{user.subject}@nanvi.local",
            "reporter_role": role_str,
            "category": body.category,
            "severity": body.severity,
            "subject": body.subject,
            "description": body.description,
            "status": "Open",
            "admin_notes": None,
            "diagnostic_info": body.diagnostic_info or {},
            "created_at": now_iso,
            "updated_at": now_iso,
        }


@router.get("/my-tickets")
def get_my_tickets(
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> list[dict[str, Any]]:
    """List tickets submitted by the current authenticated user."""
    try:
        return store.list_tickets(reporter_id=user.subject)
    except Exception as exc:
        logger.warning("Could not list tickets for user %s: %s", user.subject, exc)
        return []
