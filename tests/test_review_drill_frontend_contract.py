from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
AI_STRATEGY_SOURCE = (ROOT / "web" / "src" / "AiStrategyWorkspace.tsx").read_text(encoding="utf-8")
API_SOURCE = (ROOT / "web" / "src" / "api.ts").read_text(encoding="utf-8")
MAIN_SOURCE = (ROOT / "web" / "src" / "main.tsx").read_text(encoding="utf-8")
STYLES_SOURCE = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
TYPES_SOURCE = (ROOT / "web" / "src" / "types.ts").read_text(encoding="utf-8")


def test_workspace_launch_marker_is_consumed_without_dropping_other_url_state():
    assert 'new URLSearchParams(window.location.search).get("grit_ui")' in APP_SOURCE
    assert "function clearWorkspaceLaunchMarker()" in APP_SOURCE
    assert 'url.searchParams.delete("grit_ui")' in APP_SOURCE
    assert "const nextUrl = `${url.pathname}${url.search}${url.hash}`" in APP_SOURCE
    assert 'window.history.replaceState(window.history.state, "", nextUrl)' in APP_SOURCE
    assert "clearWorkspaceLaunchMarker();" in APP_SOURCE


def test_review_drill_date_stats_use_selected_date_group_summary():
    assert "const dataReviewSelectedDateSummary = useMemo" in APP_SOURCE
    assert "dataReviewDateSummaryGroups.find((group) => group.group_key === date)" in APP_SOURCE
    assert "function DataReviewCalendar" in APP_SOURCE
    assert "selectedDateSummary={dataReviewSelectedDateSummary}" in APP_SOURCE
    assert "<SummaryMiniFacts summary={props.selectedDateSummary} />" in APP_SOURCE
    assert 'summary={activeReviewDrillTab === "date" ? summary : selectedSymbolSummary}' not in APP_SOURCE


def test_review_drill_breakdowns_are_scoped_to_active_selection():
    assert "const [dateSymbolBreakdownByDate, setDateSymbolBreakdownByDate]" in APP_SOURCE
    assert "datesToPreload" not in APP_SOURCE
    assert 'fetchReviewSummaryGroups("symbol", { date: refreshDate }, requestOptions)' in APP_SOURCE
    assert "const nextDateSymbolBreakdownByDate: Record<string, ReviewSummaryGroup[]> = {" in APP_SOURCE
    assert "[refreshDate]: nextDateSymbolBreakdown" in APP_SOURCE
    assert "setDateSymbolBreakdownByDate(nextDateSymbolBreakdownByDate)" in APP_SOURCE
    assert "const dateSymbolBreakdownReady = Object.prototype.hasOwnProperty.call(dateSymbolBreakdownByDate, date)" in APP_SOURCE
    assert "const visibleDateSymbolBreakdown = useMemo" in APP_SOURCE
    assert "dateSymbolBreakdownByDate[date] ?? []" in APP_SOURCE
    assert "const visibleSymbolDateBreakdown = useMemo" in APP_SOURCE
    assert "symbolDateBreakdown.filter((group) => group.symbol === selectedSymbol)" in APP_SOURCE


def test_date_drill_uses_preloaded_symbol_breakdown_before_empty_state():
    assert "dateSymbolBreakdownReady" in APP_SOURCE
    assert "dateSymbolBreakdownByDate[date] ?? []" in APP_SOURCE
    assert '"读取中"' in APP_SOURCE
    assert "props.symbolBreakdown.length > 0" in APP_SOURCE
    assert 'title="该日没有标的"' in APP_SOURCE


def test_refresh_drops_stale_date_requests_before_updating_review_state():
    assert "const refreshRequestIdRef = useRef(0)" in APP_SOURCE
    assert "const refreshAbortControllerRef = useRef<AbortController | null>(null)" in APP_SOURCE
    assert "refreshAbortControllerRef.current?.abort()" in APP_SOURCE
    assert "const requestOptions = { signal: refreshAbortController.signal }" in APP_SOURCE
    assert "const refreshDate = date" in APP_SOURCE
    assert "fetchReviewSummary(refreshDate, undefined, requestOptions)" in APP_SOURCE
    assert "fetchDailySummary(refreshDate)" not in APP_SOURCE
    assert 'fetchReviewSummaryGroups("symbol", { date: refreshDate }, requestOptions)' in APP_SOURCE
    assert "if (isAbortError(err)) return;" in APP_SOURCE
    assert "if (requestId !== refreshRequestIdRef.current) return;" in APP_SOURCE
    assert "if (requestId === refreshRequestIdRef.current)" in APP_SOURCE


def test_current_review_summary_tracks_selected_date_and_symbol():
    assert "const [currentReviewSummary, setCurrentReviewSummary]" in APP_SOURCE
    assert "const currentReviewSummaryRequestIdRef = useRef(0)" in APP_SOURCE
    assert "async function loadCurrentReviewSummary(nextDate = date, symbol = selectedSymbol)" in APP_SOURCE
    assert "const currentSymbol = symbol || undefined" in APP_SOURCE
    assert "fetchReviewSummary(nextDate, currentSymbol)" in APP_SOURCE
    assert "setCurrentReviewSummary(nextSummary)" in APP_SOURCE
    assert "void loadCurrentReviewSummary();" in APP_SOURCE
    assert "}, [date, selectedSymbol]);" in APP_SOURCE
    assert "const scopedCurrentReviewSummary =" in APP_SOURCE
    assert "currentReviewSummary?.date === date && currentReviewSummary.symbol === (selectedSymbol || null)" in APP_SOURCE


def test_first_paint_get_requests_are_deduped_in_dev():
    assert "const inFlightGetRequests = new Map<string, Promise<unknown>>();" in API_SOURCE
    assert "async function readGetJson<T>(path: string, options: GetRequestOptions = {}): Promise<T>" in API_SOURCE
    assert "return readJson<T>(await fetch(path, { signal: options.signal }))" in API_SOURCE
    assert "fetch(path).then((response) => readJson<T>(response))" in API_SOURCE
    assert "inFlightGetRequests.delete(path)" in API_SOURCE
    assert "React.StrictMode" not in MAIN_SOURCE
    assert "fetchDailySummary(refreshDate)" not in APP_SOURCE
    assert 'params.set("include_details", options.includeDetails ? "true" : "false")' in API_SOURCE
    assert "fetchTradeGroups(refreshDate, undefined, requestOptions)" in APP_SOURCE
    assert "async function loadStrategyCatalog()" in APP_SOURCE
    assert 'if (activeWorkspaceTab !== "strategy") return;' in APP_SOURCE
    assert "void loadStrategyRuns();" in APP_SOURCE
    assert "void loadStrategyResearch();" in APP_SOURCE
    assert "fetchStrategyRuns(date, symbol, strategyId, { limit: 20 })" in APP_SOURCE
    assert "options: { includeDetails?: boolean; limit?: number } = {}" in API_SOURCE
    assert 'params.set("limit", String(options.limit))' in API_SOURCE


def test_api_errors_are_user_readable_instead_of_raw_status_codes():
    assert "async function apiErrorMessage(response: Response): Promise<string>" in API_SOURCE
    assert "throw new Error(await apiErrorMessage(response))" in API_SOURCE
    assert "return `API ${response.status}`" not in API_SOURCE
    assert "API 422" not in API_SOURCE
    assert "API 404" not in API_SOURCE
    assert "const apiErrorDetailMessages: Record<string, string>" in API_SOURCE
    assert 'archive_symbol_required: "请选择要归档的标的。"' in API_SOURCE
    assert 'trade_review_requires_loss: "只有已平仓的亏损交易组可以保存亏损复盘。"' in API_SOURCE
    assert 'strategy_config_history_already_current: "当前策略已经是所选历史参数，不需要重复回退。"' in API_SOURCE
    assert "function validationDetailMessage" in API_SOURCE
    assert 'if (type === "json_invalid") return "请求内容格式不正确，请刷新页面后重试。";' in API_SOURCE
    assert 'date: "日期"' in API_SOURCE


def test_archive_failure_reasons_do_not_expose_http_codes_to_operators():
    assert 'return `Yahoo 返回 HTTP ${reason.replace("yahoo_http_", "")}，系统已保存为 provider_failed。`;' not in APP_SOURCE
    assert "Yahoo 未接受 1 分钟历史请求" in APP_SOURCE
    assert "Yahoo 暂时没有接受本次分钟线请求" in APP_SOURCE
    assert "Futu 备选历史 K 线额度也已用尽" in APP_SOURCE
    assert "Futu 备选历史 K 线请求也未成功" in APP_SOURCE
    assert "分钟线包含与前后行情不连续的孤立异常柱" in APP_SOURCE


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


