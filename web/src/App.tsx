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
import { Fragment, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";

import {
  applyStrategyOptimizationCandidate,
  archiveYahooMinuteData,
  createStrategy,
  fetchBatches,
  fetchFills,
  fetchMinuteArchives,
  fetchQuarantine,
  fetchReviewSummary,
  fetchReviewSummaryGroups,
  fetchStrategies,
  fetchStrategyHistory,
  fetchStrategyOptimizationDetail,
  fetchStrategyOptimizations,
  fetchStrategyRunDetail,
  fetchStrategyRuns,
  fetchStrategyTestBatches,
  fetchStrategyTemplates,
  fetchTradeGroups,
  fetchWatchlist,
  generateWatchlist,
  runLiveStrategySignal,
  runStrategyOptimization,
  runStrategyReplay,
  runStrategyTestBatch,
  rollbackStrategyConfigHistory,
  saveTradeGroupReview,
  updateStrategy,
  uploadStpTxt
} from "./api";
import type {
  DailySummary,
  FillRow,
  ImportBatch,
  LiveStrategySignalResult,
  MarketDataStatus,
  MarketMinuteArchive,
  QuarantineRow,
  ReviewSummary,
  ReviewSummaryGroup,
  StrategyConfig,
  StrategyConfigHistory,
  StrategyOptimizationCandidate,
  StrategyOptimizationRun,
  StrategyOptimizationStatus,
  StrategyRunStatus,
  StrategySignal,
  StrategySignalAction,
  StrategySignalGroupPerformance,
  StrategySignalPerformance,
  StrategySignalRun,
  StrategyTestBatch,
  StrategyTestBatchStatus,
  StrategyTestDayResult,
  StrategyTemplate,
  TradeGroup,
  TradeGroupFill,
  TradeReviewReasonCategory,
  WatchlistRun,
  WatchlistRunStatus,
  YahooMinuteArchiveResult
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

const minuteCandleEdgeBufferBars = 10;

type LossReviewReasonOption = {
  code: string;
  label: string;
};

const lossReviewReasonCategoryLabels: Record<TradeReviewReasonCategory, string> = {
  opening_signal: "开仓信号",
  closing_signal: "平仓信号",
  misoperation: "误操作"
};

const lossReviewReasonOptions: Record<TradeReviewReasonCategory, LossReviewReasonOption[]> = {
  opening_signal: [
    { code: "chased_breakout", label: "追突破过急" },
    { code: "weak_confirmation", label: "确认不足" },
    { code: "against_context", label: "逆势入场" },
    { code: "poor_location", label: "入场位置差" }
  ],
  closing_signal: [
    { code: "stop_too_late", label: "止损过慢" },
    { code: "profit_reversed", label: "盈利回吐" },
    { code: "exit_signal_ignored", label: "平仓信号未执行" },
    { code: "exit_plan_unclear", label: "平仓计划不清" }
  ],
  misoperation: [
    { code: "wrong_side_or_symbol", label: "方向或标的点错" },
    { code: "oversized_position", label: "仓位过大" },
    { code: "duplicate_order", label: "重复下单" },
    { code: "plan_not_followed", label: "未按计划执行" }
  ]
};

const strategyStatusMeta: Record<StrategyRunStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "已完成", tone: "ok" },
  missing_archive: { label: "待归档", tone: "warn" },
  non_available_archive: { label: "行情不可用", tone: "danger" },
  insufficient_bars: { label: "分钟线不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "运行失败", tone: "danger" }
};

const liveSignalStatusMeta: Record<
  LiveStrategySignalResult["status"],
  { label: string; tone: "info" | "ok" | "warn" | "danger" }
> = {
  completed: { label: "出现信号", tone: "ok" },
  no_signal: { label: "观望", tone: "info" },
  provider_failed: { label: "行情失败", tone: "danger" },
  missing_market_data: { label: "缺实时行情", tone: "warn" },
  non_available_market_data: { label: "行情不可用", tone: "danger" },
  insufficient_bars: { label: "分钟线不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "引擎失败", tone: "danger" }
};

const strategyTestStatusMeta: Record<StrategyTestBatchStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "测试完成", tone: "ok" },
  insufficient_archive_coverage: { label: "30天覆盖不足", tone: "warn" },
  strategy_disabled: { label: "策略未开启", tone: "info" },
  failed: { label: "测试失败", tone: "danger" }
};

const strategyOptimizationStatusMeta: Record<StrategyOptimizationStatus, { label: string; tone: "info" | "ok" | "warn" | "danger" }> = {
  completed: { label: "优化完成", tone: "ok" },
  insufficient_archive_coverage: { label: "30天覆盖不足", tone: "warn" },
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
  no_strategy_signal_on_latest_bars: "最新行情未触发信号",
  strategy_disabled: "策略未开启",
  minute_bars_missing: "分钟线缺失",
  provider_failed: "行情 provider 失败",
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
  risk_reward_target: "盈亏比达标",
  atr_target: "ATR 目标达标",
  atr_target_plan: "ATR 目标计划",
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
  mean_reversion_failed: "均值回归失败",
  always_in_long: "Always In 多头",
  always_in_short: "Always In 空头",
  strong_trend_breakout: "强趋势突破",
  ema20_slope_up: "20 EMA 斜率向上",
  ema20_slope_down: "20 EMA 斜率向下",
  h2_pullback: "H2 二级回调",
  l2_pullback: "L2 二级回调",
  pullback_volume_contracting: "回调缩量",
  ema20_reclaim: "收回 20 EMA",
  ema20_reject: "跌回 20 EMA",
  ema9_trailing_exit: "9 EMA 追踪出场",
  range_regime_confirmed: "震荡区间成立",
  ema20_flat_magnet: "20 EMA 钝化磁铁",
  ema20_threaded: "K 线反复穿越 EMA",
  bottom_edge_test: "测试区间下沿",
  top_edge_test: "测试区间上沿",
  failed_breakdown: "下破失败",
  failed_breakout: "上破失败",
  bottom_edge_rejection: "下沿拒绝",
  top_edge_rejection: "上沿拒绝",
  lower_shadow_reversal: "长下影反转",
  upper_shadow_reversal: "长上影反转",
  bullish_reversal_bar: "强看涨反转 K",
  bearish_reversal_bar: "强看跌反转 K",
  next_bar_open_entry: "下一根开盘入场",
  middle_magnet_first_target: "中轴磁铁第一目标",
  opposite_range_edge_target: "对侧区间边缘目标",
  vwap_break_even_trigger: "VWAP 保本触发",
  opposite_range_edge_reached: "触达对侧区间边缘",
  opposite_trend_bar_exit: "反向趋势 K 离场"
};

const strategyParamGroups = [
  {
    key: "capital",
    title: "资金",
    detail: "本金和每次入场仓位",
    paramKeys: ["initial_capital", "entry_capital_ratio"]
  },
  {
    key: "entry",
    title: "开仓",
    detail: "突破前置、趋势过滤和动能过滤",
    paramKeys: [
      "local_window",
      "shadow_ratio",
      "range_lookback_bars",
      "min_edge_touches",
      "edge_zone_ratio",
      "trend_ema_period",
      "bb_period",
      "bb_stddev",
      "ema_period",
      "adx_period",
      "adx_trend_threshold",
      "adx_chop_threshold",
      "rsi_period",
      "volume_average_period",
      "volume_multiplier",
      "breakout_volume_multiplier",
      "pullback_volume_max_ratio",
      "squeeze_percentile",
      "setup_minutes",
      "setup_breakout_bars",
      "trend_setup_lookback",
      "max_pullback_bars",
      "opening_range_bars",
      "ema_slope_lookback",
      "ema_slope_min",
      "max_ema_slope",
      "min_ema_thread_bars",
      "edge_touch_tolerance_ticks",
      "big_body_strength_ratio",
      "body_strength_ratio",
      "entry_body_strength_ratio",
      "reversal_shadow_ratio",
      "reversal_body_strength_ratio",
      "min_range_height",
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
    paramKeys: ["exit_ema_period", "max_holding_bars", "exit_type", "first_target_exit_fraction"]
  },
  {
    key: "risk",
    title: "止盈止损",
    detail: "ATR、止损和被动止盈目标",
    paramKeys: [
      "risk_reward",
      "tick_size",
      "stop_tick_offset",
      "atr_period",
      "atr_stop_multiplier",
      "atr_target_multiplier",
      "first_target_exit_fraction"
    ]
  }
];

const strategyHistorySourceLabel: Record<StrategyConfigHistory["change_source"], string> = {
  history_rollback: "版本回退",
  manual_edit: "手工编辑",
  optimization_candidate_apply: "套用优化候选",
  template_backfill: "模板升级"
};

const integerFormatter = new Intl.NumberFormat("en-US");
const decimalFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2
});
const DEFAULT_STRATEGY_INITIAL_CAPITAL = 100000;
const DEFAULT_STRATEGY_ENTRY_CAPITAL_RATIO = 0.2;

function isAbortError(err: unknown) {
  return err instanceof Error && err.name === "AbortError";
}

type StrategyParamValue = number | string;
type StrategyConfigMode = "edit" | "create";
type WorkspaceTab = "review" | "strategy" | "live";
type LiveProvider = "futu" | "yahoo" | "fake";
type ReviewDrillSurfaceTab = "data" | "loss";
type ReviewDrillTab = "date" | "symbol";
type StrategyFeedbackTone = "info" | "ok" | "warn" | "danger";
type StrategyRunFeedback = {
  tone: StrategyFeedbackTone;
  title: string;
  detail: string;
};
type StrategyScanRow = {
  optimization: StrategyOptimizationRun | null;
  symbol: string;
  testBatch: StrategyTestBatch | null;
};
type StrategyReviewMode = "date" | "symbol";
type StrategyReviewEntry = {
  batch: StrategyTestBatch;
  day: StrategyTestDayResult;
};
type StrategyMetricSummary = {
  closedGroupCount: number;
  coverageRatio: number;
  maxDrawdown: number;
  profitFactor: number | null;
  signalCount: number;
  totalPnl: number;
  winRate: number;
};
type StrategyDateSummary = StrategyMetricSummary & {
  entries: StrategyReviewEntry[];
  status: StrategyRunStatus;
  symbolCount: number;
  tradeDate: string;
};
type StrategySymbolSummary = StrategyMetricSummary & {
  batch: StrategyTestBatch;
  entries: StrategyReviewEntry[];
  status: StrategyTestBatchStatus;
  symbol: string;
};
type StrategyTestDayDetailCacheEntry = {
  archive: MarketMinuteArchive | null;
  error: string | null;
  run: StrategySignalRun | null;
  status: "loading" | "ready" | "failed";
};
type StrategyArchiveRangeSummary = {
  availableCount: number;
  earliestAvailableDate: string | null;
  expectedCount: number;
  latestAvailableDate: string | null;
  nonAvailableCount: number;
  symbol: string;
  totalCount: number;
  windowEndDate: string | null;
  windowStartDate: string | null;
};
type LossReviewCategorySummary = {
  count: number;
  key: string;
  label: string;
  reviewedCount: number;
  share: number;
  totalPnl: number;
};
type LossReviewSortMode = "time_desc" | "loss_desc";
type LossReviewTimeFilterMode = "all" | "month" | "week" | "custom";
type ProfitLossReviewMode = "profit" | "loss";
type LossReviewTimeWindowKey =
  | "early_session"
  | "late_morning_transition"
  | "lunch_hour_squeeze"
  | "early_afternoon_drift"
  | "power_hour"
  | "outside_regular";
type LossReviewVolatilityRegimeKey = "extreme" | "high" | "normal" | "low" | "missing";
type LossReviewTimeWindowDefinition = {
  detail: string;
  endMinute: number;
  key: LossReviewTimeWindowKey;
  label: string;
  startMinute: number;
};
type LossReviewMarketRegimeMode = "all" | "loss";
type LossReviewMarketRegimeCell = {
  count: number;
  key: string;
  largestLoss: number | null;
  lossAmount: number;
  lossShare: number;
  timeWindowKey: LossReviewTimeWindowKey;
  totalPnl: number;
  volatilityKey: LossReviewVolatilityRegimeKey;
};
type LossReviewTimeWindowSummary = {
  count: number;
  key: LossReviewTimeWindowKey;
  totalPnl: number;
};
type LossReviewMarketRegimeRow = {
  cells: LossReviewMarketRegimeCell[];
  detail: string;
  key: LossReviewVolatilityRegimeKey;
  label: string;
};
type LossReviewMarketRegimeMatrix = {
  maxLossCell: LossReviewMarketRegimeCell | null;
  maxLossAmount: number;
  maxProfitCell: LossReviewMarketRegimeCell | null;
  rows: LossReviewMarketRegimeRow[];
  timeWindowSummaries: LossReviewTimeWindowSummary[];
  timeWindows: LossReviewTimeWindowDefinition[];
  topCell: LossReviewMarketRegimeCell | null;
};

const lossReviewUnreviewedKey = "unreviewed";
const LOSS_REVIEW_PAGE_SIZE = 20;
const lossReviewPieColors = ["#4f63a8", "#d46b08", "#237804", "#8c6d1f", "#0f766e", "#a8071a", "#607080"];
const lossReviewTimeFilterLabels: Record<LossReviewTimeFilterMode, string> = {
  all: "全部",
  month: "本月",
  week: "本周",
  custom: "特定时间段"
};
const profitLossReviewModeLabels: Record<ProfitLossReviewMode, string> = {
  profit: "仅看盈利单",
  loss: "仅看亏损单"
};
const lossReviewRegularTimeWindows: LossReviewTimeWindowDefinition[] = [
  { detail: "09:30-10:30", endMinute: 10 * 60 + 30, key: "early_session", label: "早盘高动能", startMinute: 9 * 60 + 30 },
  {
    detail: "10:30-11:30",
    endMinute: 11 * 60 + 30,
    key: "late_morning_transition",
    label: "早盘至中盘过渡",
    startMinute: 10 * 60 + 30
  },
  {
    detail: "11:30-13:30",
    endMinute: 13 * 60 + 30,
    key: "lunch_hour_squeeze",
    label: "中盘死寂垃圾时间",
    startMinute: 11 * 60 + 30
  },
  {
    detail: "13:30-15:00",
    endMinute: 15 * 60,
    key: "early_afternoon_drift",
    label: "尾盘蓄势期",
    startMinute: 13 * 60 + 30
  },
  { detail: "15:00-16:00", endMinute: 16 * 60, key: "power_hour", label: "尾盘生死时速", startMinute: 15 * 60 }
];
const lossReviewOutsideRegularWindow: LossReviewTimeWindowDefinition = {
  detail: "09:30前/16:00后",
  endMinute: 24 * 60,
  key: "outside_regular",
  label: "非常规",
  startMinute: 0
};
const lossReviewVolatilityRegimes: Array<{
  detail: string;
  key: LossReviewVolatilityRegimeKey;
  label: string;
}> = [
  { detail: "> 3.0 x ATR", key: "extreme", label: "极端冲击" },
  { detail: "1.5-3.0 x ATR", key: "high", label: "高波动" },
  { detail: "0.5-1.5 x ATR", key: "normal", label: "常规波动" },
  { detail: "< 0.5 x ATR", key: "low", label: "低波动" },
  { detail: "缺开仓前 20 根 ATR", key: "missing", label: "缺 ATR 证据" }
];

function strategyTestDayDetailKey(batchId: string | null | undefined, dayResultId: string) {
  return `${batchId ?? "unbatched"}:${dayResultId}`;
}

function parseStrategySymbolInput(value: string) {
  const symbols = value
    .split(/[,\s，、]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  return Array.from(new Set(symbols));
}

function strategySymbolSummary(symbols: string[]) {
  if (symbols.length <= 3) return symbols.join(", ");
  return `${symbols.slice(0, 3).join(", ")} 等 ${formatInteger(symbols.length)} 个标的`;
}

function isoDateValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function recentStrategyCalendarDates(endDate: string, windowDays = 30) {
  const cursor = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(cursor.getTime())) return [];

  cursor.setDate(cursor.getDate() - (windowDays - 1));
  return Array.from({ length: windowDays }, () => {
    const value = isoDateValue(cursor);
    cursor.setDate(cursor.getDate() + 1);
    return value;
  });
}

function isNewerArchive(candidate: MarketMinuteArchive, current: MarketMinuteArchive) {
  const createdAtOrder = candidate.created_at.localeCompare(current.created_at);
  if (createdAtOrder !== 0) return createdAtOrder > 0;
  return candidate.archive_id.localeCompare(current.archive_id) > 0;
}

function summarizeStrategyArchiveRange(
  symbol: string,
  archives: MarketMinuteArchive[],
  expectedDates: string[] = []
): StrategyArchiveRangeSummary {
  const expectedDateSet = new Set(expectedDates);
  const latestByDate = new Map<string, MarketMinuteArchive>();
  archives
    .filter((archive) => archive.symbol === symbol)
    .filter((archive) => expectedDateSet.size === 0 || expectedDateSet.has(archive.trade_date))
    .forEach((archive) => {
      const current = latestByDate.get(archive.trade_date);
      if (!current || isNewerArchive(archive, current)) latestByDate.set(archive.trade_date, archive);
    });

  const scopedArchives =
    expectedDates.length > 0
      ? expectedDates.map((tradeDate) => latestByDate.get(tradeDate) ?? null)
      : Array.from(latestByDate.values()).sort((left, right) => left.trade_date.localeCompare(right.trade_date));
  const recordedArchives = scopedArchives.filter((archive): archive is MarketMinuteArchive => Boolean(archive));
  const availableDates = recordedArchives
    .filter((archive) => archive.data_status === "available")
    .map((archive) => archive.trade_date);
  const windowDates = expectedDates.length > 0 ? expectedDates : recordedArchives.map((archive) => archive.trade_date);
  return {
    availableCount: availableDates.length,
    earliestAvailableDate: availableDates[0] ?? null,
    expectedCount: scopedArchives.length,
    latestAvailableDate: availableDates[availableDates.length - 1] ?? null,
    nonAvailableCount: scopedArchives.length - availableDates.length,
    symbol,
    totalCount: recordedArchives.length,
    windowEndDate: windowDates[windowDates.length - 1] ?? null,
    windowStartDate: windowDates[0] ?? null
  };
}

function newestRecord<T extends { created_at: string; id: string }>(items: T[]) {
  return [...items].sort((left, right) => {
    const createdAtOrder = right.created_at.localeCompare(left.created_at);
    if (createdAtOrder !== 0) return createdAtOrder;
    return right.id.localeCompare(left.id);
  })[0] ?? null;
}

function completedStrategyBatches(rows: StrategyScanRow[]) {
  return rows.map((row) => row.testBatch).filter((batch): batch is StrategyTestBatch => Boolean(batch));
}

function strategyReviewEntries(rows: StrategyScanRow[]) {
  return completedStrategyBatches(rows).flatMap((batch) => batch.day_results.map((day) => ({ batch, day })));
}

function weightedWinRate(items: Array<{ closedGroupCount: number; winRate: number }>) {
  const closedGroupCount = items.reduce((total, item) => total + item.closedGroupCount, 0);
  if (closedGroupCount <= 0) return 0;
  const winningGroups = items.reduce((total, item) => total + item.closedGroupCount * item.winRate, 0);
  return winningGroups / closedGroupCount;
}

function grossFromProfitFactor(item: { closedGroupCount: number; profitFactor: number | null; totalPnl: number }) {
  if (item.closedGroupCount <= 0) return { grossLoss: 0, grossProfit: 0, known: true };
  if (item.profitFactor === null) {
    if (item.totalPnl >= 0) return { grossLoss: 0, grossProfit: item.totalPnl, known: true };
    return { grossLoss: item.totalPnl, grossProfit: 0, known: true };
  }
  if (item.profitFactor === 0) return { grossLoss: item.totalPnl, grossProfit: 0, known: true };
  if (item.profitFactor === 1) {
    return item.totalPnl === 0
      ? { grossLoss: 0, grossProfit: 0, known: false }
      : { grossLoss: 0, grossProfit: 0, known: false };
  }
  const grossLossAbs = item.totalPnl / (item.profitFactor - 1);
  if (!Number.isFinite(grossLossAbs) || grossLossAbs < 0) return { grossLoss: 0, grossProfit: 0, known: false };
  return {
    grossLoss: -grossLossAbs,
    grossProfit: item.profitFactor * grossLossAbs,
    known: true
  };
}

function aggregateProfitFactor(items: Array<{ closedGroupCount: number; profitFactor: number | null; totalPnl: number }>) {
  let grossProfit = 0;
  let grossLoss = 0;
  for (const item of items) {
    const gross = grossFromProfitFactor(item);
    if (!gross.known) return null;
    grossProfit += gross.grossProfit;
    grossLoss += gross.grossLoss;
  }
  return grossLoss < 0 ? grossProfit / Math.abs(grossLoss) : null;
}

function maxDrawdownFromPnls(dayPnls: number[]) {
  let peak = 0;
  let equity = 0;
  let maxDrawdown = 0;
  for (const pnl of dayPnls) {
    equity += pnl;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.max(maxDrawdown, peak - equity);
  }
  return maxDrawdown;
}

function aggregateMaxDrawdownFromEntries(entries: StrategyReviewEntry[]) {
  const pnlByDate = new Map<string, number>();
  for (const entry of entries) {
    if (entry.day.status !== "completed") continue;
    pnlByDate.set(entry.day.trade_date, (pnlByDate.get(entry.day.trade_date) ?? 0) + entry.day.total_pnl);
  }
  const dayPnls = Array.from(pnlByDate.entries())
    .sort(([leftDate], [rightDate]) => leftDate.localeCompare(rightDate))
    .map(([, pnl]) => pnl);
  return maxDrawdownFromPnls(dayPnls);
}

function aggregateBatchMetrics(batches: StrategyTestBatch[]): StrategyMetricSummary | null {
  if (batches.length === 0) return null;
  const dayResults = batches.flatMap((batch) => batch.day_results);
  const dayCapacity = batches.reduce((total, batch) => total + batch.day_count, 0);
  const availableDayCount = batches.reduce((total, batch) => total + batch.available_day_count, 0);
  const entries = batches.flatMap((batch) => batch.day_results.map((day) => ({ batch, day })));
  return {
    closedGroupCount: dayResults.reduce((total, day) => total + day.closed_group_count, 0),
    coverageRatio: dayCapacity > 0 ? availableDayCount / dayCapacity : 0,
    maxDrawdown: aggregateMaxDrawdownFromEntries(entries),
    profitFactor: aggregateProfitFactor(
      batches.map((batch) => ({
        closedGroupCount: batch.day_results.reduce((total, day) => total + day.closed_group_count, 0),
        profitFactor: batch.profit_factor,
        totalPnl: batch.total_pnl
      }))
    ),
    signalCount: batches.reduce((total, batch) => total + batch.signal_count, 0),
    totalPnl: batches.reduce((total, batch) => total + batch.total_pnl, 0),
    winRate: weightedWinRate(dayResults.map((day) => ({ closedGroupCount: day.closed_group_count, winRate: day.win_rate })))
  };
}

function aggregateDayEntryMetrics(entries: StrategyReviewEntry[]): StrategyMetricSummary {
  const totalPnl = entries.reduce((total, entry) => total + entry.day.total_pnl, 0);
  return {
    closedGroupCount: entries.reduce((total, entry) => total + entry.day.closed_group_count, 0),
    coverageRatio: entries.length > 0 ? entries.filter((entry) => entry.day.status === "completed").length / entries.length : 0,
    maxDrawdown: maxDrawdownFromPnls([totalPnl]),
    profitFactor: aggregateProfitFactor(
      entries.map((entry) => ({
        closedGroupCount: entry.day.closed_group_count,
        profitFactor: entry.day.profit_factor,
        totalPnl: entry.day.total_pnl
      }))
    ),
    signalCount: entries.reduce((total, entry) => total + entry.day.signal_count, 0),
    totalPnl,
    winRate: weightedWinRate(entries.map((entry) => ({ closedGroupCount: entry.day.closed_group_count, winRate: entry.day.win_rate })))
  };
}

function hasStrategyOrders(entry: StrategyReviewEntry) {
  return entry.day.signal_count > 0 || entry.day.closed_group_count > 0;
}

function aggregateStrategyRunStatus(entries: StrategyReviewEntry[]): StrategyRunStatus {
  const statuses = entries.map((entry) => entry.day.status);
  const priority: StrategyRunStatus[] = [
    "failed",
    "non_available_archive",
    "missing_archive",
    "insufficient_bars",
    "strategy_disabled",
    "completed"
  ];
  return priority.find((status) => statuses.includes(status)) ?? "completed";
}

function strategyDateSummaries(rows: StrategyScanRow[]): StrategyDateSummary[] {
  const grouped = new Map<string, StrategyReviewEntry[]>();
  for (const entry of strategyReviewEntries(rows)) {
    grouped.set(entry.day.trade_date, [...(grouped.get(entry.day.trade_date) ?? []), entry]);
  }
  return Array.from(grouped.entries())
    .sort(([leftDate], [rightDate]) => rightDate.localeCompare(leftDate))
    .map(([tradeDate, entries]) => {
      const orderEntries = entries.filter(hasStrategyOrders);
      const statusEntries = orderEntries.length > 0 ? orderEntries : entries;
      const metrics = aggregateDayEntryMetrics(orderEntries);
      return {
        ...metrics,
        entries: orderEntries,
        status: aggregateStrategyRunStatus(statusEntries),
        symbolCount: new Set(orderEntries.map((entry) => entry.batch.symbol)).size,
        tradeDate
      };
    });
}

