from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_frontend_dockerfile_build_command_matches_repository_inputs():
    dockerfile = (ROOT / "deploy/docker/Dockerfile.frontend").read_text()
    package_lock = ROOT / "frontend/package-lock.json"
    if package_lock.exists():
        assert "npm ci" in dockerfile
    else:
        assert "npm install --no-audit --no-fund" in dockerfile


def test_backend_dockerfile_uses_pinned_requirements_and_unprivileged_runtime():
    dockerfile = (ROOT / "deploy/docker/Dockerfile.backend").read_text()
    assert "COPY requirements.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "USER nanvi" in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile


def test_compose_dev_defines_expected_dependencies_and_persistent_postgres_volume():
    compose = yaml.safe_load((ROOT / "deploy/docker/docker-compose.dev.yml").read_text())
    assert set(compose["services"]) >= {"postgres", "redis"}
    assert "nanvi_pg_dev:/var/lib/postgresql/data" in compose["services"]["postgres"]["volumes"]
