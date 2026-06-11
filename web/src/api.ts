import type {
  DailySummary,
  FillRow,
  ImportBatch,
  LiveStrategySignalResult,
  MarketContextSnapshot,
  MarketMinuteArchive,
  QuarantineRow,
  TradeReview,
  ReviewSummary,
  ReviewSummaryGroup,
  StrategyConfig,
  StrategyConfigHistory,
  StrategyOptimizationRun,
  StrategySignalRun,
  StrategyTestBatch,
  StrategyTemplate,
  TradeGroup,
  WatchlistRun,
  YahooMinuteArchiveResult
} from "./types";

function responsePath(response: Response): string {
  try {
    return new URL(response.url).pathname;
  } catch {
    return "";
  }
}

function apiLabel(pathname: string): string {
  if (pathname.includes("/api/trade-groups/") && pathname.includes("/review")) return "亏损复盘保存";
  if (pathname.includes("/api/trade-groups")) return "交易组读取";
  if (pathname.includes("/api/imports/stp-txt")) return "STP TXT 上传";
  if (pathname.includes("/api/imports")) return "导入记录读取";
  if (pathname.includes("/api/review")) return "交易复盘读取";
  if (pathname.includes("/api/fills")) return "成交记录读取";
  if (pathname.includes("/api/market-context/replay")) return "行情上下文复盘";
  if (pathname.includes("/api/market-data/yahoo-minute-archive")) return "分钟线归档";
  if (pathname.includes("/api/market-data/minute-archives")) return "分钟线归档读取";
  if (pathname.includes("/api/watchlist")) return "Watchlist";
  if (pathname.includes("/api/strategy-templates")) return "策略模板读取";
  if (pathname.includes("/api/strategy-runs")) return "策略复盘读取";
  if (pathname.includes("/api/strategy-test-runs")) return "策略测试读取";
  if (pathname.includes("/api/strategy-optimizations")) return "策略优化读取";
  if (pathname.includes("/api/strategies/") && pathname.includes("/optimization-candidates/")) return "策略候选套用";
  if (pathname.includes("/api/strategies/") && pathname.includes("/history/")) return "策略版本回退";
  if (pathname.includes("/api/strategies/") && pathname.includes("/history")) return "策略版本记录";
  if (pathname.includes("/api/strategies/") && pathname.includes("/test-runs")) return "策略30天测试";
  if (pathname.includes("/api/strategies/") && pathname.includes("/optimizations")) return "策略参数优化";
  if (pathname.includes("/api/strategies/") && pathname.includes("/live-signal")) return "实时信号预览";
  if (pathname.includes("/api/strategies/") && pathname.includes("/runs")) return "策略单日复盘";
  if (pathname.includes("/api/strategies")) return "策略配置";
  return "请求";
}

