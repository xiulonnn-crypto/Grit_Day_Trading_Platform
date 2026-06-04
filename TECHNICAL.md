# Technical Plan

## 当前 P2 切片：交易策略配置与历史信号复盘

目标：在复盘台配置交易策略，并基于已归档分钟线生成可追溯的历史开平仓信号。

范围：

- 新增 `strategy_configs`、`strategy_signal_runs` 和 `strategy_signals` 存储合同。
- 新增策略模板 registry，当前内置 `bb_squeeze_breakout_v1`、`institutional_liquidity_sweep_v1` 和 `momentum_mean_reversion_v1`，并分别 seed 默认禁用配置。
- 新增策略 API：模板、配置、启停、参数保存、历史 run 和 run 查询。
- 新增策略测试 API：最近 30 个已归档交易日 test batch、逐日结果、优化 run、候选参数和稳定性排序。
- 策略计算只读取 `market_minute_archives`，不自动归档分钟线，不修改 STP 成交事实。
- 顶层 UI 拆为「交易复盘」和「策略测试」两个 tab；交易复盘保留成交证据与买卖点，策略测试集中展示配置、单日测试、30 日测试复盘和策略优化。
- 策略测试页允许手工输入研究标的，并显式拉取该标的最近 30 个交易日分钟线归档；该数据准备动作独立于策略 run。
- 策略测试页通过「交易策略配置」操作按钮打开配置弹层，并在策略测试图中叠加 BB bands、策略 VWAP 和策略开平仓 marker。

验收：

- 缺分钟线归档显示 `missing_archive`。
- 非 available 归档显示 `non_available_archive`。
- 分钟线不足显示 `insufficient_bars`，warmup 期间不生成信号。
- 策略未开启显示 `strategy_disabled`。
- 重复运行默认复用同一 run；`force=true` 替换同一 run 的指标和信号。
- 30 日测试覆盖不足显示 `insufficient_archive_coverage`，不自动拉行情。
- 用户显式拉取最近 30 个交易日归档后，仍以已保存 `market_minute_archives` 的 available 覆盖为准；provider 缺数据或失败不补假成功日。
- 优化候选超过 120 个时拒绝运行；最佳候选只展示，用户显式套用后才更新策略配置。
- STP committed fills 的价格、数量、时间和证据字段不被策略 run 修改。

## 当前 P1 切片：Trade Replay Groups

目标：成交记录从单笔 fill 改为“每一次开仓至清仓”的交易组，并在 replay 弹层中展示该次交易的分钟蜡烛图、成交量、关键指标和可审计智能评价。

范围：

- 新增 `GET /api/trade-groups?date=YYYY-MM-DD&account=&symbol=`，从 committed `fills` read model 构建交易组，不新增持久化表。
- 交易组按 `account_canonical + symbol`、成交时间和 fill id 顺序配对，支持多头、空头、加仓、部分平仓和未清仓状态。
- Daily summary 的 `trade_group_count`、PnL、胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤复用 closed trade groups，避免 UI 分组和 KPI 口径漂移。
- Replay 弹层使用已归档 `market_minute_archives`，按开仓到清仓窗口自动缩放并保留前后缓冲，叠加组内所有成交点，并展示基于窗口分钟 high/low 的持仓最大回撤追溯。
- 智能评价采用 `trade_eval_intraday_v1` 规则模型，只读计算 VWAP 执行质量、趋势配合、成交量确认、MFE/MAE、清仓效率和 PnL 结果；持仓最大回撤是交易组 read model 字段，不由前端自行重算。
- 交易复盘 tab 头部展示有记录以来汇总；随后按交易日和按标的两个下钻 tab 展示次级汇总，选择具体日期+标的后进入分钟蜡烛和交易组复盘模块。

验收：

- closed group 才进入已实现 PnL、胜率、盈亏比、单笔期望值、每股净收益、持仓最大回撤和正常评价；open group 必须显示未清仓。
- `trade_group_id` 只暴露 hash 后 ID，不暴露原始 fill idempotency key。
- 缺分钟线、provider failure、时区冲突或无 bars 时，持仓最大回撤和评价必须返回 `insufficient_market_data`，不能生成正常评分。
- Replay 弹层不能用行情数据改写成交价格、数量或时间。
- 无 committed fills 时，全局汇总为 0、日期/标的下钻为空，UI 不展示假日期、假标的或成功复盘。
- 文档和 changelog 必须同步 P1 事实源、read model、artifact source 和负向路径。

