"""Concurrency and tenant isolation tests for CompanyDataService:
Two tenants with different folders, requests interleaved, zero cross-tenant leakage.
"""
from __future__ import annotations

import concurrent.futures
import shutil
import tempfile
from pathlib import Path
import pytest

from backend.integrations.files.company_data_service import CompanyDataService
from backend.security.authorization import UserAttributes
from backend.security.authorization.rbac import Role


@pytest.fixture
def isolated_tenants_dirs():
    """Create distinct isolated directory trees for tenant-alpha and tenant-beta."""
    temp_root = Path(tempfile.mkdtemp(prefix="nanvi_tenant_test_"))
    
    # Tenant Alpha setup
    alpha_dir = temp_root / "tenant_alpha"
    alpha_contracts = alpha_dir / "Contracts"
    alpha_contracts.mkdir(parents=True, exist_ok=True)
    (alpha_contracts / "alpha_agreements.txt").write_text(
        "CONFIDENTIAL_ALPHA_PROJECT_RED: Alpha Corp signed a $1,200,000 enterprise agreement.",
        encoding="utf-8",
    )

    # Tenant Beta setup
    beta_dir = temp_root / "tenant_beta"
    beta_contracts = beta_dir / "Contracts"
    beta_contracts.mkdir(parents=True, exist_ok=True)
    (beta_contracts / "beta_agreements.txt").write_text(
        "CONFIDENTIAL_BETA_PROJECT_BLUE: Beta Corp signed a $650,000 services contract.",
        encoding="utf-8",
    )

    yield alpha_dir, beta_dir

    shutil.rmtree(temp_root, ignore_errors=True)
    CompanyDataService.clear_registry()


def test_tenant_company_data_concurrency_and_zero_leakage(isolated_tenants_dirs):
    """Two tenants with different folders, requests interleaved concurrently, zero cross-tenant leakage."""
    alpha_dir, beta_dir = isolated_tenants_dirs
    CompanyDataService.clear_registry()

    # Initialize per-tenant services
    service_alpha = CompanyDataService.for_tenant("tenant-alpha", root_dir=alpha_dir)
    service_beta = CompanyDataService.for_tenant("tenant-beta", root_dir=beta_dir)

    # Create distinct users for both tenants
    user_alpha = UserAttributes(
        user_id="user-alpha-001",
        tenant_id="tenant-alpha",
        department="Contracts",
        roles=frozenset({Role.CEO, Role.FINANCE}),
    )
    user_beta = UserAttributes(
        user_id="user-beta-002",
        tenant_id="tenant-beta",
        department="Contracts",
        roles=frozenset({Role.CEO, Role.FINANCE}),
    )

    results_alpha: list[str] = []
    results_beta: list[str] = []
    errors: list[Exception] = []

    def run_alpha_query(q: str):
        try:
            # Alpha queries their own service
            res = service_alpha.search(user_alpha, q)
            return res.answer_content
        except Exception as e:
            errors.append(e)
            return ""

    def run_beta_query(q: str):
        try:
            # Beta queries their own service
            res = service_beta.search(user_beta, q)
            return res.answer_content
        except Exception as e:
            errors.append(e)
            return ""

    # Interleaved queries across both tenants executed concurrently
    queries_alpha = ["PROJECT_RED", "enterprise agreement", "PROJECT_BLUE", "services contract"] * 10
    queries_beta = ["PROJECT_BLUE", "services contract", "PROJECT_RED", "enterprise agreement"] * 10

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures_alpha = [executor.submit(run_alpha_query, q) for q in queries_alpha]
        futures_beta = [executor.submit(run_beta_query, q) for q in queries_beta]

        for f in concurrent.futures.as_completed(futures_alpha):
            results_alpha.append(f.result())

        for f in concurrent.futures.as_completed(futures_beta):
            results_beta.append(f.result())

    assert not errors, f"Errors occurred during concurrent execution: {errors}"

    # Strict isolation assertions:
    # 1. Tenant Alpha MUST see its own Project Red / $1,200,000 content
    combined_alpha = " ".join(results_alpha)
    assert "CONFIDENTIAL_ALPHA_PROJECT_RED" in combined_alpha
    assert "$1,200,000" in combined_alpha

    # 2. Tenant Alpha MUST NEVER see Tenant Beta's content (ZERO leakage)
    assert "CONFIDENTIAL_BETA_PROJECT_BLUE" not in combined_alpha
    assert "$650,000" not in combined_alpha
    assert "beta_agreements" not in combined_alpha

    # 3. Tenant Beta MUST see its own Project Blue / $650,000 content
    combined_beta = " ".join(results_beta)
    assert "CONFIDENTIAL_BETA_PROJECT_BLUE" in combined_beta
    assert "$650,000" in combined_beta

    # 4. Tenant Beta MUST NEVER see Tenant Alpha's content (ZERO leakage)
    assert "CONFIDENTIAL_ALPHA_PROJECT_RED" not in combined_beta
    assert "$1,200,000" not in combined_beta
    assert "alpha_agreements" not in combined_beta


def test_cross_tenant_direct_access_raises_permission_error(isolated_tenants_dirs):
    """Directly invoking a tenant's service with another tenant's user must be denied."""
    alpha_dir, beta_dir = isolated_tenants_dirs
    CompanyDataService.clear_registry()

    service_beta = CompanyDataService.for_tenant("tenant-beta", root_dir=beta_dir)

    user_alpha = UserAttributes(
        user_id="user-alpha-001",
        tenant_id="tenant-alpha",
        department="Contracts",
        roles=frozenset({Role.CEO}),
    )

    with pytest.raises(PermissionError) as exc_info:
        service_beta.search(user_alpha, "contract")
    assert "Tenant access denied" in str(exc_info.value)
    assert "tenant-alpha" in str(exc_info.value)
    assert "tenant-beta" in str(exc_info.value)
