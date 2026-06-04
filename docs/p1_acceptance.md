# P1 Acceptance Evidence

## Trade Replay Groups

| Acceptance | DB Evidence | API Evidence | UI Read Model | Status |
| --- | --- | --- | --- | --- |
| 成交记录按开仓至清仓配对 | committed `fills` 去重 read model | `/api/trade-groups` 返回 closed/open group 和组内 fills | 成交记录主表显示交易组，不再按单笔 fill 作为主行 | PASS |
| long/short、加仓和部分平仓可复现 | 同账号同标的按成交序列维护仓位 | closed group 返回 direction、quantity、PnL、holding minutes | 表格显示多头/空头、数量、PnL 和持仓时间 | PASS |
| 未清仓不进入已实现 KPI | open group 不计入 realized groups | daily summary 只汇总 closed trade groups | UI 显示未清仓，不生成正常评分 | PASS |
| 交易组 ID 不泄露原始幂等 key | 原始 `fills.idempotency_key` 只在内部参与 hash | `trade_group_id` 仅返回 `tg_` hash | UI 只展示 group/fill trace，不展示原始 key | PASS |
| Replay 弹层使用整日分钟线归档 | `market_minute_archives.bars_json` 和 `bars_hash` | replay 前读取或创建 symbol/day archive | 弹层缩放到开仓至清仓并显示成交量、VWAP、高低点和 hash | PASS |
| 规则评价可审计 | archive metrics 和 group fills 只读输入 | evaluation 返回 `trade_eval_intraday_v1`、score、grade、factors | 弹层显示评分、优势、风险和因子明细 | PASS |

Negative acceptance:

- 没有 archive 或 bars 时，评价返回 `insufficient_market_data`。
- provider failed、missing、timezone conflict 不能渲染正常评分或成功图表。
- open group 返回 `not_applicable_open_trade`，不能进入胜率、盈亏比或已实现 PnL。
- Replay 只引用行情 archive，不改写 `fills.price`、`fills.quantity` 或 `fills.filled_at`。

## Yahoo 离线分钟线归档

| Acceptance | DB Evidence | API Evidence | Status |
| --- | --- | --- | --- |
| 从 committed fills 推导交易日和标的 | `fills` read model 分组为 `trade_date + symbol` | `POST /api/market-data/yahoo-minute-archive` 返回 `target_count` 和 `source_fill_count` | PASS |
| Yahoo 分钟线归档可追溯 | `market_minute_archives.bars_json`、`bars_hash`、`archive_version` | `GET /api/market-data/minute-archives` 返回 `archive_id`、bars 和 hash | PASS |
| 重复归档幂等 | `provider + symbol + trade_date + requested_start + requested_end` 唯一 | 第二次归档复用同一 `archive_id` | PASS |
| provider failure 可见 | `data_status=provider_failed` 且 provider attempt 为 `failed` | API 返回 `failure_reason`，不渲染为成功 | PASS |
| STP 成交事实不被行情覆盖 | `fills.price`、`quantity`、`filled_at` 不变 | 归档响应只返回行情 archive，不返回修改后的 fill | PASS |
| 复盘页按日期和标的看分钟蜡烛 | `market_minute_archives.trade_date + symbol` 作为 read model key | 页面读取 `GET /api/market-data/minute-archives` 并叠加 committed fills | PASS |
| 分钟图按首尾成交缩放 | `fills.filled_at` 决定 UI 可视时间范围 | 归档 `bars_json` 不被裁剪，只在前端显示第一笔到最后一笔成交区间 | PASS |

Negative acceptance:

- 没有 committed fills 的日期返回 `no_targets`，不写 provider attempt。
- Yahoo chart error 或网络失败保存为 `provider_failed`。
- 缺分钟线保存为 `missing`，不能用空图表示成功。
- 复盘页没有 symbol 或没有分钟线归档时显示空状态，不能渲染成正常蜡烛图。