## 当前 P1 切片：Yahoo 离线分钟线归档

目标：从 committed fills 推导有交易日的标的，用 Yahoo Finance 获取 1 分钟线，并保存为可复查离线归档。

范围：

- 新增 Yahoo provider adapter，只负责分钟线获取和错误状态映射。
- 新增 `market_minute_archives` 存储合同，保存 symbol/day 级别的 bars、hash、VWAP、当日高低、成交量上下文和归档版本。
- 新增 `POST /api/market-data/yahoo-minute-archive`、`GET /api/market-data/minute-archives` 和 `scripts/archive-yahoo-minute-data.py` 作为操作入口。
- `POST /api/market-data/yahoo-minute-archive` 可按已提交成交目标归档，也可按手工 `symbol + date + window_trading_days` 归档研究标的窗口。
- 复盘页新增日期和标的选择器，按 `trade_date + symbol` 读取归档分钟线，默认显示当前标的第一笔到最后一笔 committed fill 的时间范围，并用 committed fills 标注买卖点。
- 归档目标来自已提交 `fills`，不读取 quarantine 行，不修改 STP 成交事实。
- 启用 Momentum Mean Reversion 时，归档目标还包括同日 QQQ/SMH 策略上下文标的；这些上下文归档的 `source_fill_count` 为 0，策略 run 仍只读取已归档 artifact。

验收：

- 重复运行默认不新增 archive 或 provider attempt。
- `force=true` 可以刷新已有 archive。
- Yahoo 缺数据或 provider 失败必须留下 archive 状态和 provider attempt。
- 复盘页缺归档或缺分钟线时必须显示缺失状态，不能用空蜡烛图表示成功。
- 负向路径覆盖无成交目标、provider failure、重复归档、缺 QQQ/SMH 动能上下文和 STP fill 不被行情数据改写。

本文档记录当前技术计划、阶段切片、接口草案、测试策略和开放问题。

## 当前技术真相

- 项目目标是 STP 日内交易闭环 Web 系统。
- STP TXT 是订单和成交真相源。
- P0 不接富途行情。
- 首版只做提醒和复盘，不自动下单。
- 首个真实 STP TXT 样例将决定 parser fixture 和字段合同。
- 当前实现前建议先跑工程方案复审，确认数据模型、Web 栈和验收命令。
- 当前已完成 P0 scaffold：FastAPI、SQLite、STP TXT parser、导入 API、React 复盘台和测试 fixture。
- 当前 parser 支持无表头成交 TXT：基础列为 `日期、时间、标的、买卖、股数、价格、账号、通道`，第 9 列存在时作为 `order_id`。
- 当前 import service 支持旧 parser 造成的零行 file-level 失败批次重解析。
- 当前 daily summary 的交易股数使用每个账号和标的的 BUY/SELL 配对股数，不用单边成交行数量累加。
- 当前成交 read-model 支持跨批重导去重：同一 fallback 成交签名只计算最新批次，同一文件内部重复 raw rows 仍逐行保留。
- 当前 daily summary 的 PnL、胜率、盈亏比、单笔期望值和每股净收益按已平仓 round-trip 统计，持仓最大回撤按 closed trade group 的已归档分钟线 high/low 追溯统计；前端只展示 API read model，不自行重算核心 KPI。
- 当前 P2 策略复盘只读取已归档分钟线，策略信号不会触发下单，也不会改写 STP 成交。
- 当前 `OCO_Immediate` 只作为 Institutional Liquidity Sweep 的历史出场建模模式，保存到策略参数、run artifact 和信号原因码，不向券商发送真实 OCO 订单。
- 当前 Momentum Mean Reversion 只读取目标标的、QQQ 和 SMH 的已归档分钟线；QQQ/SMH 用于动能过滤，目标标的 ADX/ATR 用于趋势熔断和动态止损，缺任一归档或不可用归档时保存失败 run，不渲染成功信号。

## 建议技术栈

当前建议采用轻量本地 Web 栈，便于个人交易台快速迭代：

- 后端：Python FastAPI。
- 存储：SQLite。
- 前端：React + Vite。
- 测试：pytest、Vitest、Playwright 或等价浏览器验收。
- 行情适配：富途 OpenAPI adapter。

这是当前 P0 scaffold 的实现基线。若后续选择不同栈，必须同步更新本节、[ARCHITECTURE.md](./ARCHITECTURE.md) 和 [README.md](./README.md)。

## 阶段切片

### P0 Contract Skeleton

目标：

