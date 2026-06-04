from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")


def _trade_marker_path_source() -> str:
    start = APP_SOURCE.index("function tradeMarkerPath")
    end = APP_SOURCE.index("\n\nfunction indicatorLinePath", start)
    return APP_SOURCE[start:end]


def test_trade_marker_glyph_tip_uses_execution_price_anchor():
    source = _trade_marker_path_source()

    assert "return `M ${x} ${y} L ${x - size} ${y + size * 2} L ${x + size} ${y + size * 2} Z`;" in source
    assert "return `M ${x} ${y} L ${x - size} ${y - size * 2} L ${x + size} ${y - size * 2} Z`;" in source
    assert "M ${x} ${y - size}" not in source
    assert "M ${x} ${y + size}" not in source


def test_trade_markers_still_use_bar_time_and_execution_price_coordinates():
    assert "const index = nearestBarIndex(fill.filled_at, bars);" in APP_SOURCE
    assert "x: xForIndex(index), y: yForPrice(fill.price)" in APP_SOURCE
    assert '<circle cx={x} cy={y} r="2.4" />' in APP_SOURCE