def test_review_drill_daily_data_shows_orders_shares_and_pnl_only():
    mini_match = re.search(
        r'<dl className="compactFacts summaryMiniFacts">.*?</dl>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert mini_match is not None
    mini_body = mini_match.group(0)
    assert "<dt>订单数</dt>" in mini_body
    assert "<dd>{formatInteger(summary.fill_count)}</dd>" in mini_body
    assert "<dt>股数</dt>" in mini_body
    assert "<dd>{formatInteger(summary.traded_quantity)}</dd>" in mini_body
    assert "<dt>PnL</dt>" in mini_body
    assert "<dt>胜率</dt>" not in mini_body
    assert "<dt>盈亏比</dt>" not in mini_body
    assert "<dt>持仓最大回撤</dt>" not in mini_body
    assert "订单数 ${formatInteger(summary.fill_count)} · 股数 ${formatInteger(summary.traded_quantity)} · PnL ${formatPnl(summary.pnl)}" in APP_SOURCE


def test_current_review_kpis_show_mfe_mae_on_same_row():
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
    assert len(re.findall(r"<Metric\s+label=", match.group(0))) == 6
    assert re.search(r'<Metric\s+label="MFE"', match.group(0)) is not None
    assert re.search(r'<Metric\s+label="MAE"', match.group(0)) is not None
    assert "持仓最大回撤" not in match.group(0)
    assert "scopedCurrentReviewSummary" in match.group(0)
    assert "summary?." not in match.group(0)
    assert "repeat(6" in style_match.group(1)


def test_trade_replay_surfaces_position_drawdown_trace():
    assert "export interface TradeGroupPositionDrawdown" in TYPES_SOURCE
    assert "position_drawdown: TradeGroupPositionDrawdown" in TYPES_SOURCE
    assert "entry_atr_multiple: number | null" in TYPES_SOURCE
    assert "max_favorable_excursion: number | null" in TYPES_SOURCE
    assert "max_adverse_excursion: number | null" in TYPES_SOURCE
    assert 'entry_atr_regime: "extreme" | "high" | "normal" | "low" | "missing"' in TYPES_SOURCE
    assert "<th>最大回撤</th>" not in APP_SOURCE
    assert "formatNullable(group.position_drawdown.max_favorable_excursion)" in APP_SOURCE
    assert "formatNullable(group.position_drawdown.max_adverse_excursion)" in APP_SOURCE
    assert "<small>{formatPositionDrawdownMeta(group.position_drawdown)}</small>" not in APP_SOURCE
    assert "${formatNullable(drawdown.max_drawdown_per_share)}/股" not in APP_SOURCE
    assert ".pnlCell small" not in STYLES_SOURCE
    assert "TradeReplayDrawdownEvidence" in APP_SOURCE
    assert "持仓最大回撤追溯" in APP_SOURCE


def test_trade_replay_view_reads_local_archives_without_provider_archive():
    match = re.search(
        r"async function onReplayTradeGroup\(group: TradeGroup\) \{(?P<body>.*?)\n  \}",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert body.index("setSelectedReplayGroup(group)") < body.index("fetchMinuteArchives(")
    assert "archiveYahooMinuteData(" not in body
    assert 'fetchMinuteArchives(tradeDate, group.symbol, "yahoo")' not in body
    assert "fetchMinuteArchives(tradeDate, group.symbol)" in body
    assert "fetchTradeGroups(tradeDate, undefined, { includeDetails: true })" in body
    assert "onRefreshReviewMinuteArchives" in APP_SOURCE
    assert "刷新本地分钟线" in APP_SOURCE


def test_non_available_minute_archives_never_render_success_charts():
    assert (
        'selectedArchive && selectedArchive.data_status === "available" && selectedArchive.bars.length > 0'
        in APP_SOURCE
    )
    assert (
        'props.archive && props.archive.data_status === "available" && props.archive.bars.length > 0'
        in APP_SOURCE
    )


def test_review_minute_archive_refresh_force_archives_before_reloading_read_model():
    match = re.search(
        r"async function onRefreshReviewMinuteArchives\(\) \{(?P<body>.*?)\n  \}",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert "await archiveYahooMinuteData(date, true, selectedSymbol, 1);" in body
    assert body.index("archiveYahooMinuteData") < body.index("fetchMinuteArchives(")
    assert 'fetchMinuteArchives(date, selectedSymbol, "yahoo")' not in body
    assert "fetchMinuteArchives(date, selectedSymbol)" in body
    assert "fetchFills(date, undefined)" in body
    assert body.index("fetchMinuteArchives(") < body.index("fetchFills(")
    assert body.index("fetchFills(") < body.index("fetchTradeGroups(")
    assert "fetchReviewSummary(date, selectedSymbol)" in body
    assert "fetchReviewSummary(date, undefined)" in body
    assert "fetchReviewSummary(undefined, undefined)" in body
    assert 'fetchReviewSummaryGroups("date", {})' in body
    assert 'fetchReviewSummaryGroups("symbol", { date })' in body
    assert "setCurrentReviewSummary(nextCurrentReviewSummary)" in body
    assert "setSummary(nextSummary)" in body
    assert "setOverallSummary(nextOverallSummary)" in body
    assert "setDateSummaryGroups(nextDateGroups)" in body
    assert "setDateSymbolBreakdownByDate" in body


def test_trade_replay_modal_keeps_header_fixed_and_backdrop_closes():
    match = re.search(
        r"function TradeReplayModal\(props: \{(?P<body>.*?)\nfunction TradeReplayDrawdownEvidence",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert "onMouseDown={(event) => {" in body
    assert "event.target === event.currentTarget" in body
    assert "props.onClose()" in body
    assert '<div className="replayModalBody">' in body
    assert ".replayModalBody" in STYLES_SOURCE
    assert re.search(r"\.replayModal\s*\{[^}]*overflow:\s*hidden;", STYLES_SOURCE, flags=re.DOTALL) is not None
    assert re.search(r"\.replayModalBody\s*\{[^}]*overflow-y:\s*auto;", STYLES_SOURCE, flags=re.DOTALL) is not None
    assert re.search(r"\.replayModal\s*>\s*\.modalHeader\s*\{[^}]*flex:\s*0 0 auto;", STYLES_SOURCE, flags=re.DOTALL) is not None


def test_loss_trade_review_action_and_reason_catalog_are_visible():
    assert "review: TradeReview | null" in TYPES_SOURCE
    assert "export type TradeReviewReasonCategory" in TYPES_SOURCE
    assert "saveTradeGroupReview" in API_SOURCE
    assert "/api/trade-groups/${encodeURIComponent(tradeGroupId)}/review" in API_SOURCE
    assert "reviewingLossGroup" not in APP_SOURCE
    assert 'const canReviewLoss = group.status === "closed" && group.pnl !== null && group.pnl < 0' in APP_SOURCE
    assert "lossReviewAction" not in APP_SOURCE
    assert 'className="linkButton lossReviewAction"' not in APP_SOURCE
    assert "showLossOnlyTradeGroups" in APP_SOURCE
    assert "setShowLossOnlyTradeGroups(event.target.checked)" in APP_SOURCE
    assert "仅看亏损单" in APP_SOURCE
    assert "当前范围没有亏损单" in APP_SOURCE
    assert "symbolScopedTradeGroups.filter" in APP_SOURCE
    assert ".tradeLedgerToolbar" in STYLES_SOURCE
    assert "待复盘" in APP_SOURCE
    assert "function LossReviewPanel" in APP_SOURCE
    assert "function LossReviewModal" not in APP_SOURCE
    order_details_index = APP_SOURCE.index("<TradeReplayOrderDetails group={props.group} />")
    loss_panel_index = APP_SOURCE.index("<LossReviewPanel", order_details_index)
    assert order_details_index < loss_panel_index
    assert ".lossReviewPanel" in STYLES_SOURCE
    assert "reason_category: reasonCategory" in APP_SOURCE
    assert "reason_code: reasonCode" in APP_SOURCE
    assert "opening_signal: \"开仓信号\"" in APP_SOURCE
    assert "closing_signal: \"平仓信号\"" in APP_SOURCE
    assert "misoperation: \"误操作\"" in APP_SOURCE
    assert "{ code: \"chased_breakout\", label: \"追突破过急\" }" in APP_SOURCE
    assert "{ code: \"weak_confirmation\", label: \"确认不足\" }" in APP_SOURCE
    assert "{ code: \"stop_too_late\", label: \"止损过慢\" }" in APP_SOURCE
    assert "{ code: \"profit_reversed\", label: \"盈利回吐\" }" in APP_SOURCE
    assert "{ code: \"wrong_side_or_symbol\", label: \"方向或标的点错\" }" in APP_SOURCE
    assert "{ code: \"plan_not_followed\", label: \"未按计划执行\" }" in APP_SOURCE


def test_profit_loss_review_drill_tab_reads_profit_and_loss_trade_groups():
    assert 'type ReviewDrillSurfaceTab = "data" | "loss" | "summary";' in APP_SOURCE
    assert 'const [activeReviewDrillSurfaceTab, setActiveReviewDrillSurfaceTab] = useState<ReviewDrillSurfaceTab>("data")' in APP_SOURCE
    assert "const [allTradeGroups, setAllTradeGroups] = useState<TradeGroup[]>([])" in APP_SOURCE
    assert "fetchTradeGroups(undefined, undefined, { ...requestOptions, includeDetails: false })" in APP_SOURCE
    assert "setAllTradeGroups(nextAllTradeGroups)" in APP_SOURCE
    assert "type ProfitLossReviewMode = \"all\" | \"profit\" | \"loss\";" in APP_SOURCE
    assert 'all: "全部订单"' in APP_SOURCE
    assert "profit: \"仅看盈利单\"" in APP_SOURCE
    assert "loss: \"仅看亏损单\"" in APP_SOURCE
    assert "function isClosedProfitTradeGroup" in APP_SOURCE
    assert "function isClosedRealizedTradeGroup" in APP_SOURCE
    assert "const profitLossReviewTradeGroups = useMemo" in APP_SOURCE
    assert "allTradeGroups.filter(isClosedRealizedTradeGroup)" in APP_SOURCE
    assert 'const [profitLossReviewMode, setProfitLossReviewMode] = useState<ProfitLossReviewMode>("all")' in APP_SOURCE
    assert 'profitLossReviewMode === "all"\n        ? props.tradeGroups' in APP_SOURCE
    assert "profitLossReviewMode === \"profit\" ? isClosedProfitTradeGroup(group) : isClosedLossTradeGroup(group)" in APP_SOURCE
    assert "showReasonModules ? buildLossReviewPrimaryReasonSummaries(timeFilteredTradeGroups) : []" in APP_SOURCE
    assert "showReasonModules ? buildLossReviewSecondaryReasonSummaries(primaryFilteredTradeGroups) : []" in APP_SOURCE
    assert "数据下钻" in APP_SOURCE
    assert "盈亏复盘" in APP_SOURCE
    assert "function LossReviewDrilldown" in APP_SOURCE
    assert "原因分类汇总" in APP_SOURCE
    assert "一级原因" in APP_SOURCE
    assert "二级原因" in APP_SOURCE
    assert "{reviewGroupLabel}列表" in APP_SOURCE
    assert "待复盘" in APP_SOURCE
    assert "Review Journal" in APP_SOURCE
    assert "onClick={() => void props.onReplayTradeGroup(group)}" in APP_SOURCE
    assert 'type LossReviewSortMode = "time_desc" | "loss_desc";' in APP_SOURCE
    assert 'type LossReviewTimeFilterMode = "all" | "month" | "week" | "custom";' in APP_SOURCE
    assert 'useState<LossReviewTimeFilterMode>("all")' in APP_SOURCE
    assert "profitLossReviewTimeFilterMode" in APP_SOURCE
    assert "function ReviewSharedTimeFilter" in APP_SOURCE
    assert "lossReviewTimeFilterLabels" in APP_SOURCE
    assert 'all: "全部"' in APP_SOURCE
    assert 'month: "本月"' in APP_SOURCE
    assert 'week: "本周"' in APP_SOURCE
    assert 'custom: "特定时间段"' in APP_SOURCE
    assert "const timeFilteredTradeGroups = useMemo" in APP_SOURCE
    assert "lossReviewDateRangeIncludesGroup(group, lossReviewTimeRange.startDate, lossReviewTimeRange.endDate)" in APP_SOURCE
    assert "const timeReviewedTradeGroupCount = showReasonModules ? timeFilteredTradeGroups.filter" in APP_SOURCE
    assert "const timeTotalReviewPnl = timeFilteredTradeGroups.reduce" in APP_SOURCE
    assert "const LOSS_REVIEW_PAGE_SIZE = 20;" in APP_SOURCE
    assert 'useState<LossReviewSortMode>("time_desc")' in APP_SOURCE
    assert 'setLossReviewSortMode("loss_desc")' in APP_SOURCE
    assert "selectedPrimaryReasonKeys" in APP_SOURCE
    assert "selectedSecondaryReasonKeys" in APP_SOURCE
    assert "lossReviewSecondaryReasonKey(group)" in APP_SOURCE
    assert "safePage * LOSS_REVIEW_PAGE_SIZE" in APP_SOURCE
    assert ".profitLossReviewModeSwitch" in STYLES_SOURCE
    assert ".profitLossReviewModeOption" in STYLES_SOURCE
    assert ".reviewDrillSurfaceTabs" in STYLES_SOURCE
    assert ".lossReviewDrillLayout" in STYLES_SOURCE
    assert ".lossReviewTimeFilter" in STYLES_SOURCE
    assert ".lossReviewCustomRange" in STYLES_SOURCE
    assert ".lossReviewSummaryRow" in STYLES_SOURCE
    assert ".compactFacts.lossReviewSummaryRow" in STYLES_SOURCE
    assert ".compactFacts.lossReviewSummaryRow {\n  grid-template-columns: repeat(4, minmax(0, 1fr));\n}" in STYLES_SOURCE
    assert ".lossReviewReasonChart" in STYLES_SOURCE
    assert ".lossReviewPie" in STYLES_SOURCE
    assert ".lossReviewFilterOption" in STYLES_SOURCE
    assert ".lossReviewTradeItem" in STYLES_SOURCE
    assert "date?: string" in API_SOURCE
    assert 'if (date) params.set("date", date);' in API_SOURCE


def test_trade_summary_third_tab_uses_shared_scope_session_summary_and_executable_rules():
    assert "交易总结" in APP_SOURCE
    assert 'activeReviewDrillSurfaceTab === "summary"' in APP_SOURCE
    assert "function TradeSummaryPanel" in APP_SOURCE
    assert "fetchTradeSummary(timeRange.startDate ?? undefined, timeRange.endDate ?? undefined" in APP_SOURCE
    summary_panel = APP_SOURCE[APP_SOURCE.index("function TradeSummaryPanel"):APP_SOURCE.index("function TradeSummaryProgress")]
    assert "generateTradeSummary(" not in summary_panel
    assert "onGenerateSummary" not in summary_panel
    assert "window.setInterval" not in summary_panel
    assert 'summary.generation.provider === "codex_session"' in summary_panel
    assert "摘要来源：本次会话" in summary_panel
    assert "不会由浏览器自动调用模型" in summary_panel
    assert "customEndDate={customProfitLossReviewEndDate}" in APP_SOURCE
    assert "customStartDate={customProfitLossReviewStartDate}" in APP_SOURCE
    assert "timeFilterMode={profitLossReviewTimeFilterMode}" in APP_SOURCE
    assert "闭合交易" in APP_SOURCE
    assert "Profit Factor" in APP_SOURCE
    assert "分钟线评价覆盖率" in APP_SOURCE
    assert "亏损 Journal 覆盖率" in APP_SOURCE
    assert "推荐执行规则" in APP_SOURCE
    assert "推荐规避错误" in APP_SOURCE
    assert "量化执行清单" in APP_SOURCE
    assert "(rule.action_steps ?? []).map" in APP_SOURCE
    assert "rule.action_steps.map" not in APP_SOURCE
    assert "会话点评：" in APP_SOURCE
    assert "盈利支持率" not in summary_panel
    assert "formatRuleEvidenceRate" not in APP_SOURCE
    assert "经典方法依据" in APP_SOURCE
    assert "AI 生成已禁用" in APP_SOURCE
    assert 'summary.evidence_status === "eligible"' in APP_SOURCE
    for status in ("not_requested", "unconfigured", "pending", "completed", "failed", "stale"):
        assert f"{status}:" in APP_SOURCE
    assert '"/api/review/trade-summary/generations"' in API_SOURCE
    assert 'method: "POST"' in API_SOURCE
    assert '`/api/review/trade-summary${suffix}`' in API_SOURCE
    assert ".tradeSummaryRuleColumns" in STYLES_SOURCE
    assert ".tradeSummaryRuleActionGrid" in STYLES_SOURCE
    assert ".tradeSummaryMetrics" in STYLES_SOURCE
    assert ".tradeSummaryAiCard" in STYLES_SOURCE
    assert ".tradeSummaryBaselineCards" in STYLES_SOURCE


def test_profit_review_view_keeps_reason_module_empty():
    loss_body_start = APP_SOURCE.index('function LossReviewDrilldown(props: {')
    loss_body_end = APP_SOURCE.index('function EmptyState', loss_body_start)
    loss_body = APP_SOURCE[loss_body_start:loss_body_end]

    assert 'const [profitLossReviewMode, setProfitLossReviewMode] = useState<ProfitLossReviewMode>("all")' in loss_body
    assert 'role="radiogroup" aria-label="盈亏单筛选"' in loss_body
    assert 'name="profitLossReviewMode"' in loss_body
    assert "setProfitLossReviewMode(mode)" in loss_body
    assert '(["all", "profit", "loss"] as ProfitLossReviewMode[])' in loss_body
    assert 'showTimeWindowPnlSummary={profitLossReviewMode === "all"}' in loss_body
    assert 'profitLossReviewMode === "all"\n                ? "pnl_extremes"' in loss_body
    assert 'buildLossReviewMarketRegimeMatrix(timeFilteredTradeGroups, profitLossReviewMode === "loss" ? "loss" : "all")' in loss_body
    assert 'showReasonModules ? (' in loss_body
    assert 'title="暂无原因分类"' in loss_body
    assert "盈利单不写入亏损原因，原因模块保持为空" in loss_body
    assert "profitLossReviewSortLabel(profitLossReviewMode)" in loss_body
    assert "<dt>结果</dt>" in loss_body
    assert "<dd>{profitLossReviewResultLabel(group)}</dd>" in loss_body


def test_loss_review_market_regime_matrix_uses_us_session_windows():
    assert "type LossReviewTimeWindowKey" in APP_SOURCE
    assert '"early_session"' in APP_SOURCE
    assert '"late_morning_transition"' in APP_SOURCE
    assert '"lunch_hour_squeeze"' in APP_SOURCE
    assert '"early_afternoon_drift"' in APP_SOURCE
    assert '"power_hour"' in APP_SOURCE
    assert "const lossReviewRegularTimeWindows" in APP_SOURCE
    assert "09:30-10:30" in APP_SOURCE
    assert "10:30-11:30" in APP_SOURCE
    assert "11:30-13:30" in APP_SOURCE
    assert "13:30-15:00" in APP_SOURCE
    assert "15:00-16:00" in APP_SOURCE
    assert "早盘高动能" in APP_SOURCE
    assert "早盘至中盘过渡" in APP_SOURCE
    assert "中盘死寂垃圾时间" in APP_SOURCE
    assert "尾盘蓄势期" in APP_SOURCE
    assert "尾盘生死时速" in APP_SOURCE
    assert "Market Regime Matrix" in APP_SOURCE
    assert "热力时间矩阵" in APP_SOURCE
    assert 'type LossReviewVolatilityRegimeKey = "extreme" | "high" | "normal" | "low" | "missing";' in APP_SOURCE
    assert '{ detail: "> 3.0 x ATR", key: "extreme", label: "极端冲击" }' in APP_SOURCE
    assert '{ detail: "1.5-3.0 x ATR", key: "high", label: "高波动" }' in APP_SOURCE
    assert '{ detail: "0.5-1.5 x ATR", key: "normal", label: "常规波动" }' in APP_SOURCE
    assert '{ detail: "< 0.5 x ATR", key: "low", label: "低波动" }' in APP_SOURCE
    assert "lossReviewEntryAtrMultiple" in APP_SOURCE
    assert "group.position_drawdown.entry_atr_multiple" in APP_SOURCE
    assert "lossReviewRegimePressure" not in APP_SOURCE
    assert '"event_shock"' not in APP_SOURCE
    assert "$1,500" not in APP_SOURCE
    assert "开仓 ATR Multiple" in APP_SOURCE
    assert "缺 ATR 证据" in APP_SOURCE
    assert 'buildLossReviewMarketRegimeMatrix(timeFilteredTradeGroups, profitLossReviewMode === "loss" ? "loss" : "all")' in APP_SOURCE
    assert "lossReviewMatchesSelectedRegimeCell(group, selectedMarketRegimeCell)" not in APP_SOURCE
    assert "selectedMarketRegimeCell" not in APP_SOURCE
    assert "toggleMarketRegimeCell" not in APP_SOURCE
    assert "summaryMode?: \"concentration\" | \"max_loss\" | \"max_profit\" | \"pnl_extremes\"" in APP_SOURCE
    assert "maxProfitCell" in APP_SOURCE
    assert "maxLossCell" in APP_SOURCE
    assert "lossReviewMarketRegimeZoneLabel" in APP_SOURCE
    assert "readOnly?: boolean" in APP_SOURCE
    assert "showTimeWindowPnlSummary?: boolean" in APP_SOURCE
    assert "timeWindowSummaries: LossReviewTimeWindowSummary[]" in APP_SOURCE
    assert '.filter((row) => row.key !== "missing" || row.cells.some((cell) => cell.count > 0))' in APP_SOURCE
    assert "props.matrix.timeWindows.map" in APP_SOURCE
    assert 'showYAxisSummary ? " minmax(132px, 0.95fr)" : ""' in APP_SOURCE
    assert "lossReviewTimeWindows" not in APP_SOURCE
    assert 'return "extended"' not in APP_SOURCE
    assert ".lossReviewMatrixPanel" in STYLES_SOURCE
    assert ".lossReviewMatrixGrid" in STYLES_SOURCE
    assert ".lossReviewMatrixCell" in STYLES_SOURCE
    loss_body_start = APP_SOURCE.index('function LossReviewDrilldown(props: {')
    loss_body_end = APP_SOURCE.index('function EmptyState', loss_body_start)
    loss_body = APP_SOURCE[loss_body_start:loss_body_end]
    assert 'profitLossReviewMode === "all"\n                ? "pnl_extremes"' in loss_body
    assert 'showTimeWindowPnlSummary={profitLossReviewMode === "all"}' in loss_body
    assert "readOnly" in loss_body
    assert "最大亏损区" in APP_SOURCE
    assert "最大盈利区" in APP_SOURCE
    assert "onToggleCell" not in APP_SOURCE
    assert "selectedCell" not in APP_SOURCE
    assert "未选择矩阵格" not in APP_SOURCE
    assert "onToggleCell={toggleMarketRegimeCell}" not in loss_body
    assert "selectedCell={selectedMarketRegimeCell}" not in loss_body


def test_all_orders_can_switch_to_share_time_matrix_with_y_axis_summary():
    loss_body_start = APP_SOURCE.index('function LossReviewDrilldown(props: {')
    loss_body_end = APP_SOURCE.index('function EmptyState', loss_body_start)
    loss_body = APP_SOURCE[loss_body_start:loss_body_end]

    assert 'type LossReviewMatrixDimension = "atr" | "shares";' in APP_SOURCE
    assert 'useState<LossReviewMatrixDimension>("atr")' in loss_body
    assert 'profitLossReviewMode === "all" ? allOrdersMatrixDimension : "atr"' in loss_body
    assert 'activeMatrixDimension === "shares"' in loss_body
    assert "buildLossReviewShareTimeMatrix(timeFilteredTradeGroups)" in loss_body
    assert "group.total_quantity" in APP_SOURCE
    assert '{ detail: "> 500 股", key: "very_large", label: "超大单" }' in APP_SOURCE
    assert '{ detail: "201-500 股", key: "large", label: "大单" }' in APP_SOURCE
    assert '{ detail: "101-200 股", key: "medium_large", label: "中大单" }' in APP_SOURCE
    assert '{ detail: "51-100 股", key: "medium", label: "中单" }' in APP_SOURCE
    assert '{ detail: "≤ 50 股", key: "small", label: "小单" }' in APP_SOURCE
    assert '{ detail: "股数缺失或非正数", key: "missing", label: "缺股数证据" }' in APP_SOURCE
    assert 'return Number.isFinite(quantity) && quantity > 0 ? quantity : null;' in APP_SOURCE
    assert 'role="radiogroup" aria-label="热力时间矩阵参数切换"' in APP_SOURCE
    assert 'atr: "ATR 时间矩阵"' in APP_SOURCE
    assert 'shares: "股数时间矩阵"' in APP_SOURCE
    assert 'name="allOrdersTimeMatrixDimension"' in APP_SOURCE
    assert 'onDimensionChange={profitLossReviewMode === "all" ? setAllOrdersMatrixDimension : undefined}' in loss_body
    assert 'showYAxisSummary={activeMatrixDimension === "shares"}' in loss_body
    assert "Y 轴汇总" in APP_SOURCE
    assert "股数档收益" in APP_SOURCE
    assert "rowSummary.tradedQuantity" in APP_SOURCE
    assert "matrixTotalSummary.tradedQuantity" in APP_SOURCE
    assert "纵轴按 committed fills 交易组的配对股数分档" in APP_SOURCE
    assert ".lossReviewMatrixDimensionSwitch" in STYLES_SOURCE
    assert ".lossReviewMatrixDimensionOption" in STYLES_SOURCE
    assert ".lossReviewMatrixRowSummary" in STYLES_SOURCE
    assert ".lossReviewMatrixGrandSummary" in STYLES_SOURCE
    assert "onToggleCell" not in APP_SOURCE


def test_loss_review_tab_does_not_render_data_drill_modules():
    assert "{activeReviewDrillSurfaceTab === \"data\" ? (" in APP_SOURCE
    assert "{activeReviewDrillSurfaceTab === \"data\" ? (\n        <>" in APP_SOURCE
    assert 'className="kpis reviewDashboard dataReviewSummaryStrip"' in APP_SOURCE
    assert '<section className="kpis currentReviewKpis"' in APP_SOURCE
    assert '<section className="reviewWorkspace" aria-label="日内复盘工作区"' in APP_SOURCE
    assert '<section className="panel tradeLedgerPanel" id="trade-ledger">' in APP_SOURCE
    assert '<section className="evidenceGrid" id="import-evidence"' in APP_SOURCE
    data_only_start = APP_SOURCE.index('<section className="kpis currentReviewKpis"')
    data_only_end = APP_SOURCE.index(') : null}\n        </>\n      ) : activeWorkspaceTab === "strategy"', data_only_start)
    data_only_body = APP_SOURCE[data_only_start:data_only_end]
    assert "分钟蜡烛复盘" in data_only_body
    assert "盘前 Watchlist" in data_only_body
    assert "操作入口" in data_only_body
    assert "成交记录" in data_only_body
    assert "导入批次与证据" in data_only_body
    assert "隔离行" in data_only_body


def test_data_drill_orders_time_filter_metrics_calendar_before_detail():
    assert "const [dataReviewTimeFilterMode, setDataReviewTimeFilterMode] = useState<LossReviewTimeFilterMode>(\"all\")" in APP_SOURCE
    assert "const dataReviewTimeFilteredTradeGroups = useMemo" in APP_SOURCE
    assert "lossReviewDateRangeIncludesGroup(group, dataReviewTimeRange.startDate, dataReviewTimeRange.endDate)" in APP_SOURCE
    assert "selectedDataMarketRegimeCell" not in APP_SOURCE
    assert "toggleDataMarketRegimeCell" not in APP_SOURCE
    assert "const dataReviewMatrixFilteredTradeGroups = useMemo" not in APP_SOURCE
    assert "buildReviewSummaryFromTradeGroups(dataReviewTimeFilteredTradeGroups)" in APP_SOURCE
    assert "buildLossReviewMarketRegimeMatrix(dataReviewTimeFilteredTradeGroups, \"all\")" not in APP_SOURCE
    assert "function DataReviewAtrEvidencePanel" not in APP_SOURCE
    assert "全部订单 ATR 证据" not in APP_SOURCE
    assert "formatTradeGroupRawLineEvidence" not in APP_SOURCE
    assert ".dataReviewAtrEvidencePanel" not in STYLES_SOURCE
    assert "buildReviewSummaryGroupsFromTradeGroups(dataReviewTimeFilteredTradeGroups, \"date\")" in APP_SOURCE
    assert "buildDataReviewCalendarDays(dataReviewCalendarMonth, dataReviewDateSummaryGroups)" in APP_SOURCE
    assert "function DataReviewCalendar" in APP_SOURCE
    assert "dataReviewWeekdayLabels" in APP_SOURCE
    data_body_start = APP_SOURCE.index('<div className="dataReviewDrilldown">')
    data_body_end = APP_SOURCE.index('<section className="reviewWorkspace" aria-label="日内复盘工作区"', data_body_start)
    data_body = APP_SOURCE[data_body_start:data_body_end]
    assert data_body.index('aria-label="数据下钻全局时间筛选"') < data_body.index('className="kpis reviewDashboard dataReviewSummaryStrip"')
    assert data_body.index('className="kpis reviewDashboard dataReviewSummaryStrip"') < data_body.index("<DataReviewCalendar")
    assert data_body.index("<DataReviewCalendar") < data_body.index('<section className="kpis currentReviewKpis"')
    assert "<LossReviewMarketRegimeMatrix" not in data_body
    assert 'aria-label="数据下钻月日历"' in APP_SOURCE
    assert "点击有订单的日期方块" in APP_SOURCE
    assert "<small>{formatInteger(day.summary.traded_quantity)} 股</small>" in APP_SOURCE
    assert "<small>{formatInteger(day.summary.fill_count)} 单</small>" not in APP_SOURCE
    assert "onSelectDate={setDate}" in data_body
    assert "onEnterReviewContext={enterReviewContext}" in data_body
    assert 'concentrationLabel="订单集中区"' not in data_body
    assert "readOnly" not in data_body
    assert "showTimeWindowPnlSummary" not in data_body
    assert 'summaryMode="pnl_extremes"' not in data_body
    assert "最大盈利区" in APP_SOURCE
    assert "最大亏损区" in APP_SOURCE
    assert "X 轴汇总" in APP_SOURCE
    assert "收益合计" in APP_SOURCE
    assert ".dataReviewCalendarPanel" in STYLES_SOURCE
    assert ".dataReviewCalendarGrid" in STYLES_SOURCE
    assert ".dataReviewCalendarDay" in STYLES_SOURCE
    assert "props.matrix.timeWindowSummaries.map" in APP_SOURCE
    assert 'onToggleCell={toggleDataMarketRegimeCell}' not in data_body
    assert 'selectedCell={selectedDataMarketRegimeCell}' not in data_body
    assert ".dataReviewDrilldown" in STYLES_SOURCE
    assert ".lossReviewMatrixCell.readOnly" in STYLES_SOURCE
    assert ".lossReviewMatrixColumnSummary" in STYLES_SOURCE


def test_data_review_calendar_switches_to_selected_range_daily_table_and_exports_excel():
    assert 'type DataReviewViewMode = "calendar" | "table"' in APP_SOURCE
    assert 'useState<DataReviewViewMode>("calendar")' in APP_SOURCE
    assert 'aria-label="月日历下钻视图切换"' in APP_SOURCE
    assert "日历视图" in APP_SOURCE
    assert "表格视图" in APP_SOURCE
    assert "dailySummaries={dataReviewDateSummaryGroups}" in APP_SOURCE
    assert "rangeLabel={dataReviewTimeRangeLabel}" in APP_SOURCE
    assert "function DataReviewDailyTable" in APP_SOURCE
    assert "props.dailySummaries.map((summary)" in APP_SOURCE
    for label in [
        "日期",
        "股数",
        "PnL",
        "胜率",
        "盈亏比",
        "单笔期望值",
        "每股净收益",
        "MFE",
        "MAE",
    ]:
        assert f"<th" in APP_SOURCE and label in APP_SOURCE
    assert "summary.traded_quantity" in APP_SOURCE
    assert "summary.max_favorable_excursion" in APP_SOURCE
    assert "summary.max_adverse_excursion" in APP_SOURCE
    assert "<th>已平仓</th>" not in APP_SOURCE
    assert "<th>未平仓</th>" not in APP_SOURCE
    assert '"已平仓交易数"' not in APP_SOURCE
    assert '"未平仓交易数"' not in APP_SOURCE
    assert "function exportDataReviewDailyMetricsToExcel" in APP_SOURCE
    assert 'type: "application/vnd.ms-excel;charset=utf-8"' in APP_SOURCE
    assert "交易复盘每日数据-${fileRange}.xls" in APP_SOURCE
    assert "props.dailySummaries.length === 0" in APP_SOURCE
    assert "所选时间段没有每日数据" in APP_SOURCE
    assert "disabled={props.dailySummaries.length === 0}" in APP_SOURCE
    assert ".dataReviewDailyTableWrap" in STYLES_SOURCE
    assert ".dataReviewDailyTable" in STYLES_SOURCE
    assert "min-width: 1420px" not in STYLES_SOURCE
    assert ".dataReviewDailyTableWrap.tableWrap" in STYLES_SOURCE
    assert "overflow-x: clip" in STYLES_SOURCE
    assert "table-layout: fixed" in STYLES_SOURCE
    assert 'data-label="MFE"' in APP_SOURCE
    assert 'data-label="MAE"' in APP_SOURCE
    assert ".dataReviewDailyTable td::before" in STYLES_SOURCE


def test_daily_mfe_mae_are_projected_from_backend_excursion_evidence():
    assert "max_favorable_excursion: number | null" in TYPES_SOURCE
    assert "max_adverse_excursion: number | null" in TYPES_SOURCE
    assert "group.position_drawdown" in APP_SOURCE
    assert "excursion.status === \"available\"" in APP_SOURCE
    assert "excursion.max_favorable_excursion" in APP_SOURCE
    assert "excursion.max_adverse_excursion ?? excursion.max_drawdown" in APP_SOURCE
    assert "缺少可用分钟归档时显示 N/A" in APP_SOURCE


def test_review_mfe_mae_labels_share_hover_and_keyboard_tooltips():
    summary_match = re.search(
        r"function SummaryMetricStrip\(.*?\n\}",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    current_match = re.search(
        r'<section className="kpis currentReviewKpis".*?</section>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    trade_table_match = re.search(
        r'<table className="tradeGroupTable">.*?</table>',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert summary_match is not None
    assert current_match is not None
    assert trade_table_match is not None
    for body in (summary_match.group(0), current_match.group(0), trade_table_match.group(0)):
        assert "MFE" in body
        assert "MAE" in body
    assert "MFE_TOOLTIP" in APP_SOURCE
    assert "MAE_TOOLTIP" in APP_SOURCE
    assert 'className="metricHelp"' in APP_SOURCE
    assert "data-tooltip={props.tooltip}" in APP_SOURCE
    assert "tabIndex={0}" in APP_SOURCE
    assert ".metricHelp:hover::after" in STYLES_SOURCE
    assert ".metricHelp:focus-visible::after" in STYLES_SOURCE


def test_loss_only_filter_also_scopes_main_chart_trade_markers():
    assert "const displayedChartFills = useMemo(() => {" in APP_SOURCE
    assert "const displayedTradeGroupFills = useMemo" in APP_SOURCE
    assert "displayedTradeGroups.flatMap((group) => group.fills)" in APP_SOURCE
    assert "const chartFillReadModel = displayedFills.length > 0 ? displayedFills : displayedTradeGroupFills;" in APP_SOURCE
    assert "if (!showLossOnlyTradeGroups) return chartFillReadModel;" in APP_SOURCE
    assert "const groupScopes = displayedTradeGroups.map((group) => ({" in APP_SOURCE
    assert "sourceBatchIds: new Set(group.source_batch_ids)" in APP_SOURCE
    assert "rawLineNumbers: new Set(group.raw_line_numbers)" in APP_SOURCE
    assert "scope.accountCanonical === fill.account_canonical" in APP_SOURCE
    assert "scope.symbol === fill.symbol" in APP_SOURCE
    assert "scope.sourceBatchIds.has(fill.source_batch_id)" in APP_SOURCE
    assert "scope.rawLineNumbers.has(fill.raw_line_number)" in APP_SOURCE
    assert "fills={displayedChartFills}" in APP_SOURCE
    assert "fills={displayedFills}" not in APP_SOURCE


def test_strategy_config_modal_keeps_single_day_and_test_batch_scopes_separate():
    assert "run.trade_date === date" in APP_SOURCE
    assert "run.symbol === primaryStrategySymbol" in APP_SOURCE
    assert "run.strategy_id === selectedStrategyId" in APP_SOURCE
    assert "batch.end_date === date" in APP_SOURCE
    assert "latestTestBatch={latestStrategyTestBatch}" in APP_SOURCE
    assert "30天测试信号" in APP_SOURCE
    assert "setStrategyRuns((current) => [run, ...current.filter" not in APP_SOURCE


def test_strategy_testing_workspace_exposes_single_day_replay_action():
    assert "onRunStrategy={() => void onRunStrategy()}" in APP_SOURCE
    assert "strategyBusy={strategyBusy}" in APP_SOURCE
    assert "strategyRunFeedback={strategyRunFeedback}" in APP_SOURCE
    match = re.search(
        r'<section className="panel strategyConfigSummary">(?P<body>.*?)\n        </section>\n\n        <section className="panel strategyBatchPanel">',
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert "props.onRunStrategy" in body
    assert '{props.strategyBusy ? "复盘中" : "策略复盘"}' in body
    assert "props.strategyDraftDirty" in body
    assert "props.strategyRunFeedback" in body
    assert "props.onOpenStrategyConfig" in body


def test_strategy_test_day_detail_loads_selected_day_without_all_day_prefetch():
    assert "batch.day_results.forEach((day)" not in APP_SOURCE
    assert "const day = selectedStrategyTestDay" in APP_SOURCE
    assert "const cached = strategyTestDayDetailCache[cacheKey]" in APP_SOURCE
    assert "fetchStrategyRunDetail(day.strategy_run_id)" in APP_SOURCE
    assert "selectedStrategyTestDay?.day_result_id" in APP_SOURCE
    assert "void loadStrategyTestDayDetail(day, selectedStrategyId, batch.symbol, { batchId: batch.batch_id });" in APP_SOURCE
    assert "const firstDay = batch.day_results[0] ?? null" in APP_SOURCE
    assert "正在套用候选参数" in APP_SOURCE
    assert "套用中" in APP_SOURCE


def test_strategy_signal_order_groups_show_backend_pnl():
    assert "export interface StrategySignalGroupPerformance" in TYPES_SOURCE
    assert "signal_groups?: StrategySignalGroupPerformance[] | null" in TYPES_SOURCE
    assert "buildStrategySignalGroups(signals, props.run?.signal_groups ?? [], props.run?.params)" in APP_SOURCE
    assert "buildStrategySignalGroups(props.signals, props.run.signal_groups ?? [], props.run.params)" in APP_SOURCE
    assert "groupMetricsByEntryId" in APP_SOURCE
    assert "signalGroupPnlFromBackendSignalMetrics" in APP_SOURCE
    assert "exitSignal.metrics.pnl_per_share" in APP_SOURCE
    assert "strategyPositionQuantity(group.entry.price, params)" in APP_SOURCE
    assert "signalGroupPnl" in APP_SOURCE
    assert "formatSignalGroupPnl(group)" in APP_SOURCE
    assert ".signalGroupPnl.statPositive" in STYLES_SOURCE


def test_strategy_summary_drilldown_does_not_stretch_with_day_detail():
    match = re.search(
        r"\.strategyReviewExplorer\s*\{(?P<body>.*?)\n\}",
        STYLES_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    assert "align-self: start;" in match.group("body")


def test_review_refresh_does_not_preload_all_date_symbol_breakdowns():
    assert "datesToPreload" not in APP_SOURCE
    assert 'fetchReviewSummaryGroups("symbol", { date: refreshDate }, requestOptions)' in APP_SOURCE
    assert "nextDateSymbolBreakdownByDate: Record<string, ReviewSummaryGroup[]>" in APP_SOURCE


def test_strategy_workspace_supports_multi_ticker_screener_without_frontend_indicator_math():
    assert "function parseStrategySymbolInput" in APP_SOURCE
    assert "split(/[,\\s，、]+/)" in APP_SOURCE
    assert "const [strategySymbolInput, setStrategySymbolInput]" in APP_SOURCE
    assert "const primaryStrategySymbol = strategySymbols[0] ?? selectedSymbol" in APP_SOURCE
    assert 'placeholder="MU, NVDA, AMD, AVGO, TSM, MSFT"' in APP_SOURCE
    assert "for (const symbol of targetSymbols)" in APP_SOURCE
    assert "runStrategyTestBatch(selectedStrategy.strategy_id, date, symbol" in APP_SOURCE
    assert "runStrategyOptimization(" in APP_SOURCE
    assert "StrategyScanResults" in APP_SOURCE
    assert "test batch 仍按 symbol 保存；优化按输入标的组保存全局 optimization run、archive_scope_hash 和 params_hash。" in APP_SOURCE


def test_bb_squeeze_atr_target_contract_is_visible_without_frontend_indicator_math():
    assert 'atr_target: "ATR 目标达标"' in APP_SOURCE
    assert 'atr_target_plan: "ATR 目标计划"' in APP_SOURCE
    assert '"atr_target_multiplier"' in APP_SOURCE
    assert "ATR 止损和 ATR 第一目标仍优先于出场缓冲触发。" in APP_SOURCE
    assert "后端逐 bar 计算 ATR({atrPeriod})" in APP_SOURCE
    assert "第一止盈目标为入场价沿持仓方向推进 {atrTargetMultiplier} 倍 ATR" in APP_SOURCE
    assert "止损和 2:1 目标仍优先于出场缓冲触发。" not in APP_SOURCE


def test_range_fader_v11_partial_exit_contract_is_visible_without_frontend_indicator_math():
    assert 'middle_magnet_first_target: "中轴磁铁第一目标"' in APP_SOURCE
    assert 'opposite_range_edge_target: "对侧区间边缘目标"' in APP_SOURCE
    assert '"first_target_exit_fraction"' in APP_SOURCE
    assert "第一目标为区间中轴线，平仓比例为 {firstTargetExitFraction}" in APP_SOURCE
    assert "第二目标为对侧区间边缘；若保本止损先触发，则剩余仓位按 break-even 出场。" in APP_SOURCE
    assert '"opposite_reversal_body_strength"' not in APP_SOURCE
    assert "只有触达对侧轨且出现实体强度大于 {oppositeReversalBodyStrength} 的反向趋势 K" not in APP_SOURCE


def test_strategy_config_history_rollback_is_visible_in_config_modal_without_mutating_artifacts():
    assert "export interface StrategyConfigHistory" in TYPES_SOURCE
    assert "fetchStrategyHistory" in API_SOURCE
    assert "rollbackStrategyConfigHistory" in API_SOURCE
    assert "/api/strategies/${encodeURIComponent(strategyId)}/history" in API_SOURCE
    assert "/history/${encodeURIComponent(historyId)}/rollback" in API_SOURCE
    assert "const [strategyHistory, setStrategyHistory]" in APP_SOURCE
    assert "async function loadStrategyHistory" in APP_SOURCE
    assert "async function onRollbackStrategyHistory" in APP_SOURCE
    assert "策略版本记录" in APP_SOURCE
    assert "回退到此版本" in APP_SOURCE
    assert "历史 run、测试批次和优化候选保持原始证据" in APP_SOURCE
    assert "const rollbackAlreadyCurrent" in APP_SOURCE
    assert "item.previous_params_hash === selectedStrategy.params_hash" in APP_SOURCE
    assert "item.previous_template_version === selectedStrategy.template_version" in APP_SOURCE


def test_multi_ticker_scan_results_show_each_requested_symbol_once():
    assert "type StrategyScanRow" in APP_SOURCE
    assert "testBatch: StrategyTestBatch | null" in APP_SOURCE
    assert "const strategyScanRows = useMemo<StrategyScanRow[]>(() => {" in APP_SOURCE
    assert "return strategySymbols.map((symbol) => ({" in APP_SOURCE
    assert "testBatch: newestRecord(matchingBatches.filter((batch) => batch.symbol === symbol))" in APP_SOURCE
    assert "strategySymbols.some((symbol) => optimizationCoversSymbol(optimization, symbol))" in APP_SOURCE
    assert "optimization: newestRecord(optimizationPool.filter((optimization) => optimizationCoversSymbol(optimization, symbol)))" in APP_SOURCE
    assert "currentVersionOptimizations" in APP_SOURCE
    assert "optimizationPool" in APP_SOURCE
    assert "props.strategySymbols.length > 1" in APP_SOURCE
    assert "尚未运行30天测试；点击运行30天会为 {row.symbol} 保存独立 test batch。" in APP_SOURCE
    assert "props.scanTestBatches.length > 1" not in APP_SOURCE
    assert "props.testBatches.map((batch)" not in APP_SOURCE


def test_strategy_testing_shows_existing_archive_date_ranges_before_fetching():
    assert "type StrategyArchiveRangeSummary" in APP_SOURCE
    assert "function recentStrategyCalendarDates" in APP_SOURCE
    assert "function loadStrategyArchiveRanges" in APP_SOURCE
    assert 'fetchMinuteArchives(undefined, symbol, "yahoo")' in APP_SOURCE
    assert "summarizeStrategyArchiveRange(symbol, archiveLists[index] ?? [], expectedDates)" in APP_SOURCE
    assert "summarizeStrategyArchiveRange(symbol, archiveLists[index] ?? [])" not in APP_SOURCE
    assert "StrategyArchiveRangePrompt" in APP_SOURCE
    assert "已有标的数据日期范围" in APP_SOURCE
    assert "当前提示只统计截止日前最近30天（自然日）窗口" in APP_SOURCE
    assert "可用 ${formatInteger(range.availableCount)}${expectedText} 日" in APP_SOURCE
    assert "日缺失/不可用" in APP_SOURCE
    assert "function formatStrategyArchiveRange" in APP_SOURCE


def test_strategy_test_review_has_overview_grouping_and_day_drilldown():
    assert "type StrategyReviewMode = \"date\" | \"symbol\"" in APP_SOURCE
    assert "const strategyOverallMetrics = useMemo(() => aggregateBatchMetrics(strategyReviewBatches)" in APP_SOURCE
    assert "const strategyReviewDateRows = useMemo(() => strategyDateSummaries(strategyScanRows)" in APP_SOURCE
    assert "const strategyReviewSymbolRows = useMemo(() => strategySymbolSummaries(strategyScanRows)" in APP_SOURCE
    assert "function aggregateProfitFactor" in APP_SOURCE
    assert "function aggregateMaxDrawdownFromEntries" in APP_SOURCE
    assert "profitFactor: aggregateProfitFactor(" in APP_SOURCE
    assert "maxDrawdown: aggregateMaxDrawdownFromEntries(entries)" in APP_SOURCE
    assert "formatProfitFactorMetric(props.profitFactor, props.totalPnl, props.closedGroupCount)" in APP_SOURCE
    assert 'return "∞";' in APP_SOURCE
    assert "function hasStrategyOrders" in APP_SOURCE
    assert "const orderEntries = entries.filter(hasStrategyOrders)" in APP_SOURCE
    assert "const statusEntries = orderEntries.length > 0 ? orderEntries : entries" in APP_SOURCE
    assert "entries: orderEntries" in APP_SOURCE
    assert ".filter((row) => row.entries.length > 0)" in APP_SOURCE
    assert "策略整体指标总览" in APP_SOURCE
    assert "汇总当前标的组的最新 test batch；历史 artifact 不被改写。" in APP_SOURCE
    assert "function StrategyReviewExplorer" in APP_SOURCE
    assert "useState<StrategyReviewMode>(\"date\")" in APP_SOURCE
    assert "按日期" in APP_SOURCE
    assert "按标的" in APP_SOURCE
    assert "strategySummaryIdentity" in APP_SOURCE
    assert "StrategySummaryMiniMetrics" in APP_SOURCE
    assert "StrategyReviewEntryChips" in APP_SOURCE
    assert "props.onSelectStrategyTestDay(firstEntry.day, firstEntry.batch)" in APP_SOURCE
    assert "symbol={props.selectedStrategyTestBatch?.symbol ?? props.primaryStrategySymbol}" in APP_SOURCE
    assert "点击下方标的进入单日复盘" not in APP_SOURCE
    assert "当天没有策略订单标的。" in APP_SOURCE


def test_live_trading_tab_uses_backend_signal_preview_without_frontend_indicator_math():
    assert 'type WorkspaceTab = "review" | "strategy" | "ai_strategy" | "live";' in APP_SOURCE
    assert "实时交易" in APP_SOURCE
    assert "function LiveTradingWorkspace" in APP_SOURCE
    assert "LegacyLiveTradingWorkspace" not in APP_SOURCE
    assert "runLiveStrategySignal(" in APP_SOURCE
    assert "const [liveSignalResults, setLiveSignalResults]" in APP_SOURCE
    assert "const [liveMonitorActive, setLiveMonitorActive]" in APP_SOURCE
    assert "const [liveProvider, setLiveProvider] = useState<LiveProvider>(\"yahoo\")" in APP_SOURCE
    assert "window.setInterval(() =>" in APP_SOURCE
    assert "30000" in APP_SOURCE
    assert "multiple" in APP_SOURCE
    assert "开启监控" in APP_SOURCE
    assert "停止监控" in APP_SOURCE
    assert 'if (activeWorkspaceTab !== "live") return;' in APP_SOURCE
    assert "formatLiveOrderIntent(orderIntent)" in APP_SOURCE
    assert "reasonLabels[reason] ?? reason" in APP_SOURCE
    assert "只读下单信号预览：不自动下单，不修改 STP 成交事实" in APP_SOURCE
    assert "const liveOrderRows = props.results" in APP_SOURCE
    assert "result.signals.map((signal)" in APP_SOURCE
    assert "liveOrderRows.map(({ result, signal, orderIntent })" in APP_SOURCE
    assert "function liveOrderIntentForAction(action: StrategySignalAction)" in APP_SOURCE
    assert 'action === "ENTRY_LONG" || action === "EXIT_SHORT" ? "BUY" : "SELL"' in APP_SOURCE
    assert "function isLiveEntryOrderAction(action: StrategySignalAction)" in APP_SOURCE
    assert 'action === "ENTRY_LONG" || action === "ENTRY_SHORT"' in APP_SOURCE
    assert "function formatShareQuantity(value: number | null | undefined)" in APP_SOURCE
    assert "function formatLiveOrderOperationType(action: StrategySignalAction)" in APP_SOURCE
    assert 'action === "ENTRY_LONG" || action === "ENTRY_SHORT" ? "开仓" : "关仓"' in APP_SOURCE
    assert "Yahoo 实时" in APP_SOURCE
    assert "最新版本" in APP_SOURCE
    assert "latest_template_version" in APP_SOURCE
    assert "{strategy.name} · 最新 {strategy.latest_template_version" not in APP_SOURCE
    assert 'type LiveProvider = "futu" | "yahoo" | "fake";' in APP_SOURCE
    assert "export interface LiveStrategySignalResult" in TYPES_SOURCE
    assert "LiveStrategySignalStatus" in TYPES_SOURCE
    assert "latest_template_version: string;" in TYPES_SOURCE
    assert "position_quantity: number | null;" in TYPES_SOURCE
    assert "order_quantity: number | null;" in TYPES_SOURCE
    assert "latest_bar: MarketBar | null;" in TYPES_SOURCE
    assert '"fake" | "futu" | "yahoo" | string' in TYPES_SOURCE
    assert "runLiveStrategySignal" in API_SOURCE
    assert 'provider: "futu" | "yahoo" | "fake" = "yahoo"' in API_SOURCE
    assert "/api/strategies/${encodeURIComponent(strategyId)}/live-signal" in API_SOURCE
    assert ".liveTradingWorkspace" in STYLES_SOURCE


def test_ai_strategy_tab_is_read_only_and_uses_backend_recommendation_model():
    assert "AI策略" in APP_SOURCE
    assert 'activeWorkspaceTab === "ai_strategy"' in APP_SOURCE
    assert "<AiStrategyWorkspace" in APP_SOURCE
    assert "setSelectedStrategyId(strategyId)" in APP_SOURCE
    assert 'setActiveWorkspaceTab("strategy")' in APP_SOURCE
    assert "fetchAiStrategyRecommendations" in API_SOURCE
    assert "/api/ai-strategy-recommendations" in API_SOURCE
    assert 'marker.startsWith("ai-strategy-recommendation-") ? "ai_strategy" : "review"' in APP_SOURCE
    assert "export interface AiStrategyRecommendations" in TYPES_SOURCE
    assert "盈利期望 Top 5" in AI_STRATEGY_SOURCE
    assert "尚未通过本地归档验证" in AI_STRATEGY_SOURCE
    assert "本地回放是样本内历史结果，未计佣金与滑点，不代表未来盈利" in AI_STRATEGY_SOURCE
    assert "去策略测试" in AI_STRATEGY_SOURCE
    assert "runStrategyTestBatch" not in AI_STRATEGY_SOURCE
    assert "runStrategyReplay" not in AI_STRATEGY_SOURCE
    assert "updateStrategy" not in AI_STRATEGY_SOURCE
    assert "applyStrategyOptimizationCandidate" not in AI_STRATEGY_SOURCE
    assert "expected_pnl_per_closed_trade" in AI_STRATEGY_SOURCE
    assert "窗口总 PnL" in AI_STRATEGY_SOURCE
    assert "排除日期" in AI_STRATEGY_SOURCE
    assert "catalog_note" in AI_STRATEGY_SOURCE
    assert "recommended_param_items" in AI_STRATEGY_SOURCE
    assert 'const hasComparableEvidence = props.item.evidence_status === "backtested"' in AI_STRATEGY_SOURCE
    assert 'hasComparableEvidence ? formatCurrency(props.item.expectation.expected_pnl_per_closed_trade)' in AI_STRATEGY_SOURCE
    assert ".aiStrategyLayout" in STYLES_SOURCE
    assert "grid-template-columns: minmax(330px, 0.36fr) minmax(0, 0.64fr);" in STYLES_SOURCE


def test_live_signal_panel_only_shows_order_details():
    match = re.search(
        r"function LiveTradingWorkspace\(props: \{(?P<body>.*?)\nfunction StrategyTestingWorkspace",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    card_match = re.search(r'<article className="liveSignalCard liveSignalOrderCard".*?</article>', body, flags=re.DOTALL)
    assert card_match is not None
    signal_card = card_match.group(0)
    assert "liveOrderRows.map(({ result, signal, orderIntent })" in body
    assert "result.signals.map((signal)" in body
    assert 'className="compactFacts liveOrderFacts liveOrderOnlyFacts"' in signal_card
    assert "formatLiveOrderIntent(orderIntent)" in signal_card
    assert "<dt>操作类型</dt>" in signal_card
    assert "formatLiveOrderOperationType(signal.action)" in signal_card
    assert "formatNullable(signal?.price)" in signal_card
    assert "<dt>股数</dt>" in signal_card
    assert "formatShareQuantity(signal.order_quantity)" in signal_card
    assert "isLiveEntryOrderAction(signal.action) ? (" in signal_card
    assert "formatNullable(signal?.stop_loss_price)" in signal_card
    assert "formatNullable(signal?.take_profit_price)" in signal_card
    assert "!isLiveEntryOrderAction(signal.action) ? (" in signal_card
    assert "<dt>原因标签</dt>" in signal_card
    assert 'className="liveOrderReasonCodeList"' in signal_card
    assert "signal.reason_codes.map((reason)" in signal_card
    assert "reasonLabels[reason] ?? reason" in signal_card
    assert "formatDateTime(signal.timestamp)" in signal_card
    assert "formatStrategyAction(signal.action)" not in signal_card
    assert "策略动作" not in signal_card
    assert "liveSignalCardHeader" not in signal_card
    assert "liveSignalIntent" not in signal_card
    assert "statusPill" not in signal_card
    assert "formatLiveStatusDetail" not in signal_card
    assert "result.failure_reason" not in signal_card
    assert "result.strategy.latest_template_version" not in signal_card
    assert "result.strategy.template_version" not in signal_card
    assert "result.provider.toUpperCase()" not in signal_card
    assert "result.bar_count" not in signal_card
    assert "latestBar" not in signal_card
    assert "latest version" in body
    assert "config version" in body
    assert ".liveOrderFacts" in STYLES_SOURCE


def test_live_signal_refresh_does_not_rewrite_review_symbol():
    match = re.search(
        r"async function refreshLiveSignals\(\) \{(?P<body>.*?)\n  \}",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert "setLiveSignalResults(results)" in body
    assert "setLiveMonitorLastUpdated(new Date().toISOString())" in body
    assert "setSelectedSymbol(results[0].symbol)" not in body


def test_live_evidence_panel_shows_latest_quote_per_symbol():
    match = re.search(
        r"function LiveTradingWorkspace\(props: \{(?P<body>.*?)\nfunction StrategyTestingWorkspace",
        APP_SOURCE,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    card_match = re.search(r'<article className="liveEvidenceCard".*?</article>', body, flags=re.DOTALL)
    assert card_match is not None
    evidence_card = card_match.group(0)
    assert "const latestBar = result.latest_bar" in body
    assert 'className="liveLatestQuoteBlock"' in evidence_card
    assert 'aria-label={`${result.symbol} 最新行情`}' in evidence_card
    assert "formatDateTime(latestBar.timestamp)" in evidence_card
    assert "<dt>close</dt>" in evidence_card
    assert "formatNullable(latestBar.close)" in evidence_card
    assert "<dt>open</dt>" in evidence_card
    assert "formatNullable(latestBar.open)" in evidence_card
    assert "<dt>high</dt>" in evidence_card
    assert "formatNullable(latestBar.high)" in evidence_card
    assert "<dt>low</dt>" in evidence_card
    assert "formatNullable(latestBar.low)" in evidence_card
    assert "<dt>volume</dt>" in evidence_card
    assert "formatInteger(latestBar.volume)" in evidence_card
    assert "<dt>bars</dt>" in evidence_card
    assert "formatInteger(result.bar_count)" in evidence_card
    assert "暂无最新行情" in evidence_card
    assert ".liveLatestQuoteBlock" in STYLES_SOURCE
    assert ".liveLatestQuoteFacts" in STYLES_SOURCE