- 建立 STP upload batch、evidence ledger、quarantine、normalized orders/fills 的 schema。
- 建立 parser 和 field mapper 的版本字段。
- 建立幂等 key。
- 建立基础 API 和最小 UI read model。
- 建立真实 STP TXT fixture 接入点。

验收：

- 空文件失败可见。
- 未知列诊断可见。
- 缺关键字段进入 quarantine。
- 重复导入不重复写 normalized records。
- 每笔 normalized fill 可追溯到 evidence row。

### P0 Execution Core

目标：

- 接入真实 TXT 导入。
- 支持 parser replay。
- 支持导入批次详情和异常修复建议。
- 支持基础复盘指标。

验收：

- 真实样例导入成功。
- 部分成交和取消单语义正确。
- 跨日成交不会丢失交易日。
- parser 升级后历史记录不被覆盖。

### P1 Market Context Replay

目标：

- 通过可替换 provider 接入分钟线和日内摘要；自动测试默认使用 fake provider。
- 为每笔 fill 生成 market context snapshot。
- 在复盘页展示成交时刻、VWAP、当日高低、成交量环境、缺数据状态和按标的归档的分钟蜡烛图。
- 生成盘前 watchlist，并为每个 symbol 保存入选原因和指标。

验收：

- 分钟线缺失显示 `缺数据`。
- 富途接口失败显示 provider failure。
- 时区错位进入诊断状态。
- 盘前和盘后成交按独立 session 语义展示。
- Watchlist 每个 symbol 必须有 `reason_codes_json` 和 `metrics_json`。

## API 草案

### STP Import

```text
POST /api/imports/stp-txt
GET  /api/imports
GET  /api/imports/{batch_id}
GET  /api/imports/{batch_id}/quarantine
```

### Orders and Fills

```text
GET /api/orders
GET /api/fills
GET /api/fills/{fill_id}
GET /api/review/summary
GET /api/review/summary-groups?group_by=date|symbol
```

### Market Context

```text
POST /api/market-context/replay
GET  /api/fills/{fill_id}/market-context
GET  /api/market-context/{snapshot_id}
POST /api/watchlist/generate
GET  /api/watchlist?date=YYYY-MM-DD
PUT  /api/watchlist/{date}
```

这些 API 覆盖 P0 和 P1 合同。P0 不能移除证据账本、quarantine、幂等导入和 committed-only KPI 语义；P1 不能用行情数据改写 STP 成交。

### Strategy Replay

```text
GET   /api/strategy-templates
GET   /api/strategies
POST  /api/strategies
PATCH /api/strategies/{strategy_id}
POST  /api/strategies/{strategy_id}/runs
GET   /api/strategy-runs?date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...
POST  /api/strategies/{strategy_id}/test-runs
GET   /api/strategy-test-runs?end_date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...
POST  /api/strategies/{strategy_id}/optimizations
GET   /api/strategy-optimizations?end_date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...
GET   /api/strategy-optimizations/{optimization_id}
```

P2 策略 API 只返回后端 read model。前端不得自行计算 BB、RSI、VWAP、relative volume、9 EMA、absolute bandwidth、ADX、ATR、market regime 或策略入选理由。

## Parser 合同

Parser 必须输出：

- `parser_version`
- `field_mapper_version`
- `raw_line`
- `row_number`
- `raw_line_sha256`
- `header_source`
- `synthetic_fields`
- `account_raw`
- `account_canonical`
- `symbol`
- `side`
- `order_id`
- `execution_id`
- `quantity`
- `price`
- `timestamp`
- `row_status`
- `failure_code`
- `repair_hint`

Parser 不允许：

- 静默丢弃未知列。
- 用空字符串填补关键字段后继续成功。
- 直接覆盖旧 parser version 的历史结果。
- 将账号 canonical 值替代原始账号文本保存。

无表头成交 TXT 是 P0 的 fill-only 例外口径。Parser 必须自行补 `日期、时间、标的、买卖、股数、价格、账号、通道`，将日期和时间合成为 timestamp。第 9 列存在时作为 `order_id`；缺第 9 列时用 raw line hash 合成 fallback order id。该合成事实必须进入字段映射诊断，不得伪装成原始 TXT 字段。

## Market Context 合同

每笔 fill 的 replay 请求应记录：

- provider。
- 请求开始和结束时间。
- provider timezone。
- 返回 bar 数量。
- bars hash。
- bars JSON。
- VWAP。
- 当日高低。
- 成交量环境。
- data status。
- failure reason。

`available` 以外的状态都必须在 UI 可见。