const apiErrorDetailMessages: Record<string, string> = {
  batch_not_found: "没有找到这个导入批次，请刷新导入历史后重试。",
  fill_not_found: "没有找到这笔成交，请刷新成交记录后重试。",
  market_context_not_found: "没有找到这份行情上下文，请重新执行行情复盘。",
  trade_group_not_found: "没有找到这笔交易组，请刷新成交记录后重试。",
  trade_review_requires_closed_loss: "只有已平仓的亏损交易组可以保存亏损复盘。",
  trade_review_requires_loss: "只有已平仓的亏损交易组可以保存亏损复盘。",
  unsupported_trade_review_category: "请选择有效的亏损原因分类。",
  unsupported_trade_review_reason: "请选择有效的亏损原因。",
  archive_symbol_required: "请选择要归档的标的。",
  archive_end_date_required: "请选择归档截止日期。",
  archive_end_date_invalid: "归档截止日期格式不正确，请使用 YYYY-MM-DD。",
  archive_window_trading_days_out_of_range: "归档天数必须在 1 到 30 天之间。",
  strategy_not_found: "没有找到这个策略配置，请刷新策略列表后重试。",
  strategy_name_required: "请填写策略名称。",
  unsupported_strategy_template: "请选择有效的策略模板。",
  strategy_config_history_not_found: "没有找到这条策略版本记录，请刷新后重试。",
  strategy_config_history_missing_params_snapshot: "这条历史记录缺少参数快照，不能用于回退。",
  strategy_config_history_invalid_params_snapshot: "这条历史记录的参数快照不可读取，不能用于回退。",
  strategy_config_history_already_current: "当前策略已经是所选历史参数，不需要重复回退。",
  strategy_optimization_candidate_not_found: "没有找到这个优化候选，请刷新优化结果后重试。",
  strategy_optimization_candidate_not_eligible: "这个优化候选当前不可套用，请选择可套用候选。",
  strategy_signal_run_not_found: "没有找到这个策略 run，请刷新策略复盘记录后重试。",
  strategy_test_batch_not_found: "没有找到这个策略测试批次，请刷新测试记录后重试。",
  strategy_optimization_not_found: "没有找到这个优化 run，请刷新优化记录后重试。",
  strategy_symbol_required: "请输入至少一个策略研究标的。",
  strategy_symbol_out_of_range: "标的代码过长，请检查输入。",
  strategy_symbol_count_out_of_range: "一次最多支持 20 个标的。",
  strategy_end_date_invalid: "策略日期格式不正确，请使用 YYYY-MM-DD。",
  strategy_test_window_out_of_range: "测试窗口必须在 1 到 30 天之间。",
  unsupported_strategy_optimization_objective: "当前只支持默认优化目标。",
  strategy_optimization_candidate_cap_exceeded: "候选组合超过 120 个，请缩小参数范围后重试。",
  live_signal_lookback_out_of_range: "实时信号回看窗口必须在 30 到 390 分钟之间。",
  live_signal_symbol_required: "请输入实时信号标的。",
  unsupported_live_market_provider: "请选择有效的实时行情源。",
  missing_momentum_context: "缺少动能过滤所需的上下文归档，请先拉取 QQQ/SMH 分钟线。",
  strategy_param_out_of_range: "策略参数超出允许范围，请检查配置。",
  invalid_strategy_param: "策略参数格式不正确，请检查配置。",
  unsupported_strategy_optimization_param: "优化参数不受支持，请检查搜索空间。",
  empty_strategy_optimization_param: "优化参数不能为空，请检查搜索空间。",
  unsupported_strategy_optimization_param_type: "优化参数类型不支持，请检查搜索空间。"
};

const apiFieldLabels: Record<string, string> = {
  account: "账户",
  candidate_id: "优化候选",
  change_reason: "变更原因",
  date: "日期",
  end_date: "截止日期",
  file: "STP TXT 文件",
  force: "强制重跑选项",
  history_id: "策略版本记录",
  include_details: "详情读取选项",
  limit: "读取数量",
  lookback_minutes: "回看分钟数",
  name: "策略名称",
  note: "复盘备注",
  objective: "优化目标",
  params: "策略参数",
  provider: "行情源",
  reason_category: "亏损原因分类",
  reason_code: "亏损原因",
  search_space: "优化搜索空间",
  strategy_id: "策略",
  symbol: "标的",
  symbols: "标的组",
  trade_group_id: "交易组",
  window_trading_days: "归档天数"
};

type ValidationDetail = {
  type?: unknown;
  loc?: unknown;
  msg?: unknown;
};

