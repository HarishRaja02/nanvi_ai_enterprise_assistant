from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Iterable

# These keys are never copied into a DR backup artifact.
SECRET_KEYS = {
    "OIDC_CLIENT_SECRET",
    "DATABASE_URL",
    "REDIS_URL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
}
SECRET_MARKERS = ("SECRET", "PASSWORD", "TOKEN", "API_KEY", "PRIVATE_KEY", "CREDENTIAL")

BACKUP_RELATIVE_PATHS = (
    Path("config") / "nonsecret.env",
    Path("persistent") / "documents",
    Path("persistent") / "reports",
    Path("persistent") / "vector-index",
    Path("persistent") / "audit",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            yield path


def sanitize_env(source: Path, destination: Path) -> None:
    """Copy only explicitly safe configuration keys; fail closed on secret-like keys."""
    safe_lines: list[str] = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        upper = key.upper()
        if key in SECRET_KEYS or any(marker in upper for marker in SECRET_MARKERS):
            continue
        # Never carry an inline value that looks like a credential even if the key was unexpected.
        if any(marker in value.upper() for marker in ("PASSWORD=", "SECRET=", "TOKEN=")):
            continue
        safe_lines.append(f"{key}={value}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(safe_lines) + "\n", encoding="utf-8")


def build_nonprod_fixture(root: Path, production_env_example: Path) -> None:
    """Create synthetic, non-production state for a real restore exercise."""
    (root / "persistent/documents").mkdir(parents=True, exist_ok=True)
    (root / "persistent/reports").mkdir(parents=True, exist_ok=True)
    (root / "persistent/vector-index").mkdir(parents=True, exist_ok=True)
    (root / "persistent/audit").mkdir(parents=True, exist_ok=True)
    sanitize_env(production_env_example, root / "config/nonsecret.env")
    (root / "persistent/documents/customer.txt").write_text(
        "NONPROD-RESTORE-DOCUMENT-001\nAuthorized synthetic customer content.\n", encoding="utf-8"
    )
    (root / "persistent/reports/report-001.xlsx").write_bytes(b"SYNTHETIC-REPORT-001")
    (root / "persistent/vector-index/index.json").write_text(
        json.dumps({"index_version": 1, "chunks": ["chunk-001", "chunk-002"]}, sort_keys=True),
        encoding="utf-8",
    )
    (root / "persistent/audit/audit.jsonl").write_text(
        '{"event":"nonprod_restore_test","tenant":"tenant-test","outcome":"allow"}\n',
        encoding="utf-8",
    )


def create_backup(source: Path, archive: Path) -> Path:
    manifest: list[dict[str, str | int]] = []
    for path in _iter_files(source):
        relative = path.relative_to(source).as_posix()
        manifest.append({"path": relative, "sha256": _sha256(path), "size": path.stat().st_size})
    (source / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname="dr_snapshot")
    return archive


def restore_and_verify(archive: Path, target: Path) -> dict[str, object]:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(target, filter="data")
    restored = target / "dr_snapshot"
    manifest = json.loads((restored / "manifest.json").read_text(encoding="utf-8"))
    checked = 0
    for item in manifest:
        path = restored / item["path"]
        if not path.is_file():
            raise RuntimeError(f"Restore verification failed: missing {item['path']}")
        if _sha256(path) != item["sha256"]:
            raise RuntimeError(f"Restore verification failed: checksum mismatch for {item['path']}")
        if path.stat().st_size != item["size"]:
            raise RuntimeError(f"Restore verification failed: size mismatch for {item['path']}")
        checked += 1

    # Explicitly verify the synthetic business-state markers survived restoration.
    required = (
        restored / "persistent/documents/customer.txt",
        restored / "persistent/reports/report-001.xlsx",
        restored / "persistent/vector-index/index.json",
        restored / "persistent/audit/audit.jsonl",
    )
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Restore verification failed: required state missing: {path.name}")

    config_text = (restored / "config/nonsecret.env").read_text(encoding="utf-8")
    if any(secret_key + "=" in config_text for secret_key in SECRET_KEYS):
        raise RuntimeError("Restore verification failed: secret-bearing configuration was restored")
    return {"files_verified": checked, "restore_target": str(restored)}


def run_exercise(workdir: Path) -> dict[str, object]:
    source = workdir / "source_fixture"
    backup_dir = workdir / "backup"
    restore_dir = workdir / "restored"
    build_nonprod_fixture(source, Path(__file__).resolve().parents[1] / "config/environments/production.env.example")
    backup_dir.mkdir(parents=True, exist_ok=True)
    archive = create_backup(source, backup_dir / "nanvi-nonprod-dr.tar.gz")
    result = restore_and_verify(archive, restore_dir)
    result.update({"backup": str(archive), "secret_exclusion": "verified", "production_data_touched": False})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Nanvi's non-production DR backup/restore exercise.")
    parser.add_argument("--workdir", default=None, help="Directory for temporary DR exercise data")
    args = parser.parse_args()
    if args.workdir:
        workdir = Path(args.workdir).resolve()
        workdir.mkdir(parents=True, exist_ok=True)
        print(json.dumps(run_exercise(workdir), indent=2))
        return 0
    with tempfile.TemporaryDirectory(prefix="nanvi-dr-") as temp:
        print(json.dumps(run_exercise(Path(temp)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