Snapshot 幂等 key 是 `fill_id + provider + requested_start + requested_end`。force replay 只能更新 snapshot，不得改写 `fills`。

## Watchlist 合同

每次 watchlist 生成应记录：

- trade date。
- provider。
- rules version。
- run status。
- item count。
- failure reason。

每个 item 应记录：

- symbol。
- rank。
- reason codes JSON。
- metrics JSON。
- source。
- status。

Watchlist run 幂等 key 是 `trade_date + provider + rules_version`。UI 只展示 API read model，不自行计算入选理由。

## Strategy Replay 合同

策略配置记录：

- `template_key`
- `template_version`
- `enabled`
- `params_json`
- `params_hash`

策略 run 记录：

- `source_archive_id`
- `bars_hash`
- `params_hash`
- `params_json`
- `indicator_engine_version`
- `status`
- `indicator_series_json`
- `indicator_hash`
- `signal_count`

策略 signal 记录：

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

`bb_squeeze_breakout_v1` 默认参数为 BB(20, 2)、RSI(14)、前 20 分钟均量、2 倍量能、10% 收缩分位、10 分钟 setup、0.5 实体强度、9 EMA 出场缓冲、最小绝对带宽 2.0 和 2:1 被动止盈目标。

策略引擎逐 bar 计算指标，只能使用当前 bar 和历史 bar。持仓中不得重复生成 entry；exit signal 必须关联 entry。价格跌回或升回布林带外轨内部本身不再触发出场；多头必须触发止损、2:1 被动止盈、9 EMA 或布林中轨缓冲，空头按镜像条件处理。2:1 止盈只在复盘 run 中按 high/low 触达建模，不发送真实限价单。

`institutional_liquidity_sweep_v1` 默认参数为 20 根局部窗口、0.6 影线占比、前 20 分钟均量、1.5 倍放量、BB(20, 2) 中轨目标、1.5:1 盈亏比、0.01 tick、2 个 tick 止损偏移、最多持仓 3 根 K 和 `OCO_Immediate`。策略引擎逐 bar 计算 VWAP、局部高低点、前 5 分钟高低、BB 中轨、相对成交量和影线占比；多头必须在 VWAP 上方扫破局部低点后收回，空头必须在 VWAP 下方扫破局部高点后拒绝。`OCO_Immediate` 只在历史 run 中建模止损、BB 中轨或 1.5:1 被动止盈触达，不发送真实订单。

`momentum_mean_reversion_v1` 默认参数为 BB(20, 2)、ADX(14) 趋势熔断阈值 25、ADX 震荡激活阈值 20、ATR(14) 1.5 倍硬止损、美东 11:30 至 13:30 时间窗口、QQQ+SMH 动能过滤、0.55 Pin Bar 影线占比、近 3 根 K 波谷/波峰上下文和 50% 中轨部分止盈。策略引擎逐 bar 计算目标标的 BB、VWAP、ADX、ATR、market regime、QQQ/SMH close 与 VWAP、时间窗口和动能方向；ADX 高于趋势阈值时均值回归熔断并生成 0 信号，ADX 低于震荡阈值后才重新激活。多头必须在 QQQ 与 SMH 同时位于 VWAP 上方时，等待目标标的跌破下轨后以 Pin Bar 或阳线吞没重新收回下轨；空头按镜像条件处理。硬止损按入场价加减 ATR 倍数计算；触及中轨后生成部分止盈信号，并把剩余仓位止损上移至入场价；触及对侧外轨或 break-even 止损后生成剩余仓位出场信号。该策略不自动下单，不修改 committed fills。

策略测试批次记录：

- `archive_scope_hash`
- `params_json`
- `params_hash`
- `window_trading_days`
- `coverage_ratio`
- `total_pnl`
- `win_rate`
- `profit_factor`
- `max_drawdown`
- 逐日 `strategy_run_id`、`bars_hash`、`indicator_hash` 和失败状态

策略优化记录：

- `search_space_json`
- `search_space_hash`
- `objective=stable_profitability_v1`
- candidate `params_json`
- candidate `day_results_json`
- `stability_score`

默认优化网格来自策略模板参数 schema，硬上限 120 个 candidate。优化只保存候选，不自动覆盖 `strategy_configs`。

## 测试计划

当前固定验证命令：

```powershell
python -m pytest -q
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
```

当前 Python 集成测试覆盖 P0、P1 和 P2，包含 parser、storage contract、import API、market context、watchlist、strategy replay 和 DB/API/UI read-model 一致性。

