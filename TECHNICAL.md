# Technical Plan

## 当前 P3 切片：亏损交易组 Review Journal

目标：在 Trade Replay 弹层内为已平仓亏损交易组提供精简原因下拉，记录本次亏损的主观归因；「成交记录」模块提供「仅看亏损单」勾选项但不提供单独「复盘」操作按钮；「下钻复盘」新增「盈亏复盘」tab，默认集中查看全部亏损交易组的原因分类和明细入口，也可切到盈利单只读复查热力矩阵和订单明细。

范围：

- 新增 `trade_reviews` 作为 Review Journal canonical source。
- `GET /api/trade-groups` 返回每个交易组已有的 `review`，`date` 可省略以读取全部日期的轻量交易组。
- `PUT /api/trade-groups/{trade_group_id}/review` 保存或更新亏损交易组复盘原因。
- 原因分类固定为开仓信号、平仓信号和误操作；原因码由后端校验。
- 复盘记录保存 `trade_group_id`、交易组 PnL、parser versions、field mapper versions、source batch ids 和 raw line numbers。

验收：

- 成交记录行不显示单独「复盘」操作按钮。
- 成交记录可勾选「仅看亏损单」只查看当前范围内 closed 且 PnL 小于 0 的交易组，并同步让上方分钟蜡烛图只显示这些交易组对应的买卖点；该筛选不重新计算 KPI 或修改事实源。
- 「数据下钻」tab 按全部、本月、本周和特定时间段筛选当前下钻 read model；展示顺序固定为时间筛选、该时间范围内全部订单统计指标、热力时间矩阵、当前复盘上下文和日期/标的下钻列表。数据下钻矩阵统计全部订单，只读展示最大盈利区和最大亏损区，不筛选下方日期/标的列表，不写入 `trade_reviews`、STP 成交或行情归档。
- 「下钻复盘」默认展示「数据下钻」；切到「盈亏复盘」后读取所有日期 closed 且 PnL 非 0 的交易组，右侧单选默认选中「仅看亏损单」，可切到「仅看盈利单」。
- 盈亏复盘时间筛选提供全部、本月、本周和特定时间段；亏损视图用该时间范围控制统计指标、一级/二级原因分类汇总和亏损单列表，盈利视图用该时间范围控制统计指标、热力矩阵和盈利单列表，原因模块展示为空。
- 盈亏复盘统计指标整理在一行；亏损视图的一级原因和二级原因分别用饼图展示，并支持联动多选筛选订单明细；订单明细默认按时间倒序，也可按当前盈亏金额倒序，每页 20 笔。
- 「盈亏复盘」展示只读热力时间矩阵，按 09:30-10:30、10:30-11:30、11:30-13:30、13:30-15:00、15:00-16:00 五个美股常规盘微观结构窗口和开仓 ATR Multiple 统计当前单选范围，亏损视图只在摘要中展示最大亏损区，盈利视图只在摘要中展示最大盈利区；矩阵格不筛选订单明细。波动/冲击环境读取后端 `position_drawdown.entry_atr_multiple`，由本地 `market_minute_archives` 计算开仓 1min K 振幅 / 前 20 根 ATR；缺开仓前 20 根分钟线时显示缺 ATR 证据，不用已实现盈亏或美元回撤回退，也不新增前端行情指标计算。
- 只有 closed 且 PnL 小于 0 的交易组在 Trade Replay 弹层订单明细模块下方展示亏损原因下拉。
- 保存原因后成交记录行显示已选亏损原因。
- 盈利、持平、未清仓或不存在的交易组不能写入亏损复盘。
- 复盘原因只写 `trade_reviews`，不修改 STP committed fills、行情归档或策略 artifact。

## 当前补充：实时交易信号面板
目标：收敛「实时交易」中的「下单信号」模块，展开后端 `signals[]` 中真实 BUY/SELL 订单层面的信号明细。HOLD、失败、策略动作、策略版本、provider 状态、原因码、指标和 hash 证据继续展示在「原因与证据」模块。

