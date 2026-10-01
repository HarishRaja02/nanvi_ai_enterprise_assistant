"""Synthetic data fixtures for development and demo environments.

STRICTLY FORBIDDEN IN PRODUCTION:
Attempting to import this module when `settings.allows_synthetic_data` is False
raises a ConfigurationError to prevent accidental leakage into production runtime.

All fixtures are sourced from canonical_data.py to enforce a single source of truth.
"""
from __future__ import annotations

from typing import Any
from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.integrations.fixtures.canonical_data import (
    CANONICAL_CONTRACTS,
    CANONICAL_DEPARTMENTS,
    CANONICAL_EMPLOYEES,
    CANONICAL_INVOICES,
    CANONICAL_TRANSACTIONS,
)

if not settings.allows_synthetic_data:
    raise ConfigurationError(
        "Synthetic fixtures are forbidden when allows_synthetic_data is False (production mode)."
    )

SYNTHETIC_CONTRACTS: list[dict[str, Any]] = CANONICAL_CONTRACTS
SYNTHETIC_INVOICES: list[dict[str, Any]] = CANONICAL_INVOICES
SYNTHETIC_DEPARTMENTS: list[dict[str, Any]] = CANONICAL_DEPARTMENTS
SYNTHETIC_EMPLOYEES: list[dict[str, Any]] = CANONICAL_EMPLOYEES
SYNTHETIC_TRANSACTIONS: list[dict[str, Any]] = CANONICAL_TRANSACTIONS