async function readErrorPayload(response: Response): Promise<unknown> {
  try {
    return await response.clone().json();
  } catch {
    return null;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isValidationDetail(value: unknown): value is ValidationDetail {
  return isObject(value) && ("loc" in value || "msg" in value || "type" in value);
}

function apiFieldLabel(field: string | null): string {
  if (!field) return "输入内容";
  return apiFieldLabels[field] ?? field;
}

function errorCodeMessage(detail: string): string | null {
  const [code, suffix] = detail.split(":", 2);
  const message = apiErrorDetailMessages[detail] ?? apiErrorDetailMessages[code];
  if (!message) return null;
  if (!suffix) return message;
  return `${message}（${apiFieldLabel(suffix)}）`;
}

function readableDetailText(detail: string): string | null {
  const mapped = errorCodeMessage(detail);
  if (mapped) return mapped;
  if (/[\u4e00-\u9fff]/.test(detail)) return detail;
  return null;
}

function validationField(detail: ValidationDetail): string | null {
  if (!Array.isArray(detail.loc)) return null;
  const field = [...detail.loc]
    .reverse()
    .find((item) => typeof item === "string" && !["body", "query", "path"].includes(item));
  return typeof field === "string" ? field : null;
}

function validationDetailMessage(detail: ValidationDetail): string {
  const type = typeof detail.type === "string" ? detail.type : "";
  const msg = typeof detail.msg === "string" ? detail.msg : "";
  const field = validationField(detail);
  const label = apiFieldLabel(field);

  if (type === "json_invalid") return "请求内容格式不正确，请刷新页面后重试。";
  if (type.includes("missing")) return field ? `请填写${label}。` : "请补全必填信息。";
  if (type.includes("string_pattern")) {
    if (field === "date" || field === "end_date") return `${label}格式不正确，请使用 YYYY-MM-DD。`;
    return `${label}格式不正确，请检查输入。`;
  }
  if (type.includes("too_short")) return `${label}不能为空。`;
  if (type.includes("greater_than") || type.includes("less_than")) return `${label}超出允许范围，请检查输入。`;
  if (msg && /[\u4e00-\u9fff]/.test(msg)) return msg;
  return field ? `${label}校验未通过，请检查输入。` : "输入内容校验未通过，请检查后重试。";
}

function formatApiErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") return readableDetailText(detail);
  if (Array.isArray(detail)) {
    const messages = detail.filter(isValidationDetail).map(validationDetailMessage);
    return messages.length > 0 ? Array.from(new Set(messages)).join("；") : null;
  }
  if (isObject(detail)) {
    const nested = detail.detail ?? detail.message ?? detail.error;
    if (nested !== undefined) return formatApiErrorDetail(nested);
  }
  return null;
}

function apiPayloadMessage(payload: unknown): string | null {
  if (payload === null || payload === undefined) return null;
  if (isObject(payload)) {
    return formatApiErrorDetail(payload.detail ?? payload.message ?? payload.error);
  }
  return formatApiErrorDetail(payload);
}

async function apiErrorMessage(response: Response): Promise<string> {
  const pathname = responsePath(response);
  const label = apiLabel(pathname);
  const detailMessage = apiPayloadMessage(await readErrorPayload(response));

  if (response.status === 404) {
    if (detailMessage) return `${label}失败：${detailMessage}`;
    const routeCopy = pathname ? ` ${pathname} 路由` : "所需路由";
    return `${label}不可用：当前后端未加载${routeCopy}，通常是旧进程占用了端口。请重启本项目后端/前端进程；仍失败时运行 Login-Grit-DayTrading.cmd --check 检查旧进程。`;
  }
  if (response.status === 422) {
    return `${label}失败：${detailMessage ?? "请检查输入内容后重试。"}`;
  }
  if (response.status >= 500) {
    return `${label}暂时不可用：后端处理失败，请稍后重试；如果刚启动过本项目，请重新运行登录入口。`;
  }
  return `${label}失败：${detailMessage ?? "请检查网络或刷新页面后重试。"}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response));
  }
  return (await response.json()) as T;
}

const inFlightGetRequests = new Map<string, Promise<unknown>>();

type GetRequestOptions = {
  signal?: AbortSignal;
};

type TradeGroupRequestOptions = GetRequestOptions & {
  includeDetails?: boolean;
};

async function readGetJson<T>(path: string, options: GetRequestOptions = {}): Promise<T> {
  if (options.signal) {
    return readJson<T>(await fetch(path, { signal: options.signal }));
  }
  const existing = inFlightGetRequests.get(path) as Promise<T> | undefined;
  if (existing) return existing;
  const request = fetch(path).then((response) => readJson<T>(response));
  inFlightGetRequests.set(path, request);
  try {
    return await request;
  } finally {
    inFlightGetRequests.delete(path);
  }
}

export async function uploadStpTxt(file: File): Promise<ImportBatch> {
  const body = new FormData();
  body.append("file", file);
  return readJson<ImportBatch>(await fetch("/api/imports/stp-txt", { method: "POST", body }));
}

export async function fetchBatches(options: GetRequestOptions = {}): Promise<ImportBatch[]> {
  const payload = await readGetJson<{ items: ImportBatch[] }>("/api/imports", options);
  return payload.items;
}

export async function fetchQuarantine(batchId: string, options: GetRequestOptions = {}): Promise<QuarantineRow[]> {
  const payload = await readGetJson<{ items: QuarantineRow[] }>(`/api/imports/${batchId}/quarantine`, options);
  return payload.items;
}

export async function fetchFills(date?: string, symbol?: string, options: GetRequestOptions = {}): Promise<FillRow[]> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  const query = params.size ? `?${params.toString()}` : "";
  const payload = await readGetJson<{ items: FillRow[] }>(`/api/fills${query}`, options);
  return payload.items;
}

export async function fetchTradeGroups(
  date?: string,
  symbol?: string,
  options: TradeGroupRequestOptions = {}
): Promise<TradeGroup[]> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  params.set("include_details", options.includeDetails ? "true" : "false");
  const payload = await readGetJson<{ items: TradeGroup[] }>(`/api/trade-groups?${params.toString()}`, options);
  return payload.items;
}

export async function saveTradeGroupReview(
  tradeGroupId: string,
  payload: { reason_category: string; reason_code: string; note?: string }
): Promise<TradeReview> {
  return readJson<TradeReview>(
    await fetch(`/api/trade-groups/${encodeURIComponent(tradeGroupId)}/review`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
  );
}

export async function fetchDailySummary(date: string, options: GetRequestOptions = {}): Promise<DailySummary> {
  return readGetJson<DailySummary>(`/api/review/daily-summary?date=${encodeURIComponent(date)}`, options);
}

export async function fetchReviewSummary(date?: string, symbol?: string, options: GetRequestOptions = {}): Promise<ReviewSummary> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  const query = params.size ? `?${params.toString()}` : "";
  return readGetJson<ReviewSummary>(`/api/review/summary${query}`, options);
}

export async function fetchReviewSummaryGroups(
  groupBy: "date" | "symbol",
  filters: { date?: string; symbol?: string } = {},
  options: GetRequestOptions = {}
): Promise<ReviewSummaryGroup[]> {
  const params = new URLSearchParams({ group_by: groupBy });
  if (filters.date) params.set("date", filters.date);
  if (filters.symbol) params.set("symbol", filters.symbol);
  const payload = await readGetJson<{ items: ReviewSummaryGroup[] }>(`/api/review/summary-groups?${params.toString()}`, options);
  return payload.items;
}

export async function replayMarketContext(fillId: string, force = false): Promise<MarketContextSnapshot> {
  return readJson<MarketContextSnapshot>(
    await fetch("/api/market-context/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fill_id: fillId,
        provider: "fake",
        minutes_before: 30,
        minutes_after: 30,
        force
      })
    })
  );
}

export async function fetchMarketContext(fillId: string): Promise<MarketContextSnapshot> {
  return readGetJson<MarketContextSnapshot>(`/api/fills/${encodeURIComponent(fillId)}/market-context`);
}

export async function fetchMinuteArchives(
  date?: string | null,
  symbol?: string,
  provider = "yahoo"
): Promise<MarketMinuteArchive[]> {
  const params = new URLSearchParams({ provider });
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  const payload = await readGetJson<{ items: MarketMinuteArchive[] }>(`/api/market-data/minute-archives?${params.toString()}`);
  return payload.items;
}

export async function archiveYahooMinuteData(
  date: string,
  force = false,
  symbol?: string,
  windowTradingDays?: number
): Promise<YahooMinuteArchiveResult> {
  const body: { date: string; force: boolean; symbol?: string; window_trading_days?: number } = { date, force };
  if (symbol) body.symbol = symbol;
  if (windowTradingDays) body.window_trading_days = windowTradingDays;
  const response = await fetch("/api/market-data/yahoo-minute-archive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return readJson<YahooMinuteArchiveResult>(
    response
  );
}

export async function fetchWatchlist(date: string, options: GetRequestOptions = {}): Promise<WatchlistRun> {
  return readGetJson<WatchlistRun>(`/api/watchlist?date=${encodeURIComponent(date)}`, options);
}

export async function generateWatchlist(date: string, force = false): Promise<WatchlistRun> {
  return readJson<WatchlistRun>(
    await fetch("/api/watchlist/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, provider: "fake", force })
    })
  );
}

export async function fetchStrategyTemplates(options: GetRequestOptions = {}): Promise<StrategyTemplate[]> {
  const payload = await readGetJson<{ items: StrategyTemplate[] }>("/api/strategy-templates", options);
  return payload.items;
}

export async function fetchStrategies(options: GetRequestOptions = {}): Promise<StrategyConfig[]> {
  const payload = await readGetJson<{ items: StrategyConfig[] }>("/api/strategies", options);
  return payload.items;
}

export async function createStrategy(
  name: string,
  templateKey: StrategyTemplate["template_key"],
  params: Record<string, number | string>
): Promise<StrategyConfig> {
  return readJson<StrategyConfig>(
    await fetch("/api/strategies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, template_key: templateKey, params })
    })
  );
}

export async function updateStrategy(
  strategyId: string,
  payload: { name?: string; enabled?: boolean; params?: Record<string, number | string> }
): Promise<StrategyConfig> {
  return readJson<StrategyConfig>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
  );
}

export async function fetchStrategyHistory(
  strategyId: string,
  options: GetRequestOptions = {}
): Promise<StrategyConfigHistory[]> {
  const payload = await readGetJson<{ items: StrategyConfigHistory[] }>(
    `/api/strategies/${encodeURIComponent(strategyId)}/history`,
    options
  );
  return payload.items;
}

export async function rollbackStrategyConfigHistory(
  strategyId: string,
  historyId: string,
  changeReason = "history_rollback"
): Promise<StrategyConfig> {
  return readJson<StrategyConfig>(
    await fetch(
      `/api/strategies/${encodeURIComponent(strategyId)}/history/${encodeURIComponent(historyId)}/rollback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ change_reason: changeReason })
      }
    )
  );
}

