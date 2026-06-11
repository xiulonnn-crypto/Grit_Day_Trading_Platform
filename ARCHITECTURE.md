# Architecture

## P3 Review Journal 亏损复盘边界

- Canonical source: `trade_reviews` 保存用户对已平仓亏损交易组的主观复盘原因，原因分类只允许 `opening_signal`、`closing_signal` 和 `misoperation`。
- Read model: `GET /api/trade-groups` 在每个交易组上返回 `review`；`PUT /api/trade-groups/{trade_group_id}/review` 只允许保存 closed 且 PnL 小于 0 的交易组复盘。
- UI read model: 「成交记录」行只保留 Trade Replay 入口和复盘状态摘要，不提供单独「复盘」操作按钮；「仅看亏损单」过滤当前 `GET /api/trade-groups` read model 中 closed 且 PnL 小于 0 的交易组，并用交易组 `source_batch_ids`、`raw_line_numbers`、账号和标的匹配 `GET /api/fills` read model，让上方分钟蜡烛图只显示对应买卖点；「下钻复盘」外层提供「数据下钻」和「亏损复盘」，亏损复盘读取全部日期的轻量 trade group read model，只展示 closed 且 PnL 小于 0 的时间范围统计、热力时间矩阵、一级/二级原因分类汇总和明细入口；全部、本月、本周和特定时间段只作为前端只读筛选投影，不改变交易组、复盘记录或 STP 成交事实；热力时间矩阵按美股常规盘五大微观结构窗口和 `position_drawdown.entry_atr_multiple` 分桶，该倍数由本地分钟线归档计算开仓 1min K 振幅 / 前 20 根 ATR；数据下钻矩阵只读展示最大盈利区和最大亏损区，不筛选日期/标的列表；亏损复盘矩阵只读展示最大亏损区，不筛选亏损明细；复盘原因表单展示在 Trade Replay 弹层订单明细模块下方，并只读取交易组 `review` read model。
- Artifact source: 复盘记录保存 `trade_group_id`、交易组 PnL、parser versions、field mapper versions、source batch ids 和 raw line numbers 作为只读追溯证据。
- Idempotency key: `trade_review_v1 + trade_group_id`，同一交易组重复保存会更新 Review Journal 记录，不新增重复复盘。
- Failure contract: 盈利、持平、未清仓或不存在的交易组不能写入亏损复盘；不支持的原因分类或原因码返回失败，不落入主观复盘账本。
- Boundary: Review Journal 只能解释亏损原因，不能覆盖 STP TXT、committed fills、行情归档或策略 run artifact。

## P2/P3 Live Signal Panel Boundary
- UI read model: 「下单信号」模块展开 live-signal 返回的 `signals[]`，只展示真实 BUY/SELL 订单级字段，包括 symbol、order intent、operation type、signal price、order quantity、timestamp 和 bar index；`order_quantity` 由后端按 `initial_capital * entry_capital_ratio / entry_price` 计算，平仓单按后端 `exit_fraction` 折算；`operation type` 由后端 `strategy action` 派生为「开仓」或「关仓」，只有开仓单展示 stop loss / take profit，关仓单不展示止损止盈并展示后端 reason codes 映射的原因标签，`order_intent=HOLD`、失败状态或空 `signals[]` 不进入该模块。
- Evidence boundary: HOLD、失败状态、完整 strategy action、strategy latest version、config version、provider、bar count、reason codes、metrics、hash 和 idempotency key 属于「原因与证据」模块，不进入「下单信号」模块。
- Failure contract: provider failure、策略未开启、缺行情或无信号时可以显示状态和失败原因，但不能伪造订单明细。

## P2/P3 Live Monitor Extension
- Canonical source: Yahoo、Futu 或 Fake 实时行情 provider 返回的分钟线；当前 UI 默认 Yahoo。每个被选中的 symbol 都独立调用 live-signal read model，STP TXT 和 committed fills 仍是成交真相源且不被覆盖。
- Read model: 「实时交易」监控只读取 `POST /api/strategies/{strategy_id}/live-signal` 返回的只读结果数组；前端只负责轮询和展示，不计算指标、原因码或开平仓条件。
- Artifact source: 每个 symbol 的 `bars_hash`、`params_hash`、`indicator_hash`、`provider_attempt_status`、`reason_codes`、`metrics`、`position_quantity`、`order_quantity` 和 `idempotency_key` 是监控证据；监控不写入 `strategy_signal_runs` 或 `strategy_signals`。
- Idempotency: 单个 symbol 仍沿用 `live_signal_preview + strategy_id + provider + symbol + requested_start + requested_end + bars_hash + params_hash + template_version + indicator_engine_version`，多标的监控只是这些单 symbol 结果的 UI 聚合。
- Failure contract: 切换策略、标的、provider 或窗口会停止当前监控并作废旧请求；策略未开启、provider failure、缺分钟线、非 available 行情或分钟线不足不得渲染成功信号。
- Runtime readiness: Windows 登录入口除了检查 API health，还必须检查前端 UI 指纹、前端代理 `/openapi.json` 中的当前后端路由合同，并在短暂可用后复查；旧前端进程或指向旧后端的代理不能被当成当前 read model。

