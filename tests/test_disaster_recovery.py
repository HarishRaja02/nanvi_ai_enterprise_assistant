from pathlib import Path

from scripts.dr_nonprod_restore import run_exercise


def test_nonproduction_backup_restore_exercise(tmp_path: Path):
    result = run_exercise(tmp_path)
    assert result["production_data_touched"] is False
    assert result["secret_exclusion"] == "verified"
    assert result["files_verified"] >= 4
    restored = Path(result["restore_target"])
    assert "NONPROD-RESTORE-DOCUMENT-001" in (restored / "persistent/documents/customer.txt").read_text()
    config = (restored / "config/nonsecret.env").read_text()
    assert "OIDC_CLIENT_SECRET=" not in config
    assert "DATABASE_URL=" not in config
    assert "REDIS_URL=" not in config