export async function applyStrategyOptimizationCandidate(
  strategyId: string,
  candidateId: string,
  changeReason = "optimization_candidate_apply"
): Promise<StrategyConfig> {
  return readJson<StrategyConfig>(
    await fetch(
      `/api/strategies/${encodeURIComponent(strategyId)}/optimization-candidates/${encodeURIComponent(candidateId)}/apply`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ change_reason: changeReason })
      }
    )
  );
}

export async function runStrategyReplay(
  strategyId: string,
  date: string,
  symbol: string,
  force = false
): Promise<StrategySignalRun> {
  return readJson<StrategySignalRun>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, symbol, provider: "yahoo", force })
    })
  );
}

export async function runLiveStrategySignal(
  strategyId: string,
  symbol: string,
  provider: "futu" | "yahoo" | "fake" = "yahoo",
  lookbackMinutes = 180
): Promise<LiveStrategySignalResult> {
  return readJson<LiveStrategySignalResult>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}/live-signal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        provider,
        lookback_minutes: lookbackMinutes
      })
    })
  );
}

export async function fetchStrategyRuns(
  date: string,
  symbol?: string,
  strategyId?: string,
  options: { includeDetails?: boolean; limit?: number } = {}
): Promise<StrategySignalRun[]> {
  const params = new URLSearchParams({ date });
  if (symbol) params.set("symbol", symbol);
  if (strategyId) params.set("strategy_id", strategyId);
  if (options.includeDetails) params.set("include_details", "true");
  if (options.limit) params.set("limit", String(options.limit));
  const payload = await readGetJson<{ items: StrategySignalRun[] }>(`/api/strategy-runs?${params.toString()}`);
  return payload.items;
}

