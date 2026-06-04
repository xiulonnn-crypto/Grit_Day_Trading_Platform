# Grit Day Trading Platform

## P2 交易策略配置与历史信号复盘

- 复盘台顶层拆分为「交易复盘」和「策略测试」两个工作区；交易复盘只保留成交证据、分钟线、买卖点、Watchlist、交易组和批次证据，策略研究集中到策略测试。
- 交易复盘工作区头部展示有记录以来的 committed fills 汇总，并支持按交易日或按标的下钻；选择具体日期+标的后进入分钟蜡烛和交易组复盘模块，成交组会展示来自分钟线最值的持仓最大回撤追溯。
- 策略测试工作区按「策略配置」「策略测试」「测试复盘（最近30个交易日）」「策略优化」组织，避免把成交复盘和参数研究混在同一个操作面板。
- 复盘台提供「交易策略配置」操作按钮，可打开配置弹层，从模板添加策略、编辑参数、开启或关闭策略。
- `POST /api/strategies/{strategy_id}/test-runs` 会基于所选标的截至日期的最近 30 个已归档交易日分钟线生成 strategy test batch；归档覆盖不足时保存可见失败状态，不自动拉行情。
- 策略测试页可手工输入研究标的，并通过分钟线归档操作为该标的准备最近 30 个交易日数据；该动作属于显式数据准备，不会在策略 run 中自动触发。
- `POST /api/strategies/{strategy_id}/optimizations` 会用默认参数网格运行可追溯优化，保存候选参数、逐日结果和稳定性排序；最佳候选只展示，必须由用户显式套用后才会更新策略配置。
- 当前内置策略包括 `1分钟布林带收缩突破策略 (BB Squeeze Breakout)`、`1分钟机构流动性掠夺策略 (Institutional Liquidity Sweep)` 和 `1分钟动能过滤均值回归策略 (Momentum Mean Reversion)`。
- BB Squeeze 默认参数为 BB(20, 2)、RSI(14)、前 20 分钟均量、2 倍量能、10% 收缩分位、10 分钟 setup、9 EMA 出场缓冲、最小绝对带宽 2.0 和 2:1 被动止盈目标。
- Liquidity Sweep 默认参数为 20 根局部窗口、0.6 影线占比、前 20 分钟均量、1.5 倍放量、BB(20, 2) 中轨目标、1.5:1 盈亏比、2 个 tick 止损偏移、最多持仓 3 根 K 和 `OCO_Immediate` 历史出场模式。
- Momentum Mean Reversion 默认只在美东 11:30 至 13:30 执行，要求 QQQ 与 SMH 同时在各自 VWAP 上方或下方；后端会用 ADX 区分趋势/震荡，趋势熔断时均值回归生成 0 信号，震荡恢复后才等待目标标的跌破或冲破 BB(20, 2) 并以 Pin Bar 或吞没形态收回布林带内入场；硬止损按 1 分钟 ATR 动态计算，并按中轨部分止盈、对侧外轨最终止盈和 break-even 止损建模。
- 策略运行只读取已保存的 `market_minute_archives`，不会自动拉行情，也不会修改 STP 成交价格、数量或时间。
- Momentum Mean Reversion 额外读取同日已归档的 QQQ 和 SMH 分钟线作为动能过滤输入；缺任一归档时保存缺归档状态，不渲染成功信号。
- 启用 Momentum Mean Reversion 后，Yahoo 分钟线归档会把同日 QQQ 和 SMH 作为策略上下文目标一起归档；策略 run 仍然只读取已归档 artifact。
- 被动止盈和 `OCO_Immediate` 只在历史策略 run 中按 high/low 触达建模为出场信号，不会向券商或 STP 发送真实限价单。
- `POST /api/strategies/{strategy_id}/runs` 会生成可追溯的 strategy run，保存 `source_archive_id`、`bars_hash`、指标序列、`indicator_hash` 和开平仓信号。
- 每次单日 run 会保存当时的 `params_json`，策略配置后续变更不会改写历史 run 的参数解释。
- 分钟蜡烛图会叠加 BB bands、策略 VWAP 和策略开平仓 marker；实际成交 marker 仍只来自 committed fills。
- 缺分钟线归档、非可用行情或分钟线不足时会显示策略 run 状态，不渲染假信号。