本文档记录 P1 Market Context Replay 与盘前 Watchlist 的验收口径。当前仓库已移除 P0.5，P1 直接接在 P0-only 基线上，因此本次 SQLite schema 从 v1 升到 v2。

## Scope

- 本次阶段切片：P1。
- Canonical source：
  - 成交事实仍来自 `fills`，只使用 committed STP import。
  - 行情上下文来自 provider bars，经 `market_context_snapshots` 固化。
  - Watchlist 来自 provider summary，经 `watchlist_runs` 和 `watchlist_items` 固化。
- Read model：
  - `/api/fills/{fill_id}/market-context`
  - `/api/market-context/{snapshot_id}`
  - `/api/watchlist?date=YYYY-MM-DD`
- Artifact source：
  - `tests/fixtures/stp_sample.tsv`
  - fake market provider fixtures in tests
  - P1 API payloads

## Idempotency

- STP import batch：`file_hash`。
- Market context snapshot：`fill_id + provider + requested_start + requested_end`。
- Provider attempt：每次 provider request 单独记录。
- Watchlist run：`trade_date + provider + rules_version`。
- Watchlist item：`run_id + symbol`。

## Parser And Mapper Versions

- P1 不修改 STP parser。
- `parser_version` 和 `field_mapper_version` 继续由 P0 import rows、orders、fills 保存。
- Market context replay 只引用 committed fill，不改写成交价格、数量、时间或 parser 结果。

## Acceptance Matrix

| Acceptance | DB Evidence | API Evidence | UI Read Model | Status |
| --- | --- | --- | --- | --- |
| 每个 snapshot 可追溯到 fill/window/hash | `market_context_snapshots.fill_id`, `requested_start`, `requested_end`, `bars_hash` | replay API returns `fill_id`, `requested_start`, `requested_end`, `bars_hash` | context panel shows status, bars count, hash | PASS |
| provider failure 不画空图冒充成功 | snapshot `data_status=provider_failed` and `failure_reason` | replay API returns `provider_failed` | context panel shows 行情获取失败 | PASS |
| 缺数据和部分数据可见 | snapshot `data_status` supports `missing`, `partial` | fake provider tests cover both | context panel shows 缺数据/部分数据 | PASS |
| VWAP/高低点只来自 provider bars | `vwap`, `day_high`, `day_low` saved in snapshot | API returns saved values | UI only displays API values | PASS |
| 时区冲突可诊断 | snapshot `data_status=timezone_conflict` | replay API returns `failure_reason` | context panel shows 时区冲突 | PASS |
| Watchlist 每个 symbol 有原因和指标 | `reason_codes_json`, `metrics_json` | watchlist API returns `reason_codes`, `metrics`, `metrics_hash` | watchlist panel shows reason chips and metrics | PASS |
| Watchlist 重跑幂等 | `watchlist_runs` unique contract, items replaced on force | PUT/generate returns same `run_id` | UI 重跑 keeps one run model | PASS |
| STP 成交真相源不被行情覆盖 | no writes to `fills` during replay | replay returns snapshot only | fills table still displays STP values | PASS |
| 日期+标的蜡烛复盘 | `market_minute_archives` 保存 symbol/day bars 和 hash | archive API returns selected symbol/day bars | chart overlays BUY/SELL markers from committed fills | PASS |

## Negative Acceptance

- fill 不存在时 replay 返回 `fill_not_found`。
- snapshot 不存在时读取返回 `market_context_not_found`。
- 日期格式错误返回 422。
- provider failed 时写入 provider attempt，并生成失败状态 snapshot 或 watchlist run。
- watchlist 零结果时返回 completed run with zero items，不补假 symbol。

## Remaining Risks

- Live Futu adapter 目前是可替换占位，CI 和本地自动验收使用 fake provider。
- P1 没有实现实时行情长连接、声音告警、自动下单、期权链或全市场 tick 扫描。
- 当前蜡烛图读取已归档 Yahoo 分钟线；未归档 symbol 需要先触发归档或运行离线脚本。
