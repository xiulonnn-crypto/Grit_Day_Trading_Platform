export type ImportBatchStatus = "uploaded" | "parsing" | "committed" | "failed" | "retry_requested";

export interface ImportBatch {
  id: string;
  batch_id: string;
  file_name: string;
  file_hash: string;
  uploaded_at: string;
  parser_version: string;
  field_mapper_version: string;
  status: ImportBatchStatus;
  status_reason: string | null;
  row_count: number;
  accepted_rows: number;
  quarantined_rows: number;
  duplicate?: boolean;
}

export interface QuarantineRow {
  id: string;
  quarantine_id: string;
  batch_id: string;
  import_row_id: string;
  raw_line_number: number;
  raw_text: string;
  raw_line: string;
  failed_field: string;
  reason_code: string;
  reason: string;
  repair_hint: string;
  review_status: string;
}

export interface FillRow {
  id: string;
  fill_id: string;
  account_raw: string;
  account_canonical: string;
  symbol: string;
  side: "BUY" | "SELL";
  order_id: string;
  execution_id: string | null;
  filled_at: string;
  quantity: number;
  price: number;
  source_batch_id: string;
  source_import_row_id: string;
  raw_line_number: number;
  parser_version: string;
  field_mapper_version: string;
  uses_fallback_idempotency_key: boolean;
}

export interface TradeGroupFill {
  id: string;
  fill_id: string;
  account_raw: string;
  account_canonical: string;
  symbol: string;
  side: "BUY" | "SELL";
  order_id: string;
  execution_id: string | null;
  filled_at: string;
  quantity: number;
  price: number;
  source_batch_id: string;
  source_import_row_id: string;
  raw_line_number: number;
  parser_version: string;
  field_mapper_version: string;
  uses_fallback_idempotency_key: boolean;
}

export interface TradeEvaluationFactor {
  name: string;
  label: string;
  score: number;
  max_score: number;
  detail: string;
}

export interface TradeEvaluation {
  model_version: "trade_eval_intraday_v1";
  evaluation_status: "available" | "insufficient_market_data" | "not_applicable_open_trade";
  score: number | null;
  grade: "A" | "B" | "C" | "D" | null;
  summary: string;
  strengths: string[];
  risks: string[];
  factors: TradeEvaluationFactor[];
}

export interface TradeGroupPositionDrawdown {
  status: "available" | "insufficient_market_data" | "not_applicable_open_trade";
  max_drawdown: number | null;
  max_drawdown_per_share: number | null;
  source: "market_minute_archives" | null;
  source_archive_id: string | null;
  bars_hash: string | null;
  bar_count: number;
  window_start: string | null;
  window_end: string | null;
  window_high: number | null;
  window_low: number | null;
  worst_price: number | null;
  price_basis: "minute_high_low" | null;
}

export interface TradeGroup {
  id: string;
  trade_group_id: string;
  account_raw: string;
  account_canonical: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  status: "closed" | "open";
  opened_at: string;
  closed_at: string | null;
  holding_minutes: number | null;
  fill_count: number;
  total_quantity: number;
  entry_quantity: number;
  exit_quantity: number;
  avg_entry_price: number | null;
  avg_exit_price: number | null;
  pnl: number | null;
  source: "committed_fills_only";
  parser_versions: string[];
  field_mapper_versions: string[];
  source_batch_ids: string[];
  raw_line_numbers: number[];
  fills: TradeGroupFill[];
  position_drawdown: TradeGroupPositionDrawdown;
  evaluation: TradeEvaluation;
}

export interface DailySummary {
  date: string | null;
  symbol: string | null;
  fill_count: number;
  trade_group_count: number;
  open_trade_group_count: number;
  traded_quantity: number;
  pnl: number;
  win_rate: number;
  profit_factor: number | null;
  expected_value_per_trade: number | null;
  net_profit_per_share: number | null;
  max_single_day_drawdown: number;
  quarantine_row_count: number;
  source: "committed_fills_only";
}

export type ReviewSummary = DailySummary;

export interface ReviewSummaryGroup extends ReviewSummary {
  group_by: "date" | "symbol";
  group_key: string;
  group_label: string;
}

export type MarketDataStatus = "available" | "partial" | "missing" | "provider_failed" | "timezone_conflict";

export interface MarketBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface VolumeContext {
  bar_count: number;
  expected_bar_count: number;
  total_volume: number;
  avg_bar_volume: number;
}

