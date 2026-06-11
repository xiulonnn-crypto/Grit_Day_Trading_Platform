from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_login_launcher_uses_crlf_for_cmd_labels():
    launcher = ROOT / "Login-Grit-DayTrading.cmd"
    content = launcher.read_bytes()

    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")


def test_login_launcher_auto_fallbacks_when_default_backend_is_stale():
    launcher = (ROOT / "Login-Grit-DayTrading.cmd").read_text(encoding="utf-8")
    vite_config = (ROOT / "web" / "vite.config.ts").read_text(encoding="utf-8")

    assert "GRIT_BACKEND_FALLBACK_START" in launcher
    assert "GRIT_FRONTEND_FALLBACK_START" in launcher
    assert "Choosing fallback ports" in launcher
    assert "Run Login-Grit-DayTrading.cmd without --check to auto-start on fallback ports" in launcher
    assert "call :is_backend_review_ready" in launcher
    assert '"%BACKEND_URL%%REQUIRED_REVIEW_ROUTE%"' in launcher
    assert "REQUIRED_TRADE_REVIEW_ROUTE=/api/trade-groups/{trade_group_id}/review" in launcher
    assert "REQUIRED_STRATEGY_TEMPLATE=one_minute_range_fader_v1" in launcher
    assert "REQUIRED_STRATEGY_RUN_DETAIL_ROUTE=/api/strategy-runs/{run_id}" in launcher
    assert "REQUIRED_LIVE_SIGNAL_CONTRACT=live_order_quantity_reason_tags_v1" in launcher
    assert "REQUIRED_FRONTEND_MARKER=LossReviewPanel" in launcher
    assert "FRONTEND_CACHE_BUSTER=loss-review-inline-v1" in launcher
    assert "%REQUIRED_STRATEGY_RUN_DETAIL_ROUTE%" in launcher
    assert "%REQUIRED_TRADE_REVIEW_ROUTE%" in launcher
    assert "%FRONTEND_URL%/api/healthz" in launcher
    assert "%FRONTEND_URL%/openapi.json" in launcher
    assert "$h.live_signal_contract -ne '%REQUIRED_LIVE_SIGNAL_CONTRACT%'" in launcher
    assert "%FRONTEND_URL%/src/App.tsx" in launcher
    assert ".Contains('%REQUIRED_FRONTEND_MARKER%')" in launcher
    assert "%FRONTEND_URL%/?grit_ui=%FRONTEND_CACHE_BUSTER%" in launcher
    assert "%FRONTEND_URL%%REQUIRED_REVIEW_ROUTE%" not in launcher
    assert "timeout /t 2 /nobreak >nul" in launcher
    assert '"/openapi.json": apiProxy' in vite_config


def test_login_launcher_reports_port_owner_for_runtime_failures():
    launcher = (ROOT / "Login-Grit-DayTrading.cmd").read_text(encoding="utf-8")

    assert ":print_port_owner" in launcher
    assert "Port %~1 owner PID" in launcher
    assert ":backend_runtime_failed" in launcher
    assert "The data DB may be locked by another backend process" in launcher
