from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
STYLES_SOURCE = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
TYPES_SOURCE = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")


def test_review_drill_date_stats_use_selected_date_group_summary():
    assert "const selectedDateSummary = useMemo" in APP_SOURCE
    assert "dateSummaryGroups.find((group) => group.group_key === date)" in APP_SOURCE
    assert '<SummaryMiniFacts summary={activeDrillSummary} />' in APP_SOURCE
    assert 'summary={activeReviewDrillTab === "date" ? summary : selectedSymbolSummary}' not in APP_SOURCE


def test_review_drill_breakdowns_are_scoped_to_active_selection():
    assert "const [dateSymbolBreakdownDate, setDateSymbolBreakdownDate]" in APP_SOURCE
    assert "setDateSymbolBreakdownDate(refreshDate)" in APP_SOURCE
    assert "const dateSymbolBreakdownReady = dateSymbolBreakdownDate === date" in APP_SOURCE
    assert "const visibleDateSymbolBreakdown = useMemo" in APP_SOURCE
    assert "dateSymbolBreakdownDate === date ? dateSymbolBreakdown.filter((group) => group.date === date) : []" in APP_SOURCE
    assert "const visibleSymbolDateBreakdown = useMemo" in APP_SOURCE
    assert "symbolDateBreakdown.filter((group) => group.symbol === selectedSymbol)" in APP_SOURCE


def test_date_drill_waits_for_matching_symbol_breakdown_before_empty_state():
    assert "dateSymbolBreakdownReady" in APP_SOURCE
    assert '"读取中"' in APP_SOURCE
    assert 'title="正在读取标的"' in APP_SOURCE
    assert 'title="该日没有标的"' in APP_SOURCE


def test_refresh_drops_stale_date_requests_before_updating_review_state():
    assert "const refreshRequestIdRef = useRef(0)" in APP_SOURCE
    assert "const refreshDate = date" in APP_SOURCE
    assert "fetchDailySummary(refreshDate)" in APP_SOURCE
    assert 'fetchReviewSummaryGroups("symbol", { date: refreshDate })' in APP_SOURCE
    assert "if (requestId !== refreshRequestIdRef.current) return;" in APP_SOURCE
    assert "if (requestId === refreshRequestIdRef.current)" in APP_SOURCE


def test_current_review_kpis_do_not_show_fill_count():
    match = re.search(
        r'<section className="kpis currentReviewKpis".*?</section>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    assert 'Metric label="成交数"' not in match.group(0)


def test_single_day_kpis_do_not_show_net_profit_per_share():
    current_match = re.search(
        r'<section className="kpis currentReviewKpis".*?</section>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    mini_match = re.search(
        r'<dl className="compactFacts summaryMiniFacts">.*?</dl>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert current_match is not None
    assert mini_match is not None
    assert "每股净收益" not in current_match.group(0)
    assert "net_profit_per_share" not in current_match.group(0)
    assert "每股净收益" not in mini_match.group(0)
    assert "net_profit_per_share" not in mini_match.group(0)


def test_current_review_kpis_keep_drawdown_on_same_row():
    match = re.search(
        r'<section className="kpis currentReviewKpis".*?</section>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    style_match = re.search(
        r"\.currentReviewKpis\s*\{[^}]*grid-template-columns:\s*([^;]+);",
        STYLES_SOURCE,
    )
    assert match is not None
    assert style_match is not None
    assert match.group(0).count("<Metric label=") == 5
    assert 'Metric label="持仓最大回撤"' in match.group(0)
    assert "repeat(5" in style_match.group(1)


def test_trade_replay_surfaces_position_drawdown_trace():
    assert "export interface TradeGroupPositionDrawdown" in TYPES_SOURCE
    assert "position_drawdown: TradeGroupPositionDrawdown" in TYPES_SOURCE
    assert "<th>最大回撤</th>" in APP_SOURCE
    assert "formatPositionDrawdown(group.position_drawdown)" in APP_SOURCE
    assert "TradeReplayDrawdownEvidence" in APP_SOURCE
    assert "持仓最大回撤追溯" in APP_SOURCE


def test_trade_replay_view_opens_before_market_archive_requests():
    match = re.search(
        r"async function onReplayTradeGroup\(group: TradeGroup\) \{(?P<body>.*?)\n  \}",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert body.index("setSelectedReplayGroup(group)") < body.index("fetchMinuteArchives(")
    assert body.index("setSelectedReplayGroup(group)") < body.index("archiveYahooMinuteData(")
    assert "fetchTradeGroups(tradeDate)" in body
