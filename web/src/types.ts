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

export interface DailySummary {
  date: string;
  fill_count: number;
  trade_group_count: number;
  traded_quantity: number;
  pnl: number;
  win_rate: number;
  profit_factor: number | null;
  quarantine_row_count: number;
  source: "committed_fills_only";
}