export interface MarketContextSnapshot {
  id: string;
  snapshot_id: string;
  fill_id: string;
  provider: "fake" | "futu" | string;
  symbol: string;
  requested_start: string;
  requested_end: string;
  provider_timezone: string;
  bar_count: number;
  bars_hash: string;
  bars_json: string;
  bars: MarketBar[];
  vwap: number | null;
  day_high: number | null;
  day_low: number | null;
  volume_context: VolumeContext;
  data_status: MarketDataStatus;
  failure_reason: string | null;
  created_at: string;
}

export interface MarketMinuteArchiveVolumeContext {
  bar_count: number;
  requested_start: string;
  requested_end: string;
  total_volume: number;
  avg_bar_volume: number;
}

export interface MarketMinuteArchive {
  id: string;
  archive_id: string;
  provider: "yahoo" | "futu" | string;
  symbol: string;
  trade_date: string;
  requested_start: string;
  requested_end: string;
  provider_timezone: string;
  bar_count: number;
  bars_hash: string;
  bars_json: string;
  bars: MarketBar[];
  vwap: number | null;
  day_high: number | null;
  day_low: number | null;
  volume_context: MarketMinuteArchiveVolumeContext;
  data_status: MarketDataStatus;
  failure_reason: string | null;
  source_fill_count: number;
  archive_version: string;
  idempotency_key: string;
  created_at: string;
}

export interface YahooMinuteArchiveResult {
  status: "no_targets" | "completed";
  provider: "yahoo";
  archive_version: string;
  trade_date: string | null;
  symbol?: string;
  window_trading_days?: number;
  requested_trade_dates?: string[];
  target_count: number;
  stored_count: number;
  available_count: number;
  non_available_count: number;
  provider_failed_count: number;
  selected_symbol_available_count?: number;
  items: MarketMinuteArchive[];
}

export type WatchlistRunStatus = "not_generated" | "completed" | "failed";

export interface WatchlistItem {
  id: string;
  item_id: string;
  run_id: string;
  trade_date: string;
  symbol: string;
  rank: number;
  reason_codes_json: string;
  reason_codes: string[];
  metrics_json: string;
  metrics: Record<string, number>;
  metrics_hash: string;
  source: string;
  status: "included" | "missing" | "provider_failed";
}

export interface WatchlistRun {
  id: string | null;
  run_id: string | null;
  trade_date: string;
  provider: string | null;
  rules_version: string;
  status: WatchlistRunStatus;
  item_count: number;
  failure_reason: string | null;
  created_at: string | null;
  items: WatchlistItem[];
}

export interface StrategyTemplateParam {
  key: string;
  label: string;
  type: "integer" | "number" | "enum";
  min?: number;
  max?: number;
  options?: { value: string; label: string }[];
}

export interface StrategyTemplate {
  template_key: "bb_squeeze_breakout_v1" | "institutional_liquidity_sweep_v1" | "momentum_mean_reversion_v1";
  template_version: string;
  name: string;
  description: string;
  default_params: Record<string, number | string>;
  param_schema: StrategyTemplateParam[];
}

export interface StrategyConfig {
  id: string;
  strategy_id: string;
  name: string;
  template_key: string;
  template_version: string;
  enabled: boolean;
  params_json: string;
  params_hash: string;
  params: Record<string, number | string>;
  created_at: string;
  updated_at: string;
}

export type StrategyRunStatus =
  | "completed"
  | "missing_archive"
  | "non_available_archive"
  | "insufficient_bars"
  | "strategy_disabled"
  | "failed";

export type StrategySignalAction = "ENTRY_LONG" | "EXIT_LONG" | "ENTRY_SHORT" | "EXIT_SHORT";

export interface StrategyIndicatorPoint {
  timestamp: string;
  bar_index: number;
  close: number;
  bb_middle: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  bandwidth: number | null;
  exit_ema: number | null;
  vwap: number | null;
  rsi: number | null;
  avg_volume: number | null;
  relative_volume: number | null;
  local_low?: number | null;
  local_high?: number | null;
  first_five_high?: number | null;
  first_five_low?: number | null;
  lower_shadow_ratio?: number | null;
  upper_shadow_ratio?: number | null;
  time_window?: number | null;
  atr?: number | null;
  adx?: number | null;
  market_regime?: string | null;
  mean_reversion_enabled?: number | null;
  momentum_long?: number | null;
  momentum_short?: number | null;
  qqq_close?: number | null;
  qqq_vwap?: number | null;
  smh_close?: number | null;
  smh_vwap?: number | null;
}

