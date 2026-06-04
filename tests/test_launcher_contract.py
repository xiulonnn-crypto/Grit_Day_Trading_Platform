from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_launcher_uses_crlf_for_cmd_labels():
    launcher = ROOT / "Login-Grit-DayTrading.cmd"
    content = launcher.read_bytes()

    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")


def test_login_launcher_auto_fallbacks_when_default_backend_is_stale():
    launcher = (ROOT / "Login-Grit-DayTrading.cmd").read_text(encoding="utf-8")

    assert "GRIT_BACKEND_FALLBACK_START" in launcher
    assert "GRIT_FRONTEND_FALLBACK_START" in launcher
    assert "Choosing fallback ports" in launcher
    assert "Run Login-Grit-DayTrading.cmd without --check to auto-start on fallback ports" in launcher
    assert "call :is_backend_review_ready" in launcher
    assert '"%BACKEND_URL%%REQUIRED_REVIEW_ROUTE%"' in launcher
    assert "%FRONTEND_URL%/api/healthz" in launcher
    assert "%FRONTEND_URL%%REQUIRED_REVIEW_ROUTE%" not in launcher


def test_login_launcher_reports_port_owner_for_runtime_failures():
    launcher = (ROOT / "Login-Grit-DayTrading.cmd").read_text(encoding="utf-8")

    assert ":print_port_owner" in launcher
    assert "Port %~1 owner PID" in launcher
    assert ":backend_runtime_failed" in launcher
    assert "The data DB may be locked by another backend process" in launcher