## P1 Yahoo 离线分钟线归档

- P1 现在可以从已提交成交记录推导有交易日的标的，并用 Yahoo Finance 获取 1 分钟线归档。
- 如果启用了需要动能过滤的均值回归策略，同日 QQQ/SMH 会作为零成交数的策略上下文目标纳入归档队列。
- 归档入口是 `POST /api/market-data/yahoo-minute-archive`，读取入口是 `GET /api/market-data/minute-archives`。
- 归档入口支持按已提交成交目标批量归档，也支持手工指定 `symbol + end_date + window_trading_days` 拉取研究标的的最近交易日分钟线。
- 离线脚本入口是 `python scripts/archive-yahoo-minute-data.py --date YYYY-MM-DD`；不传日期时会扫描所有已提交成交涉及的交易日和标的。
- 复盘页支持按日期和标的读取已归档分钟线，分钟蜡烛图会自动缩放到该标的第一笔到最后一笔 committed fill，并把买卖点叠加到图上。
- 归档只写入 `market_minute_archives` 和 provider attempt 记录，不会修改 STP 成交价格、数量或时间。
- 每条归档保存 `bars_hash`、`bars_json`、VWAP、当日高低、成交量上下文、provider 状态和归档版本。

## P1 Market Context And Watchlist

P1 已接到当前 P0-only 基线。STP TXT 和 committed fills 仍是成交真相源，行情只作为复盘上下文进入 snapshot，不会改写成交价格、数量或时间。

- Market Context Replay：`POST /api/market-context/replay` 会按 `fill_id + provider + requested_start + requested_end` 固化 snapshot，并保存 `bars_hash`、VWAP、当日高低、成交量环境和数据状态。
- Market Context Read：`GET /api/fills/{fill_id}/market-context` 与 `GET /api/market-context/{snapshot_id}` 只读取已保存 snapshot。
- Watchlist：`POST /api/watchlist/generate` 与 `GET /api/watchlist?date=YYYY-MM-DD` 返回 provider summary 生成的关注列表，每个 symbol 都带 `reason_codes`、`metrics` 和 `metrics_hash`。
- 数据状态：`available`、`partial`、`missing`、`provider_failed`、`timezone_conflict` 都会进入 API/UI read model；provider failure 不会渲染成正常图表。
- 自动验收使用 fake provider；live Futu adapter 保持可替换占位。

验收证据见 [docs/p1_acceptance.md](./docs/p1_acceptance.md)。

Grit Day Trading Platform 是个人日内交易闭环 Web 系统。首版目标不是做自动下单，也不是做漂亮但不可追溯的报表，而是稳定回答两个问题：

- STP 最终实际成交了什么？
- 这些成交是否能追溯到原始证据？

当前项目处于文档基线阶段。本文档把 2026-06-02 的 CEO Review 补强版确认为第一版产品和工程事实源，后续实现必须同步更新 [ARCHITECTURE.md](./ARCHITECTURE.md)、[TECHNICAL.md](./TECHNICAL.md)、[AGENTS.md](./AGENTS.md) 和 [CHANGELOG.md](./CHANGELOG.md)。

## 当前范围

- 使用 STP TXT 作为订单、委托和成交真相源。
- P0 只支持导入证据账本、异常隔离、幂等导入、解析版本留痕和基础复盘指标。
- P0 前端只做复盘台：上传、批次状态、异常行、成交列表、PnL、胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤。
- P1 前端在复盘台展示盘前 watchlist、成交市场上下文和已归档分钟蜡烛图。
- P2 前端在复盘台展示策略配置、历史策略 run 和策略开平仓信号。
- 富途行情和成交市场上下文重建属于 P0 之后能力，不能覆盖 STP 成交真相。

## 当前实现状态