## 本地登录入口

根目录提供 `Login-Grit-DayTrading.cmd` 作为 Windows 双击入口：

- 后端默认端口：`8001`。
- 前端默认端口：`5173`。
- 后端备用端口从 `8011` 起选择，前端备用端口从 `5183` 起选择。
- 前端 API 代理默认指向当前选中的后端端口；只有用户显式设置 `VITE_API_PROXY` 时才保留外部指定值。
- 启动前会验证后端 `healthz`、复盘汇总 API、P2 必需 API 路由和策略模板；如果默认端口上是旧后端，正常启动会自动切到备用后端和前端端口，避免前端连到会返回 404 的服务。
- 如果备用后端可以监听但复盘 API 不可用，启动器必须将其归类为后端运行态失败并打印端口 owner PID，避免误报为前端未启动。
- `--check` 检查 Python、npm 和端口配置；如果后端正在运行，也会验证 P2 必需 API 路由，但不启动服务、不自动切换备用端口。
- `GRIT_NO_BROWSER=1` 可跳过自动打开浏览器，便于脚本验证。
- `GRIT_NO_PAUSE=1` 可让失败时直接返回退出码，便于自动化验证。
- 修改 Windows `.cmd` 启动脚本后必须保持 CRLF，并运行 launcher contract 或真实启动路径验证，避免批处理标签解析失败。

服务 helper：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-frontend.cmd
```

### P0 Tests

- 真实 STP TXT 样例。
- 无表头成交 TXT 和第 9 列 `order_id`。
- 旧 parser 的零行 file-level 失败批次重解析。
- 缺 execution id 重复成交行逐行入账。
- 缺 execution id 跨批修正重导不重复计算 read-model。
- 已平仓 round-trip 胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤。
- Daily summary 交易股数和 PnL。
- 重复导入。
- 空文件。
- 缺字段。
- 未知列。
- 部分成交。
- 取消单。
- 跨日成交。
- 原始行可追溯。
- quarantine 行可复查。
- parser version 可重跑。

### P1 Tests

- 分钟线缺失。
- 时区错位。
- 盘前成交。
- 盘后成交。
- 富途接口失败。
- provider 返回 partial bars。
- Replay 幂等和 force replay。
- Watchlist 稳定排序、入选理由、零结果、provider failure。
- API 404/422、fill 不存在、日期格式错误、watchlist 重跑。

### P2 Tests

- Strategy storage v4 表、索引、状态枚举和 run 幂等。
- BB Squeeze long/short entry、stop exit、2:1 exit、warmup 无信号和无未来函数。
- Institutional Liquidity Sweep long/short sweep entry、OCO 止盈、止损、影线不足拒绝和 run artifact 保存。
- Momentum Mean Reversion long/short 动能过滤、11:30-13:30 时间过滤、ADX 趋势熔断、ATR 动态止损、反转形态、缺 QQQ/SMH 归档、部分止盈、break-even 止损和组合输入 hash 保存。
- Strategy API 模板、配置、新增、启停、缺归档、可用归档、重复运行和 force 重跑。
- Strategy test batch：v5 schema、最近 30 日覆盖不足、非 available 归档、只读归档、逐日 run 证据和幂等。
- Strategy optimization：候选上限、默认网格、重复运行、force 重跑、最佳候选追溯和不自动改配置。
- Integration：策略 run 保存 source archive、bars hash、indicator hash，且 committed fills 不被修改。

### UI Acceptance

- 上传后能看到批次状态。
- 失败行显示字段和修复建议。
- 30 秒内找到一笔交易。
- 交易详情展示证据 row 和 market context 状态。
- 用户可以打标签并写复盘结论。
- 策略配置可添加、保存参数、开启和运行；策略信号能叠加在分钟蜡烛图上。

## 待定事项

- 第一份真实 STP TXT 样例字段结构。
- STP TXT 是否包含 execution id 的稳定字段。
- STP 时间戳时区和交易日归属规则。
- 富途分钟线拉取窗口大小。
- 本地 SQLite schema 命名最终版本。
- UI 首屏路由和信息架构。
- 是否需要导入前文件预览和字段映射确认页。

## 实施前工程复审问题

建议在写代码前完成一次工程复审，至少确认：

- 是否采用建议技术栈。
- schema 是否足以支持 parser replay。
- 幂等 key 在真实 STP 样例中是否可稳定生成。
- Market Context Replay 的数据缓存策略。
- UI 是否先做导入和详情页薄切片。