验收：
- 「下单信号」每个真实 BUY/SELL 信号订单只展示标的、订单意图、操作类型、信号价、股数、触发时间和 bar index；开仓单额外展示止损/止盈，股数由后端按策略资金参数和开仓价计算，关仓单不展示止损/止盈并展示平仓原因标签；操作类型由后端策略动作派生为「开仓」或「关仓」，同一标的窗口内的开仓和关仓都要展示。
- 「下单信号」不展示 HOLD、失败状态、状态徽标、状态摘要、完整策略动作、provider、bar count、latest strategy version、config version 或 hash 证据。
- `Login-Grit-DayTrading.cmd --check` 会检查前端 `App.tsx` 是否包含当前信号面板指纹，避免旧前端进程被误判为可用。
- provider failure、策略未开启或无信号时仍保留状态和失败原因，不渲染假订单。

## 当前补充：实时交易监控
目标：将「实时交易」从单次刷新改为多标的监控。用户下拉多选标的后，默认使用 Yahoo 实时行情；点击「开启监控」会立即读取一次最新行情，并每 30 秒继续调用后端 live-signal read model 输出只读下单信号和原因。

验收：
- 标的选择支持多选，同一轮监控按每个 symbol 独立调用 `POST /api/strategies/{strategy_id}/live-signal`。
- 前端默认 provider 为 Yahoo，后端请求未显式传 provider 时也默认 Yahoo。
- 切换策略、标的、行情源或分钟线窗口会停止监控并清空旧结果，避免旧行情覆盖新选择。
- 负向路径仍展示 `strategy_disabled`、provider failure、缺分钟线、非 available 行情和分钟线不足，不渲染成功 BUY/SELL 信号。

## 当前 P2/P3 切片：实时交易信号预览

目标：在复盘台新增「实时交易」tab，让用户选择策略和标的后，用 Futu、Yahoo 或 Fake 实时行情 provider 分钟线输出后端策略引擎的只读下单信号和原因。

范围：

- 新增 `POST /api/strategies/{strategy_id}/live-signal`，读取当前 `strategy_configs`，返回当前配置版本和最新策略版本，按 provider 获取目标标的分钟线，并复用后端策略引擎计算 BUY/SELL/HOLD。
- Momentum Mean Reversion 实时预览会同步读取 QQQ/SMH provider 分钟线作为动能上下文；缺任一上下文时返回失败状态，不生成成功信号。
- 「实时交易」tab 提供策略下拉、标的下拉、行情源和分钟线窗口选择；展示最新策略版本、信号价、止损、止盈、原因码、provider 状态和 hash 证据。
- 该切片不写入 `strategy_signal_runs`、`strategy_signals`、STP 成交、订单或券商委托；历史复盘仍只读取已归档 `market_minute_archives`。

验收：

- 策略未开启返回 `strategy_disabled` 和 HOLD，不请求行情成功状态。
- provider failure、缺分钟线、非 available 行情、分钟线不足或引擎失败不得渲染 BUY/SELL 成功信号。
- 前端只读 API read model，不自行计算 BB、RSI、VWAP、relative volume、ADX、ATR、EMA 或开平仓信号。
- 返回 `bars_hash`、`params_hash`、`indicator_hash`、`provider_attempt_status` 和 live preview idempotency key，便于人工复查本次信号来源。

## 当前 P2 切片：交易策略配置与历史信号复盘

目标：在复盘台配置交易策略，并基于已归档分钟线生成可追溯的历史开平仓信号。

范围：