- 已初始化 FastAPI + SQLite + React/Vite scaffold。
- 已实现 `POST /api/imports/stp-txt`、批次查询、quarantine 查询、fills 查询和 daily summary。
- 已实现 STP TXT parser、字段映射诊断、账号 canonicalization、parser/mapping version 留痕。
- 已支持无表头成交 TXT 按 `日期、时间、标的、买卖、股数、价格、账号、通道` 自动补字段合同；第 9 列存在时作为 `order_id`。
- 已支持旧 parser 造成的零行 file-level 失败批次在新 parser 下重解析，避免同一文件永远返回旧失败状态。
- 已支持缺 execution id 的重复成交行逐行入账，并在 daily summary 中展示配对交易股数。
- 已支持跨批次重导的成交 read-model 去重：原始批次和 evidence rows 保留，成交列表和 KPI 不重复计算同一批修正重导。
- 已支持按平仓 round-trip 计算 PnL、胜率、盈亏比、单笔期望值和每股净收益：每次 B&S 或 S&B 回到平仓状态才算一笔交易；复盘指标中的持仓最大回撤只读引用已归档分钟线 high/low，不改写成交事实。
- 已实现 storage migration marker、唯一索引、账号 canonicalization trigger 和幂等写入。
- 已实现 P0 复盘台骨架，展示上传、批次、异常行、成交表和基础 KPI。

## 不在首版范围

- 不自动下单。
- 不做期权链。
- 不做多用户或商业化权限体系。
- 不做全市场实时扫描。
- 不让富途行情覆盖 STP 成交真相。

## 事实源边界

| 领域 | 事实源 | 用途 | 禁止行为 |
| --- | --- | --- | --- |
| 订单与成交 | STP TXT 原始文件和证据账本 | 订单、成交、取消、部分成交、跨日成交的最终真相 | 用富途或 UI 手工数据覆盖成交 |
| 市场上下文 | 富途行情 | 分钟线、VWAP、当日高低、成交量环境、watchlist 信号 | 行情缺失时展示空图冒充成功 |
| 复盘结论 | Review Journal | 标签、错误分类、改进结论 | 把主观复盘当作成交真相 |

## 路线图

### P0

- STP TXT 导入。
- STP Evidence Ledger。
- 异常行 quarantine。
- 订单和成交标准化。
- 基础复盘指标。

### P1

- 盘前 watchlist。
- Market Context Replay。
- 图表化复盘。

### P2

- 交易策略配置。
- 历史分钟线策略信号复盘。
- 蜡烛图叠加策略指标、开仓信号和平仓信号。
- 信号只做复盘和提示，不触发下单。

### P3

- 信号采纳率。
- 误报率。
- 计划执行质量。
- 规则改进反馈。

## 首版验收

首版可用性验收以真实交易工作流为准：

- 导入真实 STP TXT 样例后，用户必须能看到成功批次、失败批次、失败行、失败字段和修复建议。
- 无表头成交 TXT 应按默认字段合同解析；第 9 列存在时作为 `order_id`，不能停在 file-level `missing_header`。
- 同一文件、同一 order id、同一 execution id 重复导入不得重复记账。
- 同一成交文件因补表头、编码或尾部空行导致文件 hash 变化后重导，不得让成交列表和 KPI 双倍计数。
- 一笔成交必须能追溯到原始文件 hash、原始行、parser version 和字段映射版本。
- 缺 execution id 的重复成交行不得因字段完全相同而被压成一笔。
- 行情缺失必须显示为 `缺数据`，不能渲染成正常图表。
- 导入后 30 秒内，用户应能找到一笔交易、看到证据追溯字段、打标签并写复盘结论。

## 文档导航

- [ARCHITECTURE.md](./ARCHITECTURE.md)：系统边界、事实源矩阵、数据流、存储合同和失败语义。
- [TECHNICAL.md](./TECHNICAL.md)：当前技术计划、阶段切片、接口草案、测试策略和开放问题。
- [AGENTS.md](./AGENTS.md)：Codex 和后续工程 agent 的操作规则、交付门禁和变更纪律。
- [CHANGELOG.md](./CHANGELOG.md)：公开变更记录。
- [docs/p0_acceptance.md](./docs/p0_acceptance.md)：P0 DB/API/UI read-model 一致性和验收证据。
- [designs/2026-06-03-review-desk-layout/spec.md](./designs/2026-06-03-review-desk-layout/spec.md)：复盘台主图优先、盘前工作栏和导入证据区布局规格。

