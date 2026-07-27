import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_INDEX = ROOT / "index.html"
STATIC_JS = ROOT / "static-review.js"
STATIC_CSS = ROOT / "static-review.css"
SNAPSHOT = ROOT / "review-snapshot.json"


def load_snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_root_index_exposes_three_review_tabs_and_static_assets() -> None:
    html = ROOT_INDEX.read_text(encoding="utf-8")

    assert '<link rel="stylesheet" href="./static-review.css?v=20260728-style-parity"' in html
    assert '<script defer src="./static-review.js?v=20260728-style-parity"' in html
    assert 'id="snapshot-loading"' in html
    assert 'id="review-content" hidden' in html
    assert 'data-review-tab="data"' in html
    assert 'data-review-tab="loss"' in html
    assert 'data-review-tab="summary"' in html
    assert 'data-review-panel="data"' in html
    assert 'data-review-panel="loss"' in html
    assert 'data-review-panel="summary"' in html
    assert "数据下钻" in html
    assert "盈亏复盘" in html
    assert "交易总结" in html
    assert "P2 Review Desk" in html
    assert "日内复盘台" in html
    assert "STP 成交证据、行情上下文、盘前 watchlist 与策略复盘信号" in html
    assert "上传 STP TXT" in html
    assert ">只读云端快照<" not in html
    assert "P3 REVIEW DESK" not in html
    assert 'aria-label="工作区切换"' in html
    assert 'aria-label="交易复盘下钻"' in html
    assert 'aria-label="下钻复盘模块"' in html
    assert 'class="cloudSnapshotMeta visuallyHidden"' in html
    assert 'class="lucide lucide-file-up"' in html
    assert 'class="lucide lucide-table-properties"' in html
    assert 'class="lucide lucide-sliders-horizontal"' in html
    assert 'class="lucide lucide-brain-circuit"' in html
    assert 'class="lucide lucide-power"' in html
    assert 'class="lucide lucide-triangle-alert"' in html
    assert 'class="lucide lucide-list-checks"' in html
    assert "buttonIcon" not in html
    assert "uploadIcon" not in html
    assert "原始 STP 行" in html


def test_static_review_supports_tabs_calendar_filters_and_failure_blocking() -> None:
    script = STATIC_JS.read_text(encoding="utf-8")
    stylesheet = STATIC_CSS.read_text(encoding="utf-8")

    assert 'document.querySelectorAll("[data-review-tab]")' in script
    assert 'document.querySelectorAll("[data-review-panel]")' in script
    assert "[data-calendar-shift]" in script
    assert "[data-calendar-date]" in script
    assert "[data-selected-date]" in script
    assert "data-profit-loss-mode=" in script
    assert "data-matrix-dimension=" in script
    assert "[data-sort-mode]" in script
    assert "[data-page-shift]" in script
    assert '"#profit-loss-review"' in script
    assert '"#trade-summary"' in script
    assert "云端复盘快照不可用" in script
    assert "页面不会用旧数字或空图伪装成功" in script
    assert 'class="compactFacts summaryMiniFacts"' in script
    assert 'svgIcon("calendar-days", 17)' in script
    assert 'svgIcon("chevron-left", 15)' in script
    assert 'svgIcon("chevron-right", 15)' in script
    assert 'svgIcon("play", 14)' in script
    assert "@import url(\"./web/src/styles.css\")" in stylesheet
    assert ".cloudSnapshotMeta.visuallyHidden" in stylesheet
    assert "@media (max-width: 720px)" in stylesheet


def test_review_snapshot_matches_local_committed_fill_read_model() -> None:
    snapshot = load_snapshot()
    groups = [
        group
        for group in snapshot["trade_groups"]
        if group["status"] == "closed" and group["pnl"] is not None
    ]

    assert snapshot["schema_version"] == "github_pages_review_snapshot_v1"
    assert snapshot["as_of_date"] == "2026-07-27"
    assert len(snapshot["source_hash"]) == hashlib.sha256().digest_size * 2
    assert len(groups) == snapshot["summary"]["trade_group_count"] == 1318
    assert (
        sum(int(group["total_quantity"]) for group in groups)
        == snapshot["summary"]["traded_quantity"]
        == 87643
    )
    assert abs(
        sum(float(group["pnl"]) for group in groups)
        - float(snapshot["summary"]["pnl"])
    ) < 0.000001
    assert snapshot["summary"]["pnl"] == -4385.2515

    summary_metrics = snapshot["trade_summary"]["metrics"]
    assert summary_metrics["closed_trade_count"] == 1318
    assert summary_metrics["win_count"] == 1081
    assert summary_metrics["loss_count"] == 215
    assert summary_metrics["flat_count"] == 22


def test_review_snapshot_excludes_private_or_raw_evidence_fields() -> None:
    serialized = SNAPSHOT.read_text(encoding="utf-8")

    forbidden_tokens = (
        "account_raw",
        "account_canonical",
        "raw_line",
        "raw_line_numbers",
        "source_batch_ids",
        "idempotency_key",
        "artifact_id",
        "artifact_summary_key",
    )
    for token in forbidden_tokens:
        assert token not in serialized
