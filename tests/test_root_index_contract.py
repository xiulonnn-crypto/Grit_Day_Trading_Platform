from pathlib import Path


ROOT_INDEX = Path(__file__).resolve().parents[1] / "index.html"


def test_root_index_static_review_tabs_are_switchable() -> None:
    html = ROOT_INDEX.read_text(encoding="utf-8")

    assert 'data-review-tab="data"' in html
    assert 'data-review-tab="loss"' in html
    assert 'id="data-review-panel"' in html
    assert 'id="loss-review-panel"' in html
    assert "数据下钻热力矩阵" in html
    assert "亏损热力矩阵" in html
    assert "亏损单列表" in html
    assert "P3 亏损复盘静态快照已更新" in html
    assert 'document.querySelectorAll("[data-review-tab]")' in html
    assert "function selectReviewTab(target)" in html
    assert 'panel.hidden = key !== target' in html
    assert 'get("view") === "loss"' in html
    assert 'window.location.hash === "#loss-review"' in html
