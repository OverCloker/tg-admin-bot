from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_update_does_not_exec_deploy_and_uses_kernel_lock():
    script = (ROOT / "server-auto-update.sh").read_text(encoding="utf-8")

    assert 'exec sh "$PROJECT_DIR/server-deploy.sh"' not in script
    assert 'sh "$PROJECT_DIR/server-deploy.sh" "$BRANCH"' in script
    assert "flock -n 9" in script
    assert "trap release_lock EXIT INT TERM" in script


def test_status_reports_legacy_stale_lock():
    script = (ROOT / "server-autoupdate-status.sh").read_text(encoding="utf-8")

    assert "Legacy stale lock found" in script
