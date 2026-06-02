# Architecture

本文档记录 Grit Day Trading Platform 的系统事实源、数据流、存储合同和失败语义。当前版本是文档基线，后续实现若改变事实源或验收标准，必须先更新本文档。

## 系统目标

系统要把日内交易从分散的计划、成交、行情和复盘文本收束成一个可追溯闭环：

```text
Trade Plan
  -> Planned Intent
  -> STP Fill Match
  -> Execution Deviation
  -> Review Journal

STP TXT
  -> Upload Batch
  -> Raw Evidence Ledger
  -> Parser + Field Mapper
  -> Quarantine invalid rows
  -> Normalized Orders / Fills
  -> Match Trade Plan
  -> Review Dashboard

Futu Market Data
  -> Daily / Minute Bars
  -> Watchlist Engine
  -> Market Context Replay
  -> Signal Engine later
```

## 外部系统边界

### Sterling Trader Pro

STP 指 Sterling Trader Pro。首版不直接调用 STP COM 下单，也不把 STP 当实时运行时。STP TXT 是订单、委托和成交的唯一真相源。

### 富途

富途只提供行情和 watchlist 相关数据。富途可以解释成交当时的市场上下文，但不能修正、覆盖或补写 STP 成交。

### Web 应用

Web 应用负责上传、解析、证据账本展示、计划录入、匹配分析、市场上下文复盘和复盘结论管理。

## 事实源矩阵

| 对象 | Canonical Source | Read Model | 关键证据 | 缺失语义 |
| --- | --- | --- | --- | --- |
| Upload Batch | `import_batches` | 导入历史列表 | `file_hash`、文件名、上传时间、parser version | 批次失败必须可见 |
| Raw Evidence | `import_rows` | 原始行详情 | 原始行文本、行号、row hash、字段映射版本 | 不能删除后假装导入成功 |
| Quarantine | `quarantine_rows` | 导入异常中心 | 失败字段、失败原因、修复建议 | 失败行不得进入 fills |
| Orders | `orders` | 订单列表和复盘摘要 | 原始账号、canonical 账号、order id、状态 | 缺 order id 时必须进入 quarantine |
| Fills | `fills` | 成交列表和复盘摘要 | execution id、成交时间、数量、价格、来源 raw row | 缺 execution id 时必须使用 fallback key 并显示 |
| Trade Plan | `trade_plans` | 计划列表和计划详情 | 创建时间、symbol、方向、setup、入场理由、止损、目标、失效条件、计划仓位 | 未匹配不等于失败 |
| Plan Match | `trade_plan_fill_matches` | 执行偏差分析 | match rule、置信度、人工覆盖标记 | 多计划冲突必须人工确认 |
| Market Context | `market_context_snapshots` | 复盘图表和上下文面板 | provider、请求窗口、bars hash、数据状态 | 缺行情显示 `缺数据` |
| Review Journal | `trade_reviews` | 标签和复盘结论 | 标签、错误分类、结论、更新时间 | 主观结论不得覆盖成交 |

## P0 数据合同

### `import_batches`

建议字段：

- `id`
- `file_name`
- `file_hash`
- `uploaded_at`
- `parser_version`
- `field_mapper_version`
- `source_timezone`
- `row_count`
- `parsed_row_count`
- `quarantine_row_count`
- `status`
- `status_reason`

`file_hash` 是批次级幂等 key。同一文件重复导入应返回已有批次，不得重复写入 orders 或 fills。

### `import_rows`

建议字段：

- `id`
- `batch_id`
- `row_number`
- `raw_line`
- `raw_line_sha256`
- `parser_version`
- `field_mapper_version`
- `parsed_payload_json`
- `source_account_raw`
- `source_account_canonical`
- `normalized_order_id`
- `normalized_fill_id`
- `row_status`

原始行必须保留。parser 升级只能追加 replay 或新解析结果，不能污染历史记录。

### `quarantine_rows`

建议字段：

- `id`
- `batch_id`
- `evidence_row_id`
- `failed_field`
- `failure_code`
- `failure_message`
- `repair_hint`
- `review_status`

导入失败不能静默。UI 必须展示失败字段和修复建议。

### `orders`

建议字段：