## P2/P3 Real-Time Trading Signal Preview 事实源

- Canonical source: Futu、Yahoo 或 Fake 实时行情 provider 返回的目标标的分钟线；Momentum Mean Reversion 还读取同窗口 QQQ/SMH provider 分钟线作为动能上下文。STP TXT 和 committed fills 仍是成交真相源，不被实时信号覆盖。
- Read model: `POST /api/strategies/{strategy_id}/live-signal` 返回策略、当前配置版本、最新策略版本、标的、provider、provider attempt 状态、最新分钟线、后端策略引擎信号、原因码、`bars_hash`、`params_hash`、`indicator_hash` 和只读 idempotency key。
- UI read model: 「实时交易」tab 只展示 API 返回的 BUY/SELL/HOLD、最新策略版本、信号价、止损、止盈、原因码和证据 hash；前端不计算 BB、RSI、VWAP、relative volume、ADX、ATR、EMA 或开平仓条件。
- Artifact source: `live_provider_minute_bars` response 中的 `bars_hash`、`indicator_hash`、`reason_codes`、`metrics`、`provider_attempt_status` 和 `idempotency_key` 是本次预览证据；该切片不写入 `strategy_signal_runs` 或 `strategy_signals`。
- Idempotency key: `live_signal_preview + strategy_id + provider + symbol + requested_start + requested_end + bars_hash + params_hash + template_version + indicator_engine_version`。
- Failure contract: 策略未开启返回 `strategy_disabled` 和 HOLD；provider failure、缺分钟线、非 available 行情、分钟线不足或引擎失败不得渲染成功信号。
- Boundary: 实时信号只做人工下单前的策略提示，不触发自动下单，不创建券商订单，不修改 STP 成交价格、数量或时间。

## P2 Strategy Configuration And Historical Signal Replay 事实源