function strategySymbolSummaries(rows: StrategyScanRow[]): StrategySymbolSummary[] {
  return completedStrategyBatches(rows)
    .map((batch) => {
      const entries = batch.day_results.map((day) => ({ batch, day })).filter(hasStrategyOrders);
      return {
        ...(aggregateBatchMetrics([batch]) ?? {
          closedGroupCount: 0,
          coverageRatio: 0,
          maxDrawdown: 0,
          profitFactor: null,
          signalCount: 0,
          totalPnl: 0,
          winRate: 0
        }),
        batch,
        entries,
        status: batch.status,
        symbol: batch.symbol
      };
    })
    .filter((row) => row.entries.length > 0);
}

function mergeStrategyTestBatches(current: StrategyTestBatch[], next: StrategyTestBatch[]) {
  const nextIds = new Set(next.map((item) => item.batch_id));
  return [...next, ...current.filter((item) => !nextIds.has(item.batch_id))];
}

function mergeStrategyOptimizations(current: StrategyOptimizationRun[], next: StrategyOptimizationRun[]) {
  const nextIds = new Set(next.map((item) => item.optimization_id));
  return [...next, ...current.filter((item) => !nextIds.has(item.optimization_id))];
}

function dedupeStrategyOptimizations(items: StrategyOptimizationRun[]) {
  const byId = new Map<string, StrategyOptimizationRun>();
  items.forEach((item) => {
    if (!byId.has(item.optimization_id)) {
      byId.set(item.optimization_id, item);
    }
  });
  return Array.from(byId.values());
}

function optimizationSymbols(optimization: StrategyOptimizationRun) {
  if (optimization.symbols?.length) return optimization.symbols;
  return parseStrategySymbolInput(optimization.symbol);
}

function optimizationCoversSymbol(optimization: StrategyOptimizationRun, symbol: string) {
  return optimizationSymbols(optimization).includes(symbol.trim().toUpperCase());
}

function optimizationScopeLabel(optimization: StrategyOptimizationRun) {
  return strategySymbolSummary(optimizationSymbols(optimization));
}

function isClosedLossTradeGroup(group: TradeGroup) {
  return group.status === "closed" && group.pnl !== null && group.pnl < 0;
}

function isClosedProfitTradeGroup(group: TradeGroup) {
  return group.status === "closed" && group.pnl !== null && group.pnl > 0;
}

function isClosedProfitLossTradeGroup(group: TradeGroup) {
  return isClosedProfitTradeGroup(group) || isClosedLossTradeGroup(group);
}

function profitLossReviewGroupLabel(mode: ProfitLossReviewMode) {
  return mode === "profit" ? "盈利单" : "亏损单";
}

function tradeGroupReviewDate(group: TradeGroup) {
  return (group.closed_at ?? group.opened_at).slice(0, 10);
}

function tradeGroupReviewTimestamp(group: TradeGroup) {
  return group.closed_at ?? group.opened_at;
}

