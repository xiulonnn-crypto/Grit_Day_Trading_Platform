import type {
  DailySummary,
  FillRow,
  ImportBatch,
  MarketContextSnapshot,
  MarketMinuteArchive,
  QuarantineRow,
  ReviewSummary,
  ReviewSummaryGroup,
  StrategyConfig,
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
  if (pathname.includes("/api/strategy")) return "策略配置 API";
  if (pathname.includes("/api/market-data/yahoo-minute-archive")) return "Yahoo 分钟线归档 API";
  if (pathname.includes("/api/market-data/minute-archives")) return "分钟线 API";
  return "API";
}

function apiErrorMessage(response: Response): string {
  if (response.status === 404) {
    const pathname = responsePath(response);
    const routeCopy = pathname ? ` ${pathname} 路由` : "所需路由";
    return `${apiLabel(pathname)} 404：当前后端未加载${routeCopy}，通常是旧进程占用了端口。请重启本项目后端/前端进程；仍失败时运行 Login-Grit-DayTrading.cmd --check 检查旧进程。`;
  }
  return `API ${response.status}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(apiErrorMessage(response));
  }
  return (await response.json()) as T;
}

export async function uploadStpTxt(file: File): Promise<ImportBatch> {
  const body = new FormData();
  body.append("file", file);
  return readJson<ImportBatch>(await fetch("/api/imports/stp-txt", { method: "POST", body }));
}

export async function fetchBatches(): Promise<ImportBatch[]> {
  const payload = await readJson<{ items: ImportBatch[] }>(await fetch("/api/imports"));
  return payload.items;
}

export async function fetchQuarantine(batchId: string): Promise<QuarantineRow[]> {
  const payload = await readJson<{ items: QuarantineRow[] }>(await fetch(`/api/imports/${batchId}/quarantine`));
  return payload.items;
}

export async function fetchFills(date?: string, symbol?: string): Promise<FillRow[]> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  const query = params.size ? `?${params.toString()}` : "";
  const payload = await readJson<{ items: FillRow[] }>(await fetch(`/api/fills${query}`));
  return payload.items;
}

export async function fetchTradeGroups(date: string, symbol?: string): Promise<TradeGroup[]> {
  const params = new URLSearchParams({ date });
  if (symbol) params.set("symbol", symbol);
  const payload = await readJson<{ items: TradeGroup[] }>(await fetch(`/api/trade-groups?${params.toString()}`));
  return payload.items;
}

export async function fetchDailySummary(date: string): Promise<DailySummary> {
  return readJson<DailySummary>(await fetch(`/api/review/daily-summary?date=${encodeURIComponent(date)}`));
}

export async function fetchReviewSummary(date?: string, symbol?: string): Promise<ReviewSummary> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  if (symbol) params.set("symbol", symbol);
  const query = params.size ? `?${params.toString()}` : "";
  return readJson<ReviewSummary>(await fetch(`/api/review/summary${query}`));
}

export async function fetchReviewSummaryGroups(
  groupBy: "date" | "symbol",
  filters: { date?: string; symbol?: string } = {}
): Promise<ReviewSummaryGroup[]> {
  const params = new URLSearchParams({ group_by: groupBy });
  if (filters.date) params.set("date", filters.date);
  if (filters.symbol) params.set("symbol", filters.symbol);
  const payload = await readJson<{ items: ReviewSummaryGroup[] }>(await fetch(`/api/review/summary-groups?${params.toString()}`));
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
  return readJson<MarketContextSnapshot>(await fetch(`/api/fills/${encodeURIComponent(fillId)}/market-context`));
}

export async function fetchMinuteArchives(
  date: string,
  symbol?: string,
  provider = "yahoo"
): Promise<MarketMinuteArchive[]> {
  const params = new URLSearchParams({ date, provider });
  if (symbol) params.set("symbol", symbol);
  const response = await fetch(`/api/market-data/minute-archives?${params.toString()}`);
  const payload = await readJson<{ items: MarketMinuteArchive[] }>(response);
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

export async function fetchWatchlist(date: string): Promise<WatchlistRun> {
  return readJson<WatchlistRun>(await fetch(`/api/watchlist?date=${encodeURIComponent(date)}`));
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

export async function fetchStrategyTemplates(): Promise<StrategyTemplate[]> {
  const payload = await readJson<{ items: StrategyTemplate[] }>(await fetch("/api/strategy-templates"));
  return payload.items;
}

export async function fetchStrategies(): Promise<StrategyConfig[]> {
  const payload = await readJson<{ items: StrategyConfig[] }>(await fetch("/api/strategies"));
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

export async function fetchStrategyRuns(
  date: string,
  symbol?: string,
  strategyId?: string
): Promise<StrategySignalRun[]> {
  const params = new URLSearchParams({ date });
  if (symbol) params.set("symbol", symbol);
  if (strategyId) params.set("strategy_id", strategyId);
  const payload = await readJson<{ items: StrategySignalRun[] }>(await fetch(`/api/strategy-runs?${params.toString()}`));
  return payload.items;
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
  const payload = await readJson<{ items: StrategyTestBatch[] }>(await fetch(`/api/strategy-test-runs?${params.toString()}`));
  return payload.items;
}

export async function runStrategyOptimization(
  strategyId: string,
  endDate: string,
  symbol: string,
  force = false,
  windowTradingDays = 30
): Promise<StrategyOptimizationRun> {
  return readJson<StrategyOptimizationRun>(
    await fetch(`/api/strategies/${encodeURIComponent(strategyId)}/optimizations`, {
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

export async function fetchStrategyOptimizations(
  endDate: string,
  symbol?: string,
  strategyId?: string
): Promise<StrategyOptimizationRun[]> {
  const params = new URLSearchParams({ end_date: endDate });
  if (symbol) params.set("symbol", symbol);
  if (strategyId) params.set("strategy_id", strategyId);
  const payload = await readJson<{ items: StrategyOptimizationRun[] }>(
    await fetch(`/api/strategy-optimizations?${params.toString()}`)
  );
  return payload.items;
}

export async function fetchStrategyOptimizationDetail(optimizationId: string): Promise<StrategyOptimizationRun> {
  return readJson<StrategyOptimizationRun>(await fetch(`/api/strategy-optimizations/${encodeURIComponent(optimizationId)}`));
}