export async function fetchStrategyRunDetail(runId: string): Promise<StrategySignalRun> {
  return readGetJson<StrategySignalRun>(`/api/strategy-runs/${encodeURIComponent(runId)}`);
}

export async function runStrategyTestBatch(
  strategyId: string,
  endDate: string,
  symbol: string,
  force = false,
  windowTradingDays = 30
): Promise<StrategyTestBatch> {
  return readJson<StrategyTestBatch>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}/test-runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        end_date: endDate,
        symbol,
        provider: "yahoo",
        window_trading_days: windowTradingDays,
        force
      })
    })
  );
}

export async function fetchStrategyTestBatches(
  endDate: string,
  symbol?: string,
  strategyId?: string
): Promise<StrategyTestBatch[]> {
  const params = new URLSearchParams({ end_date: endDate });
  if (symbol) params.set("symbol", symbol);
  if (strategyId) params.set("strategy_id", strategyId);
  const payload = await readGetJson<{ items: StrategyTestBatch[] }>(`/api/strategy-test-runs?${params.toString()}`);
  return payload.items;
}

export async function runStrategyOptimization(
  strategyId: string,
  endDate: string,
  symbols: string | string[],
  force = false,
  windowTradingDays = 30
): Promise<StrategyOptimizationRun> {
  const targetSymbols = (Array.isArray(symbols) ? symbols : [symbols]).map((item) => item.trim().toUpperCase()).filter(Boolean);
  const primarySymbol = targetSymbols[0] ?? "";
  return readJson<StrategyOptimizationRun>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}/optimizations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        end_date: endDate,
        symbol: primarySymbol,
        symbols: targetSymbols,
        provider: "yahoo",
        window_trading_days: windowTradingDays,
        force
      })
    })
  );
}

export async function fetchStrategyOptimizations(
  endDate: string,
  symbol?: string,
  strategyId?: string
): Promise<StrategyOptimizationRun[]> {
  const params = new URLSearchParams({ end_date: endDate });
  if (symbol) params.set("symbol", symbol);
  if (strategyId) params.set("strategy_id", strategyId);
  const payload = await readGetJson<{ items: StrategyOptimizationRun[] }>(`/api/strategy-optimizations?${params.toString()}`);
  return payload.items;
}

export async function fetchStrategyOptimizationDetail(optimizationId: string): Promise<StrategyOptimizationRun> {
  return readGetJson<StrategyOptimizationRun>(`/api/strategy-optimizations/${encodeURIComponent(optimizationId)}`);
}