function dateKeyFromDate(date: Date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function dateFromDateKey(dateKey: string) {
  const [year, month, day] = dateKey.split("-").map((part) => Number(part));
  return new Date(year, month - 1, day);
}

function addDays(date: Date, days: number) {
  const nextDate = new Date(date);
  nextDate.setDate(nextDate.getDate() + days);
  return nextDate;
}

function monthStartDateKey(dateKey: string) {
  const date = dateFromDateKey(dateKey);
  return dateKeyFromDate(new Date(date.getFullYear(), date.getMonth(), 1));
}

function monthEndDateKey(dateKey: string) {
  const date = dateFromDateKey(dateKey);
  return dateKeyFromDate(new Date(date.getFullYear(), date.getMonth() + 1, 0));
}

function weekStartDateKey(dateKey: string) {
  const date = dateFromDateKey(dateKey);
  const weekday = date.getDay();
  const offset = weekday === 0 ? -6 : 1 - weekday;
  return dateKeyFromDate(addDays(date, offset));
}

function weekEndDateKey(dateKey: string) {
  return dateKeyFromDate(addDays(dateFromDateKey(weekStartDateKey(dateKey)), 6));
}

function normalizeLossReviewDateRange(startDate: string | null, endDate: string | null) {
  if (startDate && endDate && startDate > endDate) {
    return { endDate: startDate, startDate: endDate };
  }
  return { endDate, startDate };
}

function lossReviewTimeFilterRange(
  mode: LossReviewTimeFilterMode,
  customStartDate: string,
  customEndDate: string,
  todayDateKey: string
) {
  if (mode === "month") {
    return { endDate: monthEndDateKey(todayDateKey), startDate: monthStartDateKey(todayDateKey) };
  }
  if (mode === "week") {
    return { endDate: weekEndDateKey(todayDateKey), startDate: weekStartDateKey(todayDateKey) };
  }
  if (mode === "custom") {
    return normalizeLossReviewDateRange(customStartDate || null, customEndDate || null);
  }
  return { endDate: null, startDate: null };
}

function lossReviewTimeRangeLabel(startDate: string | null, endDate: string | null, allLabel = "全部亏损单") {
  if (startDate && endDate) return `${startDate} 至 ${endDate}`;
  if (startDate) return `${startDate} 之后`;
  if (endDate) return `${endDate} 之前`;
  return allLabel;
}

function lossReviewDateRangeIncludesGroup(group: TradeGroup, startDate: string | null, endDate: string | null) {
  const groupDate = tradeGroupReviewDate(group);
  if (startDate && groupDate < startDate) return false;
  if (endDate && groupDate > endDate) return false;
  return true;
}

function buildReviewSummaryFromTradeGroups(
  groups: TradeGroup[],
  date: string | null = null,
  symbol: string | null = null
): ReviewSummary {
  const closedGroups = groups.filter((group) => group.status === "closed");
  const openGroups = groups.filter((group) => group.status === "open");
  const realizedPnls = closedGroups.map((group) => group.pnl).filter((pnl): pnl is number => pnl !== null);
  const wins = realizedPnls.filter((pnl) => pnl > 0);
  const losses = realizedPnls.filter((pnl) => pnl < 0);
  const grossProfit = wins.reduce((total, pnl) => total + pnl, 0);
  const grossLoss = Math.abs(losses.reduce((total, pnl) => total + pnl, 0));
  const totalPnl = realizedPnls.reduce((total, pnl) => total + pnl, 0);
  const tradedQuantity = closedGroups.reduce((total, group) => total + group.total_quantity, 0);
  const maxDrawdown = closedGroups.reduce((currentMax, group) => {
    const drawdown = group.position_drawdown;
    if (drawdown.status !== "available" || drawdown.max_drawdown === null) return currentMax;
    return Math.max(currentMax, drawdown.max_drawdown);
  }, 0);
  const winRate = realizedPnls.length > 0 ? wins.length / realizedPnls.length : 0;
  const lossRate = realizedPnls.length > 0 ? losses.length / realizedPnls.length : 0;
  const averageProfit = wins.length > 0 ? grossProfit / wins.length : 0;
  const averageLoss = losses.length > 0 ? grossLoss / losses.length : 0;
  const expectedValue =
    realizedPnls.length > 0 ? winRate * averageProfit - lossRate * averageLoss : null;

  return {
    date,
    expected_value_per_trade: expectedValue,
    fill_count: groups.reduce((total, group) => total + group.fill_count, 0),
    max_single_day_drawdown: maxDrawdown,
    net_profit_per_share: tradedQuantity > 0 ? totalPnl / tradedQuantity : null,
    open_trade_group_count: openGroups.length,
    pnl: totalPnl,
    profit_factor: grossLoss > 0 ? grossProfit / grossLoss : null,
    quarantine_row_count: 0,
    source: "committed_fills_only",
    symbol,
    trade_group_count: closedGroups.length,
    traded_quantity: tradedQuantity,
    win_rate: winRate
  };
}

function buildReviewSummaryGroupsFromTradeGroups(
  groups: TradeGroup[],
  groupBy: ReviewSummaryGroup["group_by"]
): ReviewSummaryGroup[] {
  const grouped = new Map<string, TradeGroup[]>();
  for (const group of groups) {
    const key = groupBy === "date" ? tradeGroupReviewDate(group) : group.symbol;
    grouped.set(key, [...(grouped.get(key) ?? []), group]);
  }
  return Array.from(grouped.entries())
    .sort(([left], [right]) => (groupBy === "date" ? right.localeCompare(left) : left.localeCompare(right)))
    .map(([key, groupItems]) => ({
      ...buildReviewSummaryFromTradeGroups(
        groupItems,
        groupBy === "date" ? key : null,
        groupBy === "symbol" ? key : null
      ),
      group_by: groupBy,
      group_key: key,
      group_label: key
    }));
}

function lossReviewMinuteOfDay(group: TradeGroup) {
  const timestamp = tradeGroupReviewTimestamp(group);
  const match = timestamp.match(/[T\s](\d{2}):(\d{2})/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  return hour * 60 + minute;
}

function lossReviewTimeWindowKey(group: TradeGroup): LossReviewTimeWindowKey {
  const minuteOfDay = lossReviewMinuteOfDay(group);
  if (minuteOfDay === null) return "outside_regular";
  const regularWindow = lossReviewRegularTimeWindows.find(
    (window) => minuteOfDay >= window.startMinute && minuteOfDay < window.endMinute
  );
  return regularWindow?.key ?? "outside_regular";
}

function lossReviewEntryAtrMultiple(group: TradeGroup) {
  const atrMultiple = group.position_drawdown.entry_atr_multiple;
  return atrMultiple !== null && Number.isFinite(atrMultiple) ? atrMultiple : null;
}

function lossReviewVolatilityRegimeKey(group: TradeGroup): LossReviewVolatilityRegimeKey {
  const atrMultiple = lossReviewEntryAtrMultiple(group);
  if (atrMultiple === null) return "missing";
  if (atrMultiple > 3.0) return "extreme";
  if (atrMultiple >= 1.5) return "high";
  if (atrMultiple >= 0.5) return "normal";
  return "low";
}

function lossReviewMarketRegimeCellKey(timeWindowKey: LossReviewTimeWindowKey, volatilityKey: LossReviewVolatilityRegimeKey) {
  return `${timeWindowKey}:${volatilityKey}`;
}

function emptyLossReviewMarketRegimeCell(
  timeWindowKey: LossReviewTimeWindowKey,
  volatilityKey: LossReviewVolatilityRegimeKey
): LossReviewMarketRegimeCell {
  return {
    count: 0,
    key: lossReviewMarketRegimeCellKey(timeWindowKey, volatilityKey),
    largestLoss: null,
    lossAmount: 0,
    lossShare: 0,
    timeWindowKey,
    totalPnl: 0,
    volatilityKey
  };
}

function buildLossReviewMarketRegimeMatrix(
  groups: TradeGroup[],
  mode: LossReviewMarketRegimeMode = "loss"
): LossReviewMarketRegimeMatrix {
  const hasOutsideRegular = groups.some((group) => lossReviewTimeWindowKey(group) === "outside_regular");
  const timeWindows = hasOutsideRegular
    ? [...lossReviewRegularTimeWindows, lossReviewOutsideRegularWindow]
    : lossReviewRegularTimeWindows;
  const cells = new Map<string, LossReviewMarketRegimeCell>();
  for (const regime of lossReviewVolatilityRegimes) {
    for (const window of timeWindows) {
      cells.set(
        lossReviewMarketRegimeCellKey(window.key, regime.key),
        emptyLossReviewMarketRegimeCell(window.key, regime.key)
      );
    }
  }

  let totalLossAmount = 0;
  for (const group of groups) {
    const timeWindowKey = lossReviewTimeWindowKey(group);
    const volatilityKey = lossReviewVolatilityRegimeKey(group);
    const cell = cells.get(lossReviewMarketRegimeCellKey(timeWindowKey, volatilityKey));
    if (!cell) continue;
    const pnl = group.pnl ?? 0;
    const lossAmount = mode === "all" ? Math.abs(pnl) : Math.abs(Math.min(pnl, 0));
    cell.count += 1;
    cell.lossAmount += lossAmount;
    cell.totalPnl += pnl;
    if (cell.largestLoss === null || pnl < cell.largestLoss) {
      cell.largestLoss = pnl;
    }
    totalLossAmount += lossAmount;
  }

  let maxLossAmount = 0;
  let maxLossCell: LossReviewMarketRegimeCell | null = null;
  let maxProfitCell: LossReviewMarketRegimeCell | null = null;
  let topCell: LossReviewMarketRegimeCell | null = null;
  for (const cell of cells.values()) {
    cell.lossShare = totalLossAmount > 0 ? cell.lossAmount / totalLossAmount : 0;
    if (cell.count > 0 && cell.totalPnl < 0 && (maxLossCell === null || cell.totalPnl < maxLossCell.totalPnl)) {
      maxLossCell = cell;
    }
    if (cell.count > 0 && cell.totalPnl > 0 && (maxProfitCell === null || cell.totalPnl > maxProfitCell.totalPnl)) {
      maxProfitCell = cell;
    }
    if (cell.lossAmount > maxLossAmount) {
      maxLossAmount = cell.lossAmount;
      topCell = cell.count > 0 ? cell : null;
    }
  }

  const rows = lossReviewVolatilityRegimes
    .map((regime) => ({
      ...regime,
      cells: timeWindows.map((window) => cells.get(lossReviewMarketRegimeCellKey(window.key, regime.key))!)
    }))
    .filter((row) => row.key !== "missing" || row.cells.some((cell) => cell.count > 0));
  const timeWindowSummaries = timeWindows.map((window) =>
    rows.reduce<LossReviewTimeWindowSummary>(
      (summary, row) => {
        const cell = row.cells.find((item) => item.timeWindowKey === window.key);
        if (!cell) return summary;
        return {
          ...summary,
          count: summary.count + cell.count,
          totalPnl: summary.totalPnl + cell.totalPnl
        };
      },
      { count: 0, key: window.key, totalPnl: 0 }
    )
  );

  return {
    maxLossCell,
    maxLossAmount,
    maxProfitCell,
    rows,
    timeWindowSummaries,
    timeWindows,
    topCell
  };
}

function lossReviewMatrixIntensity(cell: LossReviewMarketRegimeCell, maxLossAmount: number) {
  if (cell.count === 0 || maxLossAmount <= 0) return 0;
  const ratio = cell.lossAmount / maxLossAmount;
  if (ratio >= 0.75) return 4;
  if (ratio >= 0.5) return 3;
  if (ratio >= 0.25) return 2;
  return 1;
}

function lossReviewTimeWindowLabel(key: LossReviewTimeWindowKey) {
  return [...lossReviewRegularTimeWindows, lossReviewOutsideRegularWindow].find((window) => window.key === key)?.label ?? key;
}

function lossReviewVolatilityRegimeLabel(key: LossReviewVolatilityRegimeKey) {
  return lossReviewVolatilityRegimes.find((regime) => regime.key === key)?.label ?? key;
}

function lossReviewMarketRegimeZoneLabel(cell: LossReviewMarketRegimeCell | null) {
  if (!cell) return "暂无";
  return `${lossReviewTimeWindowLabel(cell.timeWindowKey)} × ${lossReviewVolatilityRegimeLabel(
    cell.volatilityKey
  )} · ${formatPnl(cell.totalPnl)}`;
}

function sortLossReviewTradeGroups(left: TradeGroup, right: TradeGroup, mode: LossReviewSortMode = "time_desc") {
  if (mode === "loss_desc") {
    const lossOrder = Math.abs(right.pnl ?? 0) - Math.abs(left.pnl ?? 0);
    if (lossOrder !== 0) return lossOrder;
  }
  const timeOrder = tradeGroupReviewTimestamp(right).localeCompare(tradeGroupReviewTimestamp(left));
  if (timeOrder !== 0) return timeOrder;
  return left.symbol.localeCompare(right.symbol);
}

function lossReviewPrimaryReasonKey(group: TradeGroup) {
  return group.review?.reason_category ?? lossReviewUnreviewedKey;
}

function lossReviewSecondaryReasonKey(group: TradeGroup) {
  if (!group.review) return lossReviewUnreviewedKey;
  return `${group.review.reason_category}:${group.review.reason_code}`;
}

function buildLossReviewReasonSummaries(
  groups: TradeGroup[],
  keyForGroup: (group: TradeGroup) => string,
  labelForGroup: (group: TradeGroup) => string
): LossReviewCategorySummary[] {
  const summaries = new Map<string, LossReviewCategorySummary>();
  for (const group of groups) {
    const key = keyForGroup(group);
    const current =
      summaries.get(key) ??
      {
        count: 0,
        key,
        label: labelForGroup(group),
        reviewedCount: 0,
        share: 0,
        totalPnl: 0
      };
    current.count += 1;
    current.reviewedCount += group.review ? 1 : 0;
    current.totalPnl += group.pnl ?? 0;
    summaries.set(key, current);
  }
  const totalCount = groups.length || 1;
  return Array.from(summaries.values()).sort((left, right) => {
    if (left.key === lossReviewUnreviewedKey) return -1;
    if (right.key === lossReviewUnreviewedKey) return 1;
    return right.count - left.count || left.label.localeCompare(right.label);
  }).map((summary) => ({ ...summary, share: summary.count / totalCount }));
}

function buildLossReviewPrimaryReasonSummaries(groups: TradeGroup[]): LossReviewCategorySummary[] {
  return buildLossReviewReasonSummaries(
    groups,
    lossReviewPrimaryReasonKey,
    (group) => group.review?.reason_category_label ?? "待复盘"
  );
}

function buildLossReviewSecondaryReasonSummaries(groups: TradeGroup[]): LossReviewCategorySummary[] {
  return buildLossReviewReasonSummaries(
    groups,
    lossReviewSecondaryReasonKey,
    (group) => group.review?.reason_label ?? "待复盘"
  );
}

function lossReviewPieColor(index: number) {
  return lossReviewPieColors[index % lossReviewPieColors.length];
}

function lossReviewPieGradient(summaries: LossReviewCategorySummary[]) {
  const totalCount = summaries.reduce((total, summary) => total + summary.count, 0);
  if (totalCount <= 0) return "#edf2f7";
  let cursor = 0;
  const segments = summaries.map((summary, index) => {
    const start = cursor;
    const end = cursor + (summary.count / totalCount) * 100;
    cursor = end;
    return `${lossReviewPieColor(index)} ${start}% ${end}%`;
  });
  return `conic-gradient(${segments.join(", ")})`;
}

export default function App() {
  const todayDateKey = useMemo(() => dateKeyFromDate(new Date()), []);
  const [date, setDate] = useState(() => getDefaultReviewDate());
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [fills, setFills] = useState<FillRow[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [currentReviewSummary, setCurrentReviewSummary] = useState<ReviewSummary | null>(null);
  const [overallSummary, setOverallSummary] = useState<ReviewSummary | null>(null);
  const [dateSummaryGroups, setDateSummaryGroups] = useState<ReviewSummaryGroup[]>([]);
  const [symbolSummaryGroups, setSymbolSummaryGroups] = useState<ReviewSummaryGroup[]>([]);
  const [dateSymbolBreakdownByDate, setDateSymbolBreakdownByDate] = useState<Record<string, ReviewSummaryGroup[]>>({});
  const [symbolDateBreakdown, setSymbolDateBreakdown] = useState<ReviewSummaryGroup[]>([]);
  const [tradeGroups, setTradeGroups] = useState<TradeGroup[]>([]);
  const [allTradeGroups, setAllTradeGroups] = useState<TradeGroup[]>([]);
  const [quarantine, setQuarantine] = useState<QuarantineRow[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistRun | null>(null);
  const [strategyTemplates, setStrategyTemplates] = useState<StrategyTemplate[]>([]);
  const [strategies, setStrategies] = useState<StrategyConfig[]>([]);
  const [strategyHistory, setStrategyHistory] = useState<StrategyConfigHistory[]>([]);
  const [strategyRuns, setStrategyRuns] = useState<StrategySignalRun[]>([]);
  const [strategyTestBatches, setStrategyTestBatches] = useState<StrategyTestBatch[]>([]);
  const [strategyOptimizations, setStrategyOptimizations] = useState<StrategyOptimizationRun[]>([]);
  const [selectedOptimization, setSelectedOptimization] = useState<StrategyOptimizationRun | null>(null);
  const [selectedStrategyTestBatchId, setSelectedStrategyTestBatchId] = useState<string | null>(null);
  const [selectedStrategyTestDayId, setSelectedStrategyTestDayId] = useState<string | null>(null);
  const [strategyTestDayDetailCache, setStrategyTestDayDetailCache] = useState<Record<string, StrategyTestDayDetailCacheEntry>>({});
  const [strategyTestDayRun, setStrategyTestDayRun] = useState<StrategySignalRun | null>(null);
  const [strategyTestDayArchive, setStrategyTestDayArchive] = useState<MarketMinuteArchive | null>(null);
  const [strategyTestDayDetailBusy, setStrategyTestDayDetailBusy] = useState(false);
  const [minuteArchives, setMinuteArchives] = useState<MarketMinuteArchive[]>([]);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceTab>("review");
  const [activeReviewDrillSurfaceTab, setActiveReviewDrillSurfaceTab] = useState<ReviewDrillSurfaceTab>("data");
  const [activeReviewDrillTab, setActiveReviewDrillTab] = useState<ReviewDrillTab>("date");
  const [dataReviewTimeFilterMode, setDataReviewTimeFilterMode] = useState<LossReviewTimeFilterMode>("all");
  const [customDataReviewStartDate, setCustomDataReviewStartDate] = useState(monthStartDateKey(todayDateKey));
  const [customDataReviewEndDate, setCustomDataReviewEndDate] = useState(todayDateKey);
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [showLossOnlyTradeGroups, setShowLossOnlyTradeGroups] = useState(false);
  const [strategySymbolInput, setStrategySymbolInput] = useState("");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const [liveSymbols, setLiveSymbols] = useState<string[]>([]);
  const [liveProvider, setLiveProvider] = useState<LiveProvider>("yahoo");
  const [liveLookbackMinutes, setLiveLookbackMinutes] = useState(180);
  const [liveSignalResults, setLiveSignalResults] = useState<LiveStrategySignalResult[]>([]);
  const [liveSignalBusy, setLiveSignalBusy] = useState(false);
  const [liveMonitorActive, setLiveMonitorActive] = useState(false);
  const [liveMonitorLastUpdated, setLiveMonitorLastUpdated] = useState<string | null>(null);
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
  const [lossReviewBusy, setLossReviewBusy] = useState<string | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [strategyBusy, setStrategyBusy] = useState(false);
  const [strategyArchiveRangeBusy, setStrategyArchiveRangeBusy] = useState(false);
  const [strategyArchiveRangeError, setStrategyArchiveRangeError] = useState<string | null>(null);
  const [strategyArchiveRanges, setStrategyArchiveRanges] = useState<StrategyArchiveRangeSummary[]>([]);
  const [strategyTestBusy, setStrategyTestBusy] = useState(false);
  const [strategyOptimizationBusy, setStrategyOptimizationBusy] = useState(false);
  const [strategySaveBusy, setStrategySaveBusy] = useState(false);
  const [strategyCreateBusy, setStrategyCreateBusy] = useState(false);
  const [strategyHistoryBusy, setStrategyHistoryBusy] = useState(false);
  const [strategyRollbackBusy, setStrategyRollbackBusy] = useState<string | null>(null);
  const [strategyRunFeedback, setStrategyRunFeedback] = useState<StrategyRunFeedback | null>(null);
  const [strategyArchiveFeedback, setStrategyArchiveFeedback] = useState<StrategyRunFeedback | null>(null);
  const [strategyScanFeedback, setStrategyScanFeedback] = useState<StrategyRunFeedback | null>(null);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const [showTradeMarkers, setShowTradeMarkers] = useState(true);
  const [showFullDayStrategyBars, setShowFullDayStrategyBars] = useState(false);
  const [strategyConfigOpen, setStrategyConfigOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewModuleRef = useRef<HTMLElement | null>(null);
  const refreshRequestIdRef = useRef(0);
  const refreshAbortControllerRef = useRef<AbortController | null>(null);
  const currentReviewSummaryRequestIdRef = useRef(0);
  const liveSignalRequestIdRef = useRef(0);
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
  const symbolScopedTradeGroups = useMemo(
    () => (selectedSymbol ? tradeGroups.filter((group) => group.symbol === selectedSymbol) : tradeGroups),
    [selectedSymbol, tradeGroups]
  );
  const displayedTradeGroups = useMemo(
    () =>
      showLossOnlyTradeGroups
        ? symbolScopedTradeGroups.filter((group) => group.status === "closed" && group.pnl !== null && group.pnl < 0)
        : symbolScopedTradeGroups,
    [showLossOnlyTradeGroups, symbolScopedTradeGroups]
  );
  const displayedChartFills = useMemo(() => {
    if (!showLossOnlyTradeGroups) return displayedFills;
    const groupScopes = displayedTradeGroups.map((group) => ({
      accountCanonical: group.account_canonical,
      rawLineNumbers: new Set(group.raw_line_numbers),
      sourceBatchIds: new Set(group.source_batch_ids),
      symbol: group.symbol
    }));
    return displayedFills.filter((fill) =>
      groupScopes.some(
        (scope) =>
          scope.accountCanonical === fill.account_canonical &&
          scope.symbol === fill.symbol &&
          scope.sourceBatchIds.has(fill.source_batch_id) &&
          scope.rawLineNumbers.has(fill.raw_line_number)
      )
    );
  }, [displayedFills, displayedTradeGroups, showLossOnlyTradeGroups]);
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
  const strategySymbols = useMemo(
    () => parseStrategySymbolInput(strategySymbolInput || selectedSymbol),
    [selectedSymbol, strategySymbolInput]
  );
  const strategySymbolsKey = strategySymbols.join(",");
  const primaryStrategySymbol = strategySymbols[0] ?? selectedSymbol;
  const liveSymbolOptions = useMemo(
    () =>
      Array.from(
        new Set([
          ...symbolOptions,
          ...(watchlist?.items.map((item) => item.symbol) ?? []),
          ...strategySymbols,
          "MU",
          "NVDA",
          "AMD",
          "AVGO",
          "TSM",
          "MSFT",
          "QQQ",
          "SMH"
        ])
      )
        .filter(Boolean)
        .sort((left, right) => left.localeCompare(right)),
    [strategySymbolsKey, symbolOptions, watchlist]
  );
  const liveSymbolsKey = liveSymbols.join(",");
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
  const latestStrategyRun = useMemo(
    () =>
      strategyRuns.find(
        (run) =>
          run.trade_date === date &&
          run.symbol === primaryStrategySymbol &&
          run.strategy_id === selectedStrategyId
      ) ?? null,
    [date, primaryStrategySymbol, selectedStrategyId, strategyRuns]
  );
  const latestStrategyTestBatch = useMemo(
    () =>
      newestRecord(
        strategyTestBatches.filter(
          (batch) =>
            batch.end_date === date &&
            batch.symbol === primaryStrategySymbol &&
            batch.strategy_id === selectedStrategyId
        )
      ),
    [date, primaryStrategySymbol, selectedStrategyId, strategyTestBatches]
  );
  const strategyScanRows = useMemo<StrategyScanRow[]>(() => {
    const matchingBatches = strategyTestBatches.filter(
      (batch) =>
        batch.end_date === date &&
        batch.strategy_id === selectedStrategyId &&
        strategySymbols.includes(batch.symbol)
    );
    const matchingOptimizations = strategyOptimizations.filter(
      (optimization) =>
        optimization.end_date === date &&
        optimization.strategy_id === selectedStrategyId &&
        strategySymbols.some((symbol) => optimizationCoversSymbol(optimization, symbol))
    );
    const currentVersionOptimizations = selectedStrategy
      ? matchingOptimizations.filter((optimization) => optimization.template_version === selectedStrategy.template_version)
      : matchingOptimizations;
    const optimizationPool = currentVersionOptimizations.length > 0 ? currentVersionOptimizations : matchingOptimizations;
    return strategySymbols.map((symbol) => ({
      optimization: newestRecord(optimizationPool.filter((optimization) => optimizationCoversSymbol(optimization, symbol))),
      symbol,
      testBatch: newestRecord(matchingBatches.filter((batch) => batch.symbol === symbol))
    }));
  }, [date, selectedStrategy?.template_version, selectedStrategyId, strategySymbolsKey, strategyTestBatches, strategyOptimizations]
  );
  const strategyReviewBatches = useMemo(() => completedStrategyBatches(strategyScanRows), [strategyScanRows]);
  const strategyOverallMetrics = useMemo(() => aggregateBatchMetrics(strategyReviewBatches), [strategyReviewBatches]);
  const strategyReviewDateRows = useMemo(() => strategyDateSummaries(strategyScanRows), [strategyScanRows]);
  const strategyReviewSymbolRows = useMemo(() => strategySymbolSummaries(strategyScanRows), [strategyScanRows]);
  const selectedStrategyTestBatch = useMemo(
    () =>
      strategyReviewBatches.find((batch) => batch.batch_id === selectedStrategyTestBatchId) ??
      latestStrategyTestBatch ??
      strategyReviewBatches[0] ??
      null,
    [latestStrategyTestBatch, selectedStrategyTestBatchId, strategyReviewBatches]
  );
  const selectedStrategyTestDay = useMemo(
    () =>
      selectedStrategyTestBatch?.day_results.find((day) => day.day_result_id === selectedStrategyTestDayId) ??
      selectedStrategyTestBatch?.day_results.find((day) => day.strategy_run_id) ??
      selectedStrategyTestBatch?.day_results[0] ??
      null,
    [selectedStrategyTestBatch, selectedStrategyTestDayId]
  );
  const selectedStrategyTestDayDetail = useMemo(() => {
    if (!selectedStrategyTestBatch || !selectedStrategyTestDay) return null;
    return strategyTestDayDetailCache[
      strategyTestDayDetailKey(selectedStrategyTestBatch.batch_id, selectedStrategyTestDay.day_result_id)
    ] ?? null;
  }, [selectedStrategyTestBatch, selectedStrategyTestDay, strategyTestDayDetailCache]);
  const latestOptimization =
    selectedOptimization ??
    (selectedStrategy
      ? strategyOptimizations.find((optimization) => optimization.template_version === selectedStrategy.template_version)
      : null) ??
    strategyOptimizations[0] ??
    null;
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
    refreshAbortControllerRef.current?.abort();
    const refreshAbortController = new AbortController();
    refreshAbortControllerRef.current = refreshAbortController;
    const requestOptions = { signal: refreshAbortController.signal };
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
        nextAllTradeGroups
      ] =
        await Promise.all([
          fetchBatches(requestOptions),
          fetchFills(refreshDate, undefined, requestOptions),
          fetchTradeGroups(refreshDate, undefined, requestOptions),
          fetchReviewSummary(refreshDate, undefined, requestOptions),
          fetchReviewSummary(undefined, undefined, requestOptions),
          fetchReviewSummaryGroups("date", {}, requestOptions),
          fetchReviewSummaryGroups("symbol", {}, requestOptions),
          fetchReviewSummaryGroups("symbol", { date: refreshDate }, requestOptions),
          refreshSymbol ? fetchReviewSummaryGroups("date", { symbol: refreshSymbol }, requestOptions) : Promise.resolve([]),
          fetchWatchlist(refreshDate, requestOptions),
          fetchTradeGroups(undefined, undefined, { ...requestOptions, includeDetails: false })
        ]);
      const nextDateSymbolBreakdownByDate: Record<string, ReviewSummaryGroup[]> = {
        [refreshDate]: nextDateSymbolBreakdown
      };
      const requestedBatch = nextBatchId
        ? nextBatches.find((batch) => batch.batch_id === nextBatchId)?.batch_id ?? null
        : null;
      const batchToLoad = requestedBatch ?? nextBatches[0]?.batch_id ?? null;
      const nextQuarantine = batchToLoad ? await fetchQuarantine(batchToLoad, requestOptions) : [];
      if (requestId !== refreshRequestIdRef.current) return;
      setBatches(nextBatches);
      setFills(nextFills);
      setTradeGroups(nextTradeGroups);
      setAllTradeGroups(nextAllTradeGroups);
      setSummary(nextSummary);
      setOverallSummary(nextOverallSummary);
      setDateSummaryGroups(nextDateGroups);
      setSymbolSummaryGroups(nextSymbolGroups);
      setDateSymbolBreakdownByDate(nextDateSymbolBreakdownByDate);
      setSymbolDateBreakdown(nextSymbolDateBreakdown);
      setWatchlist(nextWatchlist);
      setSelectedBatch(batchToLoad);
      setQuarantine(nextQuarantine);
    } catch (err: unknown) {
      if (isAbortError(err)) return;
      if (requestId === refreshRequestIdRef.current) {
        setError(err instanceof Error ? err.message : "数据加载失败");
      }
    } finally {
      if (requestId === refreshRequestIdRef.current) {
        if (refreshAbortControllerRef.current === refreshAbortController) {
          refreshAbortControllerRef.current = null;
        }
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

  async function loadStrategyArchiveRanges(symbols = strategySymbols, endDate = date) {
    if (symbols.length === 0) {
      setStrategyArchiveRanges([]);
      setStrategyArchiveRangeError(null);
      setStrategyArchiveRangeBusy(false);
      return;
    }
    setStrategyArchiveRangeBusy(true);
    setStrategyArchiveRangeError(null);
    try {
      const expectedDates = recentStrategyCalendarDates(endDate, 30);
      const archiveLists = await Promise.all(symbols.map((symbol) => fetchMinuteArchives(undefined, symbol, "yahoo")));
      setStrategyArchiveRanges(
        symbols.map((symbol, index) => summarizeStrategyArchiveRange(symbol, archiveLists[index] ?? [], expectedDates))
      );
    } catch (err) {
      setStrategyArchiveRanges([]);
      setStrategyArchiveRangeError(err instanceof Error ? err.message : "分钟线归档范围读取失败");
    } finally {
      setStrategyArchiveRangeBusy(false);
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

  async function loadCurrentReviewSummary(nextDate = date, symbol = selectedSymbol) {
    const requestId = currentReviewSummaryRequestIdRef.current + 1;
    currentReviewSummaryRequestIdRef.current = requestId;
    const currentSymbol = symbol || undefined;
    try {
      const nextSummary = await fetchReviewSummary(nextDate, currentSymbol);
      if (requestId !== currentReviewSummaryRequestIdRef.current) return;
      setCurrentReviewSummary(nextSummary);
    } catch (err) {
      if (requestId !== currentReviewSummaryRequestIdRef.current) return;
      setCurrentReviewSummary(null);
      setError(err instanceof Error ? err.message : "当前复盘摘要读取失败");
    }
  }

  async function loadStrategyCatalog() {
    try {
      const [nextTemplates, nextStrategies] = await Promise.all([fetchStrategyTemplates(), fetchStrategies()]);
      setStrategyTemplates(nextTemplates);
      setStrategies(nextStrategies);
    } catch (err) {
      setStrategyTemplates([]);
      setStrategies([]);
      setError(err instanceof Error ? err.message : "蝑閮剖???霂餃?憭梯揖");
    }
  }

  async function loadStrategyHistory(strategyId = selectedStrategyId) {
    if (!strategyId) {
      setStrategyHistory([]);
      return;
    }
    setStrategyHistoryBusy(true);
    try {
      setStrategyHistory(await fetchStrategyHistory(strategyId));
    } catch (err) {
      setStrategyHistory([]);
      setError(err instanceof Error ? err.message : "策略版本记录读取失败");
    } finally {
      setStrategyHistoryBusy(false);
    }
  }

  async function loadStrategyRuns(strategyId = selectedStrategyId, symbol = primaryStrategySymbol) {
    if (!strategyId || !symbol) {
      setStrategyRuns([]);
      return;
    }
    try {
      setStrategyRuns(await fetchStrategyRuns(date, symbol, strategyId, { limit: 20 }));
    } catch (err) {
      setStrategyRuns([]);
      setError(err instanceof Error ? err.message : "策略运行记录读取失败");
    }
  }

  async function loadStrategyResearch(strategyId = selectedStrategyId, symbols = strategySymbols) {
    const targetSymbols = symbols.length > 0 ? symbols : primaryStrategySymbol ? [primaryStrategySymbol] : [];
    if (!strategyId || targetSymbols.length === 0) {
      setStrategyTestBatches([]);
      setStrategyOptimizations([]);
      setSelectedOptimization(null);
      setSelectedStrategyTestBatchId(null);
      setSelectedStrategyTestDayId(null);
      setStrategyTestDayDetailCache({});
      setStrategyTestDayRun(null);
      setStrategyTestDayArchive(null);
      return;
    }
    try {
      const researchBySymbol = await Promise.all(
        targetSymbols.map(async (symbol) => {
          const [testBatches, optimizations] = await Promise.all([
            fetchStrategyTestBatches(date, symbol, strategyId),
            fetchStrategyOptimizations(date, symbol, strategyId)
          ]);
          return { optimizations, testBatches };
        })
      );
      const testBatches = researchBySymbol.flatMap((item) => item.testBatches);
      const optimizations = dedupeStrategyOptimizations(researchBySymbol.flatMap((item) => item.optimizations));
      const currentVersionOptimizations = selectedStrategy
        ? optimizations.filter((optimization) => optimization.template_version === selectedStrategy.template_version)
        : optimizations;
      const selectedOptimizationSummary = currentVersionOptimizations[0] ?? optimizations[0] ?? null;
      setStrategyTestBatches(testBatches);
      setStrategyOptimizations(optimizations);
      if (selectedOptimizationSummary) {
        setSelectedOptimization(await fetchStrategyOptimizationDetail(selectedOptimizationSummary.optimization_id));
      } else {
        setSelectedOptimization(null);
      }
    } catch (err) {
      setStrategyTestBatches([]);
      setStrategyOptimizations([]);
      setSelectedOptimization(null);
      setSelectedStrategyTestBatchId(null);
      setStrategyTestDayDetailCache({});
      setError(err instanceof Error ? err.message : "策略研究记录读取失败");
    }
  }

  async function loadStrategyTestDayDetail(
    day: StrategyTestDayResult | null,
    strategyId = selectedStrategyId,
    symbol = primaryStrategySymbol,
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
      const [archives, run] = await Promise.all([
        fetchMinuteArchives(day.trade_date, symbol, "yahoo"),
        day.strategy_run_id ? fetchStrategyRunDetail(day.strategy_run_id) : Promise.resolve(null)
      ]);
      const archive =
        archives.find(
          (item) =>
            (day.source_archive_id && (item.archive_id === day.source_archive_id || item.id === day.source_archive_id)) ||
            (item.symbol === symbol && item.trade_date === day.trade_date)
        ) ?? null;
      setStrategyTestDayDetailCache((current) => ({
        ...current,
        [cacheKey]: { archive, error: null, run, status: "ready" }
      }));
      if (!options.prefetch) {
        setStrategyTestDayArchive(archive);
        setStrategyTestDayRun(run);
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
    if (liveSymbols.length === 0 && liveSymbolOptions.length > 0) {
      setLiveSymbols([liveSymbolOptions[0]]);
    }
  }, [liveSymbols.length, liveSymbolOptions]);

  useEffect(() => {
    if (!strategySymbolInput && selectedSymbol) {
      setStrategySymbolInput(selectedSymbol);
    }
  }, [selectedSymbol, strategySymbolInput]);

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
    void loadCurrentReviewSummary();
  }, [date, selectedSymbol]);

  useEffect(() => {
    if (activeWorkspaceTab !== "strategy") return;
    void loadStrategyCatalog();
  }, [activeWorkspaceTab]);

  useEffect(() => {
    if (activeWorkspaceTab !== "live") return;
    void loadStrategyCatalog();
  }, [activeWorkspaceTab]);

  useEffect(() => {
    if (activeWorkspaceTab !== "strategy" || !strategyConfigOpen || strategyMode !== "edit") return;
    void loadStrategyHistory();
  }, [activeWorkspaceTab, selectedStrategyId, strategyConfigOpen, strategyMode]);

  useEffect(() => {
    if (activeWorkspaceTab !== "strategy") return;
    void loadStrategyRuns();
  }, [activeWorkspaceTab, date, primaryStrategySymbol, selectedStrategyId]);

  useEffect(() => {
    if (activeWorkspaceTab !== "strategy") return;
    void loadStrategyResearch();
  }, [activeWorkspaceTab, date, selectedStrategyId, strategySymbolsKey]);

  useEffect(() => {
    if (activeWorkspaceTab !== "strategy") return;
    void loadStrategyArchiveRanges();
  }, [activeWorkspaceTab, date, strategySymbolsKey]);

  useEffect(() => {
    const batch = selectedStrategyTestBatch;
    if (
      !batch ||
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
  }, [date, selectedStrategyTestBatch?.batch_id, selectedStrategyId, selectedStrategyTestDayId]);

  useEffect(() => {
    const batch = selectedStrategyTestBatch;
    const day = selectedStrategyTestDay;
    if (!batch || !day || batch.strategy_id !== selectedStrategyId || batch.end_date !== date) return;
    const cacheKey = strategyTestDayDetailKey(batch.batch_id, day.day_result_id);
    const cached = strategyTestDayDetailCache[cacheKey];
    if (cached?.status === "loading" || cached?.status === "ready" || cached?.status === "failed") return;
    void loadStrategyTestDayDetail(day, selectedStrategyId, batch.symbol, { batchId: batch.batch_id });
  }, [
    date,
    selectedStrategyTestBatch?.batch_id,
    selectedStrategyId,
    selectedStrategyTestDay?.day_result_id,
    strategyTestDayDetailCache
  ]);

  useEffect(() => {
    if (!selectedStrategyTestDay || !selectedStrategyTestBatch) {
      setStrategyTestDayRun(null);
      setStrategyTestDayArchive(null);
      return;
    }
    const cacheKey = strategyTestDayDetailKey(selectedStrategyTestBatch.batch_id, selectedStrategyTestDay.day_result_id);
    const cached = strategyTestDayDetailCache[cacheKey];
    if (!cached || cached.status === "loading") return;
    setStrategyTestDayArchive(cached.archive);
    setStrategyTestDayRun(cached.run);
    setStrategyTestDayDetailBusy(false);
  }, [selectedStrategyTestBatch, selectedStrategyTestDay, strategyTestDayDetailCache]);

  useEffect(() => {
    setStrategyRunFeedback(null);
    setStrategyArchiveFeedback(null);
    setStrategyScanFeedback(null);
    setSelectedStrategyTestBatchId(null);
    setSelectedStrategyTestDayId(null);
    setStrategyTestDayDetailCache({});
    strategyTestDayPrefetchingRef.current.clear();
    setStrategyTestDayRun(null);
    setStrategyTestDayArchive(null);
  }, [date, selectedStrategyId, strategyMode, strategySymbolsKey]);

  useEffect(() => {
    if (strategyDraftDirty) setStrategyRunFeedback(null);
  }, [strategyDraftDirty]);

  useEffect(() => {
    liveSignalRequestIdRef.current += 1;
    setLiveSignalResults([]);
    setLiveSignalBusy(false);
    setLiveMonitorActive(false);
    setLiveMonitorLastUpdated(null);
  }, [liveLookbackMinutes, liveProvider, liveSymbolsKey, selectedStrategyId]);

  useEffect(() => {
    if (!liveMonitorActive) return;
    void refreshLiveSignals();
    const intervalId = window.setInterval(() => {
      void refreshLiveSignals();
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, [liveMonitorActive, liveLookbackMinutes, liveProvider, liveSymbolsKey, selectedStrategyId]);

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
      const archives = await fetchMinuteArchives(tradeDate, group.symbol, "yahoo");
      setMinuteArchives(archives);
      const refreshedGroups = await fetchTradeGroups(tradeDate, undefined, { includeDetails: true });
      setTradeGroups(refreshedGroups);
      setSelectedReplayGroup(refreshedGroups.find((item) => item.trade_group_id === group.trade_group_id) ?? group);
    } catch (err) {
      setError(err instanceof Error ? err.message : "交易回放失败");
    } finally {
      setReplayBusy(null);
    }
  }

  async function onSaveLossReview(
    group: TradeGroup,
    reasonCategory: TradeReviewReasonCategory,
    reasonCode: string,
    note: string
  ) {
    setLossReviewBusy(group.trade_group_id);
    setError(null);
    try {
      const review = await saveTradeGroupReview(group.trade_group_id, {
        reason_category: reasonCategory,
        reason_code: reasonCode,
        note
      });
      const applyReview = (item: TradeGroup): TradeGroup =>
        item.trade_group_id === group.trade_group_id ? { ...item, review } : item;
      setTradeGroups((current) => current.map(applyReview));
      setAllTradeGroups((current) => current.map(applyReview));
      setSelectedReplayGroup((current) => (current ? applyReview(current) : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : "亏损复盘保存失败");
    } finally {
      setLossReviewBusy(null);
    }
  }

  function enterReviewContext(nextDate: string, nextSymbol: string) {
    setDate(nextDate);
    setSelectedSymbol(nextSymbol);
    setSelectedReplayGroup(null);
    window.setTimeout(() => reviewModuleRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  function onStrategySymbolInputChange(value: string) {
    const normalized = value.toUpperCase();
    const firstSymbol = parseStrategySymbolInput(normalized)[0];
    setStrategySymbolInput(normalized);
    setStrategyRunFeedback(null);
    setStrategyArchiveFeedback(null);
    setStrategyScanFeedback(null);
    if (firstSymbol) setSelectedSymbol(firstSymbol);
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

  async function onRefreshReviewMinuteArchives() {
    if (!selectedSymbol) return;
    setArchiveBusy(true);
    setError(null);
    try {
      setMinuteArchives(await fetchMinuteArchives(date, selectedSymbol, "yahoo"));
      setTradeGroups(await fetchTradeGroups(date));
    } catch (err) {
      setError(err instanceof Error ? err.message : "本地分钟线归档读取失败");
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
      void loadStrategyHistory(created.strategy_id);
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
      setLiveSignalResults([]);
      setLiveMonitorActive(false);
      void loadStrategyHistory(updated.strategy_id);
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
      setLiveSignalResults([]);
      setLiveMonitorActive(false);
      void loadStrategyHistory(updated.strategy_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "策略启停失败");
    } finally {
      setStrategySaveBusy(false);
    }
  }

  async function onRunStrategy() {
    const symbol = primaryStrategySymbol;
    if (!selectedStrategy || !symbol) return;
    setStrategyBusy(true);
    setError(null);
    setStrategyRunFeedback({
      tone: "info",
      title: "策略复盘已开始",
      detail: `${date} ${symbol} 正在读取已归档分钟线，并由后端生成策略 run 与信号。`
    });
    try {
      const force = latestStrategyRun?.status === "completed";
      const run = await runStrategyReplay(selectedStrategy.strategy_id, date, symbol, force);
      setStrategyRuns([run, ...strategyRuns.filter((item) => item.run_id !== run.run_id)]);
      setStrategyRunFeedback(getStrategyRunFeedback(run, latestStrategyTestBatch));
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

  async function refreshLiveSignals() {
    const symbols = Array.from(new Set(liveSymbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean)));
    if (!selectedStrategy || symbols.length === 0) return;
    const requestId = ++liveSignalRequestIdRef.current;
    setLiveSignalBusy(true);
    setError(null);
    try {
      const results = await Promise.all(
        symbols.map((symbol) =>
          runLiveStrategySignal(selectedStrategy.strategy_id, symbol, liveProvider, liveLookbackMinutes)
        )
      );
      if (requestId !== liveSignalRequestIdRef.current) return;
      setLiveSignalResults(results);
      setLiveMonitorLastUpdated(new Date().toISOString());
    } catch (err) {
      const message = err instanceof Error ? err.message : "实时交易信号读取失败";
      if (requestId === liveSignalRequestIdRef.current) {
        setError(message);
        setLiveSignalResults([]);
        setLiveMonitorActive(false);
        setLiveMonitorLastUpdated(null);
      }
    } finally {
      if (requestId === liveSignalRequestIdRef.current) setLiveSignalBusy(false);
    }
  }

  function onToggleLiveMonitor() {
    if (liveMonitorActive) {
      liveSignalRequestIdRef.current += 1;
      setLiveMonitorActive(false);
      setLiveSignalBusy(false);
      return;
    }
    setLiveMonitorActive(true);
  }

  async function onRunStrategyTestBatch() {
    const targetSymbols = strategySymbols.length > 0 ? strategySymbols : primaryStrategySymbol ? [primaryStrategySymbol] : [];
    if (!selectedStrategy || targetSymbols.length === 0) return;
    setStrategyTestBusy(true);
    setError(null);
    setStrategyScanFeedback({
      tone: "info",
      title: targetSymbols.length > 1 ? "多标的30天复盘已开始" : "30天复盘已开始",
      detail: `${strategySymbolSummary(targetSymbols)} 正在逐标的读取已归档分钟线；每个标的都会保存独立 test batch。`
    });
    try {
      const batches: StrategyTestBatch[] = [];
      for (const symbol of targetSymbols) {
        const existingBatch = strategyTestBatches.find(
          (item) => item.strategy_id === selectedStrategy.strategy_id && item.end_date === date && item.symbol === symbol
        );
        batches.push(await runStrategyTestBatch(selectedStrategy.strategy_id, date, symbol, Boolean(existingBatch)));
      }
      const batch = batches[0];
      setStrategyTestBatches((current) => mergeStrategyTestBatches(current, batches));
      setSelectedSymbol(batch.symbol);
      setSelectedStrategyTestBatchId(batch.batch_id);
      const firstDay = batch.day_results[0] ?? null;
      setSelectedStrategyTestDayId(firstDay?.day_result_id ?? null);
      if (firstDay) {
        void loadStrategyTestDayDetail(firstDay, selectedStrategy.strategy_id, batch.symbol, {
          batchId: batch.batch_id
        });
      }
      const completedCount = batches.filter((item) => item.status === "completed").length;
      const insufficientCount = batches.filter((item) => item.status === "insufficient_archive_coverage").length;
      setStrategyScanFeedback({
        tone: completedCount === batches.length ? "ok" : "warn",
        title: targetSymbols.length > 1 ? "多标的30天复盘已保存" : "30天复盘已保存",
        detail: `${strategySymbolSummary(targetSymbols)} 已生成 ${formatInteger(batches.length)} 个独立 test batch；完成 ${formatInteger(
          completedCount
        )} 个，覆盖不足 ${formatInteger(insufficientCount)} 个。`
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "策略测试运行失败";
      setError(message);
      setStrategyScanFeedback({
        tone: "danger",
        title: "策略测试运行失败",
        detail: message
      });
    } finally {
      setStrategyTestBusy(false);
    }
  }

  function onSelectStrategyTestDay(day: StrategyTestDayResult, batch = selectedStrategyTestBatch) {
    if (batch) {
      setSelectedStrategyTestBatchId(batch.batch_id);
      setSelectedSymbol(batch.symbol);
    }
    setSelectedStrategyTestDayId(day.day_result_id);
    void loadStrategyTestDayDetail(day, selectedStrategyId, batch?.symbol ?? primaryStrategySymbol, {
      batchId: batch?.batch_id ?? day.batch_id
    });
  }

  async function onArchiveStrategyWindow() {
    const targetSymbols = strategySymbols.length > 0 ? strategySymbols : primaryStrategySymbol ? [primaryStrategySymbol] : [];
    if (targetSymbols.length === 0) return;
    setArchiveBusy(true);
    setError(null);
    setStrategyArchiveFeedback({
      tone: "info",
      title: targetSymbols.length > 1 ? "多标的30天数据拉取已开始" : "30天数据拉取已开始",
      detail: `${strategySymbolSummary(targetSymbols)} 截至 ${date} 正在显式拉取最近 30 天（自然日）分钟线；策略测试不会在后台自动拉行情。`
    });
    try {
      const archiveResults: Array<{ result: YahooMinuteArchiveResult; symbol: string }> = [];
      for (const symbol of targetSymbols) {
        const existingBatch = strategyTestBatches.find(
          (item) => item.strategy_id === selectedStrategyId && item.end_date === date && item.symbol === symbol
        );
        const result = await archiveYahooMinuteData(date, Boolean(existingBatch), symbol, 30);
        archiveResults.push({ result, symbol });
      }
      const currentDateItems = archiveResults.flatMap(({ result, symbol }) =>
        result.items.filter((archive) => archive.symbol === symbol && archive.trade_date === date)
      );
      setMinuteArchives(currentDateItems.length > 0 ? currentDateItems : await fetchMinuteArchives(date, targetSymbols[0], "yahoo"));
      await loadStrategyResearch(selectedStrategyId, targetSymbols);
      await loadStrategyArchiveRanges(targetSymbols, date);
      const perSymbolCoverage = archiveResults.map(({ result, symbol }) => ({
        available: result.selected_symbol_available_count ?? 0,
        firstUnavailable:
          result.items
            .filter((archive) => archive.symbol === symbol && archive.data_status !== "available")
            .sort((left, right) => left.trade_date.localeCompare(right.trade_date))[0] ?? null,
        symbol
      }));
      const allPrepared = perSymbolCoverage.every((item) => item.available >= 30);
      const coverageText = perSymbolCoverage.map((item) => `${item.symbol} ${formatInteger(item.available)}/30`).join(" · ");
      const firstUnavailable = perSymbolCoverage.find((item) => item.firstUnavailable)?.firstUnavailable ?? null;
      setStrategyArchiveFeedback({
        tone: allPrepared ? "ok" : "warn",
        title: allPrepared ? "30天归档已准备" : "30天归档仍有不可用日期",
        detail:
          `${coverageText}。` +
          (firstUnavailable
            ? ` ${firstUnavailable.trade_date} ${formatArchiveFailureReason(firstUnavailable.failure_reason) ?? firstUnavailable.data_status}。`
            : "") +
          " 策略测试仍只读取已保存归档。"
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "30天分钟线归档失败";
      setError(message);
      setStrategyArchiveFeedback({
        tone: "danger",
        title: "30天数据拉取失败",
        detail: message
      });
    } finally {
      setArchiveBusy(false);
    }
  }

  async function onRunStrategyOptimization() {
    const targetSymbols = strategySymbols.length > 0 ? strategySymbols : primaryStrategySymbol ? [primaryStrategySymbol] : [];
    if (!selectedStrategy || targetSymbols.length === 0) return;
    setStrategyOptimizationBusy(true);
    setError(null);
    setStrategyScanFeedback({
      tone: "info",
      title: targetSymbols.length > 1 ? "多标的全局优化已开始" : "策略优化已开始",
      detail: `${strategySymbolSummary(targetSymbols)} 正在运行同一参数组的全局优化；候选只展示，必须显式套用才会更新配置。`
    });
    try {
      const existingOptimization = strategyOptimizations.find(
        (item) =>
          item.strategy_id === selectedStrategy.strategy_id &&
          item.end_date === date &&
          item.template_version === selectedStrategy.template_version &&
          optimizationSymbols(item).length === targetSymbols.length &&
          targetSymbols.every((symbol) => optimizationCoversSymbol(item, symbol))
      );
      const optimization = await runStrategyOptimization(
        selectedStrategy.strategy_id,
        date,
        targetSymbols,
        Boolean(existingOptimization)
      );
      setSelectedSymbol(targetSymbols[0]);
      setSelectedOptimization(optimization);
      setStrategyOptimizations((current) => mergeStrategyOptimizations(current, [optimization]));
      const optimizationSymbolCount = optimizationSymbols(optimization).length;
      setStrategyScanFeedback({
        tone: optimization.status === "completed" && optimization.eligible_candidate_count > 0 ? "ok" : "warn",
        title: targetSymbols.length > 1 ? "多标的全局优化已保存" : "策略优化已保存",
        detail: `${optimizationScopeLabel(optimization)} 已生成 1 个全局 optimization run；覆盖 ${formatInteger(
          optimizationSymbolCount
        )} 个标的，可候选 ${formatInteger(optimization.eligible_candidate_count)} 组。`
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "策略优化运行失败";
      setError(message);
      setStrategyScanFeedback({
        tone: "danger",
        title: "策略优化运行失败",
        detail: message
      });
    } finally {
      setStrategyOptimizationBusy(false);
    }
  }

  async function onApplyOptimizationCandidate(candidate: StrategyOptimizationCandidate) {
    if (!selectedStrategy) return;
    setStrategySaveBusy(true);
    setError(null);
    setStrategyRunFeedback({
      tone: "info",
      title: "正在套用候选参数",
      detail: "后端正在把候选参数写入策略配置；历史优化 run 和候选结果保持原始证据。"
    });
    try {
      const updated = await applyStrategyOptimizationCandidate(selectedStrategy.strategy_id, candidate.candidate_id);
      setStrategies((current) => current.map((strategy) => (strategy.strategy_id === updated.strategy_id ? updated : strategy)));
      setSelectedStrategyId(updated.strategy_id);
      setStrategyParamsDraft(updated.params);
      setStrategyRunFeedback({
        tone: "ok",
        title: "候选参数已套用",
        detail: "策略配置、模板版本和变更原因已保存；历史优化 run 和候选结果保持原始证据。"
      });
      void loadStrategyHistory(updated.strategy_id);
      void loadStrategyRuns(updated.strategy_id, primaryStrategySymbol);
      void loadStrategyResearch(updated.strategy_id, strategySymbols);
    } catch (err) {
      const message = err instanceof Error ? err.message : "候选参数套用失败";
      setError(message);
      setStrategyRunFeedback({
        tone: "danger",
        title: "候选参数套用失败",
        detail: message
      });
    } finally {
      setStrategySaveBusy(false);
    }
  }

  async function onRollbackStrategyHistory(item: StrategyConfigHistory) {
    if (!selectedStrategy || !item.can_rollback) return;
    setStrategyRollbackBusy(item.history_id);
    setError(null);
    setStrategyRunFeedback({
      tone: "info",
      title: "正在回退策略版本",
      detail: "后端正在从策略版本记录恢复历史参数快照；历史 run、测试批次和优化候选保持原始证据。"
    });
    try {
      const updated = await rollbackStrategyConfigHistory(selectedStrategy.strategy_id, item.history_id);
      setStrategies((current) => current.map((strategy) => (strategy.strategy_id === updated.strategy_id ? updated : strategy)));
      setSelectedStrategyId(updated.strategy_id);
      setStrategyNameDraft(updated.name);
      setStrategyParamsDraft(updated.params);
      setStrategyRuns([]);
      setStrategyRunFeedback({
        tone: "ok",
        title: "策略版本已回退",
        detail: "当前策略配置已恢复到所选历史记录的变更前参数；旧 strategy run artifact 没有被覆盖。"
      });
      void loadStrategyHistory(updated.strategy_id);
      void loadStrategyRuns(updated.strategy_id, primaryStrategySymbol);
      void loadStrategyResearch(updated.strategy_id, strategySymbols);
    } catch (err) {
      const message = err instanceof Error ? err.message : "策略版本回退失败";
      setError(message);
      setStrategyRunFeedback({
        tone: "danger",
        title: "策略版本回退失败",
        detail: message
      });
    } finally {
      setStrategyRollbackBusy(null);
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
  const dataReviewTimeRange = useMemo(
    () =>
      lossReviewTimeFilterRange(
        dataReviewTimeFilterMode,
        customDataReviewStartDate,
        customDataReviewEndDate,
        todayDateKey
      ),
    [customDataReviewEndDate, customDataReviewStartDate, dataReviewTimeFilterMode, todayDateKey]
  );
  const dataReviewTimeFilteredTradeGroups = useMemo(
    () =>
      allTradeGroups.filter((group) =>
        lossReviewDateRangeIncludesGroup(group, dataReviewTimeRange.startDate, dataReviewTimeRange.endDate)
      ),
    [allTradeGroups, dataReviewTimeRange.endDate, dataReviewTimeRange.startDate]
  );
  const dataReviewSummary = useMemo(
    () => buildReviewSummaryFromTradeGroups(dataReviewTimeFilteredTradeGroups),
    [dataReviewTimeFilteredTradeGroups]
  );
  const dataReviewMarketRegimeMatrix = useMemo(
    () => buildLossReviewMarketRegimeMatrix(dataReviewTimeFilteredTradeGroups, "all"),
    [dataReviewTimeFilteredTradeGroups]
  );
  const dataReviewDateSummaryGroups = useMemo(
    () => buildReviewSummaryGroupsFromTradeGroups(dataReviewTimeFilteredTradeGroups, "date"),
    [dataReviewTimeFilteredTradeGroups]
  );
  const dataReviewSymbolSummaryGroups = useMemo(
    () => buildReviewSummaryGroupsFromTradeGroups(dataReviewTimeFilteredTradeGroups, "symbol"),
    [dataReviewTimeFilteredTradeGroups]
  );
  const dataReviewSelectedDateSummary = useMemo(
    () => dataReviewDateSummaryGroups.find((group) => group.group_key === date) ?? null,
    [dataReviewDateSummaryGroups, date]
  );
  const dataReviewSelectedSymbolSummary = useMemo(
    () =>
      selectedSymbol
        ? dataReviewSymbolSummaryGroups.find((group) => group.group_key === selectedSymbol) ?? null
        : null,
    [dataReviewSymbolSummaryGroups, selectedSymbol]
  );
  const dataReviewVisibleDateSymbolBreakdown = useMemo(
    () =>
      buildReviewSummaryGroupsFromTradeGroups(
        dataReviewTimeFilteredTradeGroups.filter((group) => tradeGroupReviewDate(group) === date),
        "symbol"
      ),
    [dataReviewTimeFilteredTradeGroups, date]
  );
  const dataReviewVisibleSymbolDateBreakdown = useMemo(
    () =>
      selectedSymbol
        ? buildReviewSummaryGroupsFromTradeGroups(
            dataReviewTimeFilteredTradeGroups.filter((group) => group.symbol === selectedSymbol),
            "date"
          )
        : [],
    [dataReviewTimeFilteredTradeGroups, selectedSymbol]
  );
  const dataReviewTimeRangeLabel = lossReviewTimeRangeLabel(
    dataReviewTimeRange.startDate,
    dataReviewTimeRange.endDate,
    "全部订单"
  );
  const dataReviewSummaryNote = `${sourceLabel[dataReviewSummary.source]} · ${dataReviewTimeRangeLabel}`;
  const activeDrillSummary = activeReviewDrillTab === "date" ? selectedDateSummary : selectedSymbolSummary;
  const dataReviewActiveDrillSummary =
    activeReviewDrillTab === "date" ? dataReviewSelectedDateSummary : dataReviewSelectedSymbolSummary;
  const dateSymbolBreakdownReady = Object.prototype.hasOwnProperty.call(dateSymbolBreakdownByDate, date);
  const visibleDateSymbolBreakdown = useMemo(
    () => dateSymbolBreakdownByDate[date] ?? [],
    [date, dateSymbolBreakdownByDate]
  );
  const visibleSymbolDateBreakdown = useMemo(
    () => symbolDateBreakdown.filter((group) => group.symbol === selectedSymbol),
    [selectedSymbol, symbolDateBreakdown]
  );
  const profitLossReviewTradeGroups = useMemo(
    () => allTradeGroups.filter(isClosedProfitLossTradeGroup),
    [allTradeGroups]
  );
  const scopedCurrentReviewSummary =
    currentReviewSummary?.date === date && currentReviewSummary.symbol === (selectedSymbol || null)
      ? currentReviewSummary
      : null;
  const selectedStatus = selected ? statusMeta[selected.status] : null;
  const chartStatus = selectedArchive ? marketStatusMeta[selectedArchive.data_status] : null;
  const latestStrategyStatus = latestStrategyRun ? strategyStatusMeta[latestStrategyRun.status] : null;
  const hasFills = fills.length > 0;
  const hasDisplayedTradeGroups = displayedTradeGroups.length > 0;
  const lossOnlyFilterEmpty = showLossOnlyTradeGroups && symbolScopedTradeGroups.length > 0 && !hasDisplayedTradeGroups;
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
        <button
          aria-pressed={activeWorkspaceTab === "live"}
          className={activeWorkspaceTab === "live" ? "workspaceTab active" : "workspaceTab"}
          onClick={() => setActiveWorkspaceTab("live")}
          type="button"
        >
          <Power size={16} />
          实时交易
        </button>
      </nav>
      <datalist id="symbolOptions">
        {symbolOptions.map((symbol) => (
          <option key={symbol} value={symbol} />
        ))}
      </datalist>

      {activeWorkspaceTab === "review" ? (
        <>
      <section className="panel reviewDrillPanel" aria-label="交易复盘下钻">
        <div className="reviewDrillSurfaceTabs" role="group" aria-label="下钻复盘模块">
          <button
            aria-pressed={activeReviewDrillSurfaceTab === "data"}
            className={activeReviewDrillSurfaceTab === "data" ? "reviewDrillSurfaceTab active" : "reviewDrillSurfaceTab"}
            onClick={() => setActiveReviewDrillSurfaceTab("data")}
            type="button"
          >
            <TableProperties size={15} />
            数据下钻
          </button>
          <button
            aria-pressed={activeReviewDrillSurfaceTab === "loss"}
            className={activeReviewDrillSurfaceTab === "loss" ? "reviewDrillSurfaceTab active" : "reviewDrillSurfaceTab"}
            onClick={() => setActiveReviewDrillSurfaceTab("loss")}
            type="button"
          >
            <AlertTriangle size={15} />
            盈亏复盘
          </button>
        </div>
        {activeReviewDrillSurfaceTab === "data" ? (
          <>
        <div className="dataReviewDrilldown">
          <div className="lossReviewTimeFilter" aria-label="数据下钻全局时间筛选">
            <div className="lossReviewTimeFilterButtons" role="group" aria-label="数据下钻时间筛选">
              {(["all", "month", "week", "custom"] as LossReviewTimeFilterMode[]).map((mode) => (
                <button
                  aria-pressed={dataReviewTimeFilterMode === mode}
                  className={dataReviewTimeFilterMode === mode ? "smallButton active" : "smallButton"}
                  key={mode}
                  onClick={() => {
                    setDataReviewTimeFilterMode(mode);
                  }}
                  type="button"
                >
                  {lossReviewTimeFilterLabels[mode]}
                </button>
              ))}
            </div>
            {dataReviewTimeFilterMode === "custom" ? (
              <div className="lossReviewCustomRange">
                <label>
                  <span>开始</span>
                  <input
                    onChange={(event) => {
                      setCustomDataReviewStartDate(event.currentTarget.value);
                    }}
                    type="date"
                    value={customDataReviewStartDate}
                  />
                </label>
                <label>
                  <span>结束</span>
                  <input
                    onChange={(event) => {
                      setCustomDataReviewEndDate(event.currentTarget.value);
                    }}
                    type="date"
                    value={customDataReviewEndDate}
                  />
                </label>
              </div>
            ) : null}
            <span className="toolbarMeta">{dataReviewTimeRangeLabel}</span>
          </div>

          <SummaryMetricStrip
            className="kpis reviewDashboard dataReviewSummaryStrip"
            note={dataReviewSummaryNote}
            summary={dataReviewSummary}
          />

          <LossReviewMarketRegimeMatrix
            matrix={dataReviewMarketRegimeMatrix}
            note="时间窗口采用 09:30-16:00 五大美股日内微观结构划分；这里统计当前时间范围内全部交易组。纵轴使用后端从本地分钟线归档计算的开仓 1min K 振幅 / 前 20 根 ATR；缺足够历史分钟线时进入缺 ATR 证据，不用美元亏损回退。"
            readOnly
            showTimeWindowPnlSummary
            sourceLabel="全部订单"
            summaryMode="pnl_extremes"
            subtitle="按美股常规盘五大微观结构窗口 × 开仓 ATR Multiple 查看全部订单分布"
          />

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
            <Metric label="成交股数" value={formatInteger(scopedCurrentReviewSummary?.traded_quantity ?? 0)} note="BUY/SELL 平仓数量" />
            <Metric label="PnL" value={formatPnl(scopedCurrentReviewSummary?.pnl ?? 0)} tone={summaryTone(scopedCurrentReviewSummary?.pnl ?? 0)} />
            <Metric label="胜率" value={formatWinRate(scopedCurrentReviewSummary)} />
            <Metric label="盈亏比" value={formatProfitFactor(scopedCurrentReviewSummary)} />
            <Metric label="持仓最大回撤" value={formatNullable(scopedCurrentReviewSummary?.max_single_day_drawdown)} tone={(scopedCurrentReviewSummary?.max_single_day_drawdown ?? 0) > 0 ? "warn" : "neutral"} />
          </section>

        <header className="dataReviewDrillHead">
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
              dataReviewDateSummaryGroups.length > 0 ? (
                dataReviewDateSummaryGroups.map((group) => (
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
                <EmptyState icon={<CircleSlash size={18} />} title="暂无交易日" detail="当前时间范围没有 committed 成交可用于日期下钻" />
              )
            ) : dataReviewSymbolSummaryGroups.length > 0 ? (
              dataReviewSymbolSummaryGroups.map((group) => (
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
              <EmptyState icon={<CircleSlash size={18} />} title="暂无标的" detail="当前时间范围没有 committed 成交可用于标的下钻" />
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
                  ? formatInteger(dataReviewVisibleDateSymbolBreakdown.length)
                  : formatInteger(dataReviewVisibleSymbolDateBreakdown.length)}
                {activeReviewDrillTab === "date" ? " 个标的" : " 个交易日"}
              </span>
            </div>

            <SummaryMiniFacts summary={dataReviewActiveDrillSummary} />

            <div className="drillSecondaryList">
              {activeReviewDrillTab === "date" ? (
                dataReviewVisibleDateSymbolBreakdown.length > 0 ? (
                  dataReviewVisibleDateSymbolBreakdown.map((group) => (
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
                  <EmptyState icon={<CircleSlash size={18} />} title="该日没有标的" detail="当前时间范围或矩阵筛选下没有 committed 成交分组" />
                )
              ) : selectedSymbol ? (
                dataReviewVisibleSymbolDateBreakdown.length > 0 ? (
                  dataReviewVisibleSymbolDateBreakdown.map((group) => (
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
                  <EmptyState icon={<CircleSlash size={18} />} title="该标的没有交易日" detail="当前时间范围或矩阵筛选下没有 committed 成交分组" />
                )
              ) : (
                <EmptyState icon={<Clock3 size={18} />} title="等待选择标的" detail="从左侧选择一个标的后显示交易日汇总" />
              )}
            </div>
          </div>
        </div>
        </div>
          </>
        ) : (
          <LossReviewDrilldown
            onReplayTradeGroup={onReplayTradeGroup}
            replayBusy={replayBusy}
            tradeGroups={profitLossReviewTradeGroups}
          />
        )}
      </section>

      {activeReviewDrillSurfaceTab === "data" ? (
        <>
      <section className="reviewWorkspace" aria-label="日内复盘工作区" ref={reviewModuleRef}>
        <section className="panel chartPanel workspaceChart" aria-label="分钟蜡烛图复盘">
          <header>
            <div>
              <h2>
                <BarChart3 size={18} />
                分钟蜡烛复盘
              </h2>
            <p className="panelNote">分钟线读取本地离线归档，成交点来自已保存 read model；策略研究请切换到策略测试</p>
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
              <button className="smallButton" onClick={() => void onRefreshReviewMinuteArchives()} disabled={!selectedSymbol || archiveBusy}>
                <RefreshCw className={archiveBusy ? "spin" : undefined} size={15} />
                {archiveBusy ? "刷新中" : "刷新本地分钟线"}
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
                fills={displayedChartFills}
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

          <div className="tradeLedgerToolbar">
            <label className="inlineCheckbox tradeLossOnlyToggle">
              <input
                checked={showLossOnlyTradeGroups}
                onChange={(event) => setShowLossOnlyTradeGroups(event.target.checked)}
                type="checkbox"
              />
              <span>仅看亏损单</span>
            </label>
            <span className="toolbarMeta">
              {showLossOnlyTradeGroups
                ? `显示 ${formatInteger(displayedTradeGroups.length)} / ${formatInteger(symbolScopedTradeGroups.length)} 笔`
                : `共 ${formatInteger(symbolScopedTradeGroups.length)} 笔`}
            </span>
          </div>

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
                    const canReviewLoss = group.status === "closed" && group.pnl !== null && group.pnl < 0;
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
                        </td>
                        <td>
                          <span className={`gradePill ${evaluationTone(evaluation.evaluation_status, evaluation.grade)}`}>
                            {formatEvaluationGrade(evaluation)}
                          </span>
                        </td>
                        <td className="traceCell">
                          <span>{formatInteger(group.fill_count)} fills</span>
                          {group.status === "closed" ? (
                            <>
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
                              {group.review ? (
                                <small className="tradeReviewSummary">复盘：{group.review.reason_label}</small>
                              ) : canReviewLoss ? (
                                <small className="tradeReviewSummary pending">待复盘</small>
                              ) : null}
                            </>
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
              title={
                lossOnlyFilterEmpty
                  ? "当前范围没有亏损单"
                  : hasFills
                    ? "当前标的没有交易组"
                    : "当前日期没有 committed 成交"
              }
              detail={
                lossOnlyFilterEmpty
                  ? "取消“仅看亏损单”可查看当前范围全部交易组"
                  : "KPI 保持 0 或 N/A，隔离行仍可在批次面板复查"
              }
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
      ) : null}
        </>
      ) : activeWorkspaceTab === "strategy" ? (
        <StrategyTestingWorkspace
          archiveBusy={archiveBusy}
          date={date}
          latestOptimization={latestOptimization}
          latestStrategyTestBatch={selectedStrategyTestBatch}
          onArchiveStrategyWindow={() => void onArchiveStrategyWindow()}
          onApplyOptimizationCandidate={(candidate) => void onApplyOptimizationCandidate(candidate)}
          onDateChange={setDate}
          onOpenStrategyConfig={() => setStrategyConfigOpen(true)}
          onRunOptimization={() => void onRunStrategyOptimization()}
          onRunStrategy={() => void onRunStrategy()}
          onRunTestBatch={() => void onRunStrategyTestBatch()}
          onSelectStrategyTestDay={onSelectStrategyTestDay}
          onSymbolChange={onStrategySymbolInputChange}
          optimizationBusy={strategyOptimizationBusy}
          primaryStrategySymbol={primaryStrategySymbol}
          scanRows={strategyScanRows}
          selectedStrategy={selectedStrategy}
          selectedStrategyTestBatch={selectedStrategyTestBatch}
          selectedStrategyTestDay={selectedStrategyTestDay}
          selectedStrategyTemplate={selectedStrategyTemplate}
          selectedSymbol={strategySymbolInput || primaryStrategySymbol}
          showFullDayStrategyBars={showFullDayStrategyBars}
          strategyArchiveRangeBusy={strategyArchiveRangeBusy}
          strategyArchiveRangeError={strategyArchiveRangeError}
          strategyArchiveRanges={strategyArchiveRanges}
          strategyOverallMetrics={strategyOverallMetrics}
          strategyReviewDateRows={strategyReviewDateRows}
          strategyReviewSymbolRows={strategyReviewSymbolRows}
          strategyArchiveFeedback={strategyArchiveFeedback}
          strategyBusy={strategyBusy}
          strategyDraftDirty={strategyDraftDirty}
          strategyRunFeedback={strategyRunFeedback}
          strategySaveBusy={strategySaveBusy}
          strategyScanFeedback={strategyScanFeedback}
          strategySymbols={strategySymbols}
          strategyTestDayArchive={strategyTestDayArchive}
          strategyTestDayDetailBusy={strategyTestDayDetailBusy || selectedStrategyTestDayDetail?.status === "loading"}
          strategyTestDayRun={strategyTestDayRun}
          strategyTestBusy={strategyTestBusy}
          onToggleFullDayStrategyBars={setShowFullDayStrategyBars}
        />
      ) : (
        <LiveTradingWorkspace
          busy={liveSignalBusy}
          lookbackMinutes={liveLookbackMinutes}
          monitorActive={liveMonitorActive}
          monitorLastUpdated={liveMonitorLastUpdated}
          onLookbackMinutesChange={setLiveLookbackMinutes}
          onMonitorToggle={onToggleLiveMonitor}
          onProviderChange={setLiveProvider}
          onStrategyChange={setSelectedStrategyId}
          onSymbolChange={(symbols) =>
            setLiveSymbols(Array.from(new Set(symbols.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean))))
          }
          provider={liveProvider}
          results={liveSignalResults}
          selectedStrategyId={selectedStrategy?.strategy_id ?? null}
          selectedSymbols={liveSymbols}
          strategies={strategies}
          symbolOptions={liveSymbolOptions}
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

            <div className="strategyModalBody">
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
                        <small>最新 {strategy.latest_template_version ?? strategy.template_version}</small>
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
                        <small>
                          最新 {selectedStrategy.latest_template_version ?? selectedStrategy.template_version}
                        </small>
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
                            disabled={!primaryStrategySymbol || strategyBusy}
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
                    <section className="strategyVersionHistory" aria-label="策略版本记录">
                      <header>
                        <div>
                          <strong>策略版本记录</strong>
                          <small>每次参数版本变更都会保存前后参数 hash，可回退到历史参数快照</small>
                        </div>
                        {strategyHistoryBusy ? <span className="statusPill info">读取中</span> : null}
                      </header>
                      {strategyHistory.length > 0 ? (
                        <div className="strategyVersionList">
                          {strategyHistory.map((item) => {
                            const rollbackAlreadyCurrent =
                              item.previous_params_hash === selectedStrategy.params_hash &&
                              item.previous_template_version === selectedStrategy.template_version;
                            const rollbackDisabled =
                              strategyRollbackBusy !== null ||
                              !item.can_rollback ||
                              rollbackAlreadyCurrent;
                            return (
                              <article className="strategyVersionItem" key={item.history_id}>
                                <div className="strategyVersionMain">
                                  <span className="statusPill info">{strategyHistorySourceLabel[item.change_source]}</span>
                                  <strong>{formatDateTime(item.created_at)}</strong>
                                  <small>{item.change_reason}</small>
                                </div>
                                <dl className="strategyVersionFacts">
                                  <div>
                                    <dt>版本</dt>
                                    <dd>
                                      {item.previous_template_version} &gt; {item.next_template_version}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt>参数</dt>
                                    <dd className="monoWrap">
                                      {shortHash(item.previous_params_hash)} &gt; {shortHash(item.next_params_hash)}
                                    </dd>
                                  </div>
                                </dl>
                                <button
                                  className="smallButton"
                                  disabled={rollbackDisabled}
                                  onClick={() => void onRollbackStrategyHistory(item)}
                                  title={
                                    !item.can_rollback
                                      ? "这条旧记录缺少参数快照，不能回退"
                                      : rollbackAlreadyCurrent
                                        ? "当前策略已经使用这组参数"
                                        : "回退到这条记录变更前的参数快照"
                                  }
                                  type="button"
                                >
                                  {strategyRollbackBusy === item.history_id ? (
                                    <RefreshCw className="spin" size={14} />
                                  ) : (
                                    <RefreshCw size={14} />
                                  )}
                                  回退到此版本
                                </button>
                              </article>
                            );
                          })}
                        </div>
                      ) : (
                        <EmptyState
                          icon={<Clock3 size={18} />}
                          title={strategyHistoryBusy ? "正在读取版本记录" : "暂无版本记录"}
                          detail="保存参数、套用优化候选或回退版本后，会在这里留下可审计记录。"
                        />
                      )}
                    </section>
                  </>
                ) : (
                  <EmptyState icon={<CircleSlash size={18} />} title="暂无策略模板" detail="后端未返回可用策略模板。" />
                )}
              </div>

              <div className="strategyDescriptionPanel">
                {strategyMode === "create" && createStrategyTemplate ? (
                  <StrategyDescription
                    enabled={false}
                    latestTestBatch={null}
                    latestRun={null}
                    params={newStrategyParamsDraft}
                    strategyName={newStrategyName.trim() || `${createStrategyTemplate.name} 副本`}
                    templateKey={createStrategyTemplate.template_key}
                    templateVersion={createStrategyTemplate.template_version}
                  />
                ) : selectedStrategy && selectedStrategyTemplate ? (
                  <StrategyDescription
                    enabled={selectedStrategy.enabled}
                    latestTestBatch={latestStrategyTestBatch}
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
            </div>
          </section>
        </div>
      ) : null}

      {selectedReplayGroup ? (
        <TradeReplayModal
          archive={selectedReplayArchive}
          group={selectedReplayGroup}
          lossReviewBusy={lossReviewBusy === selectedReplayGroup.trade_group_id}
          onClose={() => setSelectedReplayGroup(null)}
          onSave={(reasonCategory, reasonCode, note) =>
            void onSaveLossReview(selectedReplayGroup, reasonCategory, reasonCode, note)
          }
        />
      ) : null}
    </main>
  );
}

function LiveTradingWorkspace(props: {
  busy: boolean;
  lookbackMinutes: number;
  monitorActive: boolean;
  monitorLastUpdated: string | null;
  onLookbackMinutesChange: (minutes: number) => void;
  onMonitorToggle: () => void;
  onProviderChange: (provider: LiveProvider) => void;
  onStrategyChange: (strategyId: string) => void;
  onSymbolChange: (symbols: string[]) => void;
  provider: LiveProvider;
  results: LiveStrategySignalResult[];
  selectedStrategyId: string | null;
  selectedSymbols: string[];
  strategies: StrategyConfig[];
  symbolOptions: string[];
}) {
  const selectedStrategy =
    props.strategies.find((strategy) => strategy.strategy_id === props.selectedStrategyId) ?? props.strategies[0] ?? null;
  const primaryResult = props.results[0] ?? null;
  const headerStatus = props.monitorActive
    ? { label: props.busy ? "读取中" : "监控中", tone: "info" as const }
    : primaryResult
      ? liveSignalStatusMeta[primaryResult.status]
      : null;
  const monitorDetail = props.monitorLastUpdated
    ? `最后更新 ${formatDateTime(props.monitorLastUpdated)}`
    : props.monitorActive
      ? "等待首次行情读取"
      : "监控未开启";
  const liveOrderRows = props.results
    .flatMap((result) =>
      result.signals.map((signal) => ({
        result,
        signal,
        orderIntent: liveOrderIntentForAction(signal.action)
      }))
    )
    .sort(
      (left, right) =>
        right.signal.timestamp.localeCompare(left.signal.timestamp) ||
        left.result.symbol.localeCompare(right.result.symbol) ||
        right.signal.bar_index - left.signal.bar_index
    );

  return (
    <section className="liveTradingWorkspace" aria-label="实时交易工作区">
      <section className="panel liveTradingHero">
        <header>
          <div>
            <h2>
              <Power size={18} />
              实时交易
            </h2>
            <p className="panelNote">只读下单信号预览：不自动下单，不修改 STP 成交事实</p>
          </div>
          {headerStatus ? <span className={`statusPill ${headerStatus.tone}`}>{headerStatus.label}</span> : null}
        </header>

        <div className="liveControlGrid">
          <label className="liveControl">
            <span>策略</span>
            <select
              value={selectedStrategy?.strategy_id ?? ""}
              onChange={(event) => props.onStrategyChange(event.currentTarget.value)}
            >
              {props.strategies.map((strategy) => (
                <option key={strategy.strategy_id} value={strategy.strategy_id}>
                  {strategy.name}
                </option>
              ))}
            </select>
          </label>
          <label className="liveControl">
            <span>标的</span>
            <select
              className="liveSymbolSelect"
              multiple
              value={props.selectedSymbols}
              onChange={(event) =>
                props.onSymbolChange(Array.from(event.currentTarget.selectedOptions, (option) => option.value))
              }
            >
              {props.symbolOptions.map((symbol) => (
                <option key={symbol} value={symbol}>
                  {symbol}
                </option>
              ))}
            </select>
          </label>
          <label className="liveControl">
            <span>行情源</span>
            <select
              value={props.provider}
              onChange={(event) => props.onProviderChange(event.currentTarget.value as LiveProvider)}
            >
              <option value="yahoo">Yahoo 实时</option>
              <option value="futu">Futu 实时</option>
              <option value="fake">Fake 验证</option>
            </select>
          </label>
          <label className="liveControl">
            <span>分钟线窗口</span>
            <select
              value={props.lookbackMinutes}
              onChange={(event) => props.onLookbackMinutesChange(Number(event.currentTarget.value))}
            >
              <option value={120}>120 分钟</option>
              <option value={180}>180 分钟</option>
              <option value={240}>240 分钟</option>
              <option value={390}>全交易日</option>
            </select>
          </label>
          <button
            className={props.monitorActive ? "smallButton liveRefreshButton" : "smallButton primary liveRefreshButton"}
            disabled={!selectedStrategy || props.selectedSymbols.length === 0}
            onClick={props.onMonitorToggle}
            type="button"
          >
            {props.busy ? <RefreshCw className="spin" size={14} /> : <RefreshCw size={14} />}
            {props.monitorActive ? "停止监控" : "开启监控"}
          </button>
        </div>
        <div className="liveMonitorMeta">
          <span>{monitorDetail}</span>
          {props.monitorActive ? <span>30s polling</span> : null}
        </div>
      </section>

      <section className="liveTradingGrid">
        <section className="panel liveSignalPanel">
          <header>
            <div>
              <h2>
                <Activity size={18} />
                下单信号
              </h2>
              <p className="panelNote">仅展示后端返回的信号订单明细</p>
            </div>
          </header>
          {liveOrderRows.length > 0 ? (
            <div className="liveSignalList">
              {liveOrderRows.map(({ result, signal, orderIntent }) => (
                  <article className="liveSignalCard liveSignalOrderCard" key={`${result.symbol}:${signal.signal_id}`}>
                    <dl className="compactFacts liveOrderFacts liveOrderOnlyFacts">
                      <div>
                        <dt>标的</dt>
                        <dd>{result.symbol}</dd>
                      </div>
                      <div>
                        <dt>订单意图</dt>
                        <dd>{formatLiveOrderIntent(orderIntent)}</dd>
                      </div>
                      <div>
                        <dt>操作类型</dt>
                        <dd>{formatLiveOrderOperationType(signal.action)}</dd>
                      </div>
                      <div>
                        <dt>信号价</dt>
                        <dd>{formatNullable(signal?.price)}</dd>
                      </div>
                      <div>
                        <dt>股数</dt>
                        <dd>{formatShareQuantity(signal.order_quantity)}</dd>
                      </div>
                      {isLiveEntryOrderAction(signal.action) ? (
                        <>
                          <div>
                            <dt>止损</dt>
                            <dd>{formatNullable(signal?.stop_loss_price)}</dd>
                          </div>
                          <div>
                            <dt>止盈</dt>
                            <dd>{formatNullable(signal?.take_profit_price)}</dd>
                          </div>
                        </>
                      ) : null}
                      {!isLiveEntryOrderAction(signal.action) ? (
                        <div>
                          <dt>原因标签</dt>
                          <dd className="liveOrderReasonCodeList">
                            {signal.reason_codes.length > 0 ? (
                              signal.reason_codes.map((reason) => (
                                <span className="reasonCode" key={`${signal.signal_id}:${reason}`}>
                                  {reasonLabels[reason] ?? reason}
                                </span>
                              ))
                            ) : (
                              <span className="reasonCode">无原因码</span>
                            )}
                          </dd>
                        </div>
                      ) : null}
                      <div>
                        <dt>触发时间</dt>
                        <dd>{signal ? formatDateTime(signal.timestamp) : "N/A"}</dd>
                      </div>
                      <div>
                        <dt>bar_index</dt>
                        <dd>{signal ? formatInteger(signal.bar_index) : "N/A"}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
            </div>
          ) : (
            <EmptyState
              icon={<Clock3 size={18} />}
              title={props.results.length > 0 ? "暂无下单信号订单" : "等待监控信号"}
              detail={props.results.length > 0 ? "当前结果没有后端策略订单，明细见右侧原因与证据。" : "尚未读取实时行情"}
            />
          )}
        </section>

        <section className="panel liveSignalPanel">
          <header>
            <div>
              <h2>
                <ListChecks size={18} />
                原因与证据
              </h2>
              <p className="panelNote">原因码、指标和 hash 均来自后端 read model</p>
            </div>
          </header>
          {props.results.length > 0 ? (
            <div className="liveEvidenceList">
              {props.results.map((result) => {
                const reasonCodes = result.reason_codes ?? result.signal?.reason_codes ?? [];
                const metricEntries = Object.entries(result.signal?.metrics ?? {}).slice(0, 6);
                const latestBar = result.latest_bar;
                return (
                  <article className="liveEvidenceCard" key={`${result.symbol}:evidence`}>
                    <header>
                      <strong>{result.symbol}</strong>
                      <span className={`statusPill ${liveSignalStatusMeta[result.status].tone}`}>
                        {liveSignalStatusMeta[result.status].label}
                      </span>
                    </header>
                    <div className="reasonList">
                      {reasonCodes.length > 0 ? (
                        reasonCodes.map((reason) => (
                          <span key={`${result.symbol}:${reason}`} className="reasonCode">
                            {reasonLabels[reason] ?? reason}
                          </span>
                        ))
                      ) : (
                        <span className="reasonCode">无原因码</span>
                      )}
                    </div>
                    <section className="liveLatestQuoteBlock" aria-label={`${result.symbol} 最新行情`}>
                      <div className="liveLatestQuoteHead">
                        <span>最新行情</span>
                        <small>{latestBar ? formatDateTime(latestBar.timestamp) : "provider 未返回分钟线"}</small>
                      </div>
                      {latestBar ? (
                        <dl className="compactFacts liveLatestQuoteFacts">
                          <div>
                            <dt>close</dt>
                            <dd>{formatNullable(latestBar.close)}</dd>
                          </div>
                          <div>
                            <dt>open</dt>
                            <dd>{formatNullable(latestBar.open)}</dd>
                          </div>
                          <div>
                            <dt>high</dt>
                            <dd>{formatNullable(latestBar.high)}</dd>
                          </div>
                          <div>
                            <dt>low</dt>
                            <dd>{formatNullable(latestBar.low)}</dd>
                          </div>
                          <div>
                            <dt>volume</dt>
                            <dd>{formatInteger(latestBar.volume)}</dd>
                          </div>
                          <div>
                            <dt>bars</dt>
                            <dd>{formatInteger(result.bar_count)}</dd>
                          </div>
                        </dl>
                      ) : (
                        <p className="liveLatestQuoteEmpty">暂无最新行情</p>
                      )}
                    </section>
                    {metricEntries.length > 0 ? (
                      <dl className="compactFacts">
                        {metricEntries.map(([key, value]) => (
                          <div key={`${result.symbol}:${key}`}>
                            <dt>{key}</dt>
                            <dd>{formatMetric(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    ) : null}
                    <dl className="compactFacts">
                      <div>
                        <dt>latest version</dt>
                        <dd>{result.strategy.latest_template_version ?? result.strategy.template_version}</dd>
                      </div>
                      <div>
                        <dt>config version</dt>
                        <dd>{result.strategy.template_version}</dd>
                      </div>
                      <div>
                        <dt>canonical source</dt>
                        <dd>{result.provider.toUpperCase()} 分钟线</dd>
                      </div>
                      <div>
                        <dt>read model</dt>
                        <dd>live-signal</dd>
                      </div>
                      <div>
                        <dt>bars_hash</dt>
                        <dd className="monoWrap">{shortHash(result.bars_hash)}</dd>
                      </div>
                      <div>
                        <dt>params_hash</dt>
                        <dd className="monoWrap">{shortHash(result.params_hash)}</dd>
                      </div>
                      <div>
                        <dt>indicator_hash</dt>
                        <dd className="monoWrap">{shortHash(result.indicator_hash)}</dd>
                      </div>
                      <div>
                        <dt>idempotency</dt>
                        <dd className="monoWrap">{shortHash(result.idempotency_key)}</dd>
                      </div>
                    </dl>
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState icon={<CircleSlash size={18} />} title="暂无证据" detail="尚无 provider 状态、hash 和原因码" />
          )}
        </section>
      </section>
    </section>
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
  onRunStrategy: () => void;
  onRunTestBatch: () => void;
  onSelectStrategyTestDay: (day: StrategyTestDayResult, batch: StrategyTestBatch) => void;
  onSymbolChange: (value: string) => void;
  onToggleFullDayStrategyBars: (value: boolean) => void;
  optimizationBusy: boolean;
  primaryStrategySymbol: string;
  scanRows: StrategyScanRow[];
  selectedStrategy: StrategyConfig | null;
  selectedStrategyTestBatch: StrategyTestBatch | null;
  selectedStrategyTestDay: StrategyTestDayResult | null;
  selectedStrategyTemplate: StrategyTemplate | null;
  selectedSymbol: string;
  showFullDayStrategyBars: boolean;
  strategyArchiveRangeBusy: boolean;
  strategyArchiveRangeError: string | null;
  strategyArchiveRanges: StrategyArchiveRangeSummary[];
  strategyOverallMetrics: StrategyMetricSummary | null;
  strategyArchiveFeedback: StrategyRunFeedback | null;
  strategyBusy: boolean;
  strategyDraftDirty: boolean;
  strategyReviewDateRows: StrategyDateSummary[];
  strategyReviewSymbolRows: StrategySymbolSummary[];
  strategyRunFeedback: StrategyRunFeedback | null;
  strategySaveBusy: boolean;
  strategyScanFeedback: StrategyRunFeedback | null;
  strategySymbols: string[];
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
            <p className="panelNote">配置、单日测试、最近 30 天（自然日）复盘和参数优化均只读取已归档分钟线</p>
          </div>
          <div className="headerActions">
            {strategyStatus ? <span className={`statusPill ${strategyStatus.tone}`}>{strategyStatus.label}</span> : null}
            <label className="compactControl">
              <span>截止日期</span>
              <input value={props.date} onChange={(event) => props.onDateChange(event.target.value)} type="date" />
            </label>
            <label className="compactControl">
              <span>测试标的组</span>
              <input
                list="symbolOptions"
                placeholder="MU, NVDA, AMD, AVGO, TSM, MSFT"
                value={props.selectedSymbol}
                onChange={(event) => props.onSymbolChange(event.target.value)}
                type="text"
              />
            </label>
          </div>
        </header>
        <div className="strategyScreenerStrip" aria-label="多标的扫描状态">
          <span>
            <Activity size={14} />
            主标的 {props.primaryStrategySymbol || "N/A"}
          </span>
          <span>{formatInteger(props.strategySymbols.length)} 个测试标的</span>
          <small>test batch 仍按 symbol 保存；优化按输入标的组保存全局 optimization run、archive_scope_hash 和 params_hash。</small>
        </div>
        <div className="strategyWorkflowSteps" aria-label="策略测试流程">
          <span>策略配置</span>
          <span>策略测试</span>
          <span>测试复盘（最近30天）</span>
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
            <div className="headerActions">
              <button
                className="smallButton primary"
                disabled={!props.selectedStrategy || !props.selectedSymbol || props.strategyBusy || props.strategyDraftDirty}
                onClick={props.onRunStrategy}
                type="button"
              >
                {props.strategyBusy ? <RefreshCw className="spin" size={14} /> : <Play size={14} />}
                {props.strategyBusy ? "复盘中" : "策略复盘"}
              </button>
              <button className="smallButton" onClick={props.onOpenStrategyConfig} type="button">
                <SlidersHorizontal size={15} />
                编辑配置
              </button>
            </div>
          </header>
          {props.selectedStrategy ? (
            <>
              <dl className="compactFacts">
                <div>
                  <dt>策略</dt>
                  <dd>{props.selectedStrategy.name}</dd>
                </div>
                <div>
                  <dt>最新版本</dt>
                  <dd>{props.selectedStrategy.latest_template_version ?? props.selectedStrategy.template_version}</dd>
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
              {props.strategyRunFeedback ? (
                <div className={`strategyRunFeedback ${props.strategyRunFeedback.tone}`} role="status" aria-live="polite">
                  {props.strategyBusy ? <RefreshCw className="spin" size={16} /> : <ListChecks size={16} />}
                  <div>
                    <strong>{props.strategyRunFeedback.title}</strong>
                    <span>{props.strategyRunFeedback.detail}</span>
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
                测试复盘（最近30天）
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
                {props.archiveBusy ? "拉取中" : "拉取30天数据"}
              </button>
              <button
                className="smallButton primary"
                onClick={props.onRunTestBatch}
                disabled={!props.selectedStrategy || !props.selectedSymbol || props.strategyTestBusy || props.strategyDraftDirty}
                type="button"
              >
                {props.strategyTestBusy ? <RefreshCw className="spin" size={14} /> : <Play size={14} />}
                {props.strategyTestBusy ? "复盘中" : "运行30天"}
              </button>
            </div>
          </header>
          <StrategyArchiveRangePrompt
            busy={props.strategyArchiveRangeBusy}
            endDate={props.date}
            error={props.strategyArchiveRangeError}
            ranges={props.strategyArchiveRanges}
            symbols={props.strategySymbols}
          />
          {props.strategyArchiveFeedback ? (
            <div className={`strategyRunFeedback ${props.strategyArchiveFeedback.tone}`} role="status" aria-live="polite">
              <RefreshCw size={16} className={props.archiveBusy ? "spin" : undefined} />
              <div>
                <strong>{props.strategyArchiveFeedback.title}</strong>
                <span>{props.strategyArchiveFeedback.detail}</span>
              </div>
            </div>
          ) : null}
          {props.strategyScanFeedback ? (
            <div className={`strategyRunFeedback ${props.strategyScanFeedback.tone}`} role="status" aria-live="polite">
              {props.strategyTestBusy || props.optimizationBusy ? <RefreshCw className="spin" size={16} /> : <ListChecks size={16} />}
              <div>
                <strong>{props.strategyScanFeedback.title}</strong>
                <span>{props.strategyScanFeedback.detail}</span>
              </div>
            </div>
          ) : null}
          {props.strategySymbols.length > 1 ? (
            <StrategyScanResults rows={props.scanRows} />
          ) : null}
          {props.strategyOverallMetrics ? (
            <>
              <section className="strategyOverallOverview" aria-label="策略整体指标总览">
                <header>
                  <div>
                    <strong>策略整体指标总览</strong>
                    <small>汇总当前标的组的最新 test batch；历史 artifact 不被改写。</small>
                  </div>
                </header>
                <StrategyResearchMetrics
                  closedGroupCount={props.strategyOverallMetrics.closedGroupCount}
                  coverageRatio={props.strategyOverallMetrics.coverageRatio}
                  maxDrawdown={props.strategyOverallMetrics.maxDrawdown}
                  profitFactor={props.strategyOverallMetrics.profitFactor}
                  signalCount={props.strategyOverallMetrics.signalCount}
                  totalPnl={props.strategyOverallMetrics.totalPnl}
                  winRate={props.strategyOverallMetrics.winRate}
                />
              </section>
              {props.latestStrategyTestBatch?.failure_reason ? (
                <div className="statusReason">
                  <AlertTriangle size={16} />
                  <span>
                    {formatStrategyFailureReason(props.latestStrategyTestBatch.failure_reason) ??
                      props.latestStrategyTestBatch.failure_reason}
                  </span>
                </div>
              ) : null}
              <div className="strategyTestReviewLayout">
                <StrategyReviewExplorer
                  dateRows={props.strategyReviewDateRows}
                  onSelectStrategyTestDay={props.onSelectStrategyTestDay}
                  selectedBatchId={props.selectedStrategyTestBatch?.batch_id ?? null}
                  selectedDayId={props.selectedStrategyTestDay?.day_result_id ?? null}
                  symbolRows={props.strategyReviewSymbolRows}
                />
                <StrategyTestDayDetail
                  archive={props.strategyTestDayArchive}
                  busy={props.strategyTestDayDetailBusy}
                  day={props.selectedStrategyTestDay}
                  run={props.strategyTestDayRun}
                  selectedStrategy={props.selectedStrategy}
                  showFullDayStrategyBars={props.showFullDayStrategyBars}
                  symbol={props.selectedStrategyTestBatch?.symbol ?? props.primaryStrategySymbol}
                  onToggleFullDayStrategyBars={props.onToggleFullDayStrategyBars}
                />
              </div>
            </>
          ) : (
            <EmptyState icon={<Clock3 size={18} />} title="尚未运行30天测试" detail="运行后会保存 test batch 和逐日 run 证据。" />
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
                  <dt>标的范围</dt>
                  <dd>{optimizationScopeLabel(props.latestOptimization)}</dd>
                </div>
                <div>
                  <dt>模板版本</dt>
                  <dd>{props.latestOptimization.template_version}</dd>
                </div>
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
                      资金PNL {formatPnl(bestCandidate.total_pnl)} · 胜率 {formatPercentValue(bestCandidate.win_rate)} ·
                      稳定分 {formatNullable(bestCandidate.stability_score)}
                    </span>
                  </div>
                  <button
                    className="smallButton primary"
                    disabled={props.strategySaveBusy || bestCandidate.status !== "eligible"}
                    onClick={() => props.onApplyOptimizationCandidate(bestCandidate)}
                    type="button"
                  >
                    {props.strategySaveBusy ? <RefreshCw className="spin" size={14} /> : <Save size={14} />}
                    {props.strategySaveBusy ? "套用中" : "套用参数"}
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

function StrategyArchiveRangePrompt(props: {
  busy: boolean;
  endDate: string;
  error: string | null;
  ranges: StrategyArchiveRangeSummary[];
  symbols: string[];
}) {
  if (props.symbols.length === 0) return null;

  const rangeBySymbol = new Map(props.ranges.map((range) => [range.symbol, range]));
  const expectedDates = recentStrategyCalendarDates(props.endDate, 30);
  const rows = props.symbols.map(
    (symbol) =>
      rangeBySymbol.get(symbol) ?? {
        availableCount: 0,
        earliestAvailableDate: null,
        expectedCount: expectedDates.length,
        latestAvailableDate: null,
        nonAvailableCount: expectedDates.length,
        symbol,
        totalCount: 0,
        windowEndDate: expectedDates[expectedDates.length - 1] ?? null,
        windowStartDate: expectedDates[0] ?? null
      }
  );
  const needsPreparation = rows.some(
    (range) => range.availableCount < range.expectedCount || range.nonAvailableCount > 0
  );
  const tone: StrategyFeedbackTone = props.error ? "danger" : needsPreparation ? "warn" : "ok";
  const detail = props.error
    ? props.error
    : needsPreparation
      ? "当前提示只统计截止日前最近30天（自然日）窗口；若存在缺失或不可用，请先点击【拉取30天数据】。"
      : "当前标的最近30天（自然日）窗口已有可用归档，可直接运行30天复盘。";

  return (
    <section className={`strategyArchivePrompt ${tone}`} aria-label="已有标的数据日期范围">
      <div className="strategyArchivePromptHeader">
        {props.busy ? <RefreshCw className="spin" size={16} /> : tone === "ok" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
        <div>
          <strong>已有标的数据日期范围</strong>
          <span>{detail}</span>
        </div>
      </div>
      <div className="strategyArchiveRangeList">
        {rows.map((range) => (
          <div className="strategyArchiveRangeRow" key={range.symbol}>
            <strong>{range.symbol}</strong>
            <span>{formatStrategyArchiveRange(range)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function formatStrategyArchiveRange(range: StrategyArchiveRangeSummary) {
  const windowText =
    range.windowStartDate && range.windowEndDate
      ? `窗口 ${range.windowStartDate} 至 ${range.windowEndDate}`
      : "窗口未确定";
  const expectedText = range.expectedCount > 0 ? `/${formatInteger(range.expectedCount)}` : "";
  const unavailableText = range.nonAvailableCount > 0 ? `，${formatInteger(range.nonAvailableCount)} 日缺失/不可用` : "";
  if (!range.earliestAvailableDate || !range.latestAvailableDate) {
    return `${windowText}，可用 0${expectedText} 日${unavailableText}`;
  }
  const availableRangeText =
    range.earliestAvailableDate === range.latestAvailableDate
      ? range.earliestAvailableDate
      : `${range.earliestAvailableDate} 至 ${range.latestAvailableDate}`;
  return `${windowText}，可用 ${formatInteger(range.availableCount)}${expectedText} 日${unavailableText}，可用范围 ${availableRangeText}`;
}

function StrategyScanResults(props: { rows: StrategyScanRow[] }) {
  const completedBatchCount = props.rows.filter((row) => row.testBatch).length;
  return (
    <section className="strategyScanResults" aria-label="多标的扫描结果">
      <div className="strategyScanResultsHeader">
        <strong>多标的一体化扫描</strong>
        <span>
          {formatInteger(props.rows.length)} 个测试标的 · {formatInteger(completedBatchCount)} 个已有批次
        </span>
      </div>
      <div className="strategyScanGrid">
        {props.rows.map((row) => {
          const batch = row.testBatch;
          const testStatus = batch ? strategyTestStatusMeta[batch.status] : { label: "待运行", tone: "warn" as const };
          const optimization = row.optimization;
          const optimizationStatus = optimization ? strategyOptimizationStatusMeta[optimization.status] : null;
          return (
            <article className={batch ? "strategyScanCard" : "strategyScanCard pending"} key={batch?.batch_id ?? row.symbol}>
              <header>
                <strong>{row.symbol}</strong>
                <span className={`statusPill ${testStatus.tone}`}>{testStatus.label}</span>
              </header>
              <dl>
                <div>
                  <dt>信号</dt>
                  <dd>{batch ? formatInteger(batch.signal_count) : "N/A"}</dd>
                </div>
                <div>
                  <dt>资金PNL</dt>
                  <dd className={batch ? summaryTone(batch.total_pnl) : undefined}>{batch ? formatPnl(batch.total_pnl) : "N/A"}</dd>
                </div>
                <div>
                  <dt>胜率</dt>
                  <dd>{batch ? formatPercentValue(batch.win_rate) : "N/A"}</dd>
                </div>
                <div>
                  <dt>覆盖</dt>
                  <dd>{batch ? formatPercentValue(batch.coverage_ratio) : "N/A"}</dd>
                </div>
              </dl>
              {!batch ? (
                <small>尚未运行30天测试；点击运行30天会为 {row.symbol} 保存独立 test batch。</small>
              ) : optimization ? (
                <small>
                  全局优化 {optimizationStatus?.label ?? optimization.status} · 可候选 {formatInteger(optimization.eligible_candidate_count)} ·
                  最佳分 {formatNullable(optimization.best_stability_score)}
                </small>
              ) : (
                <small>尚未运行覆盖该标的的全局优化。</small>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function StrategyReviewExplorer(props: {
  dateRows: StrategyDateSummary[];
  onSelectStrategyTestDay: (day: StrategyTestDayResult, batch: StrategyTestBatch) => void;
  selectedBatchId: string | null;
  selectedDayId: string | null;
  symbolRows: StrategySymbolSummary[];
}) {
  const [mode, setMode] = useState<StrategyReviewMode>("date");
  const rowsAvailable = props.dateRows.length > 0 || props.symbolRows.length > 0;

  if (!rowsAvailable) {
    return (
      <section className="strategyReviewExplorer" aria-label="策略测试汇总下钻">
        <EmptyState icon={<Clock3 size={18} />} title="暂无测试汇总" detail="运行30天后会按日期和标的生成汇总入口。" />
      </section>
    );
  }

  return (
    <section className="strategyReviewExplorer" aria-label="策略测试汇总下钻">
      <header className="strategyReviewExplorerHeader">
        <div>
          <strong>汇总下钻</strong>
          <small>默认按日期汇总；切到标的后可查看单个 symbol 的测试批次。</small>
        </div>
        <div className="segmentedControl" role="tablist" aria-label="策略测试汇总维度">
          <button
            aria-selected={mode === "date"}
            className={mode === "date" ? "active" : undefined}
            onClick={() => setMode("date")}
            role="tab"
            type="button"
          >
            按日期
          </button>
          <button
            aria-selected={mode === "symbol"}
            className={mode === "symbol" ? "active" : undefined}
            onClick={() => setMode("symbol")}
            role="tab"
            type="button"
          >
            按标的
          </button>
        </div>
      </header>
      {mode === "date" ? (
        <div className="strategySummaryList" aria-label="按日期汇总">
          {props.dateRows.map((row) => {
            const status = strategyStatusMeta[row.status];
            const firstEntry = row.entries[0] ?? null;
            return (
              <article className="strategySummaryCard" key={row.tradeDate}>
                <button
                  className="strategySummaryMain"
                  disabled={!firstEntry}
                  onClick={() => firstEntry && props.onSelectStrategyTestDay(firstEntry.day, firstEntry.batch)}
                  type="button"
                >
                  <div className="strategySummaryTitle">
                    <div className="strategySummaryIdentity">
                      <strong>{row.tradeDate}</strong>
                      <span>{row.symbolCount > 0 ? `${formatInteger(row.symbolCount)} 标的` : "无订单"}</span>
                    </div>
                    <span className={`statusPill ${status.tone}`}>{status.label}</span>
                  </div>
                  <StrategySummaryMiniMetrics metrics={row} />
                </button>
                {row.entries.length > 0 ? (
                  <StrategyReviewEntryChips
                    entries={row.entries}
                    selectedBatchId={props.selectedBatchId}
                    selectedDayId={props.selectedDayId}
                    label={(entry) => entry.batch.symbol}
                    onSelect={props.onSelectStrategyTestDay}
                  />
                ) : (
                  <small className="strategySummaryEmptyLine">当天没有策略订单标的。</small>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="strategySummaryList" aria-label="按标的汇总">
          {props.symbolRows.map((row) => {
            const status = strategyTestStatusMeta[row.status];
            const firstEntry = row.entries[0] ?? null;
            return (
              <article className="strategySummaryCard" key={row.batch.batch_id}>
                <button
                  className="strategySummaryMain"
                  disabled={!firstEntry}
                  onClick={() => firstEntry && props.onSelectStrategyTestDay(firstEntry.day, firstEntry.batch)}
                  type="button"
                >
                  <div className="strategySummaryTitle">
                    <div className="strategySummaryIdentity">
                      <strong>{row.symbol}</strong>
                      <span>
                        {formatInteger(row.batch.completed_day_count)}/{formatInteger(row.batch.day_count)} 日
                      </span>
                    </div>
                    <span className={`statusPill ${status.tone}`}>{status.label}</span>
                  </div>
                  <StrategySummaryMiniMetrics metrics={row} />
                </button>
                <StrategyReviewEntryChips
                  entries={row.entries}
                  selectedBatchId={props.selectedBatchId}
                  selectedDayId={props.selectedDayId}
                  label={(entry) => entry.day.trade_date.slice(5)}
                  onSelect={props.onSelectStrategyTestDay}
                />
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function StrategySummaryMiniMetrics(props: { metrics: Pick<StrategyMetricSummary, "closedGroupCount" | "signalCount" | "totalPnl" | "winRate"> }) {
  return (
    <dl className="strategySummaryMiniMetrics">
      <div>
        <dt>信号</dt>
        <dd>{formatInteger(props.metrics.signalCount)}</dd>
      </div>
      <div>
        <dt>闭合</dt>
        <dd>{formatInteger(props.metrics.closedGroupCount)}</dd>
      </div>
      <div>
        <dt>资金PNL</dt>
        <dd className={summaryTone(props.metrics.totalPnl)}>{formatPnl(props.metrics.totalPnl)}</dd>
      </div>
      <div>
        <dt>胜率</dt>
        <dd>{formatPercentValue(props.metrics.winRate)}</dd>
      </div>
    </dl>
  );
}

function StrategyReviewEntryChips(props: {
  entries: StrategyReviewEntry[];
  label: (entry: StrategyReviewEntry) => string;
  onSelect: (day: StrategyTestDayResult, batch: StrategyTestBatch) => void;
  selectedBatchId: string | null;
  selectedDayId: string | null;
}) {
  return (
    <div className="strategyReviewChipRow" aria-label="单日复盘入口">
      {props.entries.map((entry) => {
        const selected = props.selectedBatchId === entry.batch.batch_id && props.selectedDayId === entry.day.day_result_id;
        const status = strategyStatusMeta[entry.day.status];
        return (
          <button
            aria-pressed={selected}
            className={selected ? "strategyReviewChip active" : "strategyReviewChip"}
            key={`${entry.batch.batch_id}:${entry.day.day_result_id}`}
            onClick={() => props.onSelect(entry.day, entry.batch)}
            title={`${entry.day.trade_date} ${entry.batch.symbol} ${status.label}`}
            type="button"
          >
            <span>{props.label(entry)}</span>
            <small>{formatInteger(entry.day.signal_count)}</small>
          </button>
        );
      })}
    </div>
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
          <dt>资金PNL</dt>
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
        {props.strategySaveBusy ? <RefreshCw className="spin" size={14} /> : <Save size={14} />}
        {props.strategySaveBusy ? "套用中" : "套用本组"}
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
  const signalReplay = useMemo(
    () => buildStrategySignalGroups(signals, props.run?.signal_groups ?? [], props.run?.params),
    [signals, props.run?.signal_groups, props.run?.params]
  );
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
        <EmptyState icon={<Clock3 size={18} />} title="选择测试日" detail="运行 30 天测试后，从日列表选择一日查看图形与订单明细。" />
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
                <span>30 天结果载入后会提前缓存归档分钟线与策略 run read model。</span>
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
                  <dt>资金PNL</dt>
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
                    <details className="signalGroupCard strategyDayOrderCard" key={group.id}>
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
                          <span className={`signalGroupPnl ${signalGroupPnlTone(group)}`}>
                            资金PNL {formatSignalGroupPnl(group)}
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
                        <StrategySignalGroupIntervalChart archive={props.archive} group={group} run={props.run} />
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
        <dt>资金PNL</dt>
        <dd>{formatPnl(props.totalPnl)}</dd>
      </div>
      <div>
        <dt>胜率</dt>
        <dd>{formatPercentValue(props.winRate)}</dd>
      </div>
      <div>
        <dt>盈亏比</dt>
        <dd>{formatProfitFactorMetric(props.profitFactor, props.totalPnl, props.closedGroupCount)}</dd>
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

function getStrategyRunFeedback(run: StrategySignalRun, testBatch: StrategyTestBatch | null = null): StrategyRunFeedback {
  const status = strategyStatusMeta[run.status];
  const testBatchClosedGroupCount =
    testBatch?.day_results.reduce((total, day) => total + day.closed_group_count, 0) ?? 0;
  const testBatchDetail = testBatch
    ? ` 最近 ${formatInteger(testBatch.window_trading_days)} 日测试复盘为 ${formatInteger(
        testBatch.signal_count
      )} 个信号，闭合组 ${formatInteger(testBatchClosedGroupCount)}。`
    : "";
  if (run.status === "completed" && run.signal_count === 0) {
    return {
      tone: "warn",
      title: "单日策略复盘已完成：0 个策略信号",
      detail: `当前日期 ${run.trade_date} ${run.symbol} 已完成计算，但没有触发开仓或平仓条件。${testBatchDetail}`
    };
  }
  if (run.status === "completed") {
    return {
      tone: "ok",
      title: `单日策略复盘已完成：${formatInteger(run.signal_count)} 个策略信号`,
      detail: `当前日期 ${run.trade_date} ${run.symbol} 已保存信号、指标序列和策略证据。${testBatchDetail}`
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
  const calendarCoverageMatch = reason.match(/^required_recent_(\d+)_calendar_days_found_(\d+)$/);
  if (calendarCoverageMatch) {
    return `最近 ${calendarCoverageMatch[1]} 天（自然日）本地归档覆盖不足，当前只找到 ${calendarCoverageMatch[2]} 天。请先在策略测试页拉取30天数据，再重新运行测试。`;
  }
  const calendarSymbolCoverageMatch = reason.match(/^required_recent_(\d+)_calendar_days_per_symbol_found_(.+)$/);
  if (calendarSymbolCoverageMatch) {
    return `最近 ${calendarSymbolCoverageMatch[1]} 天（自然日）多标的本地归档覆盖不足：${formatSymbolCoverageFailure(
      calendarSymbolCoverageMatch[2]
    )}。请先拉取30天数据，再重新运行测试。`;
  }
  const coverageMatch = reason.match(/^required_(\d+)_archived_trading_days_found_(\d+)$/);
  if (coverageMatch) {
    return `最近 ${coverageMatch[1]} 个交易日归档覆盖不足，当前只找到 ${coverageMatch[2]} 个。请先在策略测试页拉取30天数据，再重新运行测试。`;
  }
  return reason;
}

function formatSymbolCoverageFailure(rawCoverage: string) {
  const tokens = rawCoverage.split("_").filter(Boolean);
  const pairs: string[] = [];
  for (let index = 0; index < tokens.length; index += 2) {
    const symbol = tokens[index];
    const count = tokens[index + 1];
    if (symbol && count) pairs.push(`${symbol} ${count} 天`);
  }
  return pairs.length > 0 ? pairs.join("、") : rawCoverage;
}

function formatArchiveFailureReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  if (reason === "yahoo_http_422") {
    return "Yahoo 未接受 1 分钟历史请求，常见于日期超出可取窗口或 provider 不接受该请求范围；系统已保存为行情不可用，不会渲染成功图。";
  }
  if (reason.startsWith("yahoo_http_")) {
    return "Yahoo 暂时没有接受本次分钟线请求，系统已保存为行情获取失败。";
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

function strategyRunIndicatorCount(run: StrategySignalRun | null | undefined): number {
  return run?.indicator_point_count ?? run?.indicator_series.length ?? 0;
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
            <dd>{formatInteger(strategyRunIndicatorCount(props.run))}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function StrategyDescription(props: {
  enabled: boolean;
  latestTestBatch: StrategyTestBatch | null;
  latestRun: StrategySignalRun | null;
  params: Record<string, StrategyParamValue>;
  strategyName: string;
  templateKey: string;
  templateVersion: string;
}) {
  const runStatus = props.latestRun ? strategyStatusMeta[props.latestRun.status] : null;
  const testBatchStatus = props.latestTestBatch ? strategyTestStatusMeta[props.latestTestBatch.status] : null;
  const testBatchClosedGroupCount =
    props.latestTestBatch?.day_results.reduce((total, day) => total + day.closed_group_count, 0) ?? 0;
  const bbPeriod = formatStrategyParam(props.params.bb_period);
  const bbStddev = formatStrategyParam(props.params.bb_stddev);
  const adxPeriod = formatStrategyParam(props.params.adx_period);
  const adxTrendThreshold = formatStrategyParam(props.params.adx_trend_threshold);
  const adxChopThreshold = formatStrategyParam(props.params.adx_chop_threshold);
  const atrPeriod = formatStrategyParam(props.params.atr_period);
  const atrStopMultiplier = formatStrategyParam(props.params.atr_stop_multiplier);
  const atrTargetMultiplier = formatStrategyParam(props.params.atr_target_multiplier);
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
  const trendEmaPeriod = formatStrategyParam(props.params.trend_ema_period);
  const breakoutVolumeMultiplier = formatStrategyParam(props.params.breakout_volume_multiplier);
  const pullbackVolumeMaxRatio = formatStrategyParam(props.params.pullback_volume_max_ratio);
  const setupBreakoutBars = formatStrategyParam(props.params.setup_breakout_bars);
  const trendSetupLookback = formatStrategyParam(props.params.trend_setup_lookback);
  const maxPullbackBars = formatStrategyParam(props.params.max_pullback_bars);
  const openingRangeBars = formatStrategyParam(props.params.opening_range_bars);
  const emaSlopeLookback = formatStrategyParam(props.params.ema_slope_lookback);
  const emaSlopeMin = formatStrategyParam(props.params.ema_slope_min);
  const bigBodyStrengthRatio = formatStrategyParam(props.params.big_body_strength_ratio);
  const entryBodyStrengthRatio = formatStrategyParam(props.params.entry_body_strength_ratio);
  const rangeLookbackBars = formatStrategyParam(props.params.range_lookback_bars);
  const minEdgeTouches = formatStrategyParam(props.params.min_edge_touches);
  const edgeZoneRatio = formatStrategyParam(props.params.edge_zone_ratio);
  const emaPeriod = formatStrategyParam(props.params.ema_period);
  const maxEmaSlope = formatStrategyParam(props.params.max_ema_slope);
  const minEmaThreadBars = formatStrategyParam(props.params.min_ema_thread_bars);
  const edgeTouchToleranceTicks = formatStrategyParam(props.params.edge_touch_tolerance_ticks);
  const reversalShadowRatio = formatStrategyParam(props.params.reversal_shadow_ratio);
  const reversalBodyStrengthRatio = formatStrategyParam(props.params.reversal_body_strength_ratio);
  const minRangeHeight = formatStrategyParam(props.params.min_range_height);
  const initialCapital = formatStrategyParamByKey("initial_capital", props.params.initial_capital);
  const entryCapitalRatio = formatStrategyParamByKey("entry_capital_ratio", props.params.entry_capital_ratio);
  const isLiquiditySweep = props.templateKey === "institutional_liquidity_sweep_v1";
  const isMomentumMeanReversion = props.templateKey === "momentum_mean_reversion_v1";
  const isTrendRider = props.templateKey === "one_minute_trend_rider_v1";
  const isRangeFader = props.templateKey === "one_minute_range_fader_v1";

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
            <dt>单日标的</dt>
            <dd>{props.latestRun.symbol}</dd>
          </div>
          <div>
            <dt>单日信号</dt>
            <dd>{formatInteger(props.latestRun.signal_count)}</dd>
          </div>
          <div>
            <dt>单日状态</dt>
            <dd>{runStatus?.label ?? props.latestRun.status}</dd>
          </div>
          <div>
            <dt>单日 Bars</dt>
            <dd>{formatInteger(strategyRunIndicatorCount(props.latestRun))}</dd>
          </div>
        </dl>
      ) : null}

      {props.latestTestBatch ? (
        <dl className="strategyDescriptionFacts strategyDescriptionTestFacts">
          <div className="wideFact">
            <dt>测试窗口</dt>
            <dd>
              最近 {formatInteger(props.latestTestBatch.window_trading_days)} 日至 {props.latestTestBatch.end_date}
            </dd>
          </div>
          <div>
            <dt>30天测试信号</dt>
            <dd>{formatInteger(props.latestTestBatch.signal_count)}</dd>
          </div>
          <div>
            <dt>测试闭合组</dt>
            <dd>{formatInteger(testBatchClosedGroupCount)}</dd>
          </div>
          <div>
            <dt>测试状态</dt>
            <dd>{testBatchStatus?.label ?? props.latestTestBatch.status}</dd>
          </div>
          <div>
            <dt>测试覆盖</dt>
            <dd>{formatPercentValue(props.latestTestBatch.coverage_ratio)}</dd>
          </div>
        </dl>
      ) : null}

      {props.latestRun?.failure_reason ? (
        <div className="statusReason">
          <AlertTriangle size={16} />
          <span>{formatStrategyFailureReason(props.latestRun.failure_reason) ?? props.latestRun.failure_reason}</span>
        </div>
      ) : null}

      <section className="strategyRuleBlock">
        <h3>资金模型</h3>
        <ol>
          <li>
            策略 run 使用初始本金 {initialCapital} 和入场资金比例 {entryCapitalRatio} 换算每次开仓仓位。
          </li>
          <li>单日复盘、最近30天测试和策略优化的资金PNL 均读取后端 strategy run read model。</li>
          <li>该资金模型只用于历史策略研究，不修改 STP committed fills，也不会触发自动下单。</li>
        </ol>
      </section>

      {isRangeFader ? (
        <>
          <section className="strategyRuleBlock">
            <h3>震荡区间确立</h3>
            <ol>
              <li>
                后端只读取已归档分钟线，回看最近 {rangeLookbackBars} 根 K，要求上沿和下沿各至少被测试 {minEdgeTouches} 次。
              </li>
              <li>
                区间高度必须不低于 {minRangeHeight}，触边容差为 {edgeTouchToleranceTicks} tick，避免把微小噪音当成可交易箱体。
              </li>
              <li>
                {emaPeriod} EMA 必须钝化，斜率绝对值不超过 {maxEmaSlope}；至少 {minEmaThreadBars} 根 K 要像穿糖葫芦一样穿过 EMA。
              </li>
              <li>后端同时保存 VWAP、EMA、区间上下沿和中轴线，前端只展示 strategy run read model。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>BLSH 边缘入场</h3>
            <ol>
              <li>
                只在区间顶部和底部 {edgeZoneRatio} 区域寻找信号；中间 50% dead zone 不生成开仓。
              </li>
              <li>
                做多等待价格测试或短暂跌破下沿后收回，做空等待价格测试或短暂突破上沿后被按回。
              </li>
              <li>
                反转确认要求影线占比不低于 {reversalShadowRatio}，或出现实体强度不低于 {reversalBodyStrengthRatio} 的反转 K。
              </li>
              <li>入场价使用下一根 1 分钟 K 的开盘价，信号 K 低点或高点外侧 {stopTickOffset} tick 作为硬止损。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>分批止盈</h3>
            <ol>
              <li>
                第一目标为区间中轴线，平仓比例为 {firstTargetExitFraction}；触达后剩余仓位止损上移到入场价。
              </li>
              <li>
                第二目标为对侧区间边缘；若保本止损先触发，则剩余仓位按 break-even 出场。
              </li>
              <li>若硬止损、保本止损或最长持仓 {maxHoldingBars} 根 K 先触发，则按后端出场信号记录。</li>
              <li>该策略只生成历史复盘信号，不修改 committed fills，也不会向 STP 或券商发送订单。</li>
            </ol>
          </section>
        </>
      ) : isTrendRider ? (
        <>
          <section className="strategyRuleBlock">
            <h3>趋势确立</h3>
            <ol>
              <li>
                后端逐 bar 计算 VWAP、{trendEmaPeriod} EMA、{exitEmaPeriod} EMA 和相对成交量，前端只展示 strategy run read model。
              </li>
              <li>
                多头必须在 VWAP 与 {trendEmaPeriod} EMA 上方，且 EMA({emaSlopeLookback}) 斜率至少达到 {emaSlopeMin}；空头规则反向。
              </li>
              <li>
                最近 {trendSetupLookback} 根 K 中至少出现 {setupBreakoutBars} 根大实体强趋势 K，量能达到均量 {breakoutVolumeMultiplier} 倍。
              </li>
              <li>
                强突破必须攻克前 {openingRangeBars} 根早盘区间高点或跌破早盘区间低点，确认 Always In 方向。
              </li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>H2 / L2 回调</h3>
            <ol>
              <li>突破后最多等待 {maxPullbackBars} 根 K，必须回踩或反抽到 {trendEmaPeriod} EMA 附近。</li>
              <li>
                多头等待两次微观低点下探且第二次不明显创新低，空头等待两次微观高点上探且第二次不明显创新高。
              </li>
              <li>
                回调阶段平均量必须低于强突破量的 {pullbackVolumeMaxRatio}，避免把主力砸盘误判成自然回吐。
              </li>
              <li>
                触发 K 必须重新突破前一根 K 的高点或低点、收回 {trendEmaPeriod} EMA，实体强度不低于 {entryBodyStrengthRatio}。
              </li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>止损与出场</h3>
            <ol>
              <li>硬止损取二级回调波谷/波峰与 {trendEmaPeriod} EMA 外侧 {stopTickOffset} tick 中更保守的一侧。</li>
              <li>策略不设静态止盈，`take_profit_price` 保存为空，持仓只由硬止损或 {exitEmaPeriod} EMA 收盘破位退出。</li>
              <li>所有入场、出场、H2/L2 和缩量证据都保存在 strategy_signals reason codes 与 metrics 中，不改写 STP 成交。</li>
            </ol>
          </section>
        </>
      ) : isMomentumMeanReversion ? (
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
              <li>ATR 止损和 ATR 第一目标仍优先于出场缓冲触发。</li>
            </ol>
          </section>

          <section className="strategyRuleBlock">
            <h3>止盈止损</h3>
            <ol>
              <li>
                后端逐 bar 计算 ATR({atrPeriod})；多头止损为入场价减 {atrStopMultiplier} 倍 ATR，空头为入场价加同等距离。
              </li>
              <li>
                第一止盈目标为入场价沿持仓方向推进 {atrTargetMultiplier} 倍 ATR；历史 run 使用 high/low 触达建模为被动止盈成交。
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

function LossReviewPanel(props: {
  busy: boolean;
  group: TradeGroup;
  onSave: (reasonCategory: TradeReviewReasonCategory, reasonCode: string, note: string) => void;
}) {
  const initialCategory = props.group.review?.reason_category ?? "opening_signal";
  const [reasonCategory, setReasonCategory] = useState<TradeReviewReasonCategory>(initialCategory);
  const [reasonCode, setReasonCode] = useState(
    props.group.review?.reason_code ?? lossReviewReasonOptions[initialCategory][0]?.code ?? ""
  );
  const [note, setNote] = useState(props.group.review?.note ?? "");
  const reasonOptions = lossReviewReasonOptions[reasonCategory];
  const selectedReason = reasonOptions.find((option) => option.code === reasonCode) ?? reasonOptions[0];

  useEffect(() => {
    if (!reasonOptions.some((option) => option.code === reasonCode)) {
      setReasonCode(reasonOptions[0]?.code ?? "");
    }
  }, [reasonCategory, reasonCode, reasonOptions]);
  const selectedReasonCode = selectedReason?.code ?? "";

  return (
    <section className="lossReviewPanel" aria-label={`${props.group.symbol} 亏损复盘`}>
        <header className="modalHeader">
          <div>
            <p className="eyebrow">Loss Review</p>
            <h2>
              <Pencil size={18} />
              {props.group.symbol} 亏损复盘
            </h2>
            <p className="panelNote">
              {formatDateTime(props.group.opened_at)} 至 {props.group.closed_at ? formatDateTime(props.group.closed_at) : "未清仓"}
            </p>
          </div>
          <div className="headerActions">
            {props.group.review ? <span className="statusPill ok">已保存</span> : <span className="statusPill warn">待复盘</span>}
          </div>
        </header>

        <form
          className="lossReviewForm"
          onSubmit={(event) => {
            event.preventDefault();
            props.onSave(reasonCategory, selectedReasonCode, note);
          }}
        >
          <dl className="compactFacts lossReviewFacts">
            <div>
              <dt>方向</dt>
              <dd>{formatDirection(props.group.direction)}</dd>
            </div>
            <div>
              <dt>数量</dt>
              <dd>{formatInteger(props.group.total_quantity)}</dd>
            </div>
            <div>
              <dt>PnL</dt>
              <dd className={summaryTone(props.group.pnl ?? 0)}>{props.group.pnl === null ? "N/A" : formatPnl(props.group.pnl)}</dd>
            </div>
          </dl>

          <div className="lossReviewFields">
            <label>
              <span>原因分类</span>
              <select
                disabled={props.busy}
                onChange={(event) => setReasonCategory(event.target.value as TradeReviewReasonCategory)}
                value={reasonCategory}
              >
                {Object.entries(lossReviewReasonCategoryLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>亏损原因</span>
              <select disabled={props.busy} onChange={(event) => setReasonCode(event.target.value)} value={selectedReasonCode}>
                {reasonOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="lossReviewNote">
            <span>补充记录</span>
            <textarea
              disabled={props.busy}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              placeholder="例如：入场前未等回踩确认。"
              value={note}
            />
          </label>

          <footer className="modalActions">
            <button className="smallButton primary" disabled={props.busy || !selectedReasonCode} type="submit">
              {props.busy ? <RefreshCw className="spin" size={14} /> : <Save size={14} />}
              保存复盘
            </button>
          </footer>
        </form>
    </section>
  );
}

function TradeReplayModal(props: {
  group: TradeGroup;
  archive: MarketMinuteArchive | null;
  lossReviewBusy: boolean;
  onClose: () => void;
  onSave: (reasonCategory: TradeReviewReasonCategory, reasonCode: string, note: string) => void;
}) {
  const evaluation = props.group.evaluation;
  const archiveStatus = props.archive ? marketStatusMeta[props.archive.data_status] : null;
  const canReviewLoss = props.group.status === "closed" && props.group.pnl !== null && props.group.pnl < 0;
  return (
    <div
      className="modalBackdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) props.onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`${props.group.symbol} 交易回放`}
    >
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
            <button className="iconButton" onClick={props.onClose} aria-label="关闭回放弹层" title="关闭" type="button">
              <X size={16} />
            </button>
          </div>
        </header>

        <div className="replayModalBody">
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
                  scope={tradeGroupScope(props.group, minuteCandleEdgeBufferBars)}
                  showReplayEma20
                  tradeMarkerVariant="replay"
                />
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
              <TradeReplayOrderDetails group={props.group} />
              {canReviewLoss ? (
                <LossReviewPanel
                  key={props.group.trade_group_id}
                  busy={props.lossReviewBusy}
                  group={props.group}
                  onSave={props.onSave}
                />
              ) : null}
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
  pnl: number | null;
  pnlUnit: StrategySignalGroupPerformance["unit"] | null;
};

function buildStrategySignalGroups(
  signals: StrategySignal[],
  readModelGroups: StrategySignalGroupPerformance[] = [],
  params?: Record<string, StrategyParamValue>
) {
  const groupMetricsByEntryId = new Map(readModelGroups.map((group) => [group.entry_signal_id, group]));
  const orderedSignals = [...signals].sort(compareStrategySignals);
  const groups = orderedSignals.filter(isEntrySignal).map<StrategySignalGroup>((entry) => {
    const readModelGroup = groupMetricsByEntryId.get(entry.signal_id);
    return {
      id: entry.signal_id,
      entry,
      exits: [],
      signals: [entry],
      side: entry.side,
      status: "open",
      openedAt: entry.timestamp,
      closedAt: null,
      pnl: readModelGroup?.pnl ?? null,
      pnlUnit: readModelGroup?.unit ?? null
    };
  });
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
    if (group.pnl === null) {
      const metricsPnl = signalGroupPnlFromBackendSignalMetrics(group, params);
      if (metricsPnl !== null) {
        group.pnl = metricsPnl;
        group.pnlUnit = "capital_weighted_position_pnl";
      }
    }
  });

  return {
    groups: groups.sort((left, right) => compareStrategySignals(left.entry, right.entry)),
    orphanSignals
  };
}

function signalGroupPnlFromBackendSignalMetrics(group: StrategySignalGroup, params?: Record<string, StrategyParamValue>) {
  if (group.exits.length === 0) return null;
  let pnl = 0;
  const quantity = strategyPositionQuantity(group.entry.price, params);
  for (const exitSignal of group.exits) {
    const pnlPerShare = exitSignal.metrics.pnl_per_share;
    if (!Number.isFinite(pnlPerShare)) return null;
    const rawExitFraction = exitSignal.metrics.exit_fraction ?? 1;
    const exitFraction = Number.isFinite(rawExitFraction) ? rawExitFraction : 1;
    pnl += pnlPerShare * exitFraction * quantity;
  }
  return roundSignalStat(pnl);
}

function buildStrategySignalPerformance(groups: StrategySignalGroup[]): StrategySignalPerformance {
  let totalPnl = 0;
  let grossProfit = 0;
  let grossLoss = 0;
  let closedGroupCount = 0;
  let winningGroupCount = 0;
  let losingGroupCount = 0;

  groups.forEach((group) => {
    if (group.exits.length === 0 || group.pnl === null) return;
    closedGroupCount += 1;
    const groupPnl = group.pnl;

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
    unit: "capital_weighted_position_pnl",
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

function strategyCapitalParams(params?: Record<string, StrategyParamValue>) {
  const initialCapital = Number(params?.initial_capital ?? DEFAULT_STRATEGY_INITIAL_CAPITAL);
  const entryCapitalRatio = Number(params?.entry_capital_ratio ?? DEFAULT_STRATEGY_ENTRY_CAPITAL_RATIO);
  return {
    initialCapital: Number.isFinite(initialCapital) ? initialCapital : DEFAULT_STRATEGY_INITIAL_CAPITAL,
    entryCapitalRatio: Number.isFinite(entryCapitalRatio) ? entryCapitalRatio : DEFAULT_STRATEGY_ENTRY_CAPITAL_RATIO
  };
}

function strategyPositionQuantity(entryPrice: number, params?: Record<string, StrategyParamValue>) {
  if (!Number.isFinite(entryPrice) || entryPrice <= 0) return 0;
  const { initialCapital, entryCapitalRatio } = strategyCapitalParams(params);
  return (initialCapital * entryCapitalRatio) / entryPrice;
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
  showReplayEma20?: boolean;
  showStrategyMarkers?: boolean;
  showTradeMarkers?: boolean;
  strategySignals?: StrategySignal[];
  strategyRun?: StrategySignalRun | null;
  scope?: { startMinute: number; endMinute: number };
  tradeMarkerVariant?: "compact" | "replay";
}) {
  const chartShellRef = useRef<HTMLDivElement | null>(null);
  const rawPriceClipId = useId();
  const priceClipId = `price-clip-${rawPriceClipId.replace(/:/g, "")}`;
  const [chartShellWidth, setChartShellWidth] = useState(0);
  const [strategySignalDetailOpen, setStrategySignalDetailOpen] = useState(false);
  const allBars = props.archive.bars;
  const strategySignals = props.strategySignals ?? props.strategyRun?.signals ?? [];
  const allowStrategySignalDetails = props.allowStrategySignalDetails ?? true;
  const showTradeMarkers = props.showTradeMarkers ?? true;
  const isReplayTradeMarkers = props.tradeMarkerVariant === "replay";
  const showStrategyMarkers = props.showStrategyMarkers ?? true;
  const visibleStrategySignals = showStrategyMarkers ? strategySignals : [];
  const fillScope = props.scope ?? chartMinuteScope(props.fills, visibleStrategySignals, minuteCandleEdgeBufferBars);
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
    [point.bb_middle, point.bb_upper, point.bb_lower, point.vwap, point.trend_ema, point.exit_ema].filter(
      (value): value is number => value !== null && value !== undefined
    )
  );
  const replayEma20Points = props.showReplayEma20 ? buildEma20OverlayPoints(allBars, bars) : [];
  const replayEma20Values = replayEma20Points.map((point) => point.value);
  const strategySignalExecutionPrices = visibleStrategySignals.map((signal) => signal.price);
  const fillPrices = props.fills.map((fill) => fill.price);
  const primaryPriceValues = stableChartPrimaryPrices(bars, [...fillPrices, ...strategySignalExecutionPrices]);
  const auxiliaryPriceValues = finitePriceValues([props.archive.vwap, ...strategyPriceValues, ...replayEma20Values]);
  const priceDomainValues = [
    ...primaryPriceValues,
    ...nearbyChartOverlayPrices(primaryPriceValues, auxiliaryPriceValues)
  ];
  const priceDomain = chartPriceDomain(priceDomainValues);
  const { minPrice, maxPrice, priceRange } = priceDomain;
  const isPriceVisible = (price: number | null | undefined) =>
    isFiniteNumber(price) && price >= minPrice && price <= maxPrice;
  const visibleArchiveVwap = isPriceVisible(props.archive.vwap) ? props.archive.vwap : null;
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
    replayEma20Points.length > 0 ? "含 EMA20" : null,
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
        <defs>
          <clipPath id={priceClipId}>
            <rect x={margin.left} y={margin.top} width={plotWidth} height={plotHeight} />
          </clipPath>
        </defs>
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
        <g clipPath={`url(#${priceClipId})`}>
          {visibleArchiveVwap !== null ? (
            <g>
              <line
                className="vwapLine"
                x1={margin.left}
                y1={yForPrice(visibleArchiveVwap)}
                x2={width - margin.right}
                y2={yForPrice(visibleArchiveVwap)}
              />
              <text className="vwapLabel" x={margin.left + 8} y={yForPrice(visibleArchiveVwap) - 6}>
                VWAP
              </text>
            </g>
          ) : null}
          {props.strategyRun ? (
            <g className="strategyOverlayLines">
              <path className="bbLine upper" d={indicatorLinePath(strategyLinePoints, "bb_upper", xForIndex, yForPrice, isPriceVisible)} />
              <path className="bbLine middle" d={indicatorLinePath(strategyLinePoints, "bb_middle", xForIndex, yForPrice, isPriceVisible)} />
              <path className="bbLine lower" d={indicatorLinePath(strategyLinePoints, "bb_lower", xForIndex, yForPrice, isPriceVisible)} />
              <path className="trendEmaLine" d={indicatorLinePath(strategyLinePoints, "trend_ema", xForIndex, yForPrice, isPriceVisible)} />
              <path className="exitEmaLine" d={indicatorLinePath(strategyLinePoints, "exit_ema", xForIndex, yForPrice, isPriceVisible)} />
              <path className="strategyVwapLine" d={indicatorLinePath(strategyLinePoints, "vwap", xForIndex, yForPrice, isPriceVisible)} />
            </g>
          ) : null}
          {replayEma20Points.length > 0 ? (
            <path className="replayEma20Line" d={priceLinePath(replayEma20Points, xForIndex, yForPrice, isPriceVisible)} />
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
        </g>
      </svg>
      <div className="chartLegend" aria-label="图例">
        <span className="legendItem up">上涨分钟</span>
        <span className="legendItem down">下跌分钟</span>
        {showTradeMarkers ? <span className={isReplayTradeMarkers ? "legendItem buy replay" : "legendItem buy"}>买点</span> : null}
        {showTradeMarkers ? <span className="legendItem sell">卖点</span> : null}
        {replayEma20Points.length > 0 ? <span className="legendItem replayEma">EMA20</span> : null}
        {props.strategyRun ? <span className="legendItem strategyLine">BB / EMA / 策略 VWAP</span> : null}
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
  const signalReplay = useMemo(
    () => buildStrategySignalGroups(props.signals, props.run.signal_groups ?? [], props.run.params),
    [props.signals, props.run.signal_groups, props.run.params]
  );
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
              <details className="signalGroupCard" key={group.id}>
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
                    <span className={`signalGroupPnl ${signalGroupPnlTone(group)}`}>
                      资金PNL {formatSignalGroupPnl(group)}
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
                      <dt>资金PNL</dt>
                      <dd className={signalGroupPnlTone(group)}>{formatSignalGroupPnl(group)}</dd>
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

                  <StrategySignalGroupIntervalChart archive={props.archive} group={group} run={props.run} />
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

function StrategySignalGroupIntervalChart(props: {
  archive: MarketMinuteArchive | null;
  group: StrategySignalGroup;
  run: StrategySignalRun | null;
}) {
  const groupScope = strategySignalGroupScope(props.group, 8);
  const groupRangeLabel = groupScope
    ? `${formatMinuteOfDay(groupScope.startMinute)}-${formatMinuteOfDay(groupScope.endMinute)}`
    : `${formatClock(props.group.openedAt)}-${props.group.closedAt ? formatClock(props.group.closedAt) : "未平仓"}`;

  if (!props.archive || props.archive.bars.length === 0 || !props.run || !groupScope) {
    return (
      <EmptyState
        icon={<AlertTriangle size={18} />}
        title="缺少区间蜡烛图"
        detail="当前开平仓组缺少可复用的归档分钟线或可定位信号时间，系统不会渲染假图表。"
      />
    );
  }

  return (
    <section className="signalGroupIntervalChart" aria-label="单组开平仓区间蜡烛图">
      <header className="signalGroupIntervalHeader">
        <div>
          <strong>开平仓区间蜡烛图</strong>
          <small>
            {formatClock(props.group.openedAt)}
            {props.group.closedAt ? ` -> ${formatClock(props.group.closedAt)}` : " -> 未平仓"} · {groupRangeLabel}
          </small>
        </div>
        <span className="statusPill info">{formatInteger(props.group.signals.length)} 个位置</span>
      </header>
      <MinuteCandleChart
        allowStrategySignalDetails={false}
        archive={props.archive}
        chartVariant="compact"
        fills={[]}
        scope={groupScope}
        showTradeMarkers={false}
        showStrategyMarkers
        strategyRun={props.run}
        strategySignals={props.group.signals}
      />
    </section>
  );
}

function StrategySignalOrderDetails(props: { group: StrategySignalGroup }) {
  return (
    <section className="signalOrderDetails" aria-label="订单明细">
      <div className="signalOrderDetailsHeader">
        <span>
          <ListChecks size={15} />
          订单明细
        </span>
        <small>{formatInteger(props.group.signals.length)} 个后端策略动作</small>
      </div>
      <div className="strategyOrderActionStrip" role="list" aria-label="策略动作摘要">
        {props.group.signals.map((signal, index) => (
          <span className="strategyOrderActionChip" key={`${signal.signal_id}-summary-${index}`} role="listitem">
            <span className={isEntrySignal(signal) ? "orderPhasePill entry" : "orderPhasePill exit"}>
              {isEntrySignal(signal) ? "Entry" : "Exit"}
            </span>
            <span>{formatClock(signal.timestamp)}</span>
            <strong>{decimalFormatter.format(signal.price)}</strong>
          </span>
        ))}
      </div>
      <div className="strategyOrderList" role="list">
        {props.group.signals.map((signal, index) => (
          <article
            className={isEntrySignal(signal) ? "strategyOrderItem entry" : "strategyOrderItem exit"}
            key={`${signal.signal_id}-${signal.action}-${signal.bar_index}-${index}`}
            role="listitem"
          >
            <div className="strategyOrderMain">
              <div className="strategyOrderLead">
                <span className={isEntrySignal(signal) ? "orderPhasePill entry" : "orderPhasePill exit"}>
                  {isEntrySignal(signal) ? "Entry" : "Exit"}
                </span>
                <strong>{formatStrategyAction(signal.action)}</strong>
              </div>
              <dl className="strategyOrderFacts">
                <div>
                  <dt>时间</dt>
                  <dd>{formatDateTime(signal.timestamp)}</dd>
                </div>
                <div>
                  <dt>方向</dt>
                  <dd>
                    <span className={signal.side === "LONG" ? "sidePill buy" : "sidePill sell"}>
                      {formatDirection(signal.side)}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>价格</dt>
                  <dd>{decimalFormatter.format(signal.price)}</dd>
                </div>
                <div>
                  <dt>止损</dt>
                  <dd>{formatNullable(signal.stop_loss_price)}</dd>
                </div>
                <div>
                  <dt>止盈</dt>
                  <dd>{formatNullable(signal.take_profit_price)}</dd>
                </div>
                <div>
                  <dt>关联</dt>
                  <dd className="orderTraceCell">
                    <span>bar #{formatInteger(signal.bar_index)}</span>
                    <span className="monoWrap">
                      {signal.linked_entry_signal_id ? shortHash(signal.linked_entry_signal_id) : "entry"}
                    </span>
                  </dd>
                </div>
              </dl>
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
              </div>
            </div>
            <details className="strategyMetricDetails">
              <summary>
                <span>
                  <ChevronDown className="strategyMetricChevron" size={14} />
                  数据明细
                </span>
                <small>{formatInteger(Object.entries(signal.metrics).length)} 项指标</small>
              </summary>
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
            </details>
          </article>
        ))}
      </div>
      <p className="signalOrderNote">这里展示的是策略 run 生成的复盘动作，不是券商订单，也不会修改 STP 成交事实。</p>
    </section>
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
        <dt>订单数</dt>
        <dd>{formatInteger(summary.fill_count)}</dd>
      </div>
      <div>
        <dt>股数</dt>
        <dd>{formatInteger(summary.traded_quantity)}</dd>
      </div>
      <div>
        <dt>PnL</dt>
        <dd className={summaryTone(summary.pnl)}>{formatPnl(summary.pnl)}</dd>
      </div>
    </dl>
  );
}

function LossReviewReasonChart(props: {
  onToggleKey: (key: string) => void;
  selectedKeys: string[];
  subtitle: string;
  summaries: LossReviewCategorySummary[];
  title: string;
}) {
  const totalCount = props.summaries.reduce((total, summary) => total + summary.count, 0);
  return (
    <section className="lossReviewReasonChart" aria-label={props.title}>
      <div className="lossReviewReasonChartHead">
        <div>
          <strong>{props.title}</strong>
          <small>{props.subtitle}</small>
        </div>
        <span className="sourcePill">{formatInteger(totalCount)} 笔</span>
      </div>
      <div className="lossReviewPieWrap">
        <div className="lossReviewPie" style={{ background: lossReviewPieGradient(props.summaries) }} aria-hidden="true">
          <span>{formatInteger(totalCount)}</span>
          <small>亏损单</small>
        </div>
        <div className="lossReviewPieLegend" aria-label={`${props.title}多选筛选`}>
          {props.summaries.map((summary, index) => (
            <label
              className={props.selectedKeys.includes(summary.key) ? "lossReviewFilterOption active" : "lossReviewFilterOption"}
              key={summary.key}
            >
              <input
                checked={props.selectedKeys.includes(summary.key)}
                onChange={() => props.onToggleKey(summary.key)}
                type="checkbox"
              />
              <span className="lossReviewLegendSwatch" style={{ backgroundColor: lossReviewPieColor(index) }} />
              <span className="lossReviewLegendText">
                <strong>{summary.label}</strong>
                <small>
                  {formatInteger(summary.count)} 笔 · {formatPercentValue(summary.share)} · {formatPnl(summary.totalPnl)}
                </small>
              </span>
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}

function LossReviewMarketRegimeMatrix(props: {
  concentrationLabel?: string;
  matrix: LossReviewMarketRegimeMatrix;
  note?: string;
  readOnly?: boolean;
  showTimeWindowPnlSummary?: boolean;
  sourceLabel?: string;
  subtitle?: string;
  summaryMode?: "concentration" | "max_loss" | "max_profit" | "pnl_extremes";
  title?: string;
}) {
  const topCell = props.matrix.topCell;
  const summaryMode = props.summaryMode ?? "concentration";
  const title = props.title ?? "热力时间矩阵";
  const subtitle = props.subtitle ?? "按美股常规盘五大微观结构窗口 × 开仓 ATR Multiple 定位亏损集中区";
  const sourceLabel = props.sourceLabel ?? "Market Regime Matrix";
  const concentrationLabel = props.concentrationLabel ?? "集中区";
  const note =
    props.note ??
    "时间窗口采用 09:30-16:00 五大美股日内微观结构划分；非常规时段只在存在盘前/盘后亏损时追加显示。纵轴使用后端从本地分钟线归档计算的开仓 1min K 振幅 / 前 20 根 ATR；缺足够历史分钟线时进入缺 ATR 证据，不用美元亏损回退。";
  return (
    <section className="lossReviewMatrixPanel" aria-label={`${title} Market Regime Matrix`}>
      <header className="lossReviewMatrixHeader">
        <div>
          <h3>{title}</h3>
          <p className="panelNote">{subtitle}</p>
        </div>
        <div className="lossReviewMatrixSummary">
          <span className="sourcePill">{sourceLabel}</span>
          {summaryMode === "max_loss" ? (
            <strong className={props.matrix.maxLossCell ? "bad" : "neutral"}>
              最大亏损区：{lossReviewMarketRegimeZoneLabel(props.matrix.maxLossCell)}
            </strong>
          ) : summaryMode === "max_profit" ? (
            <strong className={props.matrix.maxProfitCell ? "ok" : "neutral"}>
              最大盈利区：{lossReviewMarketRegimeZoneLabel(props.matrix.maxProfitCell)}
            </strong>
          ) : summaryMode === "pnl_extremes" ? (
            <>
              <strong className={props.matrix.maxProfitCell ? "ok" : "neutral"}>
                最大盈利区：{lossReviewMarketRegimeZoneLabel(props.matrix.maxProfitCell)}
              </strong>
              <small className={props.matrix.maxLossCell ? "bad" : "neutral"}>
                最大亏损区：{lossReviewMarketRegimeZoneLabel(props.matrix.maxLossCell)}
              </small>
            </>
          ) : topCell ? (
            <>
              <strong>
                {concentrationLabel}：{lossReviewTimeWindowLabel(topCell.timeWindowKey)} ×{" "}
                {lossReviewVolatilityRegimeLabel(topCell.volatilityKey)} · {formatPercentValue(topCell.lossShare)}
              </strong>
            </>
          ) : (
            <strong>暂无{concentrationLabel}</strong>
          )}
        </div>
      </header>
      <div className="lossReviewMatrixScroll">
        <div
          className="lossReviewMatrixGrid"
          role="grid"
          aria-label="亏损时间窗口与波动环境热力图"
          style={{
            gridTemplateColumns: `minmax(150px, 0.9fr) repeat(${props.matrix.timeWindows.length}, minmax(112px, 1fr))`
          }}
        >
          <div className="lossReviewMatrixCorner" />
          {props.matrix.timeWindows.map((window) => (
            <div className="lossReviewMatrixAxis lossReviewMatrixColumnHead" key={window.key}>
              <strong>{window.label}</strong>
              <small>{window.detail}</small>
            </div>
          ))}
          {props.matrix.rows.map((row) => (
            <Fragment key={row.key}>
              <div className="lossReviewMatrixAxis lossReviewMatrixRowHead">
                <strong>{row.label}</strong>
                <small>{row.detail}</small>
              </div>
              {row.cells.map((cell) => {
                const cellClassName = `lossReviewMatrixCell intensity${lossReviewMatrixIntensity(
                  cell,
                  props.matrix.maxLossAmount
                )}${cell.count === 0 ? " empty" : ""} readOnly`;
                const cellContent = (
                  <>
                    <strong>{formatInteger(cell.count)}</strong>
                    <span className={summaryTone(cell.totalPnl)}>{formatPnl(cell.totalPnl)}</span>
                    <small>
                      {formatPercentValue(cell.lossShare)} · 最大{" "}
                      {cell.largestLoss === null ? "N/A" : formatPnl(cell.largestLoss)}
                    </small>
                  </>
                );
                return (
                  <div
                    aria-label={`${lossReviewTimeWindowLabel(cell.timeWindowKey)} ${lossReviewVolatilityRegimeLabel(
                      cell.volatilityKey
                    )}`}
                    className={cellClassName}
                    key={cell.key}
                    role="gridcell"
                  >
                    {cellContent}
                  </div>
                );
              })}
            </Fragment>
          ))}
          {props.showTimeWindowPnlSummary ? (
            <>
              <div className="lossReviewMatrixAxis lossReviewMatrixRowHead lossReviewMatrixSummaryHead">
                <strong>X 轴汇总</strong>
                <small>收益合计</small>
              </div>
              {props.matrix.timeWindowSummaries.map((summary) => (
                <div
                  aria-label={`${lossReviewTimeWindowLabel(summary.key)} 收益合计 ${formatPnl(summary.totalPnl)}`}
                  className={`lossReviewMatrixColumnSummary${summary.count === 0 ? " empty" : ""}`}
                  key={`summary:${summary.key}`}
                  role="gridcell"
                >
                  <span>收益</span>
                  <strong className={summaryTone(summary.totalPnl)}>{formatPnl(summary.totalPnl)}</strong>
                  <small>{formatInteger(summary.count)} 笔</small>
                </div>
              ))}
            </>
          ) : null}
        </div>
      </div>
      <p className="lossReviewMatrixNote">{note}</p>
    </section>
  );
}

function LossReviewDrilldown(props: {
  onReplayTradeGroup: (group: TradeGroup) => Promise<void>;
  replayBusy: string | null;
  tradeGroups: TradeGroup[];
}) {
  const todayDateKey = useMemo(() => dateKeyFromDate(new Date()), []);
  const [lossReviewTimeFilterMode, setLossReviewTimeFilterMode] = useState<LossReviewTimeFilterMode>("all");
  const [customLossReviewStartDate, setCustomLossReviewStartDate] = useState(monthStartDateKey(todayDateKey));
  const [customLossReviewEndDate, setCustomLossReviewEndDate] = useState(todayDateKey);
  const [lossReviewPage, setLossReviewPage] = useState(1);
  const [lossReviewSortMode, setLossReviewSortMode] = useState<LossReviewSortMode>("time_desc");
  const [profitLossReviewMode, setProfitLossReviewMode] = useState<ProfitLossReviewMode>("loss");
  const [selectedPrimaryReasonKeys, setSelectedPrimaryReasonKeys] = useState<string[]>([]);
  const [selectedSecondaryReasonKeys, setSelectedSecondaryReasonKeys] = useState<string[]>([]);
  const reviewGroupLabel = profitLossReviewGroupLabel(profitLossReviewMode);
  const showReasonModules = profitLossReviewMode === "loss";
  const lossReviewTimeRange = useMemo(
    () =>
      lossReviewTimeFilterRange(
        lossReviewTimeFilterMode,
        customLossReviewStartDate,
        customLossReviewEndDate,
        todayDateKey
      ),
    [customLossReviewEndDate, customLossReviewStartDate, lossReviewTimeFilterMode, todayDateKey]
  );
  const modeTradeGroups = useMemo(
    () =>
      props.tradeGroups.filter((group) =>
        profitLossReviewMode === "profit" ? isClosedProfitTradeGroup(group) : isClosedLossTradeGroup(group)
      ),
    [profitLossReviewMode, props.tradeGroups]
  );
  const timeFilteredTradeGroups = useMemo(
    () =>
      modeTradeGroups.filter((group) =>
        lossReviewDateRangeIncludesGroup(group, lossReviewTimeRange.startDate, lossReviewTimeRange.endDate)
      ),
    [lossReviewTimeRange.endDate, lossReviewTimeRange.startDate, modeTradeGroups]
  );
  const primaryReasonSummaries = useMemo(
    () => (showReasonModules ? buildLossReviewPrimaryReasonSummaries(timeFilteredTradeGroups) : []),
    [showReasonModules, timeFilteredTradeGroups]
  );
  const marketRegimeMatrix = useMemo(
    () => buildLossReviewMarketRegimeMatrix(timeFilteredTradeGroups, profitLossReviewMode === "profit" ? "all" : "loss"),
    [profitLossReviewMode, timeFilteredTradeGroups]
  );
  const primaryFilteredTradeGroups = useMemo(
    () =>
      showReasonModules && selectedPrimaryReasonKeys.length > 0
        ? timeFilteredTradeGroups.filter((group) => selectedPrimaryReasonKeys.includes(lossReviewPrimaryReasonKey(group)))
        : timeFilteredTradeGroups,
    [selectedPrimaryReasonKeys, showReasonModules, timeFilteredTradeGroups]
  );
  const secondaryReasonSummaries = useMemo(
    () => (showReasonModules ? buildLossReviewSecondaryReasonSummaries(primaryFilteredTradeGroups) : []),
    [primaryFilteredTradeGroups, showReasonModules]
  );
  const availableSecondaryKeys = useMemo(
    () => new Set(secondaryReasonSummaries.map((summary) => summary.key)),
    [secondaryReasonSummaries]
  );
  const availableSecondaryKeySignature = secondaryReasonSummaries.map((summary) => summary.key).join("|");
  const filteredTradeGroups = useMemo(
    () =>
      showReasonModules && selectedSecondaryReasonKeys.length > 0
        ? primaryFilteredTradeGroups.filter((group) => selectedSecondaryReasonKeys.includes(lossReviewSecondaryReasonKey(group)))
        : primaryFilteredTradeGroups,
    [primaryFilteredTradeGroups, selectedSecondaryReasonKeys, showReasonModules]
  );
  const sortedTradeGroups = useMemo(
    () => [...filteredTradeGroups].sort((left, right) => sortLossReviewTradeGroups(left, right, lossReviewSortMode)),
    [filteredTradeGroups, lossReviewSortMode]
  );
  const totalPages = Math.max(1, Math.ceil(sortedTradeGroups.length / LOSS_REVIEW_PAGE_SIZE));
  const safePage = Math.min(lossReviewPage, totalPages);
  const pagedTradeGroups = sortedTradeGroups.slice(
    (safePage - 1) * LOSS_REVIEW_PAGE_SIZE,
    safePage * LOSS_REVIEW_PAGE_SIZE
  );
  const pageStart = sortedTradeGroups.length > 0 ? (safePage - 1) * LOSS_REVIEW_PAGE_SIZE + 1 : 0;
  const pageEnd = Math.min(safePage * LOSS_REVIEW_PAGE_SIZE, sortedTradeGroups.length);
  const filterSignature = [
    lossReviewTimeFilterMode,
    lossReviewTimeRange.startDate ?? "",
    lossReviewTimeRange.endDate ?? "",
    profitLossReviewMode,
    selectedPrimaryReasonKeys.join("|"),
    selectedSecondaryReasonKeys.join("|"),
    lossReviewSortMode,
    modeTradeGroups.length
  ].join("::");
  const timeReviewedTradeGroupCount = showReasonModules ? timeFilteredTradeGroups.filter((group) => group.review).length : 0;
  const timePendingTradeGroupCount = showReasonModules ? timeFilteredTradeGroups.length - timeReviewedTradeGroupCount : 0;
  const timeTotalReviewPnl = timeFilteredTradeGroups.reduce((total, group) => total + (group.pnl ?? 0), 0);
  const timeRangeLabel = lossReviewTimeRangeLabel(
    lossReviewTimeRange.startDate,
    lossReviewTimeRange.endDate,
    `全部${reviewGroupLabel}`
  );

  useEffect(() => {
    setSelectedSecondaryReasonKeys((current) => current.filter((key) => availableSecondaryKeys.has(key)));
  }, [availableSecondaryKeySignature, availableSecondaryKeys]);

  useEffect(() => {
    setSelectedPrimaryReasonKeys([]);
    setSelectedSecondaryReasonKeys([]);
  }, [profitLossReviewMode]);

  useEffect(() => {
    setLossReviewPage(1);
  }, [filterSignature]);

  useEffect(() => {
    if (lossReviewPage > totalPages) {
      setLossReviewPage(totalPages);
    }
  }, [lossReviewPage, totalPages]);

  function togglePrimaryReasonKey(key: string) {
    setSelectedPrimaryReasonKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
    );
  }

  function toggleSecondaryReasonKey(key: string) {
    setSelectedSecondaryReasonKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key]
    );
  }

  return (
    <div className="lossReviewDrilldown">
      <header className="lossReviewDrillHeader">
        <div>
          <h2>
            <AlertTriangle size={18} />
            盈亏复盘
          </h2>
          <p className="panelNote">默认查看亏损交易组；切到盈利单时只展示热力矩阵和订单明细</p>
        </div>
        <span className="sourcePill">Review Journal</span>
      </header>

      <div className="lossReviewTimeFilter" aria-label="盈亏复盘全局时间筛选">
        <div className="lossReviewTimeFilterButtons" role="group" aria-label="全局时间筛选">
          {(["all", "month", "week", "custom"] as LossReviewTimeFilterMode[]).map((mode) => (
            <button
              aria-pressed={lossReviewTimeFilterMode === mode}
              className={lossReviewTimeFilterMode === mode ? "smallButton active" : "smallButton"}
              key={mode}
              onClick={() => setLossReviewTimeFilterMode(mode)}
              type="button"
            >
              {lossReviewTimeFilterLabels[mode]}
            </button>
          ))}
        </div>
        {lossReviewTimeFilterMode === "custom" ? (
          <div className="lossReviewCustomRange">
            <label>
              <span>开始</span>
              <input
                onChange={(event) => setCustomLossReviewStartDate(event.currentTarget.value)}
                type="date"
                value={customLossReviewStartDate}
              />
            </label>
            <label>
              <span>结束</span>
              <input
                onChange={(event) => setCustomLossReviewEndDate(event.currentTarget.value)}
                type="date"
                value={customLossReviewEndDate}
              />
            </label>
          </div>
        ) : null}
        <div className="profitLossReviewModeSwitch" role="radiogroup" aria-label="盈亏单筛选">
          {(["profit", "loss"] as ProfitLossReviewMode[]).map((mode) => (
            <label
              className={profitLossReviewMode === mode ? "profitLossReviewModeOption active" : "profitLossReviewModeOption"}
              key={mode}
            >
              <input
                checked={profitLossReviewMode === mode}
                name="profitLossReviewMode"
                onChange={() => setProfitLossReviewMode(mode)}
                type="radio"
                value={mode}
              />
              <span>{profitLossReviewModeLabels[mode]}</span>
            </label>
          ))}
        </div>
      </div>

      <dl className="compactFacts lossReviewSummaryGrid lossReviewSummaryRow">
        <div>
          <dt>{reviewGroupLabel}</dt>
          <dd>{formatInteger(timeFilteredTradeGroups.length)}</dd>
        </div>
        <div>
          <dt>{showReasonModules ? "已复盘" : "原因记录"}</dt>
          <dd>{showReasonModules ? formatInteger(timeReviewedTradeGroupCount) : "不适用"}</dd>
        </div>
        <div>
          <dt>{showReasonModules ? "待复盘" : "原因筛选"}</dt>
          <dd>{showReasonModules ? formatInteger(timePendingTradeGroupCount) : "空"}</dd>
        </div>
        <div>
          <dt>{profitLossReviewMode === "profit" ? "盈利合计" : "亏损合计"}</dt>
          <dd className={summaryTone(timeTotalReviewPnl)}>{formatPnl(timeTotalReviewPnl)}</dd>
        </div>
      </dl>

      {modeTradeGroups.length > 0 ? (
        <>
          <LossReviewMarketRegimeMatrix
            matrix={marketRegimeMatrix}
            readOnly
            sourceLabel={reviewGroupLabel}
            subtitle={`按美股常规盘五大微观结构窗口 × 开仓 ATR Multiple 查看${reviewGroupLabel}分布`}
            summaryMode={profitLossReviewMode === "profit" ? "max_profit" : "max_loss"}
            title={`${reviewGroupLabel}热力时间矩阵`}
          />
          <div className="lossReviewDrillLayout">
            <div className="lossReviewCategoryPanel" aria-label="原因分类汇总">
            <div className="drillDetailHead">
              <div>
                <strong>原因分类汇总</strong>
                <small>{showReasonModules ? "一级原因与二级原因联动多选筛选" : "盈利单不写入亏损原因，原因模块保持为空"}</small>
              </div>
              <span className="sourcePill">
                {showReasonModules
                  ? `${formatInteger(selectedPrimaryReasonKeys.length + selectedSecondaryReasonKeys.length)} 个筛选`
                  : "空"}
              </span>
            </div>
            {showReasonModules ? (
              <>
                <LossReviewReasonChart
                  onToggleKey={togglePrimaryReasonKey}
                  selectedKeys={selectedPrimaryReasonKeys}
                  subtitle="按一级原因统计；未选择时显示全部"
                  summaries={primaryReasonSummaries}
                  title="一级原因"
                />
                <LossReviewReasonChart
                  onToggleKey={toggleSecondaryReasonKey}
                  selectedKeys={selectedSecondaryReasonKeys}
                  subtitle="随一级原因筛选联动；未选择时显示全部"
                  summaries={secondaryReasonSummaries}
                  title="二级原因"
                />
              </>
            ) : (
              <EmptyState
                icon={<CircleSlash size={18} />}
                title="暂无原因分类"
                detail="仅亏损单维护 Review Journal 归因；盈利单不会写入亏损原因。"
              />
            )}
            </div>

            <div className="lossReviewListPanel" aria-label={`${reviewGroupLabel}列表明细`}>
            <div className="drillDetailHead">
              <div>
                <strong>{reviewGroupLabel}列表</strong>
                <small>
                  默认按时间倒序，每页 20 笔
                  {showReasonModules ? "；可叠加原因筛选" : "；盈利视图不叠加原因筛选"}
                </small>
              </div>
              <span className="sourcePill">
                {formatInteger(pageStart)}-{formatInteger(pageEnd)} / {formatInteger(sortedTradeGroups.length)} 笔
              </span>
            </div>
            <div className="lossReviewListToolbar">
              <div className="lossReviewSortControl" role="group" aria-label="亏损单排序">
                <button
                  aria-pressed={lossReviewSortMode === "time_desc"}
                  className={lossReviewSortMode === "time_desc" ? "smallButton active" : "smallButton"}
                  onClick={() => setLossReviewSortMode("time_desc")}
                  type="button"
                >
                  按时间倒序
                </button>
                <button
                  aria-pressed={lossReviewSortMode === "loss_desc"}
                  className={lossReviewSortMode === "loss_desc" ? "smallButton active" : "smallButton"}
                  onClick={() => setLossReviewSortMode("loss_desc")}
                  type="button"
                >
                  {profitLossReviewMode === "profit" ? "按盈利金额倒序" : "按亏损金额倒序"}
                </button>
              </div>
              <span className="toolbarMeta">20 笔/页</span>
            </div>
            {pagedTradeGroups.length > 0 ? (
              <div className="lossReviewTradeList">
              {pagedTradeGroups.map((group) => (
                <article className="lossReviewTradeItem" key={group.trade_group_id}>
                  <div className="lossReviewTradeMain">
                    <strong>
                      {tradeGroupReviewDate(group)} · {group.symbol}
                    </strong>
                    <small>
                      {formatDirection(group.direction)} · {formatInteger(group.total_quantity)} 股 ·{" "}
                      {formatHoldingMinutes(group.holding_minutes)}
                    </small>
                  </div>
                  <dl className="compactFacts lossReviewTradeFacts">
                    <div>
                      <dt>PnL</dt>
                      <dd className={group.pnl === null ? undefined : summaryTone(group.pnl)}>{group.pnl === null ? "N/A" : formatPnl(group.pnl)}</dd>
                    </div>
                    {showReasonModules ? (
                      <>
                        <div>
                          <dt>复盘</dt>
                          <dd>{group.review?.reason_category_label ?? "待复盘"}</dd>
                        </div>
                        <div>
                          <dt>原因</dt>
                          <dd>{group.review?.reason_label ?? "未分类"}</dd>
                        </div>
                      </>
                    ) : (
                      <>
                        <div>
                          <dt>结果</dt>
                          <dd>盈利</dd>
                        </div>
                        <div>
                          <dt>复盘原因</dt>
                          <dd>不适用</dd>
                        </div>
                      </>
                    )}
                  </dl>
                  <button
                    className="linkButton"
                    disabled={props.replayBusy === group.trade_group_id}
                    onClick={() => void props.onReplayTradeGroup(group)}
                    type="button"
                  >
                    <Play size={14} />
                    {props.replayBusy === group.trade_group_id ? "读取中" : "下钻复盘"}
                  </button>
                </article>
              ))}
              </div>
            ) : (
              <EmptyState
                icon={<CircleSlash size={18} />}
                title={`没有符合筛选的${reviewGroupLabel}`}
                detail={showReasonModules ? "调整时间范围、一级原因或二级原因筛选后再查看列表" : "调整时间范围或切回亏损单后再查看列表"}
              />
            )}
            <div className="lossReviewPagination" aria-label="亏损单分页">
              <button
                className="smallButton"
                disabled={safePage <= 1}
                onClick={() => setLossReviewPage((current) => Math.max(1, current - 1))}
                type="button"
              >
                上一页
              </button>
              <span>
                第 {formatInteger(safePage)} / {formatInteger(totalPages)} 页
              </span>
              <button
                className="smallButton"
                disabled={safePage >= totalPages}
                onClick={() => setLossReviewPage((current) => Math.min(totalPages, current + 1))}
                type="button"
              >
                下一页
              </button>
            </div>
            </div>
          </div>
        </>
      ) : (
        <EmptyState icon={<CheckCircle2 size={18} />} title={`暂无${reviewGroupLabel}`} detail={`当前 committed 交易组中没有已闭合${reviewGroupLabel}`} />
      )}
    </div>
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

function formatShareQuantity(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N/A";
  const roundedInteger = Math.round(value);
  if (Math.abs(value - roundedInteger) < 0.000001) return integerFormatter.format(roundedInteger);
  return decimalFormatter.format(value);
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

function formatStrategyParamByKey(key: string, value: StrategyParamValue | undefined) {
  if (key === "entry_capital_ratio") {
    if (typeof value !== "number" || !Number.isFinite(value)) return "N/A";
    return formatPercentValue(value);
  }
  if (key === "initial_capital") {
    if (typeof value !== "number" || !Number.isFinite(value)) return "N/A";
    return integerFormatter.format(value);
  }
  return formatStrategyParam(value);
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

function formatProfitFactorMetric(value: number | null, totalPnl: number, closedGroupCount: number) {
  if (value !== null && Number.isFinite(value)) return decimalFormatter.format(value);
  if (closedGroupCount > 0 && totalPnl > 0) return "∞";
  return "N/A";
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
  return `${formatInteger(drawdown.bar_count)} 根分钟线`;
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

function formatLiveOrderIntent(intent: LiveStrategySignalResult["order_intent"]) {
  return {
    BUY: "BUY",
    SELL: "SELL",
    HOLD: "HOLD"
  }[intent];
}

function liveOrderIntentForAction(action: StrategySignalAction): Exclude<LiveStrategySignalResult["order_intent"], "HOLD"> {
  return action === "ENTRY_LONG" || action === "EXIT_SHORT" ? "BUY" : "SELL";
}

function isLiveEntryOrderAction(action: StrategySignalAction) {
  return action === "ENTRY_LONG" || action === "ENTRY_SHORT";
}

function formatLiveOrderOperationType(action: StrategySignalAction) {
  return action === "ENTRY_LONG" || action === "ENTRY_SHORT" ? "开仓" : "关仓";
}

function formatLiveStatusDetail(result: LiveStrategySignalResult) {
  if (result.status === "completed" && result.signal) {
    return `${formatDateTime(result.signal.timestamp)} bar ${formatInteger(result.signal.bar_index)}`;
  }
  if (result.status === "no_signal") {
    return "最新分钟线未触发策略开平仓条件";
  }
  return result.failure_reason ?? liveSignalStatusMeta[result.status].label;
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
  return `订单数 ${formatInteger(summary.fill_count)} · 股数 ${formatInteger(summary.traded_quantity)} · PnL ${formatPnl(summary.pnl)}`;
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

function formatSignalGroupPnl(group: StrategySignalGroup) {
  return group.pnl === null ? "N/A" : formatPnl(group.pnl);
}

function signalGroupPnlTone(group: StrategySignalGroup) {
  return group.pnl === null ? "statNeutral" : signalStatTone(group.pnl);
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
  if (param?.key) return formatStrategyParamByKey(param.key, value);
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

function chartMinuteScope(fills: ChartFill[], signals: StrategySignal[], bufferMinutes = 0) {
  const minutes = [
    ...fills.map((fill) => clockMinute(fill.filled_at)),
    ...signals.map((signal) => clockMinute(signal.timestamp))
  ].filter((minute): minute is number => minute !== null);
  if (minutes.length === 0) return null;
  return {
    startMinute: Math.max(0, Math.min(...minutes) - bufferMinutes),
    endMinute: Math.min(24 * 60 - 1, Math.max(...minutes) + bufferMinutes)
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

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function finitePriceValues(values: Array<number | null | undefined>) {
  return values.filter(isFiniteNumber);
}

function stableChartPrimaryPrices(bars: MarketMinuteArchive["bars"], markerPrices: number[]) {
  const bodyAndMarkerValues = finitePriceValues([
    ...bars.flatMap((bar) => [bar.open, bar.close]),
    ...markerPrices
  ]);
  const wickValues = finitePriceValues(bars.flatMap((bar) => [bar.high, bar.low]));
  return [...bodyAndMarkerValues, ...nearbyChartOverlayPrices(bodyAndMarkerValues, wickValues)];
}

function nearbyChartOverlayPrices(primaryValues: number[], auxiliaryValues: number[]) {
  if (primaryValues.length === 0) return auxiliaryValues;

  const rawMin = Math.min(...primaryValues);
  const rawMax = Math.max(...primaryValues);
  const center = (rawMin + rawMax) / 2;
  const baseRange = Math.max(rawMax - rawMin, Math.abs(center) * 0.001, 0.01);
  const allowance = Math.max(baseRange * 2, Math.abs(center) * 0.004, 0.25);
  return auxiliaryValues.filter((value) => value >= rawMin - allowance && value <= rawMax + allowance);
}

function chartPriceDomain(values: number[]) {
  const finiteValues = finitePriceValues(values);
  if (finiteValues.length === 0) {
    return { minPrice: 0, maxPrice: 1, priceRange: 1 };
  }

  const rawMin = Math.min(...finiteValues);
  const rawMax = Math.max(...finiteValues);
  const center = (rawMin + rawMax) / 2;
  const minimumRange = Math.max(Math.abs(center) * 0.001, 0.01);
  const domainRange = Math.max(rawMax - rawMin, minimumRange);
  const centeredMin = center - domainRange / 2;
  const centeredMax = center + domainRange / 2;
  const pricePadding = Math.max(domainRange * 0.06, 0.01);
  const minPrice = centeredMin - pricePadding;
  const maxPrice = centeredMax + pricePadding;
  return { minPrice, maxPrice, priceRange: Math.max(maxPrice - minPrice, 0.01) };
}

function tradeMarkerPath(x: number, y: number, side: ChartFill["side"]) {
  const size = 10;
  if (side === "BUY") {
    return `M ${x} ${y} L ${x - size} ${y + size * 2} L ${x + size} ${y + size * 2} Z`;
  }
  return `M ${x} ${y} L ${x - size} ${y - size * 2} L ${x + size} ${y - size * 2} Z`;
}

function buildEma20OverlayPoints(allBars: MarketMinuteArchive["bars"], visibleBars: MarketMinuteArchive["bars"]) {
  const period = 20;
  if (allBars.length < period || visibleBars.length === 0) return [];

  const multiplier = 2 / (period + 1);
  const closeWindow: number[] = [];
  const emaByTimestamp = new Map<string, number>();
  let currentEma: number | null = null;

  allBars.forEach((bar, index) => {
    closeWindow.push(bar.close);
    if (closeWindow.length > period) closeWindow.shift();
    if (index === period - 1) {
      currentEma = closeWindow.reduce((sum, close) => sum + close, 0) / period;
    } else if (index >= period && currentEma !== null) {
      currentEma = bar.close * multiplier + currentEma * (1 - multiplier);
    }
    if (currentEma !== null) {
      emaByTimestamp.set(bar.timestamp, currentEma);
    }
  });

  return visibleBars
    .map((bar, visibleIndex) => {
      const value = emaByTimestamp.get(bar.timestamp);
      return value === undefined ? null : { value, visibleIndex };
    })
    .filter((point): point is { value: number; visibleIndex: number } => point !== null);
}

function priceLinePath(
  points: Array<{ visibleIndex: number; value: number }>,
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
  isPriceVisible: (price: number | null | undefined) => boolean = isFiniteNumber
) {
  return points
    .filter((point) => isPriceVisible(point.value))
    .map((point, index) => {
      const command = index === 0 ? "M" : "L";
      return `${command} ${xForIndex(point.visibleIndex)} ${yForPrice(point.value)}`;
    })
    .join(" ");
}

function indicatorLinePath(
  points: VisibleIndicatorPoint[],
  key: "bb_upper" | "bb_middle" | "bb_lower" | "vwap" | "trend_ema" | "exit_ema",
  xForIndex: (index: number) => number,
  yForPrice: (price: number) => number,
  isPriceVisible: (price: number | null | undefined) => boolean = isFiniteNumber
) {
  return points
    .filter((point) => isPriceVisible(point[key]))
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