- 新增 `strategy_configs`、`strategy_signal_runs` 和 `strategy_signals` 存储合同。
- 新增策略模板 registry，当前内置 `bb_squeeze_breakout_v1`、`institutional_liquidity_sweep_v1`、`momentum_mean_reversion_v1`、`one_minute_trend_rider_v1` 和 `one_minute_range_fader_v1`，并分别 seed 默认禁用配置。
- 新增策略 API：模板、配置、启停、参数保存、历史 run 和 run 查询。
- 新增策略测试 API：截至日期最近 30 天（自然日）本地归档窗口的 test batch、逐日结果、优化 run、候选参数和稳定性排序。
- 新增策略配置历史合同：模板 registry 升级、手工参数保存、显式套用优化候选和历史回退时保存前后模板版本、前后参数 hash、参数 JSON 快照、候选来源、来源历史记录和变更原因。
- 策略计算只读取 `market_minute_archives`，不自动归档分钟线，不修改 STP 成交事实。
- 顶层 UI 拆为「交易复盘」「策略测试」和「实时交易」三个 tab；交易复盘保留成交证据与买卖点，策略测试集中展示配置、单日测试、30 天测试复盘和策略优化，实时交易只展示只读下单信号预览。
- 策略测试页允许手工输入研究标的，并显式拉取该标的最近 30 天（自然日）分钟线归档；该数据准备动作独立于策略 run。
- 策略测试页允许用逗号或空格输入标的组；多标的扫描会逐标的运行数据准备和 30 天测试，每个 symbol 仍保存独立 test batch；策略优化按输入标的组保存一个全局 optimization run、组合 archive scope 和候选证据。
- 测试复盘模块先展示策略整体指标总览，再提供按日期（默认）和按标的两个汇总维度；汇总行只下钻到对应 symbol/day 的单日复盘。
- 策略测试页通过「交易策略配置」操作按钮打开配置弹层，并在策略测试图中叠加 BB bands、策略 EMA、策略 VWAP 和策略开平仓 marker。
- 策略测试日明细和策略信号详情弹层优先从 `GET /api/strategy-runs/{run_id}` 的 `signal_groups` 读取每个开平仓订单组 PnL；旧详情响应缺少 `signal_groups` 时，只能用后端已保存的 exit signal `metrics.pnl_per_share` 与 `exit_fraction` 做展示兼容，不能用图表或 STP 成交自行重算策略收益。

验收：

- 缺分钟线归档显示 `missing_archive`。
- 非 available 归档显示 `non_available_archive`。
- 分钟线不足显示 `insufficient_bars`，warmup 期间不生成信号。
- 策略未开启显示 `strategy_disabled`。
- 重复运行默认复用同一 run；`force=true` 替换同一 run 的指标和信号。
- 最近 30 天自然日窗口内无本地归档时显示 `insufficient_archive_coverage`，不自动拉行情。
- 用户显式拉取最近 30 天（自然日）归档后，仍以已保存 `market_minute_archives` 的 available 覆盖为准；provider 缺数据或失败不补假成功日，策略测试也不会向更早交易日补足。
- 优化候选超过 120 个时拒绝运行；最佳候选只展示，用户显式套用后才更新策略配置。
- 策略配置页展示版本记录；点击回退只恢复历史参数快照并新增 `history_rollback` 记录，不覆盖历史 strategy run、test batch 或 optimization candidate artifact。
- STP committed fills 的价格、数量、时间和证据字段不被策略 run 修改。

## 当前 P1 切片：Trade Replay Groups

目标：成交记录从单笔 fill 改为“每一次开仓至清仓”的交易组，并在 replay 弹层中展示该次交易的分钟蜡烛图、成交量、关键指标和可审计智能评价。

范围：

- 新增 `GET /api/trade-groups?date=YYYY-MM-DD&account=&symbol=`，从 committed `fills` read model 构建交易组，不新增持久化表。
- 交易组按 `account_canonical + symbol`、成交时间和 fill id 顺序配对，支持多头、空头、加仓、部分平仓和未清仓状态。
- Daily summary 的 `trade_group_count`、PnL、胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤复用 closed trade groups，避免 UI 分组和 KPI 口径漂移。
- Replay 弹层只读取本地已归档 `market_minute_archives`，按开仓到清仓窗口自动缩放并保留前后缓冲，叠加组内所有成交点，并展示基于窗口分钟 high/low 的持仓最大回撤追溯；打开弹层不会自动触发行情 provider 拉取。
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
- 新增 `POST /api/market-data/yahoo-minute-archive`、`GET /api/market-data/minute-archives`、`scripts/archive-yahoo-minute-data.py` 和 `scripts/archive-local-minute-db.py` 作为操作入口。
- `POST /api/imports/stp-txt` 导入 committed 后会按本批 `source_batch_id` 下的成交日期和标的触发缺失分钟线归档，并在上传响应中返回归档摘要。
- `POST /api/market-data/yahoo-minute-archive` 可按已提交成交目标归档，也可按手工 `symbol + date + window_trading_days` 归档研究标的最近自然日窗口；`window_trading_days` 是兼容字段名，当前业务语义为最近 N 天；`archive-local-minute-db.py` 可按 `symbols + date + window_trading_days` 批量归档本地研究标的组。
- 复盘页新增日期和标的选择器，按 `trade_date + symbol` 读取归档分钟线，默认显示当前标的第一笔到最后一笔 committed fill 的时间范围，并用 committed fills 标注买卖点。
- 归档目标来自已提交 `fills`，不读取 quarantine 行，不修改 STP 成交事实。
- 启用 Momentum Mean Reversion 时，归档目标还包括同日 QQQ/SMH 策略上下文标的；这些上下文归档的 `source_fill_count` 为 0，策略 run 仍只读取已归档 artifact。