- Canonical source: `strategy_configs` 保存策略模板实例、启停状态、当前模板版本、参数 JSON 和 `params_hash`；`strategy_config_history` 保存模板版本和参数 hash 的历史变更原因。
- Read model: `GET /api/strategies` 返回策略配置；`GET /api/strategies/{strategy_id}/history` 返回配置历史和可回退参数快照；`POST /api/strategies/{strategy_id}/history/{history_id}/rollback` 显式恢复历史参数快照；`GET /api/strategy-runs` 默认返回轻量策略 run 摘要；`GET /api/strategy-runs/{run_id}` 返回单条 run 的完整指标序列、开平仓信号和按 entry/exit 配对的 `signal_groups` PnL；`GET /api/strategy-test-runs` 和 `GET /api/strategy-optimizations` 返回批量测试和优化研究结果。
- UI read model: 复盘页只展示 API 返回的策略指标和信号，不在前端计算 BB、RSI、VWAP、相对成交量、20 EMA、9 EMA、绝对带宽、ADX、ATR、market regime、H2/L2 回调或开平仓条件。
- Artifact source: `strategy_config_history.previous_template_version`、`next_template_version`、`previous_params_hash`、`next_params_hash`、`previous_params_json`、`next_params_json`、`change_reason`、`source_history_id`、`strategy_signal_runs.source_archive_id`、`bars_hash`、`params_json`、`indicator_series_json`、`indicator_hash`、`strategy_signals.reason_codes_json`、`metrics_json`、`strategy_test_batches.archive_scope_hash` 和 optimization candidate `day_results_json` 是策略复盘和研究证据；`params_json` 中的 `initial_capital` 和 `entry_capital_ratio` 是策略资金 PnL 的 artifact source。
- Idempotency key: `strategy_id + provider + symbol + trade_date + source_archive_id + bars_hash + params_hash + template_version + indicator_engine_version`。
- Strategy test idempotency key: `strategy_id + provider + symbol + end_date + window_trading_days + archive_scope_hash + params_hash + template_version + indicator_engine_version`。
- Strategy optimization idempotency key: `strategy_id + provider + symbol_scope + end_date + window_trading_days + archive_scope_hash + search_space_hash + objective + template_version + indicator_engine_version`；`symbol_scope` 是单标的或输入标的组的 canonical 逗号分隔值。
- BB Squeeze engine: `strategy_indicator_engine_v3` 逐 bar 计算 BB、VWAP、RSI、ATR、relative volume、9 EMA 出场缓冲和绝对带宽；entry 必须通过相对收缩分位和最小绝对带宽，止损和第一目标按 ATR 倍数标准化，exit 不因单纯回到布林外轨内触发。
- Institutional Liquidity Sweep engine: `strategy_indicator_engine_liquidity_sweep_v1` 逐 bar 计算 VWAP、局部高低点、前 5 分钟高低、BB 中轨、相对成交量和影线占比；entry 必须扫破过去局部高低点后收回，exit 只按历史 high/low 建模 `OCO_Immediate` 止损、BB 中轨或 1.5:1 被动止盈，以及最长持仓 K 数退出。
- Momentum Mean Reversion engine: `strategy_indicator_engine_momentum_mean_reversion_v2` 逐 bar 计算目标标的 BB、目标 VWAP、ADX、ATR、QQQ/SMH 各自 VWAP 方向和反转形态；只在美东 11:30 至 13:30 执行，多头要求 QQQ 与 SMH 同时在 VWAP 上方，空头要求二者同时在 VWAP 下方；ADX 高于趋势阈值时均值回归熔断并生成 0 信号，ADX 回到震荡阈值以下才重新激活；硬止损按入场价加减 ATR 倍数计算，中轨部分止盈后将剩余仓位止损上移到 break-even。
- Trend Rider engine: `strategy_indicator_engine_trend_rider_v1` 逐 bar 计算 VWAP、20 EMA、9 EMA、EMA slope、opening range、relative volume 和 Always In 趋势方向；entry 必须先出现强趋势突破，再等待 H2/L2 二级回调、回踩/反抽 20 EMA、回调缩量和收回/跌回 20 EMA；exit 只按硬止损或 9 EMA 收盘破位，不保存静态止盈目标。
- Range Fader engine: `strategy_indicator_engine_range_fader_v2` 逐 bar 计算震荡区间上下沿、中轴线、顶部/底部 25% 边缘区、20 EMA 钝化、EMA 穿越次数和 VWAP；entry 必须先确认区间 regime，再在边缘假突破反转 K 后按下一根 K 开盘入场；exit 先按区间中轴线做部分止盈并把剩余仓位止损上移到 break-even，再以对侧区间边缘作为最终目标，硬止损、break-even 止损或最长持仓 K 数仍按历史 high/low 建模。
- Failure contract: 缺归档、非 available 归档、分钟线不足、策略未开启或策略引擎失败必须保存为 run 状态，不能渲染为成功信号。
- Strategy testing failure contract: 策略测试只读取截至日期最近 30 天（自然日）内的本地 `market_minute_archives`，不向更早交易日补足 30 个交易日；窗口内没有归档时保存 `insufficient_archive_coverage`；非 available 归档和缺 Momentum context 进入逐日失败结果；策略测试和优化都不自动拉行情。
- Data preparation boundary: 策略测试页和 `scripts/archive-local-minute-db.py` 可以显式调用 Yahoo 分钟线归档，为手工输入标的或标的组准备最近自然日窗口；该动作只写入 `market_minute_archives` 和 provider attempt，不会由策略 run 自动触发。
- Multi-ticker screener boundary: 策略测试页可把逗号分隔的多个 symbol 编组成扫描流；每个 symbol 仍分别写入自己的 `strategy_test_batches`，策略优化按输入标的组写入一个全局 `strategy_optimization_runs`、组合 `archive_scope_hash` 和候选证据，前端只展示 API read model，不计算指标或信号。
- Momentum Mean Reversion failure contract: 缺目标标的、QQQ 或 SMH 任一已归档分钟线时保存 `missing_archive`；任一归档不是 `available` 时保存 `non_available_archive`，不能用缺失动能过滤渲染成功信号。
- Boundary: 策略信号只做复盘和提示，不能修改 STP TXT 成交事实，不能触发自动下单；被动止盈和 `OCO_Immediate` 只在历史 run 中按 high/low 触达建模为出场信号，不向券商或 STP 发送真实限价单。

## P1 Yahoo 离线分钟线归档事实源

