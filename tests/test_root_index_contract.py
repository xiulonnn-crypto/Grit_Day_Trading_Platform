from pathlib import Path


ROOT_INDEX = Path(__file__).resolve().parents[1] / "index.html"


def test_root_index_static_review_tabs_are_switchable() -> None:
    html = ROOT_INDEX.read_text(encoding="utf-8")

    assert 'data-review-tab="data"' in html
    assert 'data-review-tab="loss"' in html
    assert 'id="data-review-panel"' in html
    assert 'id="loss-review-panel"' in html
    assert 'class="workspaceTabs"' in html
    assert "\u7b56\u7565\u6d4b\u8bd5" in html
    assert "\u5b9e\u65f6\u4ea4\u6613" in html
    assert "\u76c8\u4e8f\u590d\u76d8" in html
    assert "\u4ec5\u770b\u76c8\u5229\u5355" in html
    assert "\u4ec5\u770b\u4e8f\u635f\u5355" in html
    assert "\u70ed\u529b\u65f6\u95f4\u77e9\u9635" in html
    assert "X \u8f74\u6c47\u603b" in html
    assert "\u6536\u76ca\u5408\u8ba1" in html
    assert 'class="matrixColumnSummary"' in html
    assert 'document.querySelectorAll("[data-review-tab]")' in html
    assert 'class="reviewDrillSurfaceTabs"' in html
    assert 'class="reviewDrillSurfaceTab active"' in html
    assert 'document.querySelectorAll(\'input[name="static-profit-loss-filter"]\')' in html
    assert 'lossReviewPanel.setAttribute("data-profit-loss-view", input.value)' in html
    assert 'candidate.closest(".profitLossReviewModeOption")' in html
    assert "function selectReviewTab(target)" in html
    assert 'panel.hidden = key !== target' in html
    assert 'reviewViewParam === "data"' in html
    assert 'window.location.hash === "#data-review"' in html
    assert "reviewDrillPrimary" not in html
    assert "P3 \u4e8f\u635f\u590d\u76d8\u9759\u6001\u5feb\u7167" not in html


def test_root_index_defaults_to_loss_review_panel() -> None:
    html = ROOT_INDEX.read_text(encoding="utf-8")

    assert (
        'id="data-review-tab" data-review-tab="data" role="tab" '
        'aria-controls="data-review-panel" aria-selected="false"'
    ) in html
    assert (
        'id="loss-review-tab" data-review-tab="loss" role="tab" '
        'aria-controls="loss-review-panel" aria-selected="true"'
    ) in html
    assert (
        'id="data-review-panel" role="tabpanel" '
        'aria-labelledby="data-review-tab" hidden'
    ) in html
    assert (
        'id="loss-review-panel" role="tabpanel" '
        'aria-labelledby="loss-review-tab" data-profit-loss-view="loss">'
    ) in html
    assert "\u76c8\u4e8f\u590d\u76d8" in html
    assert "\u4e8f\u635f\u5355\u70ed\u529b\u65f6\u95f4\u77e9\u9635" in html
    assert "\u76c8\u5229\u5355\u70ed\u529b\u65f6\u95f4\u77e9\u9635" in html
    assert "\u539f\u56e0\u5206\u7c7b\u6c47\u603b" in html
    assert "\u4e00\u7ea7\u539f\u56e0" in html
    assert "\u4e8c\u7ea7\u539f\u56e0" in html
    assert "\u6682\u65e0\u539f\u56e0\u5206\u7c7b" in html
    assert "\u4ec5\u4e8f\u635f\u5355\u7ef4\u62a4 Review Journal \u5f52\u56e0\uff1b\u76c8\u5229\u5355\u4e0d\u4f1a\u5199\u5165\u4e8f\u635f\u539f\u56e0\u3002" in html
    assert "\u4e8f\u635f\u5355\u5217\u8868" in html
    assert "\u76c8\u5229\u5355\u5217\u8868" in html
    assert 'class="profitOnlyContent emptyState"' in html
    assert 'class="lossOnlyContent"' in html
    assert 'class="lossTradeList profitVisible"' in html
    assert "\u6700\u5927\u4e8f\u635f\u533a\uff1a\u65e9\u76d8\u9ad8\u52a8\u80fd \u00d7 \u5e38\u89c4\u6ce2\u52a8" in html
    assert "\u6700\u5927\u76c8\u5229\u533a\uff1a\u65e9\u76d8\u9ad8\u52a8\u80fd \u00d7 \u5e38\u89c4\u6ce2\u52a8" in html


def test_root_index_loss_review_snapshot_matches_local_read_model_shape() -> None:
    html = ROOT_INDEX.read_text(encoding="utf-8")

    assert '<span class="lossVisible">26</span><span class="profitVisible">259</span>' in html
    assert '<span class="bad lossVisible">-10,824.34</span>' in html
    assert '<span class="ok profitVisible">+13,859.63</span>' in html
    assert '<span class="lossVisible">1-20 / 26 \u7b14</span>' in html
    assert '<span class="profitVisible">1-20 / 259 \u7b14</span>' in html
    assert "\u5e38\u89c4\u6ce2\u52a8" in html
    assert "\u4f4e\u6ce2\u52a8" in html
    assert "\u975e\u5e38\u89c4" in html
    assert "\u7f3a ATR \u8bc1\u636e" in html
    assert "\u9006\u52bf\u5165\u573a" in html
    assert "\u8ffd\u7a81\u7834\u8fc7\u6025" in html
    assert "\u5e73\u4ed3\u4fe1\u53f7\u672a\u6267\u884c" in html
    assert "\u7b2c 1 / 2 \u9875" in html
    assert "\u7b2c 1 / 13 \u9875" in html
    assert html.count('class="lossTradeItem"') >= 40
