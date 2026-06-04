import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronDown,
  CheckCircle2,
  CircleSlash,
  Clock3,
  FileText,
  FileUp,
  Hash,
  ListChecks,
  Pencil,
  Play,
  Plus,
  Power,
  RefreshCw,
  Save,
  SlidersHorizontal,
  TableProperties,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode, type SyntheticEvent } from "react";

import {
  archiveYahooMinuteData,
  createStrategy,
  fetchBatches,
  fetchDailySummary,
  fetchFills,
  fetchMinuteArchives,
  fetchQuarantine,
  fetchReviewSummary,
  fetchReviewSummaryGroups,
  fetchStrategies,
  fetchStrategyOptimizationDetail,
  fetchStrategyOptimizations,
  fetchStrategyRuns,
  fetchStrategyTestBatches,
  fetchStrategyTemplates,
  fetchTradeGroups,
  fetchWatchlist,
  generateWatchlist,
  runStrategyOptimization,
  runStrategyReplay,
  runStrategyTestBatch,
  updateStrategy,
  uploadStpTxt
} from "./api";
import type {
  DailySummary,
  FillRow,
  ImportBatch,
  MarketDataStatus,
  MarketMinuteArchive,
  QuarantineRow,
  ReviewSummary,
  ReviewSummaryGroup,
  StrategyConfig,
  StrategyOptimizationCandidate,
  StrategyOptimizationRun,
  StrategyOptimizationStatus,
  StrategyRunStatus,
  StrategySignal,
  StrategySignalAction,
  StrategySignalPerformance,
  StrategySignalRun,
  StrategyTestBatch,
  StrategyTestBatchStatus,
  StrategyTestDayResult,
  StrategyTemplate,
  TradeGroup,
  TradeGroupFill,
  WatchlistRun,
  WatchlistRunStatus
} from "./types";
import { getDefaultReviewDate } from "./tradingDate";
import "./styles.css";

const statusMeta: Record<
  ImportBatch["status"],
  { label: string; detail: string; tone: "info" | "ok" | "warn" | "danger" }
> = {
  uploaded: { label: "已上传", detail: "等待解析", tone: "info" },
  parsing: { label: "解析中", detail: "正在建立证据链", tone: "warn" },
  committed: { label: "已提交", detail: "可用于复盘 KPI", tone: "ok" },
  failed: { label: "导入失败", detail: "需要复查失败原因", tone: "danger" },
  retry_requested: { label: "待重试", detail: "等待重新导入", tone: "warn" }
};

const sourceLabel: Record<DailySummary["source"], string> = {
  committed_fills_only: "仅来自 committed fills"
};

const marketStatusMeta: Record<MarketDataStatus, { label: string; tone: "ok" | "warn" | "danger" }> = {
  available: { label: "数据可用", tone: "ok" },
  partial: { label: "部分数据", tone: "warn" },
  missing: { label: "缺数据", tone: "warn" },
  provider_failed: { label: "行情获取失败", tone: "danger" },
  timezone_conflict: { label: "时区冲突", tone: "danger" }
};

const watchlistStatusMeta: Record<WatchlistRunStatus, { label: string; tone: "info" | "ok" | "danger" }> = {
  not_generated: { label: "未生成", tone: "info" },
  completed: { label: "已生成", tone: "ok" },
  failed: { label: "生成失败", tone: "danger" }
};

const strategyStatusMeta: Record<StrategyRunStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "已完成", tone: "ok" },
  missing_archive: { label: "待归档", tone: "warn" },
  non_available_archive: { label: "行情不可用", tone: "danger" },
  insufficient_bars: { label: "分钟线不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "运行失败", tone: "danger" }
};

const strategyTestStatusMeta: Record<StrategyTestBatchStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "测试完成", tone: "ok" },
  insufficient_archive_coverage: { label: "30日覆盖不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "测试失败", tone: "danger" }
};

const strategyOptimizationStatusMeta: Record<StrategyOptimizationStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "优化完成", tone: "ok" },
  insufficient_archive_coverage: { label: "30日覆盖不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "优化失败", tone: "danger" }
};

const strategyCandidateStatusMeta: Record<
  StrategyOptimizationCandidate["status"],
  { label: string; tone: "info" | "ok" | "warn" | "danger" }
> = {
  eligible: { label: "可候选", tone: "ok" },
  no_signals: { label: "无闭合信号", tone: "warn" },
  failed: { label: "候选失败", tone: "danger" },
  insufficient_archive_coverage: { label: "覆盖不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" }
};

const reasonLabels: Record<string, string> = {
  relative_volume_spike: "量能放大",
  gap_up: "向上缺口",
  gap_down: "向下缺口",
  momentum: "动量",
  squeeze_setup: "波动收缩",
  vwap_above: "VWAP 上方",
  vwap_below: "VWAP 下方",
  absolute_bandwidth_filter: "绝对带宽达标",
  upper_band_breakout: "突破上轨",
  lower_band_breakout: "跌破下轨",
  volume_spike: "成交量放大",
  rsi_momentum: "RSI 动能",
  passive_take_profit_order: "被动止盈目标",
  passive_take_profit_filled: "被动止盈成交",
  risk_reward_target: "2:1 达标",
  stop_loss_hit: "止损触发",
  exit_ema_breached: "触发出场 EMA",
  middle_band_breached: "触发布林中轨",
  exit_buffer_breached: "出场缓冲失守",
  close_back_inside_upper_band: "回到上轨内",
  close_back_inside_lower_band: "回到下轨内",
  liquidity_sweep_setup: "流动性扫损",
  local_low_swept: "扫破局部低点",
  local_high_swept: "扫破局部高点",
  pin_bar_reclaim: "长下影收回",
  pin_bar_reject: "长上影拒绝",
  bullish_engulfing: "阳线吞没",
  bearish_engulfing: "阴线吞没",
  oco_immediate_mode: "OCO 即时模式",
  middle_band_target: "布林中轨目标",
  max_holding_bars_elapsed: "最长持仓到期",
  time_window_1100_1430: "11:00-14:30 ET",
  time_window_1130_1330: "11:30-13:30 ET",
  regime_chop_adx: "ADX 震荡过滤通过",
  atr_dynamic_stop: "ATR 动态止损",
  momentum_filter_long: "QQQ/SMH 多头过滤",
  momentum_filter_short: "QQQ/SMH 空头过滤",
  lower_band_observation: "跌破下轨观察",
  upper_band_observation: "冲破上轨观察",
  reversal_reclaim_lower_band: "重回下轨上方",
  reversal_reject_upper_band: "跌回上轨下方",
  partial_take_profit_plan: "中轨部分止盈计划",
  break_even_after_middle_target: "中轨后保本止损",
  middle_band_first_target: "中轨第一目标",
  partial_take_profit_filled: "部分止盈成交",
  break_even_stop_armed: "保本止损已上移",
  upper_band_final_target: "上轨最终目标",
  lower_band_final_target: "下轨最终目标",
  remaining_take_profit_filled: "剩余仓位止盈",
  break_even_stop_hit: "保本止损触发",
  mean_reversion_failed: "均值回归失败"
};

const strategyParamGroups = [
  {
    key: "entry",
    title: "开仓",
    detail: "突破前置、趋势过滤和动能过滤",
    paramKeys: [
      "local_window",
      "shadow_ratio",
      "bb_period",
      "bb_stddev",
      "adx_period",
      "adx_trend_threshold",
      "adx_chop_threshold",
      "rsi_period",
      "volume_average_period",
      "volume_multiplier",
      "squeeze_percentile",
      "setup_minutes",
      "body_strength_ratio",
      "min_absolute_bandwidth",
      "start_hour",
      "start_minute",
      "end_hour",
      "end_minute",
      "pin_shadow_ratio",
      "swing_lookback",
      "momentum_context"
    ]
  },
  {
    key: "exit",
    title: "平仓",
    detail: "持仓管理和出场缓冲",
    paramKeys: ["exit_ema_period", "max_holding_bars", "exit_type"]
  },
  {
    key: "risk",
    title: "止盈止损",
    detail: "风险空间、止损和被动止盈目标",
    paramKeys: ["risk_reward", "tick_size", "stop_tick_offset", "atr_period", "atr_stop_multiplier", "first_target_exit_fraction"]
  }
];

const integerFormatter = new Intl.NumberFormat("en-US");
const decimalFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2
});

type StrategyParamValue = number | string;
type StrategyConfigMode = "edit" | "create";
type WorkspaceTab = "review" | "strategy";
type ReviewDrillTab = "date" | "symbol";
type StrategyFeedbackTone = "info" | "ok" | "warn" | "danger";
type StrategyRunFeedback = {
  tone: StrategyFeedbackTone;
  title: string;
  detail: string;
};
type StrategyTestDayDetailCacheEntry = {
  archive: MarketMinuteArchive | null;
  error: string | null;
  run: StrategySignalRun | null;
  status: "loading" | "ready" | "failed";
};

function strategyTestDayDetailKey(batchId: string | null | undefined, dayResultId: string) {
  return `${batchId ?? "unbatched"}:${dayResultId}`;
}