- Canonical source: `market_minute_archives`。基础目标集合来自已提交 `fills` 的 `trade_date + symbol`；STP TXT 上传成功后会按本批 committed fills 的 `source_batch_id` 推导日期和标的并补缺本地归档；启用 Momentum Mean Reversion 时，同日 QQQ/SMH 作为策略上下文目标加入手工/批量归档队列；外部数据源来自 Yahoo Finance 1 分钟线响应。
- Read model: `GET /api/market-data/minute-archives` 返回已归档的 symbol/day 分钟线、hash、VWAP、当日高低、成交量上下文和 provider 状态。
- UI read model: 复盘页以 `trade_date + symbol` 选择 archive，把第一笔到最后一笔 committed `fills` 覆盖的 `bars` 画成分钟蜡烛图，并只用 committed `fills` 叠加买卖点。
- Artifact source: `bars_json` 和 `bars_hash` 是可复查归档内容；`market_data_provider_attempts.request_type='archive_minute_bars'` 记录每次 Yahoo provider 尝试。
- Idempotency key: `provider + symbol + trade_date + requested_start + requested_end`，重复归档默认复用已有记录，`force=true` 才刷新。
- Upload archive boundary: `POST /api/imports/stp-txt` 只在导入状态为 committed 时触发本批成交的缺失分钟线归档；该动作只写 `market_minute_archives` 和 `market_data_provider_attempts`，并把归档结果附在上传响应中，不修改 `import_batches`、`orders` 或 `fills` 的事实字段。
- Manual research window: `POST /api/market-data/yahoo-minute-archive` 支持 `symbol + date + window_trading_days`，会按最近自然日生成 symbol/day 归档目标；`window_trading_days` 是兼容字段名，当前业务语义为最近 N 天；`archive_yahoo_minutes_for_symbol_group_window` 和 `scripts/archive-local-minute-db.py` 用同一幂等口径为 MU/NVDA/SPY 等研究标的组批量写入本地 SQLite 归档；启用 Momentum Mean Reversion 时同窗口补 QQQ/SMH 上下文归档。
- Failure contract: Yahoo 缺数据、网络失败、chart error 或时区冲突必须保存为 `missing`、`provider_failed`、`partial` 或 `timezone_conflict`，不能渲染为成功归档。
- Boundary: Yahoo 分钟线只能补充行情上下文，不能覆盖 STP TXT 的成交价格、成交数量、成交时间或订单事实。

## P1 Trade Replay Groups 事实源

- Canonical source: 交易组只从 committed `fills` read model 构建。STP TXT 的成交时间、价格、数量、方向和证据行仍是交易事实源。
- Read model: `GET /api/trade-groups?date=YYYY-MM-DD&account=&symbol=&include_details=false` 按 `account_canonical + symbol` 和成交时间把仓位从开仓到清仓配成交易组，首屏可返回不含组内 fills 和评价因子明细的轻量列表；`date` 可省略以返回全部日期的轻量交易组，供亏损复盘和数据下钻时间范围矩阵读取。数据下钻的时间筛选、统计指标、热力时间矩阵和日期/标的列表都是从轻量 trade group read model 派生的前端只读投影；矩阵按美股常规盘五大微观结构窗口和 `position_drawdown.entry_atr_multiple` 分桶只读展示全部订单分布、最大盈利区和最大亏损区，不筛选下方下钻列表，不写入行情归档、交易组或 Review Journal。replay 详情使用 `include_details=true` 读取完整 fills、已实现 PnL、持仓最大回撤、开仓 ATR Multiple 和评分证据。`GET /api/review/summary` 与 `GET /api/review/summary-groups` 只聚合 committed fills 和轻量 closed trade groups，用于全局、日期和标的下钻汇总，并返回单笔期望值、每股净收益和持仓最大回撤。复盘摘要不得触发完整交易评价模型；完整评价只属于交易列表和 replay 详情。
- Artifact source: 交易 replay 弹层只读取本地 `market_minute_archives.bars_json` 和 `bars_hash` 作为行情图表来源，打开弹层不会自动触发 provider 拉取；持仓最大回撤只读取开仓到清仓窗口内的分钟 high/low、archive id 和 bars hash；评分只读取 archive 中的 VWAP、当日高低、成交量上下文和 provider 状态。
- Idempotency key: `trade_group_id = tg_ + sha256(trade_group_v1 + account + symbol + direction + open/close time + hashed fill idempotency signatures)`。API 不暴露原始 fill idempotency key。
- Evaluation model: `trade_eval_intraday_v1` 是只读规则评分模型。评分维度包括 VWAP 执行质量、趋势配合、成交量确认、MFE/MAE、清仓效率和 PnL 结果。
- Failure contract: `provider_failed`、`missing`、`timezone_conflict` 或无 bars 时，持仓最大回撤和评价返回 `insufficient_market_data`，不能生成正常评分或成功图表；open group 返回 `not_applicable_open_trade`。
- Drilldown failure contract: 没有 committed fills 时，全局汇总返回 0、分组列表为空；UI 不渲染假日期、假标的或成功复盘。
- Boundary: Trade Group 是 read model，不新增持久化表，不回写 `fills`，不覆盖 parser version、field mapper version 或原始证据链。

本文档记录 Grit Day Trading Platform 的系统事实源、数据流、存储合同和失败语义。当前版本是文档基线，后续实现若改变事实源或验收标准，必须先更新本文档。