## P0 API

- `POST /api/imports/stp-txt`：上传 STP TXT，返回 `batch_id`、`file_hash`、`status`、`accepted_rows`、`quarantined_rows`。
- `GET /api/imports/{batch_id}`：查看批次状态、parser version、mapping version 和错误摘要。
- `GET /api/imports/{batch_id}/quarantine`：查看异常行、原始文本、失败字段、失败原因和修复建议。
- `GET /api/fills`：按日期、账号、symbol 查询 committed 成交 read-model；跨批重导的同一 fallback 成交只展示最新批次。
- `GET /api/review/daily-summary?date=YYYY-MM-DD`：查看只基于 committed 成交 read-model 计算的 PnL、胜率、盈亏比、单笔期望值、每股净收益、持仓最大回撤、成交数量和异常行数量；这些核心 KPI 按已平仓 round-trip 和成交组分钟线追溯统计。
- `GET /api/review/summary`：按全局、日期或标的范围查看 committed fills 汇总。
- `GET /api/review/summary-groups`：按交易日或标的返回下钻汇总，供复盘页选择具体日期+标的。

## P2 API

- `GET /api/strategy-templates`：查看可添加的策略模板和默认参数。
- `GET /api/strategies`：查看当前策略配置。
- `POST /api/strategies`：新增模板策略实例。
- `PATCH /api/strategies/{strategy_id}`：更新策略名称、参数或启停状态。
- `POST /api/strategies/{strategy_id}/runs`：对指定日期和标的运行历史策略复盘。
- `GET /api/strategy-runs?date=YYYY-MM-DD&symbol=SYMBOL`：读取策略 run、指标序列和信号。
- `POST /api/strategies/{strategy_id}/test-runs`：按最近 30 个已归档交易日运行批量策略测试。
- `GET /api/strategy-test-runs?end_date=YYYY-MM-DD&symbol=SYMBOL`：读取策略测试批次和逐日结果。
- `POST /api/strategies/{strategy_id}/optimizations`：按默认参数网格运行策略优化。
- `GET /api/strategy-optimizations?end_date=YYYY-MM-DD&symbol=SYMBOL`：读取优化 run 列表。
- `GET /api/strategy-optimizations/{optimization_id}`：读取优化候选参数和逐日证据。

## 登录快捷方式

Windows 下可双击根目录的 `Login-Grit-DayTrading.cmd` 进入本地复盘台。它会检查 Python、npm、复盘汇总 API 和 P2 必需 API 路由，优先复用默认后端和前端端口，并自动打开浏览器；如果默认后端端口上已有旧服务但缺少复盘汇总、P2 路由或策略模板，会自动切到备用后端和前端端口启动，并把前端代理指向备用后端，避免复盘页出现 API 404。

如果备用后端已监听但复盘 API 返回 500，启动器会按后端运行态失败处理，并打印相关端口 owner PID；通常需要先关闭占用默认后端端口的旧进程，再重新运行启动入口。

```powershell
.\Login-Grit-DayTrading.cmd
```

只做快捷方式自检、不启动服务；如果当前后端正在运行，也会验证必需 API 路由。`--check` 保持只读，不会自动切换备用端口：

```powershell
.\Login-Grit-DayTrading.cmd --check
```

如需分别查看服务控制台，可使用：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-frontend.cmd
```

## 固定验证命令

```powershell
python -m pytest -q
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
```

## 实现原则

- 先固定真实 STP TXT fixture，再写解析器。
- 证据账本优先于展示报表。
- parser version 和 field mapper version 必须随记录保存。
- 账号字段必须执行 `strip().upper()` canonicalize，同时保留原始账号文本。
- STP 与富途只做互相引用，不互相覆盖。
- 自动信号只做复盘和提醒，首版不进入下单链路。