- `id`
- `account_raw`
- `account_canonical`
- `symbol`
- `side`
- `order_id`
- `order_status`
- `submitted_at`
- `cancelled_at`
- `source_batch_id`
- `source_evidence_row_id`
- `idempotency_key`

账号 canonicalization 固定为 `strip().upper()`，同时保留 `account_raw`。

### `fills`

建议字段：

- `id`
- `account_raw`
- `account_canonical`
- `symbol`
- `side`
- `order_id`
- `execution_id`
- `filled_at`
- `quantity`
- `price`
- `liquidity`
- `source_batch_id`
- `source_evidence_row_id`
- `idempotency_key`

`execution_id` 存在时优先参与幂等。缺失时允许 fallback 到账号、symbol、方向、成交时间、数量、价格、order id 和 raw row hash 的组合，但 UI 必须标注该成交使用 fallback key。

## P0.5 Trade Plan 合同

### `trade_plans`

建议字段：

- `id`
- `created_at`
- `updated_at`
- `account_scope`
- `symbol`
- `direction`
- `setup`
- `entry_reason`
- `planned_entry`
- `stop_loss`
- `target_price`
- `invalid_condition`
- `planned_quantity`
- `status`
- `notes`

Trade Plan 是交易意图真相源。成交导入后可以产生匹配、偏差和复盘结论，但不能改写计划原文。

### `trade_plan_fill_matches`

建议字段：

- `id`
- `trade_plan_id`
- `fill_id`
- `match_rule`
- `match_confidence`
- `matched_at`
- `manual_override`
- `override_reason`

自动匹配规则按以下优先级执行：

- 账号、symbol、方向和计划有效时间窗口完全匹配。
- 一笔计划可匹配多笔成交。
- 多笔计划同 symbol 且时间窗口重叠时进入冲突队列。
- 未匹配成交必须保留在复盘入口。
- 超计划仓位、方向不一致、止损外成交必须进入执行偏差分析。

## P1 Market Context Replay 合同

### `market_context_snapshots`

建议字段：

- `id`
- `fill_id`
- `provider`
- `symbol`
- `requested_start`
- `requested_end`
- `provider_timezone`
- `bar_count`
- `bars_hash`
- `vwap`
- `day_high`
- `day_low`
- `volume_context`
- `data_status`
- `failure_reason`

`data_status` 至少包含：

- `available`
- `partial`
- `missing`
- `provider_failed`
- `timezone_conflict`

行情缺失必须显示 `缺数据`。不得用空数组、默认价格或静态图表伪装成功。

## 幂等规则

- 批次幂等：`file_hash`。
- 原始行幂等：`batch_id + row_number + raw_line_sha256`。
- 订单幂等：优先 `account_canonical + order_id`，缺字段时标注 fallback。
- 成交幂等：优先 `account_canonical + execution_id`，缺字段时标注 fallback。
- replay 幂等：同一 evidence row 在不同 parser version 下可以产生新 replay 结果，但必须能对比旧结果。

## 失败语义

- 上传空文件：批次状态为失败，显示原因。
- 未知列：进入字段映射诊断，不应静默丢列。
- 缺关键字段：行进入 quarantine。
- 部分成交：保留每笔成交，同时在 order 汇总中展示累计数量。
- 取消单：保留订单状态，不伪造成成交。
- 跨日成交：按成交时间和交易日同时建索引。
- 富途接口失败：market context 状态为 `provider_failed`。
- 分钟线缺失：market context 状态为 `missing` 或 `partial`。
- 时区错位：market context 状态为 `timezone_conflict`，禁止自动平移后当作成功。

## 安全边界

- 首版没有自动下单路径。
- 信号引擎只允许做提醒和复盘解释。
- 不保存券商密码或交易凭据。
- STP TXT 原始文件和原始行属于敏感交易证据，日志、截图和 changelog 不应暴露原文。
- 对外展示文档不得包含真实账号、本机路径、原始 payload 或内部调试 id。

## 阶段实施顺序

1. P0 `Contract Skeleton`：schema、parser fixture、证据账本、quarantine、orders/fills、基础导入测试。
2. P0 `Execution Core`：真实 TXT 导入、幂等、parser replay、导入异常 UI。
3. P0.5：Trade Plan、自动匹配、执行偏差分析。
4. P1：富途行情接入、market context snapshot、图表化复盘。
5. P2：watchlist 信号提醒。
6. P3：信号质量和规则反馈。