## 系统目标

系统要把日内交易从分散的计划、成交、行情和复盘文本收束成一个可追溯闭环：

```text
STP TXT
  -> Upload Batch
  -> Raw Evidence Ledger
  -> Parser + Field Mapper
  -> Quarantine invalid rows
  -> Normalized Orders / Fills
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

Web 应用负责上传、解析、证据账本展示、市场上下文复盘和复盘结论管理。

## 事实源矩阵

| 对象 | Canonical Source | Read Model | 关键证据 | 缺失语义 |
| --- | --- | --- | --- | --- |
| Upload Batch | `import_batches` | 导入历史列表 | `file_hash`、文件名、上传时间、parser version | 批次失败必须可见 |
| Raw Evidence | `import_rows` | 原始行详情 | 原始行文本、行号、row hash、字段映射版本 | 不能删除后假装导入成功 |
| Quarantine | `quarantine_rows` | 导入异常中心 | 失败字段、失败原因、修复建议 | 失败行不得进入 fills |
| Orders | `orders` | 订单列表和复盘摘要 | 原始账号、canonical 账号、order id、状态 | 缺 order id 时必须进入 quarantine |
| Fills | `fills` | 成交列表和复盘摘要 | execution id、成交时间、数量、价格、来源 raw row | 缺 execution id 时必须使用 fallback key 并显示 |
| Trade Groups | committed `fills` read model | `/api/trade-groups` 轻量列表和 replay 详情 | group id、组内 fills、parser/mapper version、评分模型版本 | 未清仓不得进入已实现 PnL 或正常评分 |
| Review Summary | committed `fills` read model + closed Trade Groups | 全局、日期和标的下钻汇总 | scope、closed/open group count、PnL、胜率、盈亏比、单笔期望值、每股净收益、持仓最大回撤 | 无 committed fills 时返回 0 和空分组 |
| Market Context | `market_context_snapshots` | 复盘图表和上下文面板 | provider、请求窗口、bars hash、数据状态 | 缺行情显示 `缺数据` |
| Minute Archive | `market_minute_archives` | 日期+标的分钟蜡烛图 | `bars_json`、`bars_hash`、VWAP、当日高低、provider 状态 | 缺归档或缺分钟线不得画成功图 |
| Watchlist | `watchlist_runs` + `watchlist_items` | 盘前关注列表 | trade date、rules version、reason codes、metrics hash | provider failure 显示失败 run |
| Strategy Config | `strategy_configs` | 策略配置列表 | template version、params JSON、params hash、enabled | 未开启策略显示 disabled run |
| Strategy Config History | `strategy_config_history` | 策略配置历史和回退入口 | previous/next template version、previous/next params hash、previous/next params JSON、change reason、candidate id、source history id | 历史 run 不被当前配置变更覆盖；缺参数快照不得回退 |
| Strategy Signal | `strategy_signal_runs` + `strategy_signals` | 策略复盘图层 | source archive、bars hash、indicator hash、reason codes、metrics | 缺归档或缺分钟线不得画假信号 |
| Strategy Test Batch | `strategy_test_batches` + `strategy_test_day_results` | 策略测试工作区 | archive scope hash、params hash、逐日 strategy run | 最近 30 天自然日窗口内无本地归档显示 `insufficient_archive_coverage` |
| Strategy Optimization | `strategy_optimization_runs` + `strategy_optimization_candidates` | 策略优化候选列表 | symbol scope、search space hash、candidate params hash、逐 symbol/day 结果 JSON | 无合格候选或覆盖不足不得自动套用参数 |
| Review Journal | `trade_reviews` | 标签和复盘结论 | 标签、错误分类、结论、更新时间 | 主观结论不得覆盖成交 |

## P0 数据合同

### `import_batches`

当前字段：

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

### 无表头成交 TXT

P0 允许一种窄口径的 fill-only TXT：文件无表头，基础列顺序固定为 `日期、时间、标的、买卖、股数、价格、账号、通道`。如果第 9 列存在，按 `order_id` 处理；如果第 10 列存在，作为未知尾列保留在 parsed payload。Parser 必须：

- 用默认字段合同补齐表头。
- 将 `日期 + 时间` 合成为成交 timestamp。
- 优先使用第 9 列 `order_id`；缺失时用原始行 hash 生成 fallback order id。
- 在 parsed payload 中记录合成字段来源。
- 缺价格、缺数量或方向无法识别时进入 quarantine。

除该窄口径外，缺 order id 的普通 STP 行仍必须进入 quarantine。

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

成交 read-model 必须在不删除证据账本的前提下处理跨批重导：如果同一批成交因补表头、编码变化或尾部空行导致 `file_hash` 改变，`import_batches`、`import_rows` 和底层 `fills` 可保留全部证据；`GET /api/fills` 和 daily summary 只对同一 fallback 成交签名的最新批次计数。同一文件内部重复的 raw rows 仍按出现次数保留，不能被压缩成一笔。

Daily summary 与 review summary 的 PnL、胜率、盈亏比、单笔期望值和每股净收益必须按已平仓 round-trip 计算：同一账号和标的下，仓位从 0 开始，B&S 或 S&B 回到 0 时结算一笔交易；多次开平仓必须拆成多笔。未平仓单边成交不进入胜率、盈亏比、单笔期望值、每股净收益、持仓最大回撤或已实现 PnL。全局、日期和标的下钻汇总都只能读取 committed fills 和 closed trade groups，不得由前端按成交列表自行重算核心 KPI。单笔期望值按 `胜率 * 平均盈利金额 - 败率 * 平均亏损金额` 计算；每股净收益按 `PnL / 成交股数` 计算；持仓最大回撤按 closed trade group 引用的 `market_minute_archives` 窗口 high/low 计算，汇总取范围内可用成交组的最大值。

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
- `bars_json`
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

### `market_data_provider_attempts`

每次 provider 请求都单独记录：

- `id`
- `provider`
- `symbol`
- `request_type`
- `requested_start`
- `requested_end`
- `status`
- `error_code`
- `payload_hash`
- `created_at`

provider attempt 是故障追溯来源，不是 UI KPI 来源。

### `watchlist_runs`

当前字段：

- `id`
- `trade_date`
- `provider`
- `rules_version`
- `status`
- `item_count`
- `failure_reason`
- `created_at`

### `watchlist_items`

当前字段：

- `id`
- `run_id`
- `trade_date`
- `symbol`
- `rank`
- `reason_codes_json`
- `metrics_json`
- `source`
- `status`

Watchlist 每个入选 symbol 必须有 reason codes 和 metrics。UI 只显示 API read model，不在前端自行计算入选理由。

## P2 Strategy Replay 合同

### `strategy_configs`

当前字段：

- `id`
- `name`
- `template_key`
- `template_version`
- `enabled`
- `params_json`
- `params_hash`
- `created_at`
- `updated_at`

默认 seed 禁用的 `bb_squeeze_breakout_v1`、`institutional_liquidity_sweep_v1`、`momentum_mean_reversion_v1`、`one_minute_trend_rider_v1` 和 `one_minute_range_fader_v1` 策略配置。新增策略从模板复制默认参数，用户只能调整参数、初始本金、入场资金比例和启停状态；默认初始本金为 100000，默认入场资金比例为 20%。策略配置不保存 STP parser version 或 field mapper version。

### `strategy_config_history`

当前字段：

- `id`
- `strategy_id`
- `change_source`
- `previous_template_version`
- `next_template_version`
- `previous_params_hash`
- `next_params_hash`
- `previous_params_json`
- `next_params_json`
- `change_reason`
- `optimization_run_id`
- `candidate_id`
- `source_history_id`
- `idempotency_key`
- `created_at`

模板 registry 升级、手工参数编辑、显式套用优化候选或历史回退时必须写入历史记录。`template_backfill` 用于保存代码模板版本升级导致的配置回填；`manual_edit` 用于保存配置弹层手工参数保存；`optimization_candidate_apply` 用于保存用户显式套用优化候选；`history_rollback` 用于保存从历史记录恢复参数快照。历史记录只解释当前配置如何变化，不覆盖 `strategy_signal_runs.params_json`、test batch 或 optimization candidate 的原始 artifact source。缺少 `previous_params_json` 的旧历史记录只能展示，不能回退。

### `strategy_signal_runs`

当前字段：

- `id`
- `strategy_id`
- `provider`
- `symbol`
- `trade_date`
- `source_archive_id`
- `bars_hash`
- `params_hash`
- `params_json`
- `indicator_engine_version`
- `status`
- `failure_reason`
- `indicator_series_json`
- `indicator_hash`
- `signal_count`
- `idempotency_key`
- `created_at`

`status` 至少包含：

- `completed`
- `missing_archive`
- `non_available_archive`
- `insufficient_bars`
- `strategy_disabled`
- `failed`

策略 run 只引用 `market_minute_archives`，不触发行情归档。`force=true` 可以替换同一幂等 key 下的指标序列和信号。`params_json` 保存运行时参数快照，历史 run 优先展示该快照，不被后续 `strategy_configs` 修改覆盖。

Momentum Mean Reversion 的 `source_archive_id` 指向目标标的分钟线归档；`bars_hash` 保存目标标的、QQQ 和 SMH 三组归档的组合输入 hash。目标标的 ADX、ATR、market regime、mean reversion enabled 状态，以及 QQQ/SMH 的 close、VWAP 和方向过滤结果进入 `indicator_series_json` 与 `indicator_hash`，作为复查动能过滤和趋势熔断的 artifact source。

### `strategy_signals`

当前字段：

- `id`
- `run_id`
- `timestamp`
- `bar_index`
- `side`
- `action`
- `price`
- `stop_loss_price`
- `take_profit_price`
- `linked_entry_signal_id`
- `reason_codes_json`
- `metrics_json`

`action` 固定为 `ENTRY_LONG`、`EXIT_LONG`、`ENTRY_SHORT`、`EXIT_SHORT`。同一策略、标的、日期在持仓中不得重复发出新的 entry signal；exit signal 必须引用对应 entry signal。

BB Squeeze 信号的 `metrics_json` 必须包含足以复查 entry/exit 的核心指标。entry 至少包含相对带宽、绝对带宽、最小绝对带宽、VWAP、RSI、相对成交量、实体强度和被动止盈目标；exit 至少包含 entry price、exit price、单股 PnL，并在可用时包含 9 EMA 和布林中轨。

Institutional Liquidity Sweep 信号的 `metrics_json` 必须包含足以复查扫损毛刺的核心指标。entry 至少包含局部窗口、局部高低点、VWAP、BB 中轨、相对成交量、实际影线占比、要求影线占比、扫破距离、tick 止损偏移和被动止盈目标；exit 至少包含 entry price、exit price、单股 PnL、持仓 K 数，并在可用时包含 VWAP 和 BB 中轨。

Momentum Mean Reversion 信号的 `metrics_json` 必须包含足以复查反转均值回归的核心指标。entry 至少包含目标 BB 中轨/上下轨、目标 VWAP、ADX、ATR、ADX 趋势阈值、ADX 震荡阈值、market regime 编码、QQQ/SMH close 与 VWAP、止损价格、中轨第一目标、对侧外轨最终目标、ATR 止损倍数、ATR 止损距离、Pin Bar 或吞没形态标记；exit 至少包含 entry price、exit price、单股 PnL、平仓比例、第一目标、最终目标、ADX/ATR 和 break-even 止损状态。

Trend Rider 信号的 `metrics_json` 必须包含足以复查 PA 趋势中继的核心指标。entry 至少包含 VWAP、20 EMA、EMA slope、opening range 高低点、强突破 K 数、突破量能、H2/L2 探针价格、回调均量、回调缩量比例、实体强度和硬止损；exit 至少包含 entry price、exit price、单股 PnL、硬止损和 9 EMA。`take_profit_price` 必须为空，表示没有静态止盈目标。

Range Fader 信号的 `metrics_json` 必须包含足以复查 BLSH 区间边缘反转的核心指标。entry 至少包含区间上沿、下沿、中轴线、上下边缘区、区间高度、上下沿触碰次数、20 EMA、EMA 斜率、EMA 穿越 K 数、VWAP、反转影线占比、反转实体强度、信号 K index、下一根开盘 entry price、硬止损、中轴第一目标、对侧边缘最终目标、break-even stop price 和第一目标平仓比例；exit 至少包含 entry price、exit price、单股 PnL、exit fraction、current stop、break-even stop 状态、第一目标触达状态、第一目标、最终目标、区间上下沿、20 EMA 和 VWAP。

### `strategy_test_batches` / `strategy_test_day_results`

批量测试只读取截至 `end_date` 的最近 30 天（自然日）窗口内已保存的 `market_minute_archives`；如果窗口内只有部分交易日归档，就只对这些本地归档生成逐日结果，不会向更早交易日补足 30 个交易日。批次保存 `archive_scope_hash`、`params_json`、`params_hash`、`template_version`、`indicator_engine_version`、状态、覆盖率、信号数、资金 PnL、胜率、盈亏比和最大回撤。逐日结果保存 `source_archive_id`、`bars_hash`、`strategy_run_id`、状态、失败原因、信号数、`indicator_hash` 和当日复盘统计；资金 PnL 按运行时 `initial_capital * entry_capital_ratio / entry_price` 换算策略仓位。

### `strategy_optimization_runs` / `strategy_optimization_candidates`

优化 run 保存 `archive_scope_hash`、`search_space_json`、`search_space_hash`、`objective=stable_profitability_v1`、候选数、合格候选数和最佳候选引用。候选保存 `params_json`、`params_hash`、`day_results_json`、资金 PnL、胜率、盈亏比、最大回撤、覆盖率和 `stability_score`。最佳候选只作为研究结果展示，只有用户显式套用参数时才更新 `strategy_configs`，同时写入 `strategy_config_history` 的前后模板版本、前后参数 hash、候选来源和变更原因。

## 幂等规则

- 批次幂等：`file_hash`。
- 原始行幂等：`batch_id + row_number + raw_line_sha256`。
- 订单幂等：优先 `account_canonical + order_id`；无表头成交 TXT 缺第 9 列时使用 raw line hash 合成 fallback order id 并标注。
- 成交幂等：优先 `account_canonical + execution_id`；缺 execution id 时使用 source import row 参与 fallback，保留同一 STP 文件内的重复成交行。成交 read-model 另按 fallback 成交签名和出现序号做跨批去重，避免修正重导双算 KPI。
- KPI 分组：`trade_group_count` 是已平仓 round-trip 数；胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤不能用当日账号+标的净 PnL 或前端成交列表代替。
- replay 幂等：`fill_id + provider + requested_start + requested_end`，并保存 `bars_hash` 作为 provider bars 证据。
- watchlist run 幂等：`trade_date + provider + rules_version`；重跑时替换该 run 下的 items。
- strategy run 幂等：`strategy_id + provider + symbol + trade_date + source_archive_id + bars_hash + params_hash + template_version + indicator_engine_version`；重跑只替换同一 run 的指标和信号。Momentum Mean Reversion 的 `bars_hash` 是目标标的、QQQ 和 SMH 已归档分钟线的组合输入 hash，因此动能过滤归档变化会生成新的幂等口径。
- strategy test batch 幂等：`strategy_id + provider + symbol + end_date + window_trading_days + archive_scope_hash + params_hash + template_version + indicator_engine_version`。
- strategy optimization 幂等：`strategy_id + provider + symbol_scope + end_date + window_trading_days + archive_scope_hash + search_space_hash + objective + template_version + indicator_engine_version`；多标的时 `symbol_scope` 是输入标的组的 canonical 逗号分隔值，candidate 幂等为 `optimization_run_id + params_hash`。
- strategy config history 幂等：模板回填按 `strategy_id + template_backfill + previous_template_version + next_template_version + next_params_hash` 去重；优化候选套用按 `strategy_id + optimization_candidate_apply + optimization_run_id + candidate_id + next_template_version + next_params_hash` 去重；手工编辑按 `strategy_id + manual_edit + previous_params_hash + next_template_version + next_params_hash` 去重；历史回退按 `strategy_id + history_rollback + source_history_id + previous_params_hash + next_template_version + next_params_hash` 去重。
- 零行 file-level 失败重解析：如果旧 parser 只留下 `row_count=0` 的文件级失败，新 parser 可以用同一 `file_hash` 重解析该批次；已有 evidence rows 的批次不得被该路径覆盖。

## 失败语义

- 上传空文件：批次状态为失败，显示原因。
- 无表头成交 TXT：按默认字段合同解析，第 9 列作为 `order_id`，不作为 file-level `missing_header`。
- 旧 parser 的零行 file-level 失败：新 parser 可重解析并更新为新的可见批次状态。
- 未知列：进入字段映射诊断，不应静默丢列。
- 缺关键字段：行进入 quarantine。
- 部分成交：保留每笔成交，同时在 order 汇总中展示累计数量。
- 缺 execution id 重复成交：同一文件内逐行保留；重复导入仍由批次 `file_hash` 幂等拦截；文件 hash 改变但成交签名重叠时，read-model 只计算最新批次。
- 取消单：保留订单状态，不伪造成成交。
- 跨日成交：按成交时间和交易日同时建索引。
- 富途接口失败：market context 状态为 `provider_failed`。
- 分钟线缺失：market context 状态为 `missing` 或 `partial`。
- 时区错位：market context 状态为 `timezone_conflict`，禁止自动平移后当作成功。
- 策略缺归档：strategy run 状态为 `missing_archive`，UI 不渲染策略线或信号。
- 策略归档不可用：strategy run 状态为 `non_available_archive`，保留 failure reason。
- 策略分钟线不足：strategy run 状态为 `insufficient_bars`，不生成 warmup 信号。

## 安全边界

- 首版没有自动下单路径。
- 信号引擎只允许做提醒和复盘解释。
- 不保存券商密码或交易凭据。
- STP TXT 原始文件和原始行属于敏感交易证据，日志、截图和 changelog 不应暴露原文。
- 对外展示文档不得包含真实账号、本机路径、原始 payload 或内部调试 id。

## 阶段实施顺序

1. P0 `Contract Skeleton`：schema、parser fixture、证据账本、quarantine、orders/fills、基础导入测试。
2. P0 `Execution Core`：真实 TXT 导入、幂等、parser replay、导入异常 UI。
3. P1：Market Context Replay、provider attempts、盘前 Watchlist。
4. P2：交易策略配置、历史策略信号复盘和图表增强。
5. P3：信号质量和规则反馈。