export default function App() {
  const [date, setDate] = useState(() => getDefaultReviewDate());
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [fills, setFills] = useState<FillRow[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [overallSummary, setOverallSummary] = useState<ReviewSummary | null>(null);
  const [dateSummaryGroups, setDateSummaryGroups] = useState<ReviewSummaryGroup[]>([]);
  const [symbolSummaryGroups, setSymbolSummaryGroups] = useState<ReviewSummaryGroup[]>([]);
  const [dateSymbolBreakdown, setDateSymbolBreakdown] = useState<ReviewSummaryGroup[]>([]);
  const [dateSymbolBreakdownDate, setDateSymbolBreakdownDate] = useState<string | null>(null);
  const [symbolDateBreakdown, setSymbolDateBreakdown] = useState<ReviewSummaryGroup[]>([]);
  const [tradeGroups, setTradeGroups] = useState<TradeGroup[]>([]);
  const [quarantine, setQuarantine] = useState<QuarantineRow[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistRun | null>(null);
  const [strategyTemplates, setStrategyTemplates] = useState<StrategyTemplate[]>([]);
  const [strategies, setStrategies] = useState<StrategyConfig[]>([]);
  const [strategyRuns, setStrategyRuns] = useState<StrategySignalRun[]>([]);
  const [strategyTestBatches, setStrategyTestBatches] = useState<StrategyTestBatch[]>([]);
  const [strategyOptimizations, setStrategyOptimizations] = useState<StrategyOptimizationRun[]>([]);
  const [selectedOptimization, setSelectedOptimization] = useState<StrategyOptimizationRun | null>(null);
  const [selectedStrategyTestDayId, setSelectedStrategyTestDayId] = useState<string | null>(null);
  const [strategyTestDayDetailCache, setStrategyTestDayDetailCache] = useState<Record<string, StrategyTestDayDetailCacheEntry>>({});
  const [strategyTestDayRun, setStrategyTestDayRun] = useState<StrategySignalRun | null>(null);
  const [strategyTestDayArchive, setStrategyTestDayArchive] = useState<MarketMinuteArchive | null>(null);
  const [strategyTestDayDetailBusy, setStrategyTestDayDetailBusy] = useState(false);
  const [minuteArchives, setMinuteArchives] = useState<MarketMinuteArchive[]>([]);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>("review");
  const [activeReviewDrillTab, setActiveReviewDrillTab] = useState<ReviewDrillTab>("date");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const [strategyNameDraft, setStrategyNameDraft] = useState("");
  const [strategyParamsDraft, setStrategyParamsDraft] = useState<Record<string, StrategyParamValue>>({});
  const [newStrategyName, setNewStrategyName] = useState("");
  const [newStrategyTemplateKey, setNewStrategyTemplateKey] = useState<StrategyTemplate["template_key"] | "">("");
  const [newStrategyParamsDraft, setNewStrategyParamsDraft] = useState<Record<string, StrategyParamValue>>({});
  const [strategyMode, setStrategyMode] = useState<StrategyConfigMode>("edit");
  const [selectedReplayGroup, setSelectedReplayGroup] = useState<TradeGroup | null>(null);
  const [selectedBatch, setSelectedBatch] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [replayBusy, setReplayBusy] = useState<string | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [strategyBusy, setStrategyBusy] = useState(false);
  const [strategyTestBusy, setStrategyTestBusy] = useState(false);
  const [strategyOptimizationBusy, setStrategyOptimizationBusy] = useState(false);
  const [strategySaveBusy, setStrategySaveBusy] = useState(false);
  const [strategyCreateBusy, setStrategyCreateBusy] = useState(false);
  const [strategyRunFeedback, setStrategyRunFeedback] = useState<StrategyRunFeedback | null>(null);
  const [strategyArchiveFeedback, setStrategyArchiveFeedback] = useState<StrategyRunFeedback | null>(null);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const [showTradeMarkers, setShowTradeMarkers] = useState(true);
  const [showFullDayStrategyBars, setShowFullDayStrategyBars] = useState(false);
  const [strategyConfigOpen, setStrategyConfigOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewModuleRef = useRef<HTMLElement | null>(null);
  const refreshRequestIdRef = useRef(0);
  const strategyTestDayPrefetchingRef = useRef<Set<string>>(new Set());

  const symbolOptions = useMemo(
    () =>
      Array.from(
        new Set([
          ...fills.map((fill) => fill.symbol),
          ...minuteArchives.map((archive) => archive.symbol),
          ...symbolSummaryGroups.map((group) => group.group_key)
        ])
      ).sort((left, right) => left.localeCompare(right)),
    [fills, minuteArchives, symbolSummaryGroups]
  );
  const displayedFills = useMemo(
    () => (selectedSymbol ? fills.filter((fill) => fill.symbol === selectedSymbol) : fills),
    [fills, selectedSymbol]
  );
  const displayedTradeGroups = useMemo(
    () => (selectedSymbol ? tradeGroups.filter((group) => group.symbol === selectedSymbol) : tradeGroups),
    [selectedSymbol, tradeGroups]
  );
  const selectedArchive = useMemo(
    () =>
      minuteArchives.find((archive) => archive.symbol === selectedSymbol && archive.trade_date === date) ??
      minuteArchives[0] ??
      null,
    [date, minuteArchives, selectedSymbol]
  );
  const selectedReplayArchive = useMemo(
    () =>
      selectedReplayGroup
        ? minuteArchives.find(
            (archive) => archive.symbol === selectedReplayGroup.symbol && archive.trade_date === selectedReplayGroup.opened_at.slice(0, 10)
          ) ?? null
        : null,
    [minuteArchives, selectedReplayGroup]
  );
  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.strategy_id === selectedStrategyId) ?? strategies[0] ?? null,
    [selectedStrategyId, strategies]
  );
  const selectedStrategyTemplate = useMemo(
    () =>
      strategyTemplates.find((template) => template.template_key === selectedStrategy?.template_key) ??
      strategyTemplates[0] ??
      null,
    [selectedStrategy, strategyTemplates]
  );
  const createStrategyTemplate = useMemo(
    () =>
      strategyTemplates.find((template) => template.template_key === newStrategyTemplateKey) ??
      strategyTemplates[0] ??
      null,
    [newStrategyTemplateKey, strategyTemplates]
  );
  const latestStrategyRun = useMemo(() => strategyRuns[0] ?? null, [strategyRuns]);
  const latestStrategyTestBatch = useMemo(() => strategyTestBatches[0] ?? null, [strategyTestBatches]);
  const selectedStrategyTestDay = useMemo(
    () =>
      latestStrategyTestBatch?.day_results.find((day) => day.day_result_id === selectedStrategyTestDayId) ??
      latestStrategyTestBatch?.day_results.find((day) => day.strategy_run_id) ??
      latestStrategyTestBatch?.day_results[0] ??
      null,
    [latestStrategyTestBatch, selectedStrategyTestDayId]
  );
  const selectedStrategyTestDayDetail = useMemo(() => {
    if (!latestStrategyTestBatch || !selectedStrategyTestDay) return null;
    return strategyTestDayDetailCache[
      strategyTestDayDetailKey(latestStrategyTestBatch.batch_id, selectedStrategyTestDay.day_result_id)
    ] ?? null;
  }, [latestStrategyTestBatch, selectedStrategyTestDay, strategyTestDayDetailCache]);
  const latestOptimization = selectedOptimization ?? strategyOptimizations[0] ?? null;
  const strategyDraftDirty = useMemo(() => {
    if (!selectedStrategy || strategyMode !== "edit") return false;
    return (
      strategyNameDraft.trim() !== selectedStrategy.name ||
      strategyParamsSignature(strategyParamsDraft) !== strategyParamsSignature(selectedStrategy.params)
    );
  }, [selectedStrategy, strategyMode, strategyNameDraft, strategyParamsDraft]);

  async function refresh(nextBatchId = selectedBatch) {
    const requestId = refreshRequestIdRef.current + 1;
    refreshRequestIdRef.current = requestId;
    const refreshDate = date;
    const refreshSymbol = selectedSymbol;
    setLoading(true);
    setError(null);
    try {
      const [
        nextBatches,
        nextFills,
        nextTradeGroups,
        nextSummary,
        nextOverallSummary,
        nextDateGroups,
        nextSymbolGroups,
        nextDateSymbolBreakdown,
        nextSymbolDateBreakdown,
        nextWatchlist,
        nextTemplates,
        nextStrategies
      ] =
        await Promise.all([
          fetchBatches(),
          fetchFills(refreshDate),
          fetchTradeGroups(refreshDate),
          fetchDailySummary(refreshDate),
          fetchReviewSummary(),
          fetchReviewSummaryGroups("date"),
          fetchReviewSummaryGroups("symbol"),
          fetchReviewSummaryGroups("symbol", { date: refreshDate }),
          refreshSymbol ? fetchReviewSummaryGroups("date", { symbol: refreshSymbol }) : Promise.resolve([]),
          fetchWatchlist(refreshDate),
          fetchStrategyTemplates(),
          fetchStrategies()
        ]);
      const requestedBatch = nextBatchId
        ? nextBatches.find((batch) => batch.batch_id === nextBatchId)?.batch_id ?? null
        : null;
      const batchToLoad = requestedBatch ?? nextBatches[0]?.batch_id ?? null;
      const nextQuarantine = batchToLoad ? await fetchQuarantine(batchToLoad) : [];
      if (requestId !== refreshRequestIdRef.current) return;
      setBatches(nextBatches);
      setFills(nextFills);
      setTradeGroups(nextTradeGroups);
      setSummary(nextSummary);
      setOverallSummary(nextOverallSummary);
      setDateSummaryGroups(nextDateGroups);
      setSymbolSummaryGroups(nextSymbolGroups);
      setDateSymbolBreakdown(nextDateSymbolBreakdown);
      setDateSymbolBreakdownDate(refreshDate);
      setSymbolDateBreakdown(nextSymbolDateBreakdown);
      setWatchlist(nextWatchlist);
      setStrategyTemplates(nextTemplates);
      setStrategies(nextStrategies);
      setSelectedBatch(batchToLoad);
      setQuarantine(nextQuarantine);
    } catch (err: unknown) {
      if (requestId === refreshRequestIdRef.current) {
        setError(err instanceof Error ? err.message : "数据加载失败");
      }
    } finally {
      if (requestId === refreshRequestIdRef.current) {
        setLoading(false);
      }
    }
  }

  async function loadMinuteArchives(symbol = selectedSymbol) {
    if (!symbol) {
      setMinuteArchives([]);
      return;
    }
    try {
      setMinuteArchives(await fetchMinuteArchives(date, symbol, "yahoo"));
    } catch (err) {
      setMinuteArchives([]);
      setError(err instanceof Error ? err.message : "分钟线归档读取失败");
    }
  }

  async function loadSymbolDateBreakdown(symbol = selectedSymbol) {
    if (!symbol) {
      setSymbolDateBreakdown([]);
      return;
    }
    try {
      setSymbolDateBreakdown(await fetchReviewSummaryGroups("date", { symbol }));
    } catch (err) {
      setSymbolDateBreakdown([]);
      setError(err instanceof Error ? err.message : "标的交易日汇总读取失败");
    }
  }

  async function loadStrategyRuns(strategyId = selectedStrategyId, symbol = selectedSymbol) {
    if (!strategyId || !symbol) {
      setStrategyRuns([]);
      return;
    }
    try {
      setStrategyRuns(await fetchStrategyRuns(date, symbol, strategyId));
    } catch (err) {
      setStrategyRuns([]);
      setError(err instanceof Error ? err.message : "策略运行记录读取失败");
    }
  }

  async function loadStrategyResearch(strategyId = selectedStrategyId, symbol = selectedSymbol) {
    if (!strategyId || !symbol) {
      setStrategyTestBatches([]);
      setStrategyOptimizations([]);
      setSelectedOptimization(null);
      setSelectedStrategyTestDayId(null);
      setStrategyTestDayDetailCache({});
      setStrategyTestDayRun(null);
      setStrategyTestDayArchive(null);
      return;
    }
    try {
      const [testBatches, optimizations] = await Promise.all([
        fetchStrategyTestBatches(date, symbol, strategyId),
        fetchStrategyOptimizations(date, symbol, strategyId)
      ]);
      setStrategyTestBatches(testBatches);
      setStrategyOptimizations(optimizations);
      if (optimizations[0]) {
        setSelectedOptimization(await fetchStrategyOptimizationDetail(optimizations[0].optimization_id));
      } else {
        setSelectedOptimization(null);
      }
    } catch (err) {
      setStrategyTestBatches([]);
      setStrategyOptimizations([]);
      setSelectedOptimization(null);
      setStrategyTestDayDetailCache({});
      setError(err instanceof Error ? err.message : "策略研究记录读取失败");
    }
  }

  async function loadStrategyTestDayDetail(
    day: StrategyTestDayResult | null,
    strategyId = selectedStrategyId,
    symbol = selectedSymbol,
    options: { batchId?: string | null; prefetch?: boolean } = {}
  ) {
    if (!day || !strategyId || !symbol) {
      if (!options.prefetch) {
        setSelectedStrategyTestDayId(day?.day_result_id ?? null);
        setStrategyTestDayRun(null);
        setStrategyTestDayArchive(null);
        setStrategyTestDayDetailBusy(false);
      }
      return;
    }

    const cacheKey = strategyTestDayDetailKey(options.batchId ?? latestStrategyTestBatch?.batch_id ?? day.batch_id, day.day_result_id);
    const cached = strategyTestDayDetailCache[cacheKey];
    if (!options.prefetch) {
      setSelectedStrategyTestDayId(day.day_result_id);
      if (cached?.status === "ready" || cached?.status === "failed") {
        setStrategyTestDayArchive(cached.archive);
        setStrategyTestDayRun(cached.run);
        setStrategyTestDayDetailBusy(false);
        if (cached.status === "failed" && cached.error) setError(cached.error);
        return;
      }
    }
    if (strategyTestDayPrefetchingRef.current.has(cacheKey)) {
      if (!options.prefetch) setStrategyTestDayDetailBusy(false);
      return;
    }

    strategyTestDayPrefetchingRef.current.add(cacheKey);
    if (!options.prefetch) setStrategyTestDayDetailBusy(true);
    if (!options.prefetch) setError(null);
    setStrategyTestDayDetailCache((current) => ({
      ...current,
      [cacheKey]: current[cacheKey] ?? { archive: null, error: null, run: null, status: "loading" }
    }));
    try {
      const [archives, runs] = await Promise.all([
        fetchMinuteArchives(day.trade_date, symbol, "yahoo"),
        day.strategy_run_id ? fetchStrategyRuns(day.trade_date, symbol, strategyId) : Promise.resolve([])
      ]);
      const archive =
        archives.find(
          (item) =>
            (day.source_archive_id && (item.archive_id === day.source_archive_id || item.id === day.source_archive_id)) ||
            (item.symbol === symbol && item.trade_date === day.trade_date)
        ) ?? null;
      const run =
        day.strategy_run_id
          ? runs.find((item) => item.run_id === day.strategy_run_id || item.id === day.strategy_run_id) ?? null
          : null;
      setStrategyTestDayDetailCache((current) => ({
        ...current,
        [cacheKey]: { archive, error: null, run, status: "ready" }
      }));
      if (!options.prefetch) {
        setStrategyTestDayArchive(archive);
        setStrategyTestDayRun(run);
      }
      if (run) {
        setStrategyRuns((current) => [run, ...current.filter((item) => item.run_id !== run.run_id)]);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "failed_to_load_strategy_test_day_detail";
      setStrategyTestDayDetailCache((current) => ({
        ...current,
        [cacheKey]: { archive: null, error: message, run: null, status: "failed" }
      }));
      if (!options.prefetch) {
        setStrategyTestDayRun(null);
        setStrategyTestDayArchive(null);
        setError(message);
      }
    } finally {
      strategyTestDayPrefetchingRef.current.delete(cacheKey);
      if (!options.prefetch) setStrategyTestDayDetailBusy(false);
    }
  }

  useEffect(() => {
    setSelectedReplayGroup(null);
    void refresh();
  }, [date]);

  useEffect(() => {
    if (!selectedSymbol && symbolOptions.length > 0) {
      setSelectedSymbol(symbolOptions[0]);
    }
  }, [selectedSymbol, symbolOptions]);

  useEffect(() => {
    if (strategies.length === 0) {
      if (selectedStrategyId) setSelectedStrategyId(null);
      return;
    }
    if (!selectedStrategyId || !strategies.some((strategy) => strategy.strategy_id === selectedStrategyId)) {
      setSelectedStrategyId(strategies[0].strategy_id);
    }
  }, [selectedStrategyId, strategies]);

  useEffect(() => {
    if (strategyTemplates.length === 0) {
      if (newStrategyTemplateKey) setNewStrategyTemplateKey("");
      return;
    }
    if (!newStrategyTemplateKey || !strategyTemplates.some((template) => template.template_key === newStrategyTemplateKey)) {
      setNewStrategyTemplateKey(strategyTemplates[0].template_key);
    }
  }, [newStrategyTemplateKey, strategyTemplates]);

  useEffect(() => {
    if (!selectedStrategy) {
      setStrategyNameDraft("");
      setStrategyParamsDraft({});
      return;
    }
    setStrategyNameDraft(selectedStrategy.name);
    setStrategyParamsDraft(selectedStrategy.params);
  }, [selectedStrategy]);

  useEffect(() => {
    if (!createStrategyTemplate) {
      setNewStrategyParamsDraft({});
      return;
    }
    setNewStrategyParamsDraft(createStrategyTemplate.default_params);
  }, [createStrategyTemplate]);

  useEffect(() => {
    void loadMinuteArchives();
  }, [date, selectedSymbol]);

  useEffect(() => {
    void loadSymbolDateBreakdown();
  }, [selectedSymbol]);

  useEffect(() => {
    void loadStrategyRuns();
  }, [date, selectedSymbol, selectedStrategyId]);

  useEffect(() => {
    void loadStrategyResearch();
  }, [date, selectedSymbol, selectedStrategyId]);

  useEffect(() => {
    const batch = latestStrategyTestBatch;
    if (
      !batch ||
      batch.symbol !== selectedSymbol ||
      batch.strategy_id !== selectedStrategyId ||
      batch.end_date !== date ||
      batch.day_results.length === 0
    ) {
      void loadStrategyTestDayDetail(null);
      return;
    }
    if (selectedStrategyTestDayId && batch.day_results.some((day) => day.day_result_id === selectedStrategyTestDayId)) {
      return;
    }
    setSelectedStrategyTestDayId(batch.day_results[0].day_result_id);
  }, [date, latestStrategyTestBatch?.batch_id, selectedStrategyId, selectedStrategyTestDayId, selectedSymbol]);

  useEffect(() => {
    const batch = latestStrategyTestBatch;
    if (!batch || batch.symbol !== selectedSymbol || batch.strategy_id !== selectedStrategyId || batch.end_date !== date) return;
    batch.day_results.forEach((day) => {
      void loadStrategyTestDayDetail(day, selectedStrategyId, selectedSymbol, { batchId: batch.batch_id, prefetch: true });
    });
  }, [date, latestStrategyTestBatch?.batch_id, selectedStrategyId, selectedSymbol]);

  useEffect(() => {
    if (!selectedStrategyTestDay || !latestStrategyTestBatch) {
      setStrategyTestDayRun(null);
      setStrategyTestDayArchive(null);
      return;
    }
    const cacheKey = strategyTestDayDetailKey(latestStrategyTestBatch.batch_id, selectedStrategyTestDay.day_result_id);
    const cached = strategyTestDayDetailCache[cacheKey];
    if (!cached || cached.status === "loading") return;
    setStrategyTestDayArchive(cached.archive);
    setStrategyTestDayRun(cached.run);
    setStrategyTestDayDetailBusy(false);
  }, [latestStrategyTestBatch, selectedStrategyTestDay, strategyTestDayDetailCache]);

  useEffect(() => {
    setStrategyRunFeedback(null);
    setStrategyArchiveFeedback(null);
    setSelectedStrategyTestDayId(null);
    setStrategyTestDayDetailCache({});
    strategyTestDayPrefetchingRef.current.clear();
    setStrategyTestDayRun(null);
    setStrategyTestDayArchive(null);
  }, [date, selectedSymbol, selectedStrategyId, strategyMode]);

  useEffect(() => {
    if (strategyDraftDirty) setStrategyRunFeedback(null);
  }, [strategyDraftDirty]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const batch = await uploadStpTxt(file);
      await refresh(batch.batch_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  async function onReplayTradeGroup(group: TradeGroup) {
    if (group.status !== "closed") return;
    setReplayBusy(group.trade_group_id);
    setError(null);
    setSelectedReplayGroup(group);
    try {
      setSelectedSymbol(group.symbol);
      const tradeDate = group.opened_at.slice(0, 10);
      let archives = await fetchMinuteArchives(tradeDate, group.symbol, "yahoo");
      if (archives.length === 0) {
        const archived = await archiveYahooMinuteData(tradeDate, false, group.symbol, 1);
        archives = archived.items.filter((item) => item.symbol === group.symbol && item.trade_date === tradeDate);
        if (archives.length === 0) {
          archives = await fetchMinuteArchives(tradeDate, group.symbol, "yahoo");
        }
      }
      setMinuteArchives(archives);
      const refreshedGroups = await fetchTradeGroups(tradeDate);
      setTradeGroups(refreshedGroups);
      setSelectedReplayGroup(refreshedGroups.find((item) => item.trade_group_id === group.trade_group_id) ?? group);
    } catch (err) {
      setError(err instanceof Error ? err.message : "交易回放失败");
    } finally {
      setReplayBusy(null);
    }
  }

  function enterReviewContext(nextDate: string, nextSymbol: string) {
    setDate(nextDate);
    setSelectedSymbol(nextSymbol);
    setSelectedReplayGroup(null);
    window.setTimeout(() => reviewModuleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  async function onGenerateWatchlist() {
    setWatchlistBusy(true);
    setError(null);
    try {
      setWatchlist(await generateWatchlist(date, watchlist?.status === "completed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Watchlist 生成失败");
    } finally {
      setWatchlistBusy(false);
    }
  }

  async function onArchiveYahooMinutes() {
    if (!selectedSymbol) return;
    setArchiveBusy(true);
    setError(null);
    try {
      const hasExistingArchive = minuteArchives.some(
        (archive) => archive.symbol === selectedSymbol && archive.trade_date === date
      );
      const result = await archiveYahooMinuteData(date, hasExistingArchive, selectedSymbol, 1);
      const matchingItems = result.items.filter(
        (archive) => archive.symbol === selectedSymbol && archive.trade_date === date
      );
      setMinuteArchives(matchingItems.length > 0 ? matchingItems : await fetchMinuteArchives(date, selectedSymbol, "yahoo"));
      setTradeGroups(await fetchTradeGroups(date));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yahoo 分钟线归档失败");
    } finally {
      setArchiveBusy(false);
    }
  }

  async function onCreateStrategy() {
    const template = createStrategyTemplate;
    if (!template) return;
    setStrategyCreateBusy(true);
    setError(null);
    try {
      const created = await createStrategy(
        newStrategyName.trim() || `${template.name} 副本`,
        template.template_key,
        newStrategyParamsDraft
      );
      setStrategies(await fetchStrategies());
      setSelectedStrategyId(created.strategy_id);
      setNewStrategyName("");
      setNewStrategyParamsDraft(template.default_params);
      setStrategyMode("edit");
      setStrategyRunFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略添加失败");
    } finally {
      setStrategyCreateBusy(false);
    }
  }

  async function onSaveStrategy() {
    if (!selectedStrategy) return;
    setStrategySaveBusy(true);
    setError(null);
    try {
      const updated = await updateStrategy(selectedStrategy.strategy_id, {
        name: strategyNameDraft,
        params: strategyParamsDraft
      });
      setStrategies(await fetchStrategies());
      setSelectedStrategyId(updated.strategy_id);
      setStrategyRuns([]);
      setStrategyRunFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略保存失败");
    } finally {
      setStrategySaveBusy(false);
    }
  }

  async function onToggleStrategy() {
    if (!selectedStrategy) return;
    setStrategySaveBusy(true);
    setError(null);
    try {
      const updated = await updateStrategy(selectedStrategy.strategy_id, { enabled: !selectedStrategy.enabled });
      setStrategies(await fetchStrategies());
      setSelectedStrategyId(updated.strategy_id);
      setStrategyRuns([]);
      setStrategyRunFeedback(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略启停失败");
    } finally {
      setStrategySaveBusy(false);
    }
  }

  async function onRunStrategy() {
    if (!selectedStrategy || !selectedSymbol) return;
    setStrategyBusy(true);
    setError(null);
    setStrategyRunFeedback({
      tone: "info",
      title: "策略复盘已开始",
      detail: `${date} ${selectedSymbol} 正在读取已归档分钟线，并由后端生成策略 run 与信号。`
    });
    try {
      const force = latestStrategyRun?.status === "completed";
      const run = await runStrategyReplay(selectedStrategy.strategy_id, date, selectedSymbol, force);
      setStrategyRuns([run, ...strategyRuns.filter((item) => item.run_id !== run.run_id)]);
      setStrategyRunFeedback(getStrategyRunFeedback(run));
    } catch (err) {
      const message = err instanceof Error ? err.message : "策略复盘运行失败";
      setError(message);
      setStrategyRunFeedback({
        tone: "danger",
        title: "策略复盘失败",
        detail: message
      });
    } finally {
      setStrategyBusy(false);
    }
  }

  async function onRunStrategyTestBatch() {
    if (!selectedStrategy || !selectedSymbol) return;
    setStrategyTestBusy(true);
    setError(null);
    try {
      const batch = await runStrategyTestBatch(selectedStrategy.strategy_id, date, selectedSymbol, Boolean(latestStrategyTestBatch));
      setStrategyTestBatches([batch, ...strategyTestBatches.filter((item) => item.batch_id !== batch.batch_id)]);
      setSelectedStrategyTestDayId(batch.day_results[0]?.day_result_id ?? null);
      batch.day_results.forEach((day) => {
        void loadStrategyTestDayDetail(day, selectedStrategy.strategy_id, selectedSymbol, {
          batchId: batch.batch_id,
          prefetch: true
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略测试运行失败");
    } finally {
      setStrategyTestBusy(false);
    }
  }

  function onSelectStrategyTestDay(day: StrategyTestDayResult) {
    setSelectedStrategyTestDayId(day.day_result_id);
    void loadStrategyTestDayDetail(day, selectedStrategyId, selectedSymbol, {
      batchId: latestStrategyTestBatch?.batch_id ?? day.batch_id,
      prefetch: true
    });
  }

  async function onArchiveStrategyWindow() {
    if (!selectedSymbol) return;
    setArchiveBusy(true);
    setError(null);
    setStrategyArchiveFeedback({
      tone: "info",
      title: "30日数据拉取已开始",
      detail: `${selectedSymbol} 截至 ${date} 正在显式拉取最近 30 个交易日分钟线；策略测试不会在后台自动拉行情。`
    });
    try {
      const result = await archiveYahooMinuteData(date, Boolean(latestStrategyTestBatch), selectedSymbol, 30);
      const selectedAvailable = result.selected_symbol_available_count ?? 0;
      const selectedItems = result.items.filter((archive) => archive.symbol === selectedSymbol);
      const unavailableItems = selectedItems.filter((archive) => archive.data_status !== "available");
      const firstUnavailable = unavailableItems[0] ?? null;
      const currentDateItems = result.items.filter(
        (archive) => archive.symbol === selectedSymbol && archive.trade_date === date
      );
      setMinuteArchives(currentDateItems.length > 0 ? currentDateItems : await fetchMinuteArchives(date, selectedSymbol, "yahoo"));
      await loadStrategyResearch(selectedStrategyId, selectedSymbol);
      setStrategyArchiveFeedback({
        tone: selectedAvailable >= 30 ? "ok" : "warn",
        title: selectedAvailable >= 30 ? "30日归档已准备" : "30日归档仍有不可用日期",
        detail:
          `${selectedSymbol} 截至 ${date} 已保存 ${selectedAvailable}/30 个可用交易日。` +
          (firstUnavailable
            ? ` ${firstUnavailable.trade_date} ${formatArchiveFailureReason(firstUnavailable.failure_reason) ?? firstUnavailable.data_status}。`
            : "") +
          " 策略测试仍只读取已保存归档。"
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "30日分钟线归档失败";
      setError(message);
      setStrategyArchiveFeedback({
        tone: "danger",
        title: "30日数据拉取失败",
        detail: message
      });
    } finally {
      setArchiveBusy(false);
    }
  }

  async function onRunStrategyOptimization() {
    if (!selectedStrategy || !selectedSymbol) return;
    setStrategyOptimizationBusy(true);
    setError(null);
    try {
      const optimization = await runStrategyOptimization(
        selectedStrategy.strategy_id,
        date,
        selectedSymbol,
        Boolean(latestOptimization)
      );
      setSelectedOptimization(optimization);
      setStrategyOptimizations([
        optimization,
        ...strategyOptimizations.filter((item) => item.optimization_id !== optimization.optimization_id)
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略优化运行失败");
    } finally {
      setStrategyOptimizationBusy(false);
    }
  }

  async function onApplyOptimizationCandidate(candidate: StrategyOptimizationCandidate) {
    if (!selectedStrategy) return;
    setStrategySaveBusy(true);
    setError(null);
    try {
      const updated = await updateStrategy(selectedStrategy.strategy_id, { params: candidate.params });
      setStrategies((current) => current.map((strategy) => (strategy.strategy_id === updated.strategy_id ? updated : strategy)));
      setSelectedStrategyId(updated.strategy_id);
      setStrategyParamsDraft(updated.params);
      setStrategyRunFeedback({
        tone: "ok",
        title: "候选参数已套用",
        detail: "策略配置已通过显式保存更新；历史优化 run 和候选结果保持原始证据。"
      });
      void loadStrategyRuns(updated.strategy_id, selectedSymbol);
      void loadStrategyResearch(updated.strategy_id, selectedSymbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : "候选参数套用失败");
    } finally {
      setStrategySaveBusy(false);
    }
  }

  function onStrategyParamChange(param: StrategyTemplate["param_schema"][number], value: string) {
    setStrategyParamsDraft((current) => ({
      ...current,
      [param.key]: coerceStrategyParamValue(param, value, current[param.key])
    }));
  }

  function onNewStrategyParamChange(param: StrategyTemplate["param_schema"][number], value: string) {
    setNewStrategyParamsDraft((current) => ({
      ...current,
      [param.key]: coerceStrategyParamValue(param, value, current[param.key])
    }));
  }

  const selected = useMemo(
    () => batches.find((batch) => batch.batch_id === selectedBatch) ?? null,
    [batches, selectedBatch]
  );
  const selectedSymbolSummary = useMemo(
    () => (selectedSymbol ? symbolSummaryGroups.find((group) => group.group_key === selectedSymbol) ?? null : null),
    [selectedSymbol, symbolSummaryGroups]
  );
  const selectedDateSummary = useMemo(() => {
    const grouped = dateSummaryGroups.find((group) => group.group_key === date) ?? null;
    if (grouped) return grouped;
    return summary?.date === date && summary.symbol === null ? summary : null;
  }, [date, dateSummaryGroups, summary]);
  const activeDrillSummary = activeReviewDrillTab === "date" ? selectedDateSummary : selectedSymbolSummary;
  const dateSymbolBreakdownReady = dateSymbolBreakdownDate === date;
  const visibleDateSymbolBreakdown = useMemo(
    () => (dateSymbolBreakdownDate === date ? dateSymbolBreakdown.filter((group) => group.date === date) : []),
    [date, dateSymbolBreakdown, dateSymbolBreakdownDate]
  );
  const visibleSymbolDateBreakdown = useMemo(
    () => symbolDateBreakdown.filter((group) => group.symbol === selectedSymbol),
    [selectedSymbol, symbolDateBreakdown]
  );
  const selectedStatus = selected ? statusMeta[selected.status] : null;
  const chartStatus = selectedArchive ? marketStatusMeta[selectedArchive.data_status] : null;
  const latestStrategyStatus = latestStrategyRun ? strategyStatusMeta[latestStrategyRun.status] : null;
  const hasFills = fills.length > 0;
  const hasDisplayedTradeGroups = displayedTradeGroups.length > 0;
  const hasBatches = batches.length > 0;
  const summaryNote = summary ? sourceLabel[summary.source] : "等待复盘摘要";
  const overallSummaryNote = overallSummary ? sourceLabel[overallSummary.source] : "等待全局摘要";
  const watchStatus = watchlistStatusMeta[watchlist?.status ?? "not_generated"];
  const closedTradeGroupCount = displayedTradeGroups.filter((group) => group.status === "closed").length;
  const openTradeGroupCount = displayedTradeGroups.filter((group) => group.status === "open").length;
  const latestBatch = batches[0] ?? null;
  const latestBatchStatus = latestBatch ? statusMeta[latestBatch.status] : null;

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">P2 Review Desk</p>
          <h1>日内复盘台</h1>
          <p>STP 成交证据、行情上下文、盘前 watchlist 与策略复盘信号</p>
        </div>
        <label className={busy ? "uploadButton busy" : "uploadButton"} aria-busy={busy}>
          <FileUp size={18} />
          <span>{busy ? "导入中" : "上传 STP TXT"}</span>
          <input
            type="file"
            accept=".txt,.tsv,.csv"
            disabled={busy}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0] ?? null;
              event.currentTarget.value = "";
              void onUpload(file);
            }}
          />
        </label>
      </section>

      {error ? (
        <div className="error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      <nav className="workspaceTabs" aria-label="工作区切换">
        <button
          aria-pressed={activeWorkspaceTab === "review"}
          className={activeWorkspaceTab === "review" ? "workspaceTab active" : "workspaceTab"}
          onClick={() => setActiveWorkspaceTab("review")}
          type="button"
        >
          <TableProperties size={16} />
          交易复盘
        </button>
        <button
          aria-pressed={activeWorkspaceTab === "strategy"}
          className={activeWorkspaceTab === "strategy" ? "workspaceTab active" : "workspaceTab"}
          onClick={() => setActiveWorkspaceTab("strategy")}
          type="button"
        >
          <SlidersHorizontal size={16} />
          策略测试
        </button>
      </nav>
      <datalist id="symbolOptions">
        {symbolOptions.map((symbol) => (
          <option key={symbol} value={symbol} />
        ))}
      </datalist>

      {activeWorkspaceTab === "review" ? (
        <>
      <SummaryMetricStrip className="kpis reviewDashboard" note={overallSummaryNote} summary={overallSummary} />

      <section className="panel reviewDrillPanel" aria-label="交易复盘下钻">
        <header>
          <div>
            <h2>
              <Activity size={18} />
              下钻复盘
            </h2>
            <p className="panelNote">先按交易日或标的查看次级汇总，再进入当前复盘模块</p>
          </div>
          <div className="reviewDrillTabs" role="group" aria-label="下钻方式">
            <button
              aria-pressed={activeReviewDrillTab === "date"}
              className={activeReviewDrillTab === "date" ? "reviewDrillTab active" : "reviewDrillTab"}
              onClick={() => setActiveReviewDrillTab("date")}
              type="button"
            >
              按交易日
            </button>
            <button
              aria-pressed={activeReviewDrillTab === "symbol"}
              className={activeReviewDrillTab === "symbol" ? "reviewDrillTab active" : "reviewDrillTab"}
              onClick={() => setActiveReviewDrillTab("symbol")}
              type="button"
            >
              按标的
            </button>
          </div>
        </header>

        <div className="reviewDrillLayout">
          <div className="reviewDrillPrimary" aria-label={activeReviewDrillTab === "date" ? "交易日列表" : "标的列表"}>
            {activeReviewDrillTab === "date" ? (
              dateSummaryGroups.length > 0 ? (
                dateSummaryGroups.map((group) => (
                  <button
                    aria-pressed={group.group_key === date}
                    className={group.group_key === date ? "drillPrimaryItem active" : "drillPrimaryItem"}
                    key={group.group_key}
                    onClick={() => setDate(group.group_key)}
                    type="button"
                  >
                    <strong>{group.group_label}</strong>
                    <small>{formatReviewGroupMeta(group)}</small>
                  </button>
                ))
              ) : (
                <EmptyState icon={<CircleSlash size={18} />} title="暂无交易日" detail="还没有 committed 成交可用于日期下钻" />
              )
            ) : symbolSummaryGroups.length > 0 ? (
              symbolSummaryGroups.map((group) => (
                <button
                  aria-pressed={group.group_key === selectedSymbol}
                  className={group.group_key === selectedSymbol ? "drillPrimaryItem active" : "drillPrimaryItem"}
                  key={group.group_key}
                  onClick={() => setSelectedSymbol(group.group_key)}
                  type="button"
                >
                  <strong>{group.group_label}</strong>
                  <small>{formatReviewGroupMeta(group)}</small>
                </button>
              ))
            ) : (
              <EmptyState icon={<CircleSlash size={18} />} title="暂无标的" detail="还没有 committed 成交可用于标的下钻" />
            )}
          </div>

          <div className="reviewDrillDetail">
            <div className="drillDetailHead">
              <div>
                <strong>
                  {activeReviewDrillTab === "date"
                    ? `${date} 日统计`
                    : selectedSymbol
                      ? `${selectedSymbol} 标的统计`
                      : "未选择标的"}
                </strong>
                <small>{activeReviewDrillTab === "date" ? "选择标的进入复盘模块" : "选择交易日进入复盘模块"}</small>
              </div>
              <span className="sourcePill">
                {activeReviewDrillTab === "date"
                  ? dateSymbolBreakdownReady
                    ? formatInteger(visibleDateSymbolBreakdown.length)
                    : "读取中"
                  : formatInteger(visibleSymbolDateBreakdown.length)}
                {activeReviewDrillTab === "date" ? " 个标的" : " 个交易日"}
              </span>
            </div>

            <SummaryMiniFacts summary={activeDrillSummary} />

            <div className="drillSecondaryList">
              {activeReviewDrillTab === "date" ? (
                !dateSymbolBreakdownReady ? (
                  <EmptyState icon={<Clock3 size={18} />} title="正在读取标的" detail="正在读取当前交易日的 committed 成交分组" />
                ) : visibleDateSymbolBreakdown.length > 0 ? (
                  visibleDateSymbolBreakdown.map((group) => (
                    <article
                      className={group.group_key === selectedSymbol ? "drillSecondaryItem active" : "drillSecondaryItem"}
                      key={group.group_key}
                    >
                      <div>
                        <strong>{group.group_label}</strong>
                        <small>{formatReviewGroupMeta(group)}</small>
                      </div>
                      <button className="linkButton" onClick={() => enterReviewContext(date, group.group_key)} type="button">
                        <Play size={14} />
                        进入复盘
                      </button>
                    </article>
                  ))
                ) : (
                  <EmptyState icon={<CircleSlash size={18} />} title="该日没有标的" detail="当前交易日没有 committed 成交分组" />
                )
              ) : selectedSymbol ? (
                visibleSymbolDateBreakdown.length > 0 ? (
                  visibleSymbolDateBreakdown.map((group) => (
                    <article className={group.group_key === date ? "drillSecondaryItem active" : "drillSecondaryItem"} key={group.group_key}>
                      <div>
                        <strong>{group.group_label}</strong>
                        <small>{formatReviewGroupMeta(group)}</small>
                      </div>
                      <button className="linkButton" onClick={() => enterReviewContext(group.group_key, selectedSymbol)} type="button">
                        <Play size={14} />
                        进入复盘
                      </button>
                    </article>
                  ))
                ) : (
                  <EmptyState icon={<CircleSlash size={18} />} title="该标的没有交易日" detail="当前标的没有 committed 成交分组" />
                )
              ) : (
                <EmptyState icon={<Clock3 size={18} />} title="等待选择标的" detail="从左侧选择一个标的后显示交易日汇总" />
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="kpis currentReviewKpis" aria-label="当前复盘模块指标">
        <label className="dateControl">
          <span>当前复盘日期</span>
          <input value={date} onChange={(event) => setDate(event.target.value)} type="date" />
        </label>
        <label className="dateControl">
          <span>当前复盘标的</span>
          <input
            list="symbolOptions"
            placeholder="输入或选择标的"
            value={selectedSymbol}
            onChange={(event) => setSelectedSymbol(event.target.value.trim().toUpperCase())}
            type="text"
          />
        </label>
        <Metric label="成交股数" value={formatInteger(summary?.traded_quantity ?? 0)} note="BUY/SELL 平仓数量" />
        <Metric label="PnL" value={formatPnl(summary?.pnl ?? 0)} tone={summaryTone(summary?.pnl ?? 0)} />
        <Metric label="胜率" value={formatWinRate(summary)} />
        <Metric label="盈亏比" value={formatProfitFactor(summary)} />
        <Metric label="持仓最大回撤" value={formatNullable(summary?.max_single_day_drawdown)} tone={(summary?.max_single_day_drawdown ?? 0) > 0 ? "warn" : "neutral"} />
      </section>

      <section className="reviewWorkspace" aria-label="日内复盘工作区" ref={reviewModuleRef}>
        <section className="panel chartPanel workspaceChart" aria-label="分钟蜡烛图复盘">
          <header>
            <div>
              <h2>
                <BarChart3 size={18} />
                分钟蜡烛复盘
              </h2>
              <p className="panelNote">分钟线和成交点来自已保存 read model；策略研究请切换到策略测试</p>
            </div>
            <div className="headerActions">
              {chartStatus ? <span className={`statusPill ${chartStatus.tone}`}>{chartStatus.label}</span> : null}
              <div className="layerToggles" aria-label="图层开关">
                <label className="toggleControl">
                  <input
                    checked={showTradeMarkers}
                    onChange={(event) => setShowTradeMarkers(event.currentTarget.checked)}
                    type="checkbox"
                  />
                  <span>买卖点</span>
                </label>
              </div>
              <button className="smallButton" onClick={() => void onArchiveYahooMinutes()} disabled={!selectedSymbol || archiveBusy}>
                <RefreshCw className={archiveBusy ? "spin" : undefined} size={15} />
                {selectedArchive ? "重新归档" : "归档分钟线"}
              </button>
            </div>
          </header>

          {selectedArchive && selectedArchive.bars.length > 0 ? (
            <>
              <div className="chartMeta" aria-label="分钟线摘要">
                <span>{selectedArchive.symbol}</span>
                <span>{selectedArchive.provider.toUpperCase()}</span>
                <span>Bars {formatInteger(selectedArchive.bar_count)}</span>
                <span>VWAP {formatNullable(selectedArchive.vwap)}</span>
                <span>High {formatNullable(selectedArchive.day_high)}</span>
                <span>Low {formatNullable(selectedArchive.day_low)}</span>
                <span>Volume {formatInteger(selectedArchive.volume_context.total_volume)}</span>
                <span className="monoWrap">hash {shortHash(selectedArchive.bars_hash)}</span>
              </div>
              <MinuteCandleChart
                archive={selectedArchive}
                fills={displayedFills}
                showStrategyMarkers={false}
                showTradeMarkers={showTradeMarkers}
                strategyRun={null}
              />
              {selectedArchive.failure_reason ? (
                <div className="statusReason">
                  <AlertTriangle size={16} />
                  <span>{formatArchiveFailureReason(selectedArchive.failure_reason) ?? selectedArchive.failure_reason}</span>
                </div>
              ) : null}
            </>
          ) : selectedArchive ? (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="分钟线不可用"
              detail={formatArchiveFailureReason(selectedArchive.failure_reason) ?? "provider 返回缺数据状态，未渲染成功图表"}
            />
          ) : selectedSymbol ? (
            <EmptyState
              icon={<Clock3 size={18} />}
              title="尚未归档分钟线"
              detail="当前标的没有可用 symbol/day 分钟线归档"
            />
          ) : (
            <EmptyState icon={<CircleSlash size={18} />} title="当前日期没有标的" detail="先导入 STP TXT 并提交成交记录" />
          )}
        </section>

        <aside className="reviewRail" aria-label="盘前工作栏">
          <section className="panel watchlistPanel">
            <header>
              <div>
                <h2>
                  <ListChecks size={18} />
                  盘前 Watchlist
                </h2>
                <p className="panelNote">reason codes 与 metrics hash 来自 watchlist read model</p>
              </div>
              <div className="headerActions">
                <span className={`statusPill ${watchStatus.tone}`}>{watchStatus.label}</span>
                <button className="smallButton" onClick={() => void onGenerateWatchlist()} disabled={watchlistBusy}>
                  <RefreshCw className={watchlistBusy ? "spin" : undefined} size={15} />
                  {watchlist?.status === "completed" ? "重跑" : "生成"}
                </button>
              </div>
            </header>
            {watchlist?.failure_reason ? (
              <div className="statusReason">
                <AlertTriangle size={16} />
                <span>{watchlist.failure_reason}</span>
              </div>
            ) : null}
            {watchlist && watchlist.items.length > 0 ? (
              <div className="watchlistGrid">
                {watchlist.items.map((item) => (
                  <article key={item.item_id} className="watchlistItem">
                    <div className="watchlistHead">
                      <strong>#{item.rank}</strong>
                      <span className="symbolText">{item.symbol}</span>
                      <span className="sourcePill">{item.source}</span>
                    </div>
                    <div className="reasonList">
                      {item.reason_codes.map((reason) => (
                        <span key={reason} className="reasonCode">
                          {reasonLabels[reason] ?? reason}
                        </span>
                      ))}
                    </div>
                    <dl className="compactFacts">
                      {Object.entries(item.metrics).map(([key, value]) => (
                        <div key={key}>
                          <dt>{key}</dt>
                          <dd>{formatMetric(value)}</dd>
                        </div>
                      ))}
                    </dl>
                    <small className="monoWrap">metrics {shortHash(item.metrics_hash)}</small>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                icon={<CircleSlash size={18} />}
                title="暂无 watchlist 项"
                detail={watchlist?.status === "failed" ? "provider_failed" : "当前日期没有入选 symbol"}
              />
            )}
          </section>

          <section className="panel operationPanel">
            <header>
              <div>
                <h2>
                  <Activity size={18} />
                  操作入口
                </h2>
                <p className="panelNote">导入证据、交易回放与刷新动作</p>
              </div>
            </header>
            <dl className="compactFacts operationFacts">
              <div>
                <dt>最新批次</dt>
                <dd>{latestBatchStatus?.label ?? "无批次"}</dd>
              </div>
              <div>
                <dt>可回放</dt>
                <dd>{formatInteger(closedTradeGroupCount)}</dd>
              </div>
              <div>
                <dt>未清仓</dt>
                <dd>{formatInteger(openTradeGroupCount)}</dd>
              </div>
            </dl>
            {latestBatch ? (
              <div className="latestBatchLine">
                <span className="batchFile" title={latestBatch.file_name}>
                  {latestBatch.file_name}
                </span>
                {latestBatchStatus ? <span className={`statusPill ${latestBatchStatus.tone}`}>{latestBatchStatus.label}</span> : null}
              </div>
            ) : null}
            <div className="operationActions">
              <a className="linkButton" href="#trade-ledger">
                <Play size={14} />
                交易组
              </a>
              <a className="linkButton" href="#import-evidence">
                <FileText size={14} />
                批次证据
              </a>
              <button className="smallButton" onClick={() => void refresh()} type="button">
                <RefreshCw className={loading ? "spin" : undefined} size={14} />
                刷新
              </button>
            </div>
          </section>
        </aside>
      </section>

      <section className="panel tradeLedgerPanel" id="trade-ledger">
          <header>
            <div>
              <h2>
                <TableProperties size={18} />
                成交记录
              </h2>
              <p className="panelNote">按每一次开仓至清仓配对展示，PnL 只来自 committed fills</p>
            </div>
            <span className="sourcePill">{summaryNote}</span>
          </header>

          {hasDisplayedTradeGroups ? (
            <div className="tableWrap">
              <table className="tradeGroupTable">
                <thead>
                  <tr>
                    <th>开仓 / 清仓 / 持仓</th>
                    <th>账户</th>
                    <th>Symbol</th>
                    <th>方向</th>
                    <th>数量</th>
                    <th>PnL</th>
                    <th>最大回撤</th>
                    <th>评价</th>
                    <th>追溯</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedTradeGroups.map((group) => {
                    const evaluation = group.evaluation;
                    return (
                      <tr key={group.trade_group_id}>
                        <td className="timeCell">
                          <div className="timeStack">
                            <span className="timeLabel">开仓</span>
                            <span className="timeValue">{formatDateTime(group.opened_at)}</span>
                          </div>
                          <div className="timeStack">
                            <span className="timeLabel">清仓</span>
                            <span className="timeValue">{group.closed_at ? formatDateTime(group.closed_at) : "未清仓"}</span>
                          </div>
                          <div className="timeStack">
                            <span className="timeLabel">持仓</span>
                            <span className="timeValue">{formatHoldingMinutes(group.holding_minutes)}</span>
                          </div>
                        </td>
                        <td className="textCell">
                          <span className="monoWrap" title={group.account_canonical}>
                            {group.account_canonical}
                          </span>
                          {group.account_raw && group.account_raw !== group.account_canonical ? (
                            <small title={group.account_raw}>raw {group.account_raw}</small>
                          ) : null}
                        </td>
                        <td className="textCell">
                          <span className="symbolText" title={group.symbol}>
                            {group.symbol}
                          </span>
                        </td>
                        <td>
                          <span className={group.direction === "LONG" ? "sidePill buy" : "sidePill sell"}>
                            {formatDirection(group.direction)}
                          </span>
                        </td>
                        <td>
                          <strong>{formatInteger(group.total_quantity)}</strong>
                          <small>
                            {formatNullable(group.avg_entry_price)} → {formatNullable(group.avg_exit_price)}
                          </small>
                        </td>
                        <td className={group.pnl !== null ? `pnlCell ${summaryTone(group.pnl)}` : "pnlCell"}>
                          {group.pnl === null ? "N/A" : formatPnl(group.pnl)}
                        </td>
                        <td className={`pnlCell ${positionDrawdownTone(group.position_drawdown)}`}>
                          <strong>{formatPositionDrawdown(group.position_drawdown)}</strong>
                          <small>{formatPositionDrawdownMeta(group.position_drawdown)}</small>
                        </td>
                        <td>
                          <span className={`gradePill ${evaluationTone(evaluation.evaluation_status, evaluation.grade)}`}>
                            {formatEvaluationGrade(evaluation)}
                          </span>
                        </td>
                        <td className="traceCell">
                          <span>{formatInteger(group.fill_count)} fills</span>
                          {group.status === "closed" ? (
                            <button
                              className="linkButton"
                              onClick={() => void onReplayTradeGroup(group)}
                              disabled={replayBusy === group.trade_group_id}
                            >
                              {replayBusy === group.trade_group_id ? (
                                <RefreshCw className="spin" size={14} />
                              ) : (
                                <Play size={14} />
                              )}
                              查看
                            </button>
                          ) : (
                            <span className="fallbackPill">未清仓</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={<CircleSlash size={18} />}
              title={hasFills ? "当前标的没有交易组" : "当前日期没有 committed 成交"}
              detail="KPI 保持 0 或 N/A，隔离行仍可在批次面板复查"
            />
          )}
      </section>

      <section className="evidenceGrid" id="import-evidence" aria-label="导入证据与隔离行">
        <section className="panel importEvidencePanel">
          <header>
            <div>
              <h2>
                <Hash size={18} />
                导入批次与证据
              </h2>
              <p className="panelNote">file_hash、parser version 与 field mapper version 保留在证据链</p>
            </div>
            <button className="iconButton" onClick={() => void refresh()} title="刷新" aria-label="刷新导入证据">
              <RefreshCw className={loading ? "spin" : undefined} size={16} />
            </button>
          </header>

          {hasBatches ? (
            <div className="importEvidenceLayout">
              <div className="batchList evidenceBatchList" aria-label="导入批次列表">
                {batches.map((batch) => {
                  const meta = statusMeta[batch.status];
                  return (
                    <button
                      className={batch.batch_id === selectedBatch ? "batch active" : "batch"}
                      key={batch.batch_id}
                      onClick={() => void refresh(batch.batch_id)}
                    >
                      <span className="batchRow">
                        <span className="batchFile" title={batch.file_name}>
                          {batch.file_name}
                        </span>
                        <span className={`statusPill ${meta.tone}`}>{meta.label}</span>
                      </span>
                      <small>
                        rows {formatInteger(batch.row_count)} · accepted {formatInteger(batch.accepted_rows)} · quarantine{" "}
                        {formatInteger(batch.quarantined_rows)}
                      </small>
                      {batch.duplicate ? <span className="duplicateNote">重复文件，沿用既有批次</span> : null}
                    </button>
                  );
                })}
              </div>

              <div className="batchEvidenceDetail">
                {selected ? (
                  <>
                    <div className="batchEvidenceHead">
                      <strong className="wrapValue" title={selected.file_name}>
                        {selected.file_name}
                      </strong>
                      {selectedStatus ? <span className={`statusPill ${selectedStatus.tone}`}>{selectedStatus.label}</span> : null}
                    </div>
                    <dl className="batchFacts">
                      <div>
                        <dt>file_hash</dt>
                        <dd className="monoWrap" title={selected.file_hash}>
                          {shortHash(selected.file_hash)}
                        </dd>
                      </div>
                      <div>
                        <dt>parser version</dt>
                        <dd>{selected.parser_version}</dd>
                      </div>
                      <div>
                        <dt>field mapper version</dt>
                        <dd>{selected.field_mapper_version}</dd>
                      </div>
                      <div>
                        <dt>批次状态</dt>
                        <dd>{selectedStatus?.detail}</dd>
                      </div>
                      <div>
                        <dt>accepted</dt>
                        <dd>{formatInteger(selected.accepted_rows)}</dd>
                      </div>
                      <div>
                        <dt>隔离行</dt>
                        <dd>{formatInteger(selected.quarantined_rows)}</dd>
                      </div>
                    </dl>
                    {selected.status_reason ? (
                      <div className="statusReason">
                        <AlertTriangle size={16} />
                        <span>{selected.status_reason}</span>
                      </div>
                    ) : null}
                  </>
                ) : (
                  <EmptyState icon={<Clock3 size={18} />} title="未选择批次" detail="导入 STP TXT 后会自动选择最新批次" />
                )}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<CircleSlash size={18} />}
              title="还没有导入批次"
              detail="上传 STP TXT 后会出现批次、证据行和隔离行"
            />
          )}
        </section>

        <section className="panel quarantinePanel">
          <header>
            <div>
              <h2>
                <AlertTriangle size={18} />
                隔离行
              </h2>
              <p className="panelNote">失败字段、原因码和修复提示保留在 evidence ledger</p>
            </div>
            {selected ? (
              <span className={selected.quarantined_rows > 0 ? "warningPill" : "okPill"}>
                {selected.quarantined_rows > 0 ? "需要复查" : "无隔离行"}
              </span>
            ) : null}
          </header>
          <div className="quarantineGrid">
            {selected && quarantine.length > 0
              ? quarantine.map((row) => (
                  <article key={row.id} className="quarantineItem">
                    <div className="quarantineHeader">
                      <strong>line {row.raw_line_number}</strong>
                      <span className="failedField">{row.failed_field}</span>
                      <span className="reasonCode">{row.reason_code}</span>
                    </div>
                    <p>{row.reason}</p>
                    <code>{row.raw_text}</code>
                    <small>{row.repair_hint}</small>
                  </article>
                ))
              : null}
            {selected && quarantine.length === 0 ? (
              <EmptyState
                icon={<CheckCircle2 size={18} />}
                title="当前批次没有隔离行"
                detail="accepted rows 已写入 normalized orders/fills"
              />
            ) : null}
            {!selected ? <EmptyState icon={<Clock3 size={18} />} title="等待批次" detail="选择导入批次后显示 quarantine 行" /> : null}
          </div>
        </section>
      </section>
        </>
      ) : (
        <StrategyTestingWorkspace
          archiveBusy={archiveBusy}
          date={date}
          latestOptimization={latestOptimization}
          latestStrategyTestBatch={latestStrategyTestBatch}
          onArchiveStrategyWindow={() => void onArchiveStrategyWindow()}
          onApplyOptimizationCandidate={(candidate) => void onApplyOptimizationCandidate(candidate)}
          onDateChange={setDate}
          onOpenStrategyConfig={() => setStrategyConfigOpen(true)}
          onRunOptimization={() => void onRunStrategyOptimization()}
          onRunTestBatch={() => void onRunStrategyTestBatch()}
          onSelectStrategyTestDay={onSelectStrategyTestDay}
          onSymbolChange={setSelectedSymbol}
          optimizationBusy={strategyOptimizationBusy}
          selectedStrategy={selectedStrategy}
          selectedStrategyTestDay={selectedStrategyTestDay}
          selectedStrategyTemplate={selectedStrategyTemplate}
          selectedSymbol={selectedSymbol}
          showFullDayStrategyBars={showFullDayStrategyBars}
          strategyArchiveFeedback={strategyArchiveFeedback}
          strategyDraftDirty={strategyDraftDirty}
          strategySaveBusy={strategySaveBusy}
          strategyTestDayArchive={strategyTestDayArchive}
          strategyTestDayDetailBusy={strategyTestDayDetailBusy || selectedStrategyTestDayDetail?.status === "loading"}
          strategyTestDayRun={strategyTestDayRun}
          strategyTestBusy={strategyTestBusy}
          onToggleFullDayStrategyBars={setShowFullDayStrategyBars}
        />
      )}

      {strategyConfigOpen ? (
        <div className="modalBackdrop" role="dialog" aria-modal="true" aria-label="交易策略配置">
          <section className="strategyModal">
            <header className="modalHeader">
              <div>
                <p className="eyebrow">Strategy Configuration</p>
                <h2>
                  <SlidersHorizontal size={18} />
                  交易策略配置
                </h2>
                <p className="panelNote">策略信号只来自已归档分钟线，不修改 committed fills</p>
              </div>
              <div className="headerActions">
                {strategyMode === "create" ? <span className="statusPill info">新增中</span> : null}
                {strategyMode === "edit" && selectedStrategy ? (
                  <span className={selectedStrategy.enabled ? "okPill" : "warningPill"}>
                    {selectedStrategy.enabled ? "已开启" : "未开启"}
                  </span>
                ) : null}
                {strategyMode === "edit" && latestStrategyStatus ? (
                  <span className={`statusPill ${latestStrategyStatus.tone}`}>{latestStrategyStatus.label}</span>
                ) : null}
                <button className="iconButton" onClick={() => setStrategyConfigOpen(false)} aria-label="关闭交易策略配置" title="关闭">
                  <X size={16} />
                </button>
              </div>
            </header>

            <div className="strategyGrid">
              <div className="strategyList">
                <div className="strategyListHeader">
                  <strong>策略实例</strong>
                  <small>{formatInteger(strategies.length)} 个配置</small>
                </div>
                <div className="strategyListActions" role="group" aria-label="策略配置操作">
                  <button
                    aria-pressed={strategyMode === "create"}
                    className={strategyMode === "create" ? "smallButton primary" : "smallButton"}
                    disabled={!createStrategyTemplate}
                    onClick={() => setStrategyMode("create")}
                    type="button"
                  >
                    <Plus size={14} />
                    新增策略
                  </button>
                </div>
                <div className="strategyListItems">
                  {strategies.map((strategy) => (
                    <button
                      aria-pressed={strategyMode === "edit" && strategy.strategy_id === selectedStrategy?.strategy_id}
                      className={
                        strategyMode === "edit" && strategy.strategy_id === selectedStrategy?.strategy_id
                          ? "strategyListItem active"
                          : "strategyListItem"
                      }
                      key={strategy.strategy_id}
                      onClick={() => {
                        setSelectedStrategyId(strategy.strategy_id);
                        setStrategyMode("edit");
                      }}
                      type="button"
                    >
                      <span>
                        <strong>{strategy.name}</strong>
                        <small>{strategy.template_version}</small>
                      </span>
                      <span className={strategy.enabled ? "okPill" : "warningPill"}>{strategy.enabled ? "ON" : "OFF"}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className={strategyRunFeedback && strategyMode === "edit" ? "strategyEditor hasRunFeedback" : "strategyEditor"}>
                {strategyMode === "create" && createStrategyTemplate ? (
                  <>
                    <div className="strategyPanelTitle">
                      <div>
                        <strong>新增策略</strong>
                        <small>{createStrategyTemplate.name}</small>
                      </div>
                      <span className="statusPill info">草稿</span>
                    </div>
                    <div className="strategyNameRow strategyCreateFields">
                      <label>
                        <span>策略模板</span>
                        <select
                          aria-label="选择策略模板"
                          value={createStrategyTemplate.template_key}
                          onChange={(event) => setNewStrategyTemplateKey(event.currentTarget.value as StrategyTemplate["template_key"])}
                        >
                          {strategyTemplates.map((template) => (
                            <option key={template.template_key} value={template.template_key}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>策略名称</span>
                        <input
                          value={newStrategyName}
                          onChange={(event) => setNewStrategyName(event.target.value)}
                          placeholder={`${createStrategyTemplate.name} 副本`}
                        />
                      </label>
                    </div>
                    <div className="strategyParamSections">
                      {groupStrategyParams(createStrategyTemplate.param_schema).map((section) => (
                        <section className="strategyParamSection" key={section.key}>
                          <header>
                            <strong>{section.title}</strong>
                            <small>{section.detail}</small>
                          </header>
                          <div className="paramGrid">
                            {section.params.map((param) => (
                              <label key={param.key}>
                                <span>{param.label}</span>
                                {param.type === "enum" ? (
                                  <select
                                    value={String(newStrategyParamsDraft[param.key] ?? createStrategyTemplate.default_params[param.key] ?? "")}
                                    onChange={(event) => onNewStrategyParamChange(param, event.currentTarget.value)}
                                  >
                                    {(param.options ?? []).map((option) => (
                                      <option key={option.value} value={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    max={param.max}
                                    min={param.min}
                                    step={param.type === "integer" ? 1 : 0.1}
                                    type="number"
                                    value={newStrategyParamsDraft[param.key] ?? createStrategyTemplate.default_params[param.key] ?? 0}
                                    onChange={(event) => onNewStrategyParamChange(param, event.target.value)}
                                  />
                                )}
                              </label>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                    <div className="strategyActions strategyActionBar">
                      <button
                        className="smallButton primary"
                        onClick={() => void onCreateStrategy()}
                        disabled={!createStrategyTemplate || strategyCreateBusy}
                      >
                        <Plus size={14} />
                        新增策略
                      </button>
                      <button className="smallButton" onClick={() => setStrategyMode("edit")} disabled={!selectedStrategy}>
                        <Pencil size={14} />
                        返回编辑
                      </button>
                    </div>
                  </>
                ) : selectedStrategy && selectedStrategyTemplate ? (
                  <>
                    <div className="strategyPanelTitle">
                      <div>
                        <strong>编辑策略</strong>
                        <small>{selectedStrategy.template_version}</small>
                      </div>
                      <span className={selectedStrategy.enabled ? "okPill" : "warningPill"}>
                        {selectedStrategy.enabled ? "已开启" : "未开启"}
                      </span>
                    </div>
                    <div className="strategyNameRow">
                      <label>
                        <span>策略名称</span>
                        <input value={strategyNameDraft} onChange={(event) => setStrategyNameDraft(event.target.value)} />
                      </label>
                      <div className="strategyInlineActions">
                        <button className="smallButton" onClick={() => void onToggleStrategy()} disabled={strategySaveBusy}>
                          <Power size={14} />
                          {selectedStrategy.enabled ? "停用" : "开启"}
                        </button>
                        <button className="smallButton primary" onClick={() => void onSaveStrategy()} disabled={strategySaveBusy}>
                          <Save size={14} />
                          保存编辑
                        </button>
                        {!strategyDraftDirty ? (
                          <button
                            className="smallButton primary"
                            onClick={() => void onRunStrategy()}
                            disabled={!selectedSymbol || strategyBusy}
                          >
                            {strategyBusy ? <RefreshCw className="spin" size={14} /> : <Play size={14} />}
                            {strategyBusy ? "复盘中" : "策略复盘"}
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {strategyRunFeedback ? (
                      <div className={`strategyRunFeedback ${strategyRunFeedback.tone}`} role="status" aria-live="polite">
                        {strategyBusy ? <RefreshCw className="spin" size={16} /> : <ListChecks size={16} />}
                        <div>
                          <strong>{strategyRunFeedback.title}</strong>
                          <span>{strategyRunFeedback.detail}</span>
                        </div>
                      </div>
                    ) : null}
                    <div className="strategyParamSections">
                      {groupStrategyParams(selectedStrategyTemplate.param_schema).map((section) => (
                        <section className="strategyParamSection" key={section.key}>
                          <header>
                            <strong>{section.title}</strong>
                            <small>{section.detail}</small>
                          </header>
                          <div className="paramGrid">
                            {section.params.map((param) => (
                              <label key={param.key}>
                                <span>{param.label}</span>
                                {param.type === "enum" ? (
                                  <select
                                    value={String(strategyParamsDraft[param.key] ?? selectedStrategy.params[param.key] ?? "")}
                                    onChange={(event) => onStrategyParamChange(param, event.currentTarget.value)}
                                  >
                                    {(param.options ?? []).map((option) => (
                                      <option key={option.value} value={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    max={param.max}
                                    min={param.min}
                                    step={param.type === "integer" ? 1 : 0.1}
                                    type="number"
                                    value={strategyParamsDraft[param.key] ?? selectedStrategy.params[param.key] ?? 0}
                                    onChange={(event) => onStrategyParamChange(param, event.target.value)}
                                  />
                                )}
                              </label>
                            ))}
                          </div>
                        </section>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState icon={<CircleSlash size={18} />} title="暂无策略模板" detail="后端未返回可用策略模板。" />
                )}
              </div>

              <div className="strategyDescriptionPanel">
                {strategyMode === "create" && createStrategyTemplate ? (
                  <StrategyDescription
                    enabled={false}
                    latestRun={null}
                    params={newStrategyParamsDraft}
                    strategyName={newStrategyName.trim() || `${createStrategyTemplate.name} 副本`}
                    templateKey={createStrategyTemplate.template_key}
                    templateVersion={createStrategyTemplate.template_version}
                  />
                ) : selectedStrategy && selectedStrategyTemplate ? (
                  <StrategyDescription
                    enabled={selectedStrategy.enabled}
                    latestRun={latestStrategyRun}
                    params={strategyParamsDraft}
                    strategyName={strategyNameDraft || selectedStrategy.name}
                    templateKey={selectedStrategy.template_key}
                    templateVersion={selectedStrategy.template_version}
                  />
                ) : (
                  <EmptyState icon={<Activity size={18} />} title="暂无策略描述" detail="后端返回策略模板后会展示完整规则。" />
                )}
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {selectedReplayGroup ? (
        <TradeReplayModal
          archive={selectedReplayArchive}
          group={selectedReplayGroup}
          onClose={() => setSelectedReplayGroup(null)}
        />
      ) : null}
    </main>
  );
}

function StrategyTestingWorkspace(props: {
  archiveBusy: boolean;
  date: string;
  latestOptimization: StrategyOptimizationRun | null;
  latestStrategyTestBatch: StrategyTestBatch | null;
  onArchiveStrategyWindow: () => void;
  onApplyOptimizationCandidate: (candidate: StrategyOptimizationCandidate) => void;
  onDateChange: (value: string) => void;
  onOpenStrategyConfig: () => void;
  onRunOptimization: () => void;
  onRunTestBatch: () => void;
  onSelectStrategyTestDay: (day: StrategyTestDayResult) => void;
  onSymbolChange: (value: string) => void;
  onToggleFullDayStrategyBars: (value: boolean) => void;
  optimizationBusy: boolean;
  selectedStrategy: StrategyConfig | null;
  selectedStrategyTestDay: StrategyTestDayResult | null;
  selectedStrategyTemplate: StrategyTemplate | null;
  selectedSymbol: string;
  showFullDayStrategyBars: boolean;
  strategyArchiveFeedback: StrategyRunFeedback | null;
  strategyDraftDirty: boolean;
  strategySaveBusy: boolean;
  strategyTestDayArchive: MarketMinuteArchive | null;
  strategyTestDayDetailBusy: boolean;
  strategyTestDayRun: StrategySignalRun | null;
  strategyTestBusy: boolean;
}) {
  const strategyStatus = props.selectedStrategy
    ? props.selectedStrategy.enabled
      ? { label: "已开启", tone: "ok" as const }
      : { label: "未开启", tone: "warn" as const }
    : null;
  const testStatus = props.latestStrategyTestBatch ? strategyTestStatusMeta[props.latestStrategyTestBatch.status] : null;
  const optimizationStatus = props.latestOptimization ? strategyOptimizationStatusMeta[props.latestOptimization.status] : null;
  const bestCandidate =
    props.latestOptimization?.candidates.find((candidate) => candidate.candidate_id === props.latestOptimization?.best_candidate_id) ??
    props.latestOptimization?.candidates.find((candidate) => candidate.status === "eligible") ??
    null;
  const optimizationParamKeys = props.latestOptimization ? Object.keys(props.latestOptimization.search_space) : [];

  return (
    <section className="strategyTestingWorkspace" aria-label="策略测试工作区">
      <section className="panel strategyTestingHero">
        <header>
          <div>
            <h2>
              <SlidersHorizontal size={18} />
              策略测试
            </h2>
            <p className="panelNote">配置、单日测试、最近 30 个交易日复盘和参数优化均只读取已归档分钟线</p>
          </div>
          <div className="headerActions">
            {strategyStatus ? <span className={`statusPill ${strategyStatus.tone}`}>{strategyStatus.label}</span> : null}
            <label className="compactControl">
              <span>截止日期</span>
              <input value={props.date} onChange={(event) => props.onDateChange(event.target.value)} type="date" />
            </label>
            <label className="compactControl">
              <span>测试标的</span>
              <input
                list="symbolOptions"
                placeholder="输入标的"
                value={props.selectedSymbol}
                onChange={(event) => props.onSymbolChange(event.target.value.trim().toUpperCase())}
                type="text"
              />
            </label>
          </div>
        </header>
        <div className="strategyWorkflowSteps" aria-label="策略测试流程">
          <span>策略配置</span>
          <span>策略测试</span>
          <span>测试复盘（最近30个交易日）</span>
          <span>策略优化</span>
        </div>
      </section>

      <section className="strategyTestingGrid">
        <section className="panel strategyConfigSummary">
          <header>
            <div>
              <h2>
                <Pencil size={18} />
                策略配置
              </h2>
              <p className="panelNote">参数保存到 strategy_configs；历史 run 保留当时参数快照</p>
            </div>
            <button className="smallButton primary" onClick={props.onOpenStrategyConfig} type="button">
              <SlidersHorizontal size={15} />
              编辑配置
            </button>
          </header>
          {props.selectedStrategy ? (
            <>
              <dl className="compactFacts">
                <div>
                  <dt>策略</dt>
                  <dd>{props.selectedStrategy.name}</dd>
                </div>
                <div>
                  <dt>模板</dt>
                  <dd>{props.selectedStrategy.template_version}</dd>
                </div>
                <div>
                  <dt>params_hash</dt>
                  <dd className="monoWrap">{shortHash(props.selectedStrategy.params_hash)}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>{props.selectedStrategy.enabled ? "已开启" : "未开启"}</dd>
                </div>
              </dl>
              {props.strategyDraftDirty ? (
                <div className="strategyRunFeedback warn">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>有未保存配置</strong>
                    <span>保存后再运行策略测试，避免旧参数进入 run artifact。</span>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <EmptyState icon={<CircleSlash size={18} />} title="暂无策略配置" detail="后端返回策略模板后可新增策略实例" />
          )}
        </section>

        <section className="panel strategyBatchPanel">
          <header>
            <div>
              <h2>
                <ListChecks size={18} />
                测试复盘（最近30个交易日）
              </h2>
              <p className="panelNote">窗口来自已归档 symbol/day 分钟线；覆盖不足会保留失败状态</p>
            </div>
            <div className="headerActions">
              {testStatus ? <span className={`statusPill ${testStatus.tone}`}>{testStatus.label}</span> : null}
              <button
                className="smallButton"
                onClick={props.onArchiveStrategyWindow}
                disabled={!props.selectedSymbol || props.archiveBusy}
                type="button"
              >
                {props.archiveBusy ? <RefreshCw className="spin" size={14} /> : <RefreshCw size={14} />}
                {props.archiveBusy ? "拉取中" : "拉取30日数据"}
              </button>
              <button
                className="smallButton primary"
                onClick={props.onRunTestBatch}
                disabled={!props.selectedStrategy || !props.selectedSymbol || props.strategyTestBusy || props.strategyDraftDirty}
                type="button"
              >
                {props.strategyTestBusy ? <RefreshCw className="spin" size={14} /> : <Play size={14} />}
                {props.strategyTestBusy ? "复盘中" : "运行30日"}
              </button>
            </div>
          </header>
          {props.strategyArchiveFeedback ? (
            <div className={`strategyRunFeedback ${props.strategyArchiveFeedback.tone}`} role="status" aria-live="polite">
              <RefreshCw size={16} className={props.archiveBusy ? "spin" : undefined} />
              <div>
                <strong>{props.strategyArchiveFeedback.title}</strong>
                <span>{props.strategyArchiveFeedback.detail}</span>
              </div>
            </div>
          ) : null}
          {props.latestStrategyTestBatch ? (
            <>
              <StrategyResearchMetrics
                closedGroupCount={props.latestStrategyTestBatch.day_results.reduce(
                  (total, day) => total + day.closed_group_count,
                  0
                )}
                coverageRatio={props.latestStrategyTestBatch.coverage_ratio}
                maxDrawdown={props.latestStrategyTestBatch.max_drawdown}
                profitFactor={props.latestStrategyTestBatch.profit_factor}
                signalCount={props.latestStrategyTestBatch.signal_count}
                totalPnl={props.latestStrategyTestBatch.total_pnl}
                winRate={props.latestStrategyTestBatch.win_rate}
              />
              {props.latestStrategyTestBatch.failure_reason ? (
                <div className="statusReason">
                  <AlertTriangle size={16} />
                  <span>
                    {formatStrategyFailureReason(props.latestStrategyTestBatch.failure_reason) ??
                      props.latestStrategyTestBatch.failure_reason}
                  </span>
                </div>
              ) : null}
              <div className="strategyTestReviewLayout">
                <div className="strategyDayResultList" aria-label="策略测试日列表">
                  {props.latestStrategyTestBatch.day_results.map((day) => {
                    const status = strategyStatusMeta[day.status];
                    const isSelected = props.selectedStrategyTestDay?.day_result_id === day.day_result_id;
                    return (
                      <button
                        aria-pressed={isSelected}
                        className={isSelected ? "strategyDayResult active" : "strategyDayResult"}
                        key={day.day_result_id}
                        onClick={() => props.onSelectStrategyTestDay(day)}
                        type="button"
                      >
                        <div>
                          <strong>{day.trade_date}</strong>
                          <span className={`statusPill ${status.tone}`}>{status.label}</span>
                        </div>
                        <small>
                          信号 {formatInteger(day.signal_count)} · PnL {formatPnl(day.total_pnl)} · hash {shortHash(day.indicator_hash)}
                        </small>
                        {day.failure_reason ? <small>{formatStrategyFailureReason(day.failure_reason) ?? day.failure_reason}</small> : null}
                      </button>
                    );
                  })}
                </div>
                <StrategyTestDayDetail
                  archive={props.strategyTestDayArchive}
                  busy={props.strategyTestDayDetailBusy}
                  day={props.selectedStrategyTestDay}
                  run={props.strategyTestDayRun}
                  selectedStrategy={props.selectedStrategy}
                  showFullDayStrategyBars={props.showFullDayStrategyBars}
                  symbol={props.selectedSymbol}
                  onToggleFullDayStrategyBars={props.onToggleFullDayStrategyBars}
                />
              </div>
            </>
          ) : (
            <EmptyState icon={<Clock3 size={18} />} title="尚未运行30日测试" detail="运行后会保存 test batch 和逐日 run 证据。" />
          )}
        </section>

        <section className="panel strategyOptimizationPanel">
          <header>
            <div>
              <h2>
                <Activity size={18} />
                策略优化
              </h2>
              <p className="panelNote">默认目标 stable_profitability_v1；最佳参数不会自动覆盖配置</p>
            </div>
            <div className="headerActions">
              {optimizationStatus ? (
                <span className={`statusPill ${optimizationStatus.tone}`}>{optimizationStatus.label}</span>
              ) : null}
              <button
                className="smallButton primary"
                onClick={props.onRunOptimization}
                disabled={!props.selectedStrategy || !props.selectedSymbol || props.optimizationBusy || props.strategyDraftDirty}
                type="button"
              >
                {props.optimizationBusy ? <RefreshCw className="spin" size={14} /> : <Play size={14} />}
                {props.optimizationBusy ? "优化中" : "运行优化"}
              </button>
            </div>
          </header>
          {props.latestOptimization ? (
            <>
              <dl className="compactFacts">
                <div>
                  <dt>候选数</dt>
                  <dd>{formatInteger(props.latestOptimization.candidate_count)}</dd>
                </div>
                <div>
                  <dt>可候选</dt>
                  <dd>{formatInteger(props.latestOptimization.eligible_candidate_count)}</dd>
                </div>
                <div>
                  <dt>最佳分</dt>
                  <dd>{formatNullable(props.latestOptimization.best_stability_score)}</dd>
                </div>
                <div>
                  <dt>scope hash</dt>
                  <dd className="monoWrap">{shortHash(props.latestOptimization.archive_scope_hash)}</dd>
                </div>
              </dl>
              {props.latestOptimization.failure_reason ? (
                <div className="statusReason">
                  <AlertTriangle size={16} />
                  <span>
                    {formatStrategyFailureReason(props.latestOptimization.failure_reason) ??
                      props.latestOptimization.failure_reason}
                  </span>
                </div>
              ) : null}
              {bestCandidate ? (
                <div className="bestCandidateCallout">
                  <div>
                    <strong>当前最佳候选 #{bestCandidate.rank}</strong>
                    <span>
                      PnL {formatPnl(bestCandidate.total_pnl)} · 胜率 {formatPercentValue(bestCandidate.win_rate)} ·
                      稳定分 {formatNullable(bestCandidate.stability_score)}
                    </span>
                  </div>
                  <button
                    className="smallButton primary"
                    disabled={props.strategySaveBusy || bestCandidate.status !== "eligible"}
                    onClick={() => props.onApplyOptimizationCandidate(bestCandidate)}
                    type="button"
                  >
                    <Save size={14} />
                    套用参数
                  </button>
                </div>
              ) : null}
              {props.latestOptimization.candidates.length > 0 ? (
                <section className="candidateGroupSection" aria-label="策略优化候选参数组">
                  <div className="candidateGroupHeader">
                    <div>
                      <strong>策略优化候选组</strong>
                      <span>展示搜索空间内的候选参数项值；高亮项表示与当前配置不同</span>
                    </div>
                    <span className="statusPill info">
                      {formatInteger(props.latestOptimization.candidates.length)} 组
                    </span>
                  </div>
                  <div className="strategyCandidateList">
                    {props.latestOptimization.candidates.map((candidate) => (
                      <StrategyOptimizationCandidateCard
                        candidate={candidate}
                        currentParams={props.selectedStrategy?.params ?? {}}
                        isBest={candidate.candidate_id === props.latestOptimization?.best_candidate_id}
                        key={candidate.candidate_id}
                        onApply={props.onApplyOptimizationCandidate}
                        paramKeys={optimizationParamKeys}
                        strategySaveBusy={props.strategySaveBusy}
                        template={props.selectedStrategyTemplate}
                      />
                    ))}
                  </div>
                </section>
              ) : (
                <EmptyState icon={<CircleSlash size={18} />} title="没有候选组" detail="当前优化 run 未返回可展示候选。" />
              )}
            </>
          ) : (
            <EmptyState icon={<CircleSlash size={18} />} title="尚未运行策略优化" detail="优化会保存候选参数和逐日结果，不会自动修改策略配置。" />
          )}
        </section>
      </section>
    </section>
  );
}

function StrategyOptimizationCandidateCard(props: {
  candidate: StrategyOptimizationCandidate;
  currentParams: Record<string, StrategyParamValue>;
  isBest: boolean;
  onApply: (candidate: StrategyOptimizationCandidate) => void;
  paramKeys: string[];
  strategySaveBusy: boolean;
  template: StrategyTemplate | null;
}) {
  const status = strategyCandidateStatusMeta[props.candidate.status];
  const paramItems = optimizationCandidateParamItems(
    props.candidate.params,
    props.currentParams,
    props.template,
    props.paramKeys
  );

  return (
    <article className={props.isBest ? "strategyCandidate isBest" : "strategyCandidate"}>
      <div className="candidateTopline">
        <div className="candidateIdentity">
          <span className="candidateRank">#{props.candidate.rank}</span>
          <div>
            <strong>候选参数组 #{props.candidate.rank}</strong>
            <small>params {shortHash(props.candidate.params_hash)}</small>
          </div>
        </div>
        <div className="candidateBadges">
          {props.isBest ? <span className="statusPill ok">当前最佳</span> : null}
          <span className={`statusPill ${status.tone}`}>{status.label}</span>
        </div>
      </div>

      <dl className="candidateMetricGrid">
        <div>
          <dt>稳定分</dt>
          <dd>{formatNullable(props.candidate.stability_score)}</dd>
        </div>
        <div>
          <dt>PnL</dt>
          <dd>{formatPnl(props.candidate.total_pnl)}</dd>
        </div>
        <div>
          <dt>胜率</dt>
          <dd>{formatPercentValue(props.candidate.win_rate)}</dd>
        </div>
        <div>
          <dt>盈亏比</dt>
          <dd>{formatNullable(props.candidate.profit_factor)}</dd>
        </div>
        <div>
          <dt>回撤</dt>
          <dd>{formatNullable(props.candidate.max_drawdown)}</dd>
        </div>
        <div>
          <dt>覆盖</dt>
          <dd>{formatPercentValue(props.candidate.coverage_ratio)}</dd>
        </div>
      </dl>

      <div className="candidateParamSummary">{formatParamDiff(props.candidate.params, props.currentParams)}</div>

      {paramItems.length > 0 ? (
        <dl className="candidateParamGrid">
          {paramItems.map((item) => (
            <div className={item.changed ? "candidateParam changed" : "candidateParam"} key={item.key}>
              <dt>{item.label}</dt>
              <dd>{item.valueLabel}</dd>
              <small>
                {item.key}
                {item.changed ? ` · 当前 ${item.currentValueLabel}` : " · 与当前一致"}
              </small>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mutedText">该候选没有可展示参数项值。</p>
      )}

      {props.candidate.failure_reason ? (
        <div className="candidateFailure">
          <AlertTriangle size={14} />
          <span>{formatStrategyFailureReason(props.candidate.failure_reason) ?? props.candidate.failure_reason}</span>
        </div>
      ) : null}

      <button
        className="smallButton"
        disabled={props.strategySaveBusy || props.candidate.status !== "eligible"}
        onClick={() => props.onApply(props.candidate)}
        type="button"
      >
        <Save size={14} />
        套用本组
      </button>
    </article>
  );
}

function StrategyTestDayDetail(props: {
  archive: MarketMinuteArchive | null;
  busy: boolean;
  day: StrategyTestDayResult | null;
  onToggleFullDayStrategyBars: (value: boolean) => void;
  run: StrategySignalRun | null;
  selectedStrategy: StrategyConfig | null;
  showFullDayStrategyBars: boolean;
  symbol: string;
}) {
  const signals = props.run?.signals ?? [];
  const signalRunScope = useMemo(() => strategySignalRunScope(signals, 10), [signals]);
  const signalReplay = useMemo(() => buildStrategySignalGroups(signals), [signals]);
  const fallbackSignalPerformance = useMemo(
    () => buildStrategySignalPerformance(signalReplay.groups),
    [signalReplay.groups]
  );
  const signalPerformance = props.run?.signal_performance ?? fallbackSignalPerformance;
  const status = props.day ? strategyStatusMeta[props.day.status] : null;
  const canRenderChart =
    props.day?.status === "completed" &&
    props.run?.status === "completed" &&
    Boolean(props.archive && props.archive.bars.length > 0);

  return (
    <section className="strategyTestDayDetail" aria-label="策略测试单日复盘">
      <header className="strategyTestDayHeader">
        <div>
          <strong>单日复盘</strong>
          <small>{props.day ? `${props.day.trade_date} · ${props.symbol}` : "从左侧日列表选择"}</small>
        </div>
        <div className="headerActions">
          {status ? <span className={`statusPill ${status.tone}`}>{status.label}</span> : null}
          <label className="toggleControl">
            <input
              checked={props.showFullDayStrategyBars}
              onChange={(event) => props.onToggleFullDayStrategyBars(event.currentTarget.checked)}
              type="checkbox"
            />
            <span>展示全天K线</span>
          </label>
        </div>
      </header>

      {!props.day ? (
        <EmptyState icon={<Clock3 size={18} />} title="选择测试日" detail="运行 30 日测试后，从日列表选择一日查看图形与订单明细。" />
      ) : (
        <>
          <StrategyReplayStatus
            date={props.day.trade_date}
            run={props.run}
            selectedStrategy={props.selectedStrategy}
            symbol={props.symbol}
          />
          {props.busy ? (
            <div className="strategyRunFeedback info" role="status" aria-live="polite">
              <RefreshCw className="spin" size={16} />
              <div>
                <strong>后台准备单日复盘</strong>
                <span>30 日结果载入后会提前缓存归档分钟线与策略 run read model。</span>
              </div>
            </div>
          ) : null}
          {props.day.failure_reason ? (
            <div className="statusReason">
              <AlertTriangle size={16} />
              <span>{formatStrategyFailureReason(props.day.failure_reason) ?? props.day.failure_reason}</span>
            </div>
          ) : null}

          {canRenderChart && props.archive && props.run ? (
            <>
              <dl className="signalRunFacts strategyTestDayFacts">
                <div>
                  <dt>信号</dt>
                  <dd>{formatInteger(signals.length)}</dd>
                </div>
                <div>
                  <dt>闭合组</dt>
                  <dd>{formatInteger(signalReplay.groups.length)}</dd>
                </div>
                <div>
                  <dt>PnL</dt>
                  <dd className={signalStatTone(signalPerformance.total_pnl)}>{formatPnl(signalPerformance.total_pnl)}</dd>
                </div>
                <div>
                  <dt>胜率</dt>
                  <dd>{formatSignalWinRate(signalPerformance)}</dd>
                </div>
                <div className="hashFact">
                  <dt>bars hash</dt>
                  <dd className="monoWrap">{shortHash(props.run.bars_hash)}</dd>
                </div>
                <div className="hashFact">
                  <dt>indicator hash</dt>
                  <dd className="monoWrap">{shortHash(props.run.indicator_hash)}</dd>
                </div>
              </dl>
              <MinuteCandleChart
                allowStrategySignalDetails={false}
                archive={props.archive}
                chartVariant="compact"
                fills={[]}
                scope={props.showFullDayStrategyBars ? undefined : signalRunScope}
                showStrategyMarkers
                showTradeMarkers={false}
                strategyRun={props.run}
              />

              {signalReplay.orphanSignals.length > 0 ? (
                <div className="statusReason">
                  <AlertTriangle size={16} />
                  <span>{formatInteger(signalReplay.orphanSignals.length)} 个信号缺少可追溯 entry，已从订单组明细中排除。</span>
                </div>
              ) : null}

              {signalReplay.groups.length > 0 ? (
                <div className="signalGroupList strategyDayOrderList">
                  {signalReplay.groups.map((group, index) => (
                    <details className="signalGroupCard strategyDayOrderCard" key={group.id} onToggle={scrollOpenDetailsIntoView}>
                      <summary className="signalGroupSummary">
                        <span className="signalGroupTitle">
                          <ChevronDown className="signalGroupChevron" size={16} />
                          <span className={`strategySignalPill ${group.entry.action.toLowerCase()}`}>
                            #{index + 1} {formatStrategyAction(group.entry.action)}
                          </span>
                          <span className={group.side === "LONG" ? "sidePill buy" : "sidePill sell"}>
                            {formatDirection(group.side)}
                          </span>
                          <span className={group.status === "closed" ? "statusPill ok" : "statusPill warn"}>
                            {group.status === "closed" ? "已闭合" : "持仓中"}
                          </span>
                        </span>
                        <span className="signalGroupMeta">
                          {formatClock(group.openedAt)}
                          {group.closedAt ? ` -> ${formatClock(group.closedAt)}` : " -> 未闭合"}
                          {" · "}
                          {formatInteger(group.signals.length)} 信号
                        </span>
                      </summary>
                      <div className="signalGroupBody">
                        <StrategySignalOrderDetails group={group} />
                      </div>
                    </details>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={<CircleSlash size={18} />}
                  title={props.run.signal_count === 0 ? "该日 0 信号" : "未形成可展示订单组"}
                  detail="该日策略 run 已保存，但没有可组成 entry/exit 订单明细的信号。"
                />
              )}
            </>
          ) : props.busy ? null : props.day.status !== "completed" ? (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="该日未完成策略测试"
              detail="缺归档、行情不可用、分钟线不足或策略禁用时，不渲染成功图。"
            />
          ) : !props.archive || props.archive.bars.length === 0 ? (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="缺少该日分钟归档"
              detail="单日图形只读取 market_minute_archives；未找到可用归档时不补假数据。"
            />
          ) : (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="缺少该日策略 run"
              detail="日结果指向的 strategy_signal_runs read model 未返回，暂不渲染图形和订单明细。"
            />
          )}
        </>
      )}
    </section>
  );
}

function StrategyResearchMetrics(props: {
  closedGroupCount: number;
  coverageRatio: number;
  maxDrawdown: number;
  profitFactor: number | null;
  signalCount: number;
  totalPnl: number;
  winRate: number;
}) {
  return (
    <dl className="strategyResearchMetrics">
      <div>
        <dt>信号</dt>
        <dd>{formatInteger(props.signalCount)}</dd>
      </div>
      <div>
        <dt>闭合组</dt>
        <dd>{formatInteger(props.closedGroupCount)}</dd>
      </div>
      <div>
        <dt>PnL</dt>
        <dd>{formatPnl(props.totalPnl)}</dd>
      </div>
      <div>
        <dt>胜率</dt>
        <dd>{formatPercentValue(props.winRate)}</dd>
      </div>
      <div>
        <dt>盈亏比</dt>
        <dd>{formatNullable(props.profitFactor)}</dd>
      </div>
      <div>
        <dt>回撤</dt>
        <dd>{formatNullable(props.maxDrawdown)}</dd>
      </div>
      <div>
        <dt>覆盖</dt>
        <dd>{formatPercentValue(props.coverageRatio)}</dd>
      </div>
    </dl>
  );
}

function getStrategyRunFeedback(run: StrategySignalRun): StrategyRunFeedback {
  const status = strategyStatusMeta[run.status];
  if (run.status === "completed" && run.signal_count === 0) {
    return {
      tone: "warn",
      title: "策略复盘已完成：0 个策略信号",
      detail: "后端已完成计算，但当前归档分钟线没有触发开仓或平仓条件。"
    };
  }
  if (run.status === "completed") {
    return {
      tone: "ok",
      title: `策略复盘已完成：${formatInteger(run.signal_count)} 个策略信号`,
      detail: "后端已生成策略信号，蜡烛图会按当前图层开关展示开平仓点。"
    };
  }

  const detailByStatus: Partial<Record<StrategyRunStatus, string>> = {
    missing_archive: "当前日期或标的缺少已归档分钟线，策略不会渲染假信号。",
    non_available_archive: "当前分钟线归档不可用，请先修复行情归档状态后再复盘。",
    insufficient_bars: "当前归档分钟线不足以完成策略指标窗口计算。",
    strategy_disabled: "当前策略未开启，后端已拒绝生成策略信号。",
    failed: "后端策略引擎运行失败。"
  };

  return {
    tone: status?.tone ?? "warn",
    title: `策略复盘${status?.label ?? run.status}`,
    detail:
      formatStrategyFailureReason(run.failure_reason) ??
      detailByStatus[run.status] ??
      "当前策略 run 未产生可渲染信号。"
  };
}

function formatStrategyFailureReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  const [, rawSymbols = "QQQ,SMH"] = reason.split(":");
  const symbols = rawSymbols
    .split(",")
    .map((symbol) => symbol.trim())
    .filter(Boolean)
    .join("、");
  if (reason.startsWith("momentum_context_archive_required:")) {
    return `缺少动能过滤分钟线归档：${symbols || "QQQ、SMH"}。请先运行 Yahoo 分钟线归档，再重新执行策略复盘；系统不会用缺失行情渲染成功信号。`;
  }
  if (reason.startsWith("momentum_context_archive_unavailable:")) {
    return `动能过滤分钟线归档不可用：${symbols || "QQQ、SMH"}。请检查 Yahoo 归档状态，必要时 force 重跑归档后再执行策略复盘。`;
  }
  const coverageMatch = reason.match(/^required_(\d+)_archived_trading_days_found_(\d+)$/);
  if (coverageMatch) {
    return `最近 ${coverageMatch[1]} 个交易日归档覆盖不足，当前只找到 ${coverageMatch[2]} 个。请先在策略测试页拉取30日数据，再重新运行测试。`;
  }
  return reason;
}

function formatArchiveFailureReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  if (reason === "yahoo_http_422") {
    return "Yahoo 拒绝 1 分钟历史请求，常见于日期超出 1 分钟数据可取窗口或 provider 不接受该请求窗口；系统已保存为行情不可用，不会渲染成功图。";
  }
  if (reason.startsWith("yahoo_http_")) {
    return `Yahoo 返回 HTTP ${reason.replace("yahoo_http_", "")}，系统已保存为 provider_failed。`;
  }
  if (reason.startsWith("yahoo_url_error:")) {
    return `Yahoo 网络请求失败：${reason.replace("yahoo_url_error:", "")}。`;
  }
  if (reason.startsWith("yahoo_chart_error:")) {
    return `Yahoo chart 响应失败：${reason.replace("yahoo_chart_error:", "")}。`;
  }
  if (reason === "no_bars_returned") {
    return "provider 没有返回分钟线 bars，系统不会渲染成功图。";
  }
  if (reason === "partial_provider_window") {
    return "provider 只返回了部分请求窗口，归档保留为 partial 状态。";
  }
  if (reason === "provider_timezone_conflict") {
    return "provider 返回的时区与请求窗口不一致，请先复查归档时区。";
  }
  return reason;
}

function StrategyReplayStatus(props: {
  date: string;
  run: StrategySignalRun | null;
  selectedStrategy: StrategyConfig | null;
  symbol: string;
}) {
  if (!props.selectedStrategy) return null;
  const status = props.run ? strategyStatusMeta[props.run.status] : null;
  const strategyName = props.selectedStrategy.name;
  let tone: "info" | "ok" | "warn" | "danger" = props.selectedStrategy.enabled ? "info" : "warn";
  let title = "策略复盘未运行";
  let detail = `${strategyName} 已开启，但 ${props.date} ${props.symbol || "当前标的"} 还没有历史策略 run。点击“策略复盘”后才会生成 0 或非 0 的策略信号。`;

  if (!props.selectedStrategy.enabled) {
    title = "策略未开启";
    detail = `${strategyName} 当前停用，后端不会为当前标的生成策略 run。`;
  } else if (props.run) {
    tone = status?.tone ?? "info";
    if (props.run.status === "completed" && props.run.signal_count === 0) {
      tone = "warn";
      title = "策略复盘已完成：0 个策略信号";
      detail = "后端已读取归档分钟线并完成计算，但没有触发开仓或平仓条件；这不是蜡烛图渲染失败。";
    } else if (props.run.status === "completed") {
      tone = "ok";
      title = `策略复盘已完成：${formatInteger(props.run.signal_count)} 个策略信号`;
      detail = "策略开平仓标记默认显示，标记来自后端 strategy run read model。";
    } else {
      title = status?.label ?? props.run.status;
      detail = formatStrategyFailureReason(props.run.failure_reason) ?? "当前策略 run 未产生可渲染信号。";
    }
  }

  return (
    <div className={`strategyReplayStatus ${tone}`}>
      <ListChecks size={16} />
      <div>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      {props.run ? (
        <dl>
          <div>
            <dt>状态</dt>
            <dd>{status?.label ?? props.run.status}</dd>
          </div>
          <div>
            <dt>信号</dt>
            <dd>{formatInteger(props.run.signal_count)}</dd>
          </div>
          <div>
            <dt>Bars</dt>
            <dd>{formatInteger(props.run.indicator_series.length)}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function StrategyDescription(props: {
  enabled: boolean;
  latestRun: StrategySignalRun | null;
  params: Record<string, StrategyParamValue>;
  strategyName: string;
  templateKey: string;
  templateVersion: string;
}) {
  const runStatus = props.latestRun ? strategyStatusMeta[props.latestRun.status] : null;
  const bbPeriod = formatStrategyParam(props.params.bb_period);
  const bbStddev = formatStrategyParam(props.params.bb_stddev);
  const adxPeriod = formatStrategyParam(props.params.adx_period);
  const adxTrendThreshold = formatStrategyParam(props.params.adx_trend_threshold);
  const adxChopThreshold = formatStrategyParam(props.params.adx_chop_threshold);
  const atrPeriod = formatStrategyParam(props.params.atr_period);
  const atrStopMultiplier = formatStrategyParam(props.params.atr_stop_multiplier);
  const rsiPeriod = formatStrategyParam(props.params.rsi_period);
  const volumeAveragePeriod = formatStrategyParam(props.params.volume_average_period);
  const volumeMultiplier = formatStrategyParam(props.params.volume_multiplier);
  const squeezePercentile = formatStrategyParam(props.params.squeeze_percentile);
  const setupMinutes = formatStrategyParam(props.params.setup_minutes);
  const bodyStrengthRatio = formatStrategyParam(props.params.body_strength_ratio);
  const riskReward = formatStrategyParam(props.params.risk_reward);
  const exitEmaPeriod = formatStrategyParam(props.params.exit_ema_period);
  const minAbsoluteBandwidth = formatStrategyParam(props.params.min_absolute_bandwidth);
  const localWindow = formatStrategyParam(props.params.local_window);
  const shadowRatio = formatStrategyParam(props.params.shadow_ratio);
  const tickSize = formatStrategyParam(props.params.tick_size);
  const stopTickOffset = formatStrategyParam(props.params.stop_tick_offset);
  const maxHoldingBars = formatStrategyParam(props.params.max_holding_bars);
  const exitType = formatStrategyParam(props.params.exit_type);
  const startHour = formatStrategyParam(props.params.start_hour);
  const startMinute = formatStrategyParam(props.params.start_minute);
  const endHour = formatStrategyParam(props.params.end_hour);
  const endMinute = formatStrategyParam(props.params.end_minute);
  const pinShadowRatio = formatStrategyParam(props.params.pin_shadow_ratio);
  const swingLookback = formatStrategyParam(props.params.swing_lookback);
  const firstTargetExitFraction = formatStrategyParam(props.params.first_target_exit_fraction);
  const momentumContext = formatStrategyParam(props.params.momentum_context);
  const isLiquiditySweep = props.templateKey === "institutional_liquidity_sweep_v1";
  const isMomentumMeanReversion = props.templateKey === "momentum_mean_reversion_v1";

  return (
    <>
      <div className="strategyDescriptionHead">
        <div>
          <p className="eyebrow">完整策略描述</p>
          <h3>{props.strategyName}</h3>
          <small>{props.templateVersion}</small>
        </div>
        <span className={props.enabled ? "okPill" : "warningPill"}>{props.enabled ? "已开启" : "未开启"}</span>
      </div>

      {props.latestRun ? (
        <dl className="strategyDescriptionFacts">
          <div>
            <dt>标的</dt>
            <dd>{props.latestRun.symbol}</dd>
          </div>
          <div>
            <dt>信号</dt>
            <dd>{formatInteger(props.latestRun.signal_count)}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{runStatus?.label ?? props.latestRun.status}</dd>
          </div>
          <div>
            <dt>Bars</dt>
            <dd>{formatInteger(props.latestRun.indicator_series.length)}</dd>
          </div>
        </dl>
      ) : null}

      {props.latestRun?.failure_reason ? (
        <div className="statusReason">
          <AlertTriangle size={16} />
          <span>{formatStrategyFailureReason(props.latestRun.failure_reason) ?? props.latestRun.failure_reason}</span>
        </div>
      ) : null}

      {isMomentumMeanReversion ? (
        <>
          <section className="strategyRuleBlock">
            <h3>前置过滤</h3>
            <ol>
              <li>
                仅在美东时间 {startHour}:{String(startMinute).padStart(2, "0")} 至 {endHour}:{String(endMinute).padStart(2, "0")} 执行。
              </li>
              <li>动能过滤读取已归档 {momentumContext} 分钟线；缺任一归档时后端保存缺归档状态，不生成信号。</li>
              <li>做多池要求 QQQ 与 SMH 同时在各自 VWAP 上方；做空池要求两者同时在 VWAP 下方。</li>
              <li>
                ADX({adxPeriod}) 大于 {adxTrendThreshold} 时均值回归熔断；ADX 低于 {adxChopThreshold} 时才重新激活。
              </li>
              <li>过滤结果由后端指标序列保存，前端只展示 strategy run read model。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>开仓</h3>
            <ol>
              <li>
                使用 BB({bbPeriod}, {bbStddev})；做多观察标的跌破下轨，做空观察标的冲破上轨。
              </li>
              <li>
                观察 K 不操作；只有反转 K 收盘重新站上下轨，或跌回上轨下方，才在收盘价生成入场信号。
              </li>
              <li>
                反转形态支持 Pin Bar，要求影线占比不低于 {pinShadowRatio}，也支持吞没前一根反向实体。
              </li>
              <li>同一策略、标的和日期持仓中不重复开仓。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>止盈止损</h3>
            <ol>
              <li>
                硬止损按 ATR({atrPeriod}) 动态计算：多头为入场价减 {atrStopMultiplier} 倍 ATR，空头为入场价加 {atrStopMultiplier} 倍 ATR。
              </li>
              <li>近 {swingLookback} 根 K 的波谷或波峰仍进入信号指标，作为复查反转位置的上下文。</li>
              <li>
                第一目标为布林中轨，平仓比例为 {firstTargetExitFraction}；触达后剩余仓位止损上移到入场价。
              </li>
              <li>第二目标为布林对侧外轨；若保本止损先触发，则剩余仓位按 break-even 出场。</li>
              <li>该策略只生成历史复盘信号，不修改 committed fills，也不触发自动下单。</li>
            </ol>
          </section>
        </>
      ) : isLiquiditySweep ? (
        <>
          <section className="strategyRuleBlock">
            <h3>开仓</h3>
            <ol>
              <li>
                多头只在 VWAP 上方寻找过去 {localWindow} 根分钟线的局部低点，空头只在 VWAP 下方寻找局部高点。
              </li>
              <li>
                当前 1 分钟 K 必须扫破局部高低点后收回，影线占整根 K 的比例不低于 {shadowRatio}。
              </li>
              <li>
                成交量至少为前 {volumeAveragePeriod} 分钟均量的 {volumeMultiplier} 倍，确认扫损流动性已经释放。
              </li>
              <li>信号在扫损 K 收盘后生成；同一策略、标的和日期持仓中不再重复开仓。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>平仓</h3>
            <ol>
              <li>出场模式为 {exitType}，历史 run 只建模 OCO 止盈止损触达，不发送真实券商订单。</li>
              <li>
                止盈优先取 BB({bbPeriod}, {bbStddev}) 中轨与 {riskReward}:1 盈亏比目标中更近的一档。
              </li>
              <li>若 {maxHoldingBars} 根 K 内未触发止盈或止损，按当前收盘价生成时间退出信号。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>止盈止损</h3>
            <ol>
              <li>
                多头止损放在扫损 K 最低点下方 {stopTickOffset} 个 tick；空头止损放在扫损 K 最高点上方同等距离。
              </li>
              <li>当前 tick size 为 {tickSize}，止盈止损价格和指标证据由后端策略 run 保存。</li>
              <li>该策略只生成复盘信号，不修改 committed fills 的成交价格、数量或时间。</li>
            </ol>
          </section>
        </>
      ) : (
        <>
          <section className="strategyRuleBlock">
            <h3>开仓</h3>
            <ol>
              <li>
                使用 BB({bbPeriod}, {bbStddev})，突破前需要至少 {setupMinutes} 分钟 setup。
              </li>
              <li>
                布林带相对带宽低于历史 {squeezePercentile}% 分位，且绝对带宽大于 {minAbsoluteBandwidth}。
              </li>
              <li>多头要求价格在 VWAP 上方突破上轨，空头要求价格在 VWAP 下方跌破下轨。</li>
              <li>
                成交量至少为前 {volumeAveragePeriod} 分钟均量的 {volumeMultiplier} 倍，实体强度不低于{" "}
                {bodyStrengthRatio}，RSI({rsiPeriod}) 多头大于 50、空头小于 50。
              </li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>平仓</h3>
            <ol>
              <li>同一策略、标的和日期持仓中不再开新信号。</li>
              <li>
                单纯跌回或升回布林带外轨内部不触发出场；多头必须跌破 {exitEmaPeriod} EMA 或布林中轨，空头按镜像条件处理。
              </li>
              <li>止损和 2:1 目标仍优先于出场缓冲触发。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>止盈止损</h3>
            <ol>
              <li>多头止损取布林中轨与突破 K 低点中较近位置，空头取布林中轨与突破 K 高点中较近位置。</li>
              <li>
                止盈目标按风险空间的 {riskReward} 倍计算；历史 run 使用 high/low 触达建模为被动止盈成交。
              </li>
              <li>该策略只生成复盘信号，不向券商或 STP 发送真实限价单。</li>
            </ol>
          </section>
        </>
      )}

      {props.latestRun?.indicator_hash ? <small className="monoWrap">indicator {shortHash(props.latestRun.indicator_hash)}</small> : null}
    </>
  );
}

function TradeReplayModal(props: { group: TradeGroup; archive: MarketMinuteArchive | null; onClose: () => void }) {
  const evaluation = props.group.evaluation;
  const archiveStatus = props.archive ? marketStatusMeta[props.archive.data_status] : null;
  return (
    <div className="modalBackdrop" role="dialog" aria-modal="true" aria-label={`${props.group.symbol} 交易回放`}>
      <section className="replayModal">
        <header className="modalHeader">
          <div>
            <p className="eyebrow">Trade Replay</p>
            <h2>
              <BarChart3 size={18} />
              {props.group.symbol} {formatDirection(props.group.direction)} 回放
            </h2>
            <p className="panelNote">
              {formatDateTime(props.group.opened_at)} 至 {props.group.closed_at ? formatDateTime(props.group.closed_at) : "未清仓"}
            </p>
          </div>
          <div className="headerActions">
            {archiveStatus ? <span className={`statusPill ${archiveStatus.tone}`}>{archiveStatus.label}</span> : null}
            <button className="iconButton" onClick={props.onClose} aria-label="关闭回放弹层" title="关闭">
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="replayGrid">
          <section className="replayChartPane">
            {props.archive && props.archive.bars.length > 0 ? (
              <>
                <div className="chartMeta">
                  <span>{props.archive.provider.toUpperCase()}</span>
                  <span>Bars {formatInteger(props.archive.bar_count)}</span>
                  <span>VWAP {formatNullable(props.archive.vwap)}</span>
                  <span>High {formatNullable(props.archive.day_high)}</span>
                  <span>Low {formatNullable(props.archive.day_low)}</span>
                  <span>Volume {formatInteger(props.archive.volume_context.total_volume)}</span>
                  <span className="monoWrap">hash {shortHash(props.archive.bars_hash)}</span>
                </div>
                <MinuteCandleChart
                  archive={props.archive}
                  fills={props.group.fills}
                  scope={tradeGroupScope(props.group, 10)}
                  tradeMarkerVariant="replay"
                />
                <TradeReplayOrderDetails group={props.group} />
                {props.archive.failure_reason ? (
                  <div className="statusReason">
                    <AlertTriangle size={16} />
                    <span>{formatArchiveFailureReason(props.archive.failure_reason) ?? props.archive.failure_reason}</span>
                  </div>
                ) : null}
              </>
            ) : props.archive ? (
              <EmptyState
                icon={<AlertTriangle size={18} />}
                title="分钟线不可用"
                detail={formatArchiveFailureReason(props.archive.failure_reason) ?? "provider 返回缺数据状态，系统不会渲染成功图表。"}
              />
            ) : (
              <EmptyState icon={<Clock3 size={18} />} title="尚未取得分钟线" detail="Replay 会尝试读取或归档整日分钟线。" />
            )}
          </section>

          <aside className="replaySidePane">
            <dl className="compactFacts">
              <div>
                <dt>数量</dt>
                <dd>{formatInteger(props.group.total_quantity)}</dd>
              </div>
              <div>
                <dt>持仓</dt>
                <dd>{formatHoldingMinutes(props.group.holding_minutes)}</dd>
              </div>
              <div>
                <dt>PnL</dt>
                <dd>{props.group.pnl === null ? "N/A" : formatPnl(props.group.pnl)}</dd>
              </div>
              <div>
                <dt>最大回撤</dt>
                <dd className={positionDrawdownTone(props.group.position_drawdown)}>
                  {formatPositionDrawdown(props.group.position_drawdown)}
                </dd>
              </div>
              <div>
                <dt>Entry</dt>
                <dd>{formatNullable(props.group.avg_entry_price)}</dd>
              </div>
              <div>
                <dt>Exit</dt>
                <dd>{formatNullable(props.group.avg_exit_price)}</dd>
              </div>
              <div>
                <dt>Trace</dt>
                <dd>{formatInteger(props.group.fill_count)} fills</dd>
              </div>
            </dl>

            <TradeReplayDrawdownEvidence drawdown={props.group.position_drawdown} />

            <section className="evaluationBox">
              <div className="evaluationHead">
                <span className={`gradePill ${evaluationTone(evaluation.evaluation_status, evaluation.grade)}`}>
                  {formatEvaluationGrade(evaluation)}
                </span>
                <strong>{evaluation.score === null ? "N/A" : decimalFormatter.format(evaluation.score)}</strong>
              </div>
              <p>{evaluation.summary}</p>
              <small>{evaluation.model_version}</small>
              {evaluation.strengths.length > 0 ? (
                <div className="tagList">
                  {evaluation.strengths.map((item) => (
                    <span className="okPill" key={item}>
                      {item}
                    </span>
                  ))}
                </div>
              ) : null}
              {evaluation.risks.length > 0 ? (
                <div className="tagList">
                  {evaluation.risks.map((item) => (
                    <span className="warningPill" key={item}>
                      {item}
                    </span>
                  ))}
                </div>
              ) : null}
            </section>

            <div className="factorList">
              {evaluation.factors.length > 0 ? (
                evaluation.factors.map((factor) => (
                  <div className="factorItem" key={factor.name}>
                    <span>{factor.label}</span>
                    <strong>
                      {decimalFormatter.format(factor.score)} / {formatInteger(factor.max_score)}
                    </strong>
                    <small>{factor.detail}</small>
                  </div>
                ))
              ) : (
                <EmptyState icon={<CircleSlash size={18} />} title="暂无评分因子" detail="行情不可用或交易未清仓时不生成正常评分。" />
              )}
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}

function TradeReplayDrawdownEvidence(props: { drawdown: TradeGroup["position_drawdown"] }) {
  const drawdown = props.drawdown;
  return (
    <section className="drawdownEvidenceBox" aria-label="持仓最大回撤追溯">
      <div className="drawdownEvidenceHead">
        <span>持仓最大回撤</span>
        <strong className={positionDrawdownTone(drawdown)}>{formatPositionDrawdown(drawdown)}</strong>
      </div>
      <dl>
        <div>
          <dt>每股</dt>
          <dd>{formatNullable(drawdown.max_drawdown_per_share)}</dd>
        </div>
        <div>
          <dt>窗口高点</dt>
          <dd>{formatNullable(drawdown.window_high)}</dd>
        </div>
        <div>
          <dt>窗口低点</dt>
          <dd>{formatNullable(drawdown.window_low)}</dd>
        </div>
        <div>
          <dt>最不利价</dt>
          <dd>{formatNullable(drawdown.worst_price)}</dd>
        </div>
        <div>
          <dt>Bars</dt>
          <dd>{formatInteger(drawdown.bar_count)}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd className="monoWrap">{drawdown.bars_hash ? shortHash(drawdown.bars_hash) : formatPositionDrawdownMeta(drawdown)}</dd>
        </div>
      </dl>
    </section>
  );
}

function TradeReplayOrderDetails(props: { group: TradeGroup }) {
  const orderedFills = [...props.group.fills].sort((left, right) =>
    `${left.filled_at}-${left.fill_id}`.localeCompare(`${right.filled_at}-${right.fill_id}`)
  );
  return (
    <section className="replayOrderDetails" aria-label="订单明细">
      <div className="replayOrderHead">
        <div>
          <h3>订单明细</h3>
          <p>逐笔成交来自 committed fills，只读展示 STP 事实源。</p>
        </div>
        <span>{formatInteger(orderedFills.length)} fills</span>
      </div>
      <div className="tableWrap">
        <table className="replayOrderTable">
          <thead>
            <tr>
              <th>阶段</th>
              <th>时间</th>
              <th>买卖</th>
              <th>数量</th>
              <th>价格</th>
              <th>订单号</th>
              <th>成交号</th>
              <th>追溯</th>
            </tr>
          </thead>
          <tbody>
            {orderedFills.map((fill, index) => (
              <tr key={`${fill.fill_id}-${index}`}>
                <td>
                  <span className={`orderPhasePill ${tradePhaseTone(props.group.direction, fill.side)}`}>
                    {formatTradePhase(props.group.direction, fill.side)}
                  </span>
                </td>
                <td className="timeCell">{formatDateTime(fill.filled_at)}</td>
                <td>
                  <span className={`sidePill ${fill.side.toLowerCase()}`}>{formatSide(fill.side)}</span>
                </td>
                <td className="nowrap">{formatInteger(fill.quantity)}</td>
                <td className="nowrap">{decimalFormatter.format(fill.price)}</td>
                <td className="monoCell">{fill.order_id || "N/A"}</td>
                <td className="monoCell">{fill.execution_id ?? "fallback"}</td>
                <td className="orderTraceCell">
                  <span>line {formatInteger(fill.raw_line_number)}</span>
                  <span>{shortHash(fill.source_batch_id)}</span>
                  <span>
                    {formatTraceVersion(fill.parser_version)} / {formatTraceVersion(fill.field_mapper_version)}
                  </span>
                  {fill.uses_fallback_idempotency_key ? <strong>fallback key</strong> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

type ChartFill = FillRow | TradeGroupFill;
type VisibleIndicatorPoint = StrategySignalRun["indicator_series"][number] & { visibleIndex: number };
type StrategySignalGroup = {
  id: string;
  entry: StrategySignal;
  exits: StrategySignal[];
  signals: StrategySignal[];
  side: StrategySignal["side"];
  status: "closed" | "open";
  openedAt: string;
  closedAt: string | null;
};

function buildStrategySignalGroups(signals: StrategySignal[]) {
  const orderedSignals = [...signals].sort(compareStrategySignals);
  const groups = orderedSignals.filter(isEntrySignal).map<StrategySignalGroup>((entry) => ({
    id: entry.signal_id,
    entry,
    exits: [],
    signals: [entry],
    side: entry.side,
    status: "open",
    openedAt: entry.timestamp,
    closedAt: null
  }));
  const groupsByEntryId = new Map(groups.map((group) => [group.entry.signal_id, group]));
  const orphanSignals: StrategySignal[] = [];

  orderedSignals.forEach((signal) => {
    if (isEntrySignal(signal)) return;
    const group = signal.linked_entry_signal_id ? groupsByEntryId.get(signal.linked_entry_signal_id) : undefined;
    if (!group) {
      orphanSignals.push(signal);
      return;
    }
    group.exits.push(signal);
    group.signals.push(signal);
  });

  groups.forEach((group) => {
    group.exits.sort(compareStrategySignals);
    group.signals.sort(compareStrategySignals);
    group.status = group.exits.length > 0 ? "closed" : "open";
    group.closedAt = group.exits[group.exits.length - 1]?.timestamp ?? null;
  });

  return {
    groups: groups.sort((left, right) => compareStrategySignals(left.entry, right.entry)),
    orphanSignals
  };
}

function buildStrategySignalPerformance(groups: StrategySignalGroup[]): StrategySignalPerformance {
  let totalPnl = 0;
  let grossProfit = 0;
  let grossLoss = 0;
  let closedGroupCount = 0;
  let winningGroupCount = 0;
  let losingGroupCount = 0;

  groups.forEach((group) => {
    if (group.exits.length === 0) return;
    closedGroupCount += 1;
    const groupPnl = group.exits.reduce((sum, exitSignal) => {
      const exitFraction = exitSignal.metrics.exit_fraction ?? 1;
      const priceDelta =
        group.side === "LONG" ? exitSignal.price - group.entry.price : group.entry.price - exitSignal.price;
      return sum + priceDelta * exitFraction;
    }, 0);

    totalPnl += groupPnl;
    if (groupPnl > 0) {
      winningGroupCount += 1;
      grossProfit += groupPnl;
    } else if (groupPnl < 0) {
      losingGroupCount += 1;
      grossLoss += groupPnl;
    }
  });

  return {
    unit: "price_delta_weighted_by_exit_fraction",
    total_pnl: roundSignalStat(totalPnl),
    gross_profit: roundSignalStat(grossProfit),
    gross_loss: roundSignalStat(grossLoss),
    closed_group_count: closedGroupCount,
    winning_group_count: winningGroupCount,
    losing_group_count: losingGroupCount,
    win_rate: closedGroupCount === 0 ? 0 : roundSignalStat(winningGroupCount / closedGroupCount),
    profit_factor: grossLoss < 0 ? roundSignalStat(grossProfit / Math.abs(grossLoss)) : null
  };
}

function compareStrategySignals(left: StrategySignal, right: StrategySignal) {
  if (left.bar_index !== right.bar_index) return left.bar_index - right.bar_index;
  return left.timestamp.localeCompare(right.timestamp) || left.signal_id.localeCompare(right.signal_id);
}

function isEntrySignal(signal: StrategySignal) {
  return signal.action === "ENTRY_LONG" || signal.action === "ENTRY_SHORT";
}

function MinuteCandleChart(props: {
  archive: MarketMinuteArchive;
  allowStrategySignalDetails?: boolean;
  chartVariant?: "default" | "compact";
  fills: ChartFill[];
  showStrategyMarkers?: boolean;
  showTradeMarkers?: boolean;
  strategySignals?: StrategySignal[];
  strategyRun?: StrategySignalRun | null;
  scope?: { startMinute: number; endMinute: number };
  tradeMarkerVariant?: "compact" | "replay";
}) {
  const chartShellRef = useRef<HTMLDivElement | null>(null);
  const [chartShellWidth, setChartShellWidth] = useState(0);
  const [strategySignalDetailOpen, setStrategySignalDetailOpen] = useState(false);
  const allBars = props.archive.bars;
  const strategySignals = props.strategySignals ?? props.strategyRun?.signals ?? [];
  const allowStrategySignalDetails = props.allowStrategySignalDetails ?? true;
  const showTradeMarkers = props.showTradeMarkers ?? true;
  const isReplayTradeMarkers = props.tradeMarkerVariant === "replay";
  const showStrategyMarkers = props.showStrategyMarkers ?? true;
  const visibleStrategySignals = showStrategyMarkers ? strategySignals : [];
  const fillScope = props.scope ?? chartMinuteScope(props.fills, visibleStrategySignals);
  const scopedBars = fillScope
    ? allBars.filter((bar) => {
        const minute = clockMinute(bar.timestamp);
        return minute !== null && minute >= fillScope.startMinute && minute <= fillScope.endMinute;
      })
    : allBars;
  const bars = scopedBars.length > 0 ? scopedBars : allBars;
  const scopeStartLabel = fillScope ? formatMinuteOfDay(fillScope.startMinute) : bars[0] ? formatClock(bars[0].timestamp) : "";
  const scopeEndLabel = fillScope
    ? formatMinuteOfDay(fillScope.endMinute)
    : bars[bars.length - 1]
      ? formatClock(bars[bars.length - 1].timestamp)
      : "";
  const isCompactChart = props.chartVariant === "compact";
  const height = isCompactChart ? 290 : 380;
  const width = Math.max(isCompactChart ? 760 : 980, chartShellWidth || Math.min(1280, bars.length * 2));
  const margin = { top: 18, right: 76, bottom: 34, left: 54 };
  const volumeHeight = 54;
  const priceVolumeGap = 16;
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom - volumeHeight - priceVolumeGap;
  const priceBottom = margin.top + plotHeight;
  const volumeBaseline = height - margin.bottom;
  const indicatorByTimestamp = new Map((props.strategyRun?.indicator_series ?? []).map((point) => [point.timestamp, point]));
  const strategyLinePoints = bars
    .map((bar, index) => {
      const point = indicatorByTimestamp.get(bar.timestamp);
      return point ? { ...point, visibleIndex: index } : null;
    })
    .filter((point): point is NonNullable<typeof point> => point !== null);
  const strategyPriceValues = strategyLinePoints.flatMap((point) =>
    [point.bb_middle, point.bb_upper, point.bb_lower, point.vwap].filter((value): value is number => value !== null)
  );
  const strategySignalPrices = visibleStrategySignals.flatMap((signal) =>
    [signal.price, signal.stop_loss_price, signal.take_profit_price].filter((value): value is number => value !== null)
  );
  const barValues = bars.flatMap((bar) => [bar.open, bar.high, bar.low, bar.close]);
  const fillPrices = props.fills.map((fill) => fill.price);
  const rawMin = Math.min(...barValues, ...fillPrices, ...strategyPriceValues, ...strategySignalPrices);
  const rawMax = Math.max(...barValues, ...fillPrices, ...strategyPriceValues, ...strategySignalPrices);
  const pricePadding = Math.max((rawMax - rawMin) * 0.06, 0.01);
  const minPrice = rawMin - pricePadding;
  const maxPrice = rawMax + pricePadding;
  const priceRange = Math.max(maxPrice - minPrice, 0.01);
  const candleWidth = Math.max(1, Math.min(6, (plotWidth / Math.max(bars.length, 1)) * 0.72));
  const xForIndex = (index: number) =>
    margin.left + (bars.length <= 1 ? plotWidth / 2 : (index / (bars.length - 1)) * plotWidth);
  const yForPrice = (price: number) => margin.top + ((maxPrice - price) / priceRange) * plotHeight;
  const markers = showTradeMarkers
    ? props.fills
        .map((fill) => {
          const index = nearestBarIndex(fill.filled_at, bars);
          return index < 0 ? null : { fill, index, x: xForIndex(index), y: yForPrice(fill.price) };
        })
        .filter((marker): marker is { fill: ChartFill; index: number; x: number; y: number } => marker !== null)
    : [];
  const strategyMarkers = visibleStrategySignals
    .map((signal) => {
      const index = nearestBarIndex(signal.timestamp, bars);
      return index < 0 ? null : { signal, index, x: xForIndex(index), y: yForPrice(signal.price) };
    })
    .filter((marker): marker is { signal: StrategySignal; index: number; x: number; y: number } => marker !== null);
  const strategySignalCountLabel =
    strategySignals.length === strategyMarkers.length
      ? `${formatInteger(strategySignals.length)} 个策略信号`
      : `${formatInteger(strategyMarkers.length)} / ${formatInteger(strategySignals.length)} 个可见策略信号`;
  const strategySignalButtonLabel = showStrategyMarkers
    ? strategySignalCountLabel
    : `策略信号已隐藏 · ${formatInteger(strategySignals.length)} 个信号`;
  const priceTicks = [maxPrice, minPrice + priceRange / 2, minPrice];
  const maxVolume = Math.max(...bars.map((bar) => bar.volume), 1);
  const firstBar = bars[0];
  const lastBar = bars[bars.length - 1];
  const layerLabels = [
    "分钟蜡烛图",
    showTradeMarkers ? "含买卖点" : "隐藏买卖点",
    props.strategyRun && showStrategyMarkers ? "含策略点" : null
  ].filter((label): label is string => label !== null);

  useEffect(() => {
    const element = chartShellRef.current;
    if (!element) return;

    const updateWidth = () => {
      const style = window.getComputedStyle(element);
      const horizontalPadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
      const nextWidth = Math.floor(element.clientWidth - horizontalPadding);
      setChartShellWidth(Math.max(0, nextWidth));
    };

    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!props.strategyRun) {
      setStrategySignalDetailOpen(false);
    }
  }, [props.strategyRun]);

  return (
    <div className="chartShell" ref={chartShellRef}>
      <svg
        className={isCompactChart ? "candleChart compact" : "candleChart"}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${props.archive.trade_date} ${props.archive.symbol} ${layerLabels.join("，")}`}
      >
        <rect className="chartBackground" x="0" y="0" width={width} height={height} rx="8" />
        {priceTicks.map((tick) => {
          const y = yForPrice(tick);
          return (
            <g key={tick}>
              <line className="gridLine" x1={margin.left} y1={y} x2={width - margin.right} y2={y} />
              <text className="axisLabel" x={width - margin.right + 10} y={y + 4}>
                {decimalFormatter.format(tick)}
              </text>
            </g>
          );
        })}
        <line
          className="axisLine"
          x1={margin.left}
          y1={priceBottom}
          x2={width - margin.right}
          y2={priceBottom}
        />
        {bars.map((bar, index) => {
          const x = xForIndex(index);
          const barHeight = Math.max(1, (bar.volume / maxVolume) * volumeHeight);
          return (
            <rect
              className={bar.close >= bar.open ? "volumeBar up" : "volumeBar down"}
              height={barHeight}
              key={`${bar.timestamp}-volume-${index}`}
              width={Math.max(1, candleWidth)}
              x={x - candleWidth / 2}
              y={volumeBaseline - barHeight}
            />
          );
        })}
        <text className="axisLabel" x={margin.left} y={volumeBaseline - volumeHeight - 4}>
          Volume
        </text>
        <text className="axisLabel" x={margin.left} y={height - 10}>
          {firstBar ? formatClock(firstBar.timestamp) : ""}
        </text>
        <text className="axisLabel end" x={width - margin.right} y={height - 10}>
          {lastBar ? formatClock(lastBar.timestamp) : ""}
        </text>
        {props.archive.vwap !== null ? (
          <g>
            <line
              className="vwapLine"
              x1={margin.left}
              y1={yForPrice(props.archive.vwap)}
              x2={width - margin.right}
              y2={yForPrice(props.archive.vwap)}
            />
            <text className="vwapLabel" x={margin.left + 8} y={yForPrice(props.archive.vwap) - 6}>
              VWAP
            </text>
          </g>
        ) : null}
        {props.strategyRun ? (
          <g className="strategyOverlayLines">
            <path className="bbLine upper" d={indicatorLinePath(strategyLinePoints, "bb_upper", xForIndex, yForPrice)} />
            <path className="bbLine middle" d={indicatorLinePath(strategyLinePoints, "bb_middle", xForIndex, yForPrice)} />
            <path className="bbLine lower" d={indicatorLinePath(strategyLinePoints, "bb_lower", xForIndex, yForPrice)} />
            <path className="strategyVwapLine" d={indicatorLinePath(strategyLinePoints, "vwap", xForIndex, yForPrice)} />
          </g>
        ) : null}
        {bars.map((bar, index) => {
          const x = xForIndex(index);
          const openY = yForPrice(bar.open);
          const closeY = yForPrice(bar.close);
          const highY = yForPrice(bar.high);
          const lowY = yForPrice(bar.low);
          const isUp = bar.close >= bar.open;
          return (
            <g key={`${bar.timestamp}-${index}`} className={isUp ? "candle up" : "candle down"}>
              <line className="wick" x1={x} y1={highY} x2={x} y2={lowY} />
              <rect
                x={x - candleWidth / 2}
                y={Math.min(openY, closeY)}
                width={candleWidth}
                height={Math.max(1, Math.abs(openY - closeY))}
              />
            </g>
          );
        })}
        {markers.map(({ fill, x, y }) => {
          const isBuy = fill.side === "BUY";
          if (!isReplayTradeMarkers) {
            return (
              <g key={fill.fill_id} className={isBuy ? "tradeMarker buy" : "tradeMarker sell"}>
                <path d={tradeMarkerPath(x, y, fill.side)} />
                <circle cx={x} cy={y} r="2.4" />
                <title>
                  {formatSide(fill.side)} {formatInteger(fill.quantity)} @ {decimalFormatter.format(fill.price)} ·{" "}
                  {formatDateTime(fill.filled_at)}
                </title>
              </g>
            );
          }
          const label = isBuy ? "BUY" : "SELL";
          const labelWidth = isBuy ? 38 : 44;
          const labelHeight = 20;
          const labelX = Math.max(margin.left + labelWidth / 2, Math.min(width - margin.right - labelWidth / 2, x));
          const labelY = isBuy
            ? Math.max(margin.top + 4, y - 40)
            : Math.min(priceBottom - labelHeight - 4, y + 20);
          const stemEndY = isBuy ? labelY + labelHeight : labelY;
          return (
            <g
              key={fill.fill_id}
              className={isBuy ? "tradeMarker replay buy" : "tradeMarker replay sell"}
              aria-label={`${formatSide(fill.side)} ${formatInteger(fill.quantity)} @ ${decimalFormatter.format(fill.price)}`}
            >
              <line className="markerStem" x1={x} y1={y} x2={x} y2={stemEndY} />
              <path className="markerGlyph" d={tradeMarkerPath(x, y, fill.side)} />
              <circle className="markerDot" cx={x} cy={y} r="4" />
              <rect
                className="markerLabelBg"
                height={labelHeight}
                rx="10"
                width={labelWidth}
                x={labelX - labelWidth / 2}
                y={labelY}
              />
              <text className="markerLabelText" x={labelX} y={labelY + 14}>
                {label}
              </text>
              <title>
                {formatSide(fill.side)} {formatInteger(fill.quantity)} @ {decimalFormatter.format(fill.price)} ·{" "}
                {formatDateTime(fill.filled_at)}
              </title>
            </g>
          );
        })}
        {strategyMarkers.map(({ signal, x, y }) => {
          const markerSide = strategySignalTradeSide(signal.action);
          const isBuy = markerSide === "BUY";
          const label = strategySignalMarkerLabel(signal.action);
          const labelWidth = 42;
          const labelHeight = 20;
          const labelX = Math.max(margin.left + labelWidth / 2, Math.min(width - margin.right - labelWidth / 2, x));
          const labelY = isBuy
            ? Math.max(margin.top + 4, y - 40)
            : Math.min(priceBottom - labelHeight - 4, y + 20);
          const stemEndY = isBuy ? labelY + labelHeight : labelY;
          return (
            <g
              key={signal.signal_id}
              className={isBuy ? "tradeMarker replay buy strategySignalMarker" : "tradeMarker replay sell strategySignalMarker"}
              aria-label={`${formatStrategyAction(signal.action)} @ ${decimalFormatter.format(signal.price)}`}
            >
              <line className="markerStem" x1={x} y1={y} x2={x} y2={stemEndY} />
              <path className="markerGlyph" d={tradeMarkerPath(x, y, markerSide)} />
              <circle className="markerDot" cx={x} cy={y} r="4" />
              <rect
                className="markerLabelBg"
                height={labelHeight}
                rx="10"
                width={labelWidth}
                x={labelX - labelWidth / 2}
                y={labelY}
              />
              <text className="markerLabelText" x={labelX} y={labelY + 14}>
                {label}
              </text>
              <title>
                {formatStrategyAction(signal.action)} @ {decimalFormatter.format(signal.price)} · {formatDateTime(signal.timestamp)}
              </title>
            </g>
          );
        })}
      </svg>
      <div className="chartLegend" aria-label="图例">
        <span className="legendItem up">上涨分钟</span>
        <span className="legendItem down">下跌分钟</span>
        {showTradeMarkers ? <span className={isReplayTradeMarkers ? "legendItem buy replay" : "legendItem buy"}>买点</span> : null}
        {showTradeMarkers ? <span className="legendItem sell">卖点</span> : null}
        {props.strategyRun ? <span className="legendItem strategyLine">BB / 策略 VWAP</span> : null}
        {props.strategyRun && showStrategyMarkers ? <span className="legendItem strategySignal">策略开平仓</span> : null}
        <span>
          显示 {scopeStartLabel}-{scopeEndLabel} · {formatInteger(bars.length)} / {formatInteger(allBars.length)} 根分钟线
        </span>
        {showTradeMarkers ? <span>{formatInteger(markers.length)} 个成交标记</span> : <span>成交标记已隐藏</span>}
        {props.strategyRun && allowStrategySignalDetails ? (
          <button
            className="legendCountButton"
            onClick={() => setStrategySignalDetailOpen(true)}
            title="查看策略信号执行动作与原因"
            type="button"
          >
            {strategySignalButtonLabel}
          </button>
        ) : null}
      </div>
      {strategySignalDetailOpen && props.strategyRun ? (
        <StrategySignalDetailModal
          archive={props.archive}
          onClose={() => setStrategySignalDetailOpen(false)}
          run={props.strategyRun}
          signals={strategySignals}
        />
      ) : null}
    </div>
  );
}

function StrategySignalDetailModal(props: {
  archive: MarketMinuteArchive;
  run: StrategySignalRun;
  signals: StrategySignal[];
  onClose: () => void;
}) {
  const status = strategyStatusMeta[props.run.status];
  const signalReplay = useMemo(() => buildStrategySignalGroups(props.signals), [props.signals]);
  const fallbackSignalPerformance = useMemo(
    () => buildStrategySignalPerformance(signalReplay.groups),
    [signalReplay.groups]
  );
  const signalPerformance = props.run.signal_performance ?? fallbackSignalPerformance;
  const signalRunScope = useMemo(() => strategySignalRunScope(props.signals), [props.signals]);
  return (
    <div className="modalBackdrop" role="dialog" aria-modal="true" aria-label="策略信号详情">
      <section className="strategySignalModal">
        <header className="modalHeader">
          <div>
            <p className="eyebrow">Strategy Signals</p>
            <h2>
              <ListChecks size={18} />
              策略信号详情
            </h2>
            <p className="panelNote">执行动作、原因码和指标来自后端策略 run read model</p>
          </div>
          <div className="headerActions">
            <span className={`statusPill ${status.tone}`}>{status.label}</span>
            <button className="iconButton" onClick={props.onClose} aria-label="关闭策略信号详情" title="关闭" type="button">
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="strategySignalModalBody">
          <dl className="signalRunFacts">
            <div className="wideFact">
              <dt>策略</dt>
              <dd>{props.run.strategy.name}</dd>
            </div>
            <div>
              <dt>标的</dt>
              <dd>{props.run.symbol}</dd>
            </div>
            <div>
              <dt>日期</dt>
              <dd>{props.run.trade_date}</dd>
            </div>
            <div>
              <dt>盈亏</dt>
              <dd className={signalPerformance ? signalStatTone(signalPerformance.total_pnl) : undefined}>
                {signalPerformance ? formatPnl(signalPerformance.total_pnl) : "N/A"}
              </dd>
            </div>
            <div>
              <dt>胜率</dt>
              <dd>{signalPerformance ? formatSignalWinRate(signalPerformance) : "N/A"}</dd>
            </div>
            <div>
              <dt>盈亏比</dt>
              <dd>{signalPerformance ? formatSignalProfitFactor(signalPerformance) : "N/A"}</dd>
            </div>
            <div>
              <dt>信号</dt>
              <dd>{formatInteger(props.signals.length)}</dd>
            </div>
            <div>
              <dt>开平仓组</dt>
              <dd>{formatInteger(signalReplay.groups.length)}</dd>
            </div>
            <div>
              <dt>已闭合组</dt>
              <dd>{signalPerformance ? formatInteger(signalPerformance.closed_group_count) : "N/A"}</dd>
            </div>
            <div className="hashFact">
              <dt>bars hash</dt>
              <dd className="monoWrap">{shortHash(props.run.bars_hash)}</dd>
            </div>
            <div className="hashFact">
              <dt>indicator hash</dt>
              <dd className="monoWrap">{shortHash(props.run.indicator_hash)}</dd>
            </div>
          </dl>

          {props.signals.length > 0 && props.archive.bars.length > 0 ? (
            <section className="signalDayChart" aria-label="日信号开平仓期间蜡烛图">
              <header className="signalDayChartHeader">
                <div>
                  <strong>日信号开平仓期间蜡烛图</strong>
                  <small>
                    {props.run.trade_date} · {props.run.symbol} ·{" "}
                    {signalRunScope
                      ? `${formatMinuteOfDay(signalRunScope.startMinute)}-${formatMinuteOfDay(signalRunScope.endMinute)}`
                      : "等待开平仓区间"}
                  </small>
                </div>
                <span className="statusPill info">{formatInteger(props.signals.length)} 动作</span>
              </header>
              <MinuteCandleChart
                allowStrategySignalDetails={false}
                archive={props.archive}
                chartVariant="compact"
                fills={[]}
                scope={signalRunScope}
                showTradeMarkers={false}
                showStrategyMarkers
                strategyRun={props.run}
                strategySignals={props.signals}
              />
            </section>
          ) : props.signals.length > 0 ? (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="缺少日信号蜡烛图"
              detail="当前 strategy run 没有可复用的归档分钟线，弹层不会渲染全日开平仓图表。"
            />
          ) : null}

        {signalReplay.orphanSignals.length > 0 ? (
          <div className="statusReason">
            <AlertTriangle size={16} />
            <span>
              {formatInteger(signalReplay.orphanSignals.length)}
              个平仓信号没有关联开仓 ID，已排除在开平仓组外。
            </span>
          </div>
        ) : null}

        {signalReplay.groups.length > 0 ? (
          <div className="signalGroupList">
            {signalReplay.groups.map((group, index) => (
              <details className="signalGroupCard" key={group.id} onToggle={scrollOpenDetailsIntoView}>
                <summary className="signalGroupSummary">
                  <span className="signalGroupTitle">
                    <ChevronDown className="signalGroupChevron" size={16} />
                    <span className={`strategySignalPill ${group.entry.action.toLowerCase()}`}>
                      #{index + 1} {formatStrategyAction(group.entry.action)}
                    </span>
                    <span className={group.side === "LONG" ? "sidePill buy" : "sidePill sell"}>
                      {formatDirection(group.side)}
                    </span>
                    <span className={group.status === "closed" ? "statusPill ok" : "statusPill warn"}>
                      {group.status === "closed" ? "已平仓" : "持仓中"}
                    </span>
                  </span>
                  <span className="signalGroupMeta">
                    {formatClock(group.openedAt)}
                    {group.closedAt ? ` -> ${formatClock(group.closedAt)}` : " -> 未平仓"}
                    {" · "}
                    {formatInteger(group.signals.length)} 动作
                  </span>
                </summary>

                <div className="signalGroupBody">
                  <dl className="signalFacts signalGroupFacts">
                    <div>
                      <dt>开仓价格</dt>
                      <dd>{decimalFormatter.format(group.entry.price)}</dd>
                    </div>
                    <div>
                      <dt>平仓次数</dt>
                      <dd>{formatInteger(group.exits.length)}</dd>
                    </div>
                    <div>
                      <dt>开仓 Bar</dt>
                      <dd>#{formatInteger(group.entry.bar_index)}</dd>
                    </div>
                    <div>
                      <dt>止损</dt>
                      <dd>{formatNullable(group.entry.stop_loss_price)}</dd>
                    </div>
                    <div>
                      <dt>止盈</dt>
                      <dd>{formatNullable(group.entry.take_profit_price)}</dd>
                    </div>
                  </dl>

                  {props.archive.bars.length > 0 ? (
                    <MinuteCandleChart
                      allowStrategySignalDetails={false}
                      archive={props.archive}
                      chartVariant="compact"
                      fills={[]}
                      scope={strategySignalGroupScope(group, 8)}
                      showTradeMarkers={false}
                      showStrategyMarkers
                      strategyRun={props.run}
                      strategySignals={group.signals}
                    />
                  ) : (
                    <EmptyState
                      icon={<AlertTriangle size={18} />}
                      title="缺少分钟线蜡烛图"
                      detail="当前 strategy run 没有可复用的归档分钟线，弹层不会渲染成功图表。"
                    />
                  )}

                  <StrategySignalOrderDetails group={group} />
                </div>
              </details>
            ))}
          </div>
        ) : props.signals.length > 0 ? (
          <EmptyState
            icon={<AlertTriangle size={18} />}
            title="策略信号无法配对到开仓"
            detail="弹层只按 ENTRY 信号与 linked_entry_signal_id 组织开平仓组；无法配对的信号不会被渲染成成功交易组。"
          />
        ) : (
          <EmptyState
            icon={<CircleSlash size={18} />}
            title={props.run.signal_count === 0 ? "本次策略 run 为 0 个信号" : "本次策略 run 没有可展示信号"}
            detail={
              props.run.signal_count === 0
                ? "后端已完成计算，但没有触发开仓或平仓条件；这不是蜡烛图渲染失败。"
                : "strategy_signals 中没有可展示信号，请检查策略 run 状态和 artifact source。"
            }
          />
        )}
        </div>
      </section>
    </div>
  );
}

function scrollOpenDetailsIntoView(event: SyntheticEvent<HTMLDetailsElement>) {
  const details = event.currentTarget;
  event.stopPropagation();
  if (!details.open) return;
  window.requestAnimationFrame(() => {
    const scroller = details.closest<HTMLElement>(".strategySignalModalBody");
    if (!scroller) {
      details.scrollIntoView({ block: "start", inline: "nearest" });
      return;
    }
    const scrollerTop = scroller.getBoundingClientRect().top;
    const detailsTop = details.getBoundingClientRect().top;
    scroller.scrollTo({ top: scroller.scrollTop + detailsTop - scrollerTop, behavior: "auto" });
  });
}

function StrategySignalOrderDetails(props: { group: StrategySignalGroup }) {
  return (
    <details className="signalOrderDetails" onToggle={scrollOpenDetailsIntoView}>
      <summary>
        <span>
          <ChevronDown className="signalGroupChevron" size={15} />
          复盘订单明细
        </span>
        <small>{formatInteger(props.group.signals.length)} 个后端策略动作，点击展开</small>
      </summary>
      <div className="tableWrap">
        <table className="strategyOrderTable">
          <thead>
            <tr>
              <th>阶段</th>
              <th>时间</th>
              <th>方向</th>
              <th>价格</th>
              <th>止损</th>
              <th>止盈</th>
              <th>关联</th>
              <th>原因 / 指标</th>
            </tr>
          </thead>
          <tbody>
            {props.group.signals.map((signal) => (
              <tr key={signal.signal_id}>
                <td>
                  <span className={isEntrySignal(signal) ? "orderPhasePill entry" : "orderPhasePill exit"}>
                    {isEntrySignal(signal) ? "Entry" : "Exit"}
                  </span>
                </td>
                <td className="timeCell">{formatDateTime(signal.timestamp)}</td>
                <td>
                  <span className={signal.side === "LONG" ? "sidePill buy" : "sidePill sell"}>
                    {formatDirection(signal.side)}
                  </span>
                </td>
                <td className="nowrap">{decimalFormatter.format(signal.price)}</td>
                <td className="nowrap">{formatNullable(signal.stop_loss_price)}</td>
                <td className="nowrap">{formatNullable(signal.take_profit_price)}</td>
                <td className="orderTraceCell">
                  <span>bar #{formatInteger(signal.bar_index)}</span>
                  <span className="monoWrap">
                    {signal.linked_entry_signal_id ? shortHash(signal.linked_entry_signal_id) : "entry"}
                  </span>
                </td>
                <td>
                  <div className="signalOrderEvidence">
                    <div className="tagList">
                      {signal.reason_codes.length > 0 ? (
                        signal.reason_codes.map((reason) => (
                          <span className="reasonCode" key={reason}>
                            {reasonLabels[reason] ?? reason}
                          </span>
                        ))
                      ) : (
                        <span className="mutedText">无原因码</span>
                      )}
                    </div>
                    <dl className="signalMetrics compactSignalMetrics">
                      {Object.entries(signal.metrics).length > 0 ? (
                        Object.entries(signal.metrics).map(([key, value]) => (
                          <div key={key}>
                            <dt>{key}</dt>
                            <dd>{formatMetric(value)}</dd>
                          </div>
                        ))
                      ) : (
                        <div>
                          <dt>metrics</dt>
                          <dd>N/A</dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="signalOrderNote">这里展示的是策略 run 生成的复盘动作，不是券商订单，也不会修改 STP 成交事实。</p>
    </details>
  );
}

function Metric(props: { label: string; value: number | string; note?: string; tone?: "neutral" | "ok" | "warn" | "bad" }) {
  return (
    <div className={`metric ${props.tone ?? "neutral"}`}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.note ? <small>{props.note}</small> : null}
    </div>
  );
}

function SummaryMetricStrip(props: { className: string; note: string; summary: ReviewSummary | null }) {
  const summary = props.summary;
  return (
    <section className={props.className} aria-label="有记录以来汇总指标">
      <Metric label="成交股数" value={formatInteger(summary?.traded_quantity ?? 0)} note={props.note} />
      <Metric label="PnL" value={formatPnl(summary?.pnl ?? 0)} tone={summaryTone(summary?.pnl ?? 0)} />
      <Metric label="胜率" value={formatWinRate(summary)} />
      <Metric label="盈亏比" value={formatProfitFactor(summary)} />
      <Metric label="单笔期望值" value={formatSignedNullable(summary?.expected_value_per_trade)} tone={summaryTone(summary?.expected_value_per_trade ?? 0)} />
      <Metric label="每股净收益" value={formatSignedNullable(summary?.net_profit_per_share)} tone={summaryTone(summary?.net_profit_per_share ?? 0)} />
      <Metric label="持仓最大回撤" value={formatNullable(summary?.max_single_day_drawdown)} tone={(summary?.max_single_day_drawdown ?? 0) > 0 ? "warn" : "neutral"} />
    </section>
  );
}

function SummaryMiniFacts(props: { summary: ReviewSummary | null }) {
  const summary = props.summary;
  if (!summary) {
    return <EmptyState icon={<Clock3 size={18} />} title="等待汇总" detail="当前范围还没有可用复盘汇总" />;
  }
  return (
    <dl className="compactFacts summaryMiniFacts">
      <div>
        <dt>成交股数</dt>
        <dd>{formatInteger(summary.traded_quantity)}</dd>
      </div>
      <div>
        <dt>PnL</dt>
        <dd className={summaryTone(summary.pnl)}>{formatPnl(summary.pnl)}</dd>
      </div>
      <div>
        <dt>胜率</dt>
        <dd>{formatWinRate(summary)}</dd>
      </div>
      <div>
        <dt>盈亏比</dt>
        <dd>{formatProfitFactor(summary)}</dd>
      </div>
      <div>
        <dt>持仓最大回撤</dt>
        <dd>{formatNullable(summary.max_single_day_drawdown)}</dd>
      </div>
    </dl>
  );
}

function EmptyState(props: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="emptyState">
      {props.icon}
      <div>
        <strong>{props.title}</strong>
        <p>{props.detail}</p>
      </div>
    </div>
  );
}

function formatInteger(value: number) {
  return integerFormatter.format(value);
}

function formatMetric(value: number) {
  return Math.abs(value) >= 100 ? integerFormatter.format(value) : decimalFormatter.format(value);
}

function roundSignalStat(value: number) {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function formatStrategyParam(value: StrategyParamValue | undefined) {
  if (value === undefined) return "N/A";
  if (typeof value === "string") return value || "N/A";
  if (!Number.isFinite(value)) return "N/A";
  if (Number.isInteger(value)) return integerFormatter.format(value);
  return String(Number(value.toFixed(6)));
}

function coerceStrategyParamValue(
  param: StrategyTemplate["param_schema"][number],
  value: string,
  currentValue: StrategyParamValue | undefined
): StrategyParamValue {
  if (param.type === "enum") return value;
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : currentValue ?? 0;
}

function strategyParamsSignature(params: Record<string, StrategyParamValue>) {
  return JSON.stringify(Object.keys(params).sort().map((key) => [key, params[key]]));
}

function formatNullable(value: number | null | undefined) {
  return value == null ? "N/A" : decimalFormatter.format(value);
}

function formatSignedNullable(value: number | null | undefined) {
  return value == null ? "N/A" : formatPnl(value);
}

function formatPnl(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${decimalFormatter.format(value)}`;
}

function summaryTone(value: number): "neutral" | "ok" | "bad" {
  if (value > 0) return "ok";
  if (value < 0) return "bad";
  return "neutral";
}

function formatHoldingMinutes(value: number | null) {
  return value === null ? "持仓中" : `${decimalFormatter.format(value)} 分钟`;
}

function formatDirection(direction: TradeGroup["direction"]) {
  return direction === "LONG" ? "多头" : "空头";
}

function formatTradePhase(direction: TradeGroup["direction"], side: ChartFill["side"]) {
  const isEntry = direction === "LONG" ? side === "BUY" : side === "SELL";
  return isEntry ? "Entry" : "Exit";
}

function tradePhaseTone(direction: TradeGroup["direction"], side: ChartFill["side"]) {
  return formatTradePhase(direction, side).toLowerCase();
}

function formatPositionDrawdown(drawdown: TradeGroup["position_drawdown"]) {
  if (drawdown.status !== "available" || drawdown.max_drawdown === null) return "N/A";
  return decimalFormatter.format(drawdown.max_drawdown);
}

function formatPositionDrawdownMeta(drawdown: TradeGroup["position_drawdown"]) {
  if (drawdown.status === "not_applicable_open_trade") return "持仓中";
  if (drawdown.status !== "available") return "缺分钟线";
  return `${formatInteger(drawdown.bar_count)} bars · ${formatNullable(drawdown.max_drawdown_per_share)}/股`;
}

function positionDrawdownTone(drawdown: TradeGroup["position_drawdown"]): "neutral" | "ok" | "bad" {
  if (drawdown.status !== "available" || drawdown.max_drawdown === null) return "neutral";
  return drawdown.max_drawdown > 0 ? "bad" : "ok";
}

function formatEvaluationGrade(evaluation: TradeGroup["evaluation"]) {
  if (evaluation.evaluation_status === "not_applicable_open_trade") return "未清仓";
  if (evaluation.evaluation_status === "insufficient_market_data") return "待行情";
  return evaluation.grade ? `${evaluation.grade} 级` : "N/A";
}

function evaluationTone(status: TradeGroup["evaluation"]["evaluation_status"], grade: TradeGroup["evaluation"]["grade"]) {
  if (status !== "available") return "warn";
  if (grade === "A" || grade === "B") return "ok";
  if (grade === "C") return "info";
  return "danger";
}

function formatStrategyAction(action: StrategySignalAction) {
  return {
    ENTRY_LONG: "多头开仓",
    EXIT_LONG: "多头平仓",
    ENTRY_SHORT: "空头开仓",
    EXIT_SHORT: "空头平仓"
  }[action];
}

function strategySignalTradeSide(action: StrategySignalAction): ChartFill["side"] {
  return action === "ENTRY_LONG" || action === "EXIT_SHORT" ? "BUY" : "SELL";
}

function strategySignalMarkerLabel(action: StrategySignalAction) {
  return {
    ENTRY_LONG: "开多",
    EXIT_LONG: "平多",
    ENTRY_SHORT: "开空",
    EXIT_SHORT: "平空"
  }[action];
}

function formatWinRate(summary: DailySummary | null) {
  if (!summary || summary.trade_group_count === 0) return "N/A";
  return `${decimalFormatter.format(summary.win_rate * 100)}%`;
}

function formatProfitFactor(summary: DailySummary | null) {
  if (!summary || summary.trade_group_count === 0) return "N/A";
  if (summary.profit_factor === null) return summary.pnl > 0 ? "∞" : "N/A";
  return decimalFormatter.format(summary.profit_factor);
}

function formatReviewGroupMeta(summary: ReviewSummaryGroup) {
  const openGroups = summary.open_trade_group_count ? ` · 未清仓 ${formatInteger(summary.open_trade_group_count)}` : "";
  return `成交 ${formatInteger(summary.fill_count)} · 平仓 ${formatInteger(summary.trade_group_count)}${openGroups} · PnL ${formatPnl(summary.pnl)}`;
}

function formatSignalWinRate(performance: StrategySignalPerformance) {
  if (performance.closed_group_count === 0) return "N/A";
  return `${decimalFormatter.format(performance.win_rate * 100)}%`;
}

function formatSignalProfitFactor(performance: StrategySignalPerformance) {
  if (performance.closed_group_count === 0) return "N/A";
  if (performance.profit_factor === null) return performance.gross_profit > 0 ? "∞" : "N/A";
  return decimalFormatter.format(performance.profit_factor);
}

function formatPercentValue(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "N/A";
  return `${decimalFormatter.format(value * 100)}%`;
}

function formatParamDiff(candidate: Record<string, number | string>, base: Record<string, number | string>) {
  const changes = Object.entries(candidate)
    .filter(([key, value]) => String(base[key] ?? "") !== String(value))
    .map(([key, value]) => `${key}=${formatStrategyParam(value)}`);
  return changes.length > 0 ? changes.join(" · ") : "与当前参数一致";
}

function optimizationCandidateParamItems(
  candidate: Record<string, StrategyParamValue>,
  base: Record<string, StrategyParamValue>,
  template: StrategyTemplate | null,
  focusKeys: string[]
) {
  const schema = new Map((template?.param_schema ?? []).map((param) => [param.key, param]));
  const orderedKeys = [
    ...focusKeys.filter((key) => key in candidate),
    ...Object.keys(candidate)
      .filter((key) => focusKeys.length === 0 || focusKeys.includes(key))
      .filter((key) => !focusKeys.includes(key))
      .sort()
  ];

  return orderedKeys.map((key) => {
    const param = schema.get(key);
    const value = candidate[key];
    const currentValue = base[key];
    return {
      key,
      label: param?.label ?? key,
      valueLabel: formatStrategyParamWithSchema(value, param),
      currentValueLabel: formatStrategyParamWithSchema(currentValue, param),
      changed: String(currentValue ?? "") !== String(value)
    };
  });
}

function formatStrategyParamWithSchema(
  value: StrategyParamValue | undefined,
  param: StrategyTemplate["param_schema"][number] | undefined
) {
  if (param?.type === "enum") {
    const option = param.options?.find((item) => item.value === value);
    return option?.label ?? formatStrategyParam(value);
  }
  return formatStrategyParam(value);
}

function signalStatTone(value: number) {
  if (value > 0) return "statPositive";
  if (value < 0) return "statNegative";
  return "statNeutral";
}

function formatDateTime(value: string) {
  return value.replace("T", " ").replace("Z", " UTC");
}

function formatClock(value: string) {
  const match = value.match(/T(\d{2}:\d{2})/);
  return match ? match[1] : value.slice(11, 16);
}

function formatMinuteOfDay(value: number) {
  const hour = Math.floor(value / 60)
    .toString()
    .padStart(2, "0");
  const minute = (value % 60).toString().padStart(2, "0");
  return `${hour}:${minute}`;
}

function formatSide(side: ChartFill["side"]) {
  return side === "BUY" ? "买入" : "卖出";
}

function formatTraceVersion(value: string) {
  return value.replace("stp_txt_parser_", "parser ").replace("stp_txt_mapping_", "mapping ");
}

function groupStrategyParams(params: StrategyTemplate["param_schema"]) {
  const byKey = new Map(params.map((param) => [param.key, param]));
  const used = new Set<string>();
  const sections = strategyParamGroups.map((group) => {
    const sectionParams = group.paramKeys
      .map((key) => byKey.get(key))
      .filter((param): param is StrategyTemplate["param_schema"][number] => param !== undefined);
    sectionParams.forEach((param) => used.add(param.key));
    return { ...group, params: sectionParams };
  });
  const remaining = params.filter((param) => !used.has(param.key));
  if (remaining.length > 0) {
    sections.push({
      key: "other",
      title: "其他",
      detail: "模板扩展参数",
      paramKeys: remaining.map((param) => param.key),
      params: remaining
    });
  }
  return sections.filter((section) => section.params.length > 0);
}

function clockMinute(value: string) {
  const match = value.match(/T(\d{2}):(\d{2})/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function fillMinuteScope(fills: ChartFill[]) {
  const minutes = fills.map((fill) => clockMinute(fill.filled_at)).filter((minute): minute is number => minute !== null);
  if (minutes.length === 0) return null;
  return {
    startMinute: Math.min(...minutes),
    endMinute: Math.max(...minutes)
  };
}

function chartMinuteScope(fills: ChartFill[], signals: StrategySignal[]) {
  const minutes = [
    ...fills.map((fill) => clockMinute(fill.filled_at)),
    ...signals.map((signal) => clockMinute(signal.timestamp))
  ].filter((minute): minute is number => minute !== null);
  if (minutes.length === 0) return null;
  return {
    startMinute: Math.min(...minutes),
    endMinute: Math.max(...minutes)
  };
}

function tradeGroupScope(group: TradeGroup, bufferMinutes: number) {
  const fillScope = fillMinuteScope(group.fills);
  if (!fillScope) return undefined;
  return {
    startMinute: Math.max(0, fillScope.startMinute - bufferMinutes),
    endMinute: Math.min(24 * 60 - 1, fillScope.endMinute + bufferMinutes)
  };
}

function strategySignalGroupScope(group: StrategySignalGroup, bufferMinutes: number) {
  const minutes = group.signals
    .map((signal) => clockMinute(signal.timestamp))
    .filter((minute): minute is number => minute !== null);
  if (minutes.length === 0) return undefined;
  return {
    startMinute: Math.max(0, Math.min(...minutes) - bufferMinutes),
    endMinute: Math.min(24 * 60 - 1, Math.max(...minutes) + bufferMinutes)
  };
}

function strategySignalRunScope(signals: StrategySignal[], bufferMinutes = 0) {
  const minutes = signals
    .map((signal) => clockMinute(signal.timestamp))
    .filter((minute): minute is number => minute !== null);
  if (minutes.length === 0) return undefined;
  return {
    startMinute: Math.max(0, Math.min(...minutes) - bufferMinutes),
    endMinute: Math.min(24 * 60 - 1, Math.max(...minutes) + bufferMinutes)
  };
}

function nearestBarIndex(filledAt: string, bars: MarketMinuteArchive["bars"]) {
  if (bars.length === 0) return -1;
  const target = clockMinute(filledAt);
  if (target === null) return -1;
  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  bars.forEach((bar, index) => {
    const minute = clockMinute(bar.timestamp);
    if (minute === null) return;
    const distance = Math.abs(minute - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function tradeMarkerPath(x: number, y: number, side: ChartFill["side"]) {
  const size = 10;
  if (side === "BUY") {
    return `M ${x} ${y} L ${x - size} ${y + size * 2} L ${x + size} ${y + size * 2} Z`;
  }
  return `M ${x} ${y} L ${x - size} ${y - size * 2} L ${x + size} ${y - size * 2} Z`;
}

function indicatorLinePath(
  points: VisibleIndicatorPoint[],
  key: "bb_upper" | "bb_middle" | "bb_lower" | "vwap",
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number
) {
  return points
    .filter((point) => point[key] !== null)
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command} ${xForIndex(point.visibleIndex)} ${yForPrice(Number(point[key]))}`;
    })
    .join(" ");
}

function shortHash(value: string) {
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}
