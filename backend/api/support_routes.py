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
    category: str = Field(min_length=1, max_length=100)
    severity: str = Field(default="Medium", max_length=50)
    subject: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=10, max_length=5000)
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

    ticket = store.create_ticket(
        reporter_id=user.subject,
        reporter_name=user.name or user.email or user.subject,
        reporter_email=user.email or f"{user.subject}@nanvi.local",
        reporter_role=role_str,
        category=body.category,
        severity=body.severity,
        subject=body.subject,
        description=body.description,
        diagnostic_info=body.diagnostic_info,
    )
    return ticket


@router.get("/my-tickets")
def get_my_tickets(
    user: UserIdentity = Depends(get_current_user),
    store: SupportTicketStore = Depends(get_support_ticket_store),
) -> list[dict[str, Any]]:
    """List tickets submitted by the current authenticated user."""
    return store.list_tickets(reporter_id=user.subject)