验收：

- 重复运行默认不新增 archive 或 provider attempt。
- 重复上传同一 STP TXT 默认复用既有批次和既有分钟线归档，不新增重复 provider attempt。
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
- 当前策略配置保存初始本金和入场资金比例，默认初始本金为 100000、每次入场使用 20% 资金；策略 run、测试批次和优化候选的 PnL 以运行时参数快照计算资金口径。
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
GET /api/trade-groups?date=YYYY-MM-DD&include_details=false
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
GET   /api/strategy-runs?date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...&limit=20
GET   /api/strategy-runs/{run_id}
POST  /api/strategies/{strategy_id}/test-runs
GET   /api/strategy-test-runs?end_date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...
POST  /api/strategies/{strategy_id}/optimizations
GET   /api/strategy-optimizations?end_date=YYYY-MM-DD&symbol=SYMBOL&strategy_id=...
GET   /api/strategy-optimizations/{optimization_id}
POST  /api/strategies/{strategy_id}/optimization-candidates/{candidate_id}/apply
GET   /api/strategies/{strategy_id}/history
POST  /api/strategies/{strategy_id}/history/{history_id}/rollback
```

P2 策略 API 只返回后端 read model。前端不得自行计算 BB、RSI、VWAP、relative volume、20 EMA、9 EMA、absolute bandwidth、ADX、ATR、market regime、H2/L2 回调、Range Fader 区间边缘或策略入选理由。

`GET /api/strategy-runs` 默认返回轻量摘要并限制历史 run 数量，不返回完整 `indicator_series`、`indicator_series_json` 或 `signals`；图表和单日 drilldown 必须使用 `GET /api/strategy-runs/{run_id}` 或显式详情模式读取完整 artifact source。

`GET /api/review/summary` 和 `GET /api/review/summary-groups` 使用 committed fills 与轻量 trade group 聚合生成首屏 read model；它们可以读取分钟线计算持仓最大回撤，但不得运行完整交易评价模型或返回 replay 详情。`GET /api/trade-groups` 支持 `include_details=false` 作为复盘页首屏轻量列表，不返回组内 fills 和评价因子明细；Replay 详情再用 `include_details=true` 读取完整证据，避免无关详情阻塞复盘页首屏。策略模板、策略配置、strategy runs、test runs 和 optimizations 只在策略工作区激活后加载。

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
- `params_json.initial_capital`
- `params_json.entry_capital_ratio`

策略配置历史记录：

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

`bb_squeeze_breakout_v1` 当前模板版本为 `bb_squeeze_breakout_v1.2`，默认参数为 BB(20, 2)、RSI(14)、前 20 分钟均量、2 倍量能、10% 收缩分位、10 分钟 setup、0.5 实体强度、ATR(14) 1.0 倍止损、ATR 1.5 倍第一目标、9 EMA 出场缓冲和最小绝对带宽 2.0。

策略引擎 `strategy_indicator_engine_v3` 逐 bar 计算指标，只能使用当前 bar 和历史 bar。持仓中不得重复生成 entry；exit signal 必须关联 entry。价格跌回或升回布林带外轨内部本身不再触发出场；多头止损为入场价减 ATR 倍数，第一目标为入场价加 ATR 目标倍数，空头按镜像条件处理；ATR 目标、硬止损、9 EMA 或布林中轨缓冲按优先级触发。ATR 第一目标只在复盘 run 中按 high/low 触达建模，不发送真实限价单。

`institutional_liquidity_sweep_v1` 默认参数为 20 根局部窗口、0.6 影线占比、前 20 分钟均量、1.5 倍放量、BB(20, 2) 中轨目标、1.5:1 盈亏比、0.01 tick、2 个 tick 止损偏移、最多持仓 3 根 K 和 `OCO_Immediate`。策略引擎逐 bar 计算 VWAP、局部高低点、前 5 分钟高低、BB 中轨、相对成交量和影线占比；多头必须在 VWAP 上方扫破局部低点后收回，空头必须在 VWAP 下方扫破局部高点后拒绝。`OCO_Immediate` 只在历史 run 中建模止损、BB 中轨或 1.5:1 被动止盈触达，不发送真实订单。

`momentum_mean_reversion_v1` 默认参数为 BB(20, 2)、ADX(14) 趋势熔断阈值 25、ADX 震荡激活阈值 20、ATR(14) 1.5 倍硬止损、美东 11:30 至 13:30 时间窗口、QQQ+SMH 动能过滤、0.55 Pin Bar 影线占比、近 3 根 K 波谷/波峰上下文和 50% 中轨部分止盈。策略引擎逐 bar 计算目标标的 BB、VWAP、ADX、ATR、market regime、QQQ/SMH close 与 VWAP、时间窗口和动能方向；ADX 高于趋势阈值时均值回归熔断并生成 0 信号，ADX 低于震荡阈值后才重新激活。多头必须在 QQQ 与 SMH 同时位于 VWAP 上方时，等待目标标的跌破下轨后以 Pin Bar 或阳线吞没重新收回下轨；空头按镜像条件处理。硬止损按入场价加减 ATR 倍数计算；触及中轨后生成部分止盈信号，并把剩余仓位止损上移至入场价；触及对侧外轨或 break-even 止损后生成剩余仓位出场信号。该策略不自动下单，不修改 committed fills。

`one_minute_trend_rider_v1` 默认参数为 20 EMA 趋势生命线、9 EMA 追踪出场、前 20 分钟均量、2 倍突破量能、0.8 回调缩量比例、2 根强突破 K、6 根趋势确认窗口、30 根最长回调窗口、30 根早盘区间、5 根 EMA 斜率窗口、0.02 最小 EMA 斜率、0.65 突破实体强度、0.5 入场实体强度、0.01 tick 和 4 tick 止损偏移。策略引擎逐 bar 计算 VWAP、20 EMA、9 EMA、EMA slope、opening range、relative volume 和 Always In 趋势方向；多头必须在 VWAP 与 20 EMA 上方强突破早盘高点，空头按镜像跌破早盘低点。入场必须等待 H2/L2 二级回调、回踩/反抽 20 EMA、回调缩量和触发 K 收回/跌回 20 EMA；硬止损取二级回调波谷/波峰和 20 EMA 外侧 tick 偏移中更保守的一侧。策略不保存静态止盈，`take_profit_price` 为空，只用硬止损或 9 EMA 收盘破位出场；该策略不自动下单，不修改 committed fills。

`one_minute_range_fader_v1` 当前展示名为 `PA-1min边缘狙击反转策略v1.1`，当前模板版本为 `one_minute_range_fader_v1.1`，默认参数为 45 根区间识别窗口、上下沿各 2 次触边、顶部/底部 25% 边缘区、20 EMA 磁铁、10 根 EMA 斜率窗口、最大 EMA 斜率 0.03、至少 8 根 K 穿越 EMA、6 tick 触边容差、2 tick 硬止损、50% 中轴平仓比例、最长持仓 30 根 K 和最小区间高度 0.2。策略引擎 `strategy_indicator_engine_range_fader_v2` 逐 bar 计算区间上下沿、中轴线、VWAP、20 EMA、EMA 钝化、EMA 穿越次数和 dead zone；多头必须在下沿边缘假跌破或拒绝后出现长下影或强看涨反转 K，空头按上沿假突破镜像处理。入场使用下一根 K 开盘价；第一目标为区间中轴线并按参数比例部分止盈，触达后剩余仓位止损强制上移到入场价；第二目标为对侧区间边缘，硬止损、break-even 止损和最长持仓仍按后端出场信号记录。该策略不自动下单，不修改 committed fills。

策略测试批次记录：

- `archive_scope_hash`
- `params_json`
- `params_hash`
- `window_trading_days`
- `coverage_ratio`
- `total_pnl`，按 `initial_capital * entry_capital_ratio / entry_price` 换算策略仓位
- `win_rate`
- `profit_factor`
- `max_drawdown`
- 逐日 `strategy_run_id`、`bars_hash`、`indicator_hash` 和失败状态

策略优化记录：

- `symbol_scope` 和 `symbols[]`
- `search_space_json`
- `search_space_hash`
- `objective=stable_profitability_v1`
- candidate `params_json`
- candidate `day_results_json`，逐条保存 `symbol + trade_date` 结果
- candidate `total_pnl`，与测试批次使用同一资金口径
- `stability_score`

默认优化网格来自策略模板参数 schema，硬上限 120 个 candidate。多标的优化在同一 candidate 参数组上汇总所有输入标的的逐日结果，并以全局 `stability_score` 排名。优化只保存候选，不自动覆盖 `strategy_configs`。只有 `POST /api/strategies/{strategy_id}/optimization-candidates/{candidate_id}/apply` 会套用 eligible candidate，更新当前配置的 `params_json`、`params_hash` 和当前模板版本，并写入配置历史；`POST /api/strategies/{strategy_id}/history/{history_id}/rollback` 只从历史记录的参数快照恢复当前配置并写入新的 `history_rollback` 记录；历史 run、test batch 和 optimization candidate 的 artifact source 不被改写。

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
- 启动前会验证后端 `healthz`、复盘汇总 API、P2 必需 API 路由、`GET /api/strategy-runs/{run_id}` 详情路由、亏损复盘保存路由和策略模板；前端 ready 还必须通过 Vite 代理读取 `/openapi.json` 并命中同一合同，同时在短暂可用后复查一次。如果默认端口上是旧后端，正常启动会自动切到备用后端和前端端口，避免前端连到会返回旧版大 payload、404 或短命 fallback 页面。
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
- BB Squeeze long/short entry、ATR stop、ATR target exit、warmup 无信号和无未来函数。
- Institutional Liquidity Sweep long/short sweep entry、OCO 止盈、止损、影线不足拒绝和 run artifact 保存。
- Momentum Mean Reversion long/short 动能过滤、11:30-13:30 时间过滤、ADX 趋势熔断、ATR 动态止损、反转形态、缺 QQQ/SMH 归档、部分止盈、break-even 止损和组合输入 hash 保存。
- Trend Rider long H2 entry、short L2 entry、9 EMA 追踪出场、硬止损、回调未缩量拒绝、run artifact 保存和不修改 committed fills。
- PA-1min边缘狙击反转策略v1.1：long/short 边缘假突破、下一根开盘入场、中轴部分止盈、break-even stop、对侧边缘最终目标、dead zone 拒绝、run artifact 保存和不修改 committed fills。
- Multi-Ticker Screener：逗号分隔标的组、输入后每个标的即时显示待运行或最新批次状态、历史重复批次只取最新展示、策略整体指标总览、按日期默认汇总、按标的汇总、单日复盘下钻、逐标的 30 天测试、逐标的优化、覆盖不足仍保存失败状态且不自动拉行情。
- Strategy API 模板、配置、新增、启停、缺归档、可用归档、重复运行和 force 重跑。
- Strategy test batch：v5 schema、最近 30 天自然日窗口内无归档、非 available 归档、只读归档、逐日 run 证据和幂等。
- Strategy PnL：默认初始本金、默认 20% 入场资金比例、单日 run、30 天测试和优化候选资金 PnL 口径一致。
- Strategy optimization：候选上限、默认网格、重复运行、force 重跑、最佳候选追溯和不自动改配置。
- Strategy config history：模板版本回填、优化候选套用、重复套用幂等、变更原因和历史 run artifact 不被覆盖。
- Integration：策略 run 保存 source archive、bars hash、indicator hash，且 committed fills 不被修改。

### UI Acceptance

- 上传后能看到批次状态。
- 失败行显示字段和修复建议。
- 30 秒内找到一笔交易。
- 交易详情展示证据 row 和 market context 状态。
- 用户可以打标签并写复盘结论。
- 策略配置可添加、保存参数、开启、运行、查看版本记录并从可回退历史记录恢复参数；策略信号能叠加在分钟蜡烛图上。

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