export interface StrategySignal {
  id: string;
  signal_id: string;
  run_id: string;
  timestamp: string;
  bar_index: number;
  side: "LONG" | "SHORT";
  action: StrategySignalAction;
  price: number;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  linked_entry_signal_id: string | null;
  reason_codes_json: string;
  reason_codes: string[];
  metrics_json: string;
  metrics: Record<string, number>;
}

export interface StrategySignalPerformance {
  unit: "price_delta_weighted_by_exit_fraction";
  total_pnl: number;
  gross_profit: number;
  gross_loss: number;
  closed_group_count: number;
  winning_group_count: number;
  losing_group_count: number;
  win_rate: number;
  profit_factor: number | null;
}

export interface StrategySignalRun {
  id: string;
  run_id: string;
  strategy_id: string;
  provider: "yahoo" | string;
  symbol: string;
  trade_date: string;
  source_archive_id: string | null;
  bars_hash: string;
  params_hash: string;
  indicator_engine_version: string;
  status: StrategyRunStatus;
  failure_reason: string | null;
  indicator_series_json: string;
  indicator_series: StrategyIndicatorPoint[];
  indicator_hash: string;
  signal_count: number;
  idempotency_key: string;
  created_at: string;
  strategy: {
    strategy_id: string;
    name: string;
    template_key: string;
    template_version: string;
    params: Record<string, number | string>;
  };
  signals: StrategySignal[];
  signal_performance?: StrategySignalPerformance;
}

export type StrategyTestBatchStatus = "completed" | "insufficient_archive_coverage" | "strategy_disabled" | "failed";

export interface StrategyTestDayResult {
  id: string;
  day_result_id: string;
  batch_id: string;
  trade_date: string;
  source_archive_id: string | null;
  bars_hash: string;
  strategy_run_id: string | null;
  status: StrategyRunStatus;
  failure_reason: string | null;
  signal_count: number;
  total_pnl: number;
  win_rate: number;
  profit_factor: number | null;
  closed_group_count: number;
  indicator_hash: string;
}

export interface StrategyTestBatch {
  id: string;
  batch_id: string;
  strategy_id: string;
  provider: "yahoo" | string;
  symbol: string;
  end_date: string;
  window_trading_days: number;
  archive_scope_hash: string;
  params_json: string;
  params_hash: string;
  params: Record<string, number | string>;
  template_version: string;
  indicator_engine_version: string;
  status: StrategyTestBatchStatus;
  failure_reason: string | null;
  day_count: number;
  available_day_count: number;
  completed_day_count: number;
  signal_count: number;
  total_pnl: number;
  win_rate: number;
  profit_factor: number | null;
  max_drawdown: number;
  coverage_ratio: number;
  idempotency_key: string;
  created_at: string;
  strategy: {
    strategy_id: string;
    name: string;
    template_key: string;
  };
  day_results: StrategyTestDayResult[];
}

export type StrategyOptimizationStatus = StrategyTestBatchStatus;
export type StrategyOptimizationCandidateStatus =
  | "eligible"
  | "no_signals"
  | "failed"
  | "insufficient_archive_coverage"
  | "strategy_disabled";

export interface StrategyOptimizationCandidate {
  id: string;
  candidate_id: string;
  optimization_run_id: string;
  rank: number;
  params_json: string;
  params_hash: string;
  params: Record<string, number | string>;
  day_results_json: string;
  day_results: StrategyTestDayResult[];
  status: StrategyOptimizationCandidateStatus;
  failure_reason: string | null;
  total_pnl: number;
  win_rate: number;
  profit_factor: number | null;
  max_drawdown: number;
  closed_group_count: number;
  coverage_ratio: number;
  stability_score: number;
  created_at: string;
}

export interface StrategyOptimizationRun {
  id: string;
  optimization_id: string;
  strategy_id: string;
  provider: "yahoo" | string;
  symbol: string;
  end_date: string;
  window_trading_days: number;
  archive_scope_hash: string;
  search_space_json: string;
  search_space: Record<string, Array<number | string>>;
  search_space_hash: string;
  objective: "stable_profitability_v1" | string;
  template_version: string;
  indicator_engine_version: string;
  status: StrategyOptimizationStatus;
  failure_reason: string | null;
  candidate_count: number;
  eligible_candidate_count: number;
  best_candidate_id: string | null;
  best_params_hash: string | null;
  best_stability_score: number | null;
  idempotency_key: string;
  created_at: string;
  strategy: {
    strategy_id: string;
    name: string;
    template_key: string;
  };
  candidates: StrategyOptimizationCandidate[];
}
