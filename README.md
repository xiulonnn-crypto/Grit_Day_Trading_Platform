# Grit Day Trading Platform

## 最新交易回测更新

- 本地「交易复盘」新增第四个子 tab「交易回测」，复用全部、本月、本周和特定时间段筛选；进入页面只读取当前范围最近一次结果，只有点击「运行四组回测」才会开始计算。GitHub Pages 静态快照首版仍保留现有三个复盘模块。
- 每次运行同时输出 committed fills 基准、单轮持仓上限 200 股、全账户当日组合亏损达到 1000 USD 后强制清仓并停手，以及两项规则组合后的四组结果；桌面端用对比表展示，窄屏自动切换为四张场景卡。
- 「交易回测」新增 A × B 参数组合优化：可分别输入多组单轮单边持仓上限与每日组合亏损线，按同一成交和分钟线证据运行最多 120 组候选，展示最佳组合、收益矩阵和 Top 10；完整候选账本会保留，页面不会自动套用或修改交易规则。
- 默认搜索 A=`50、100、150、200、300、500、1000` 股与 B=`500、1000、1500、2000、2500、3000、3500、4000、4500、5000` USD，共 70 组；自定义搜索仍受最多 120 组候选和基础数值校验约束。以总盈亏最大为固定目标，平局时依次优先更低的持仓上限和更低的每日亏损线，避免前端自行挑选“最佳值”。
- 回测指标、限仓数量、强制清仓、止损触发和拦截证据全部由后端 read model 计算；页面不自行计算，也不会给出应采用哪条规则的结论或修改策略配置。
- 分钟级止损只读取已保存的分钟归档。归档结构与 hash 有效但未完整覆盖成交窗口时，规则 B/C 会跳过缺失分钟并继续使用已有证据；归档仅有局部质量异常时会忽略整个受影响的日期/标的，避免坏价格进入风控。两类情况都会显示忽略数量；归档缺失、provider 失败或结构/hash 校验失败仍会明确阻断，跨日持仓和未闭合轮次首版也不显示伪造零值。
- 四场景设计规格、响应式布局和事实源 trace matrix 见 [`designs/2026-08-03-trade-backtest-tab/`](./designs/2026-08-03-trade-backtest-tab/)；组合优化规格与矩阵设计见 [`designs/2026-08-03-trade-backtest-optimization/`](./designs/2026-08-03-trade-backtest-optimization/)。两个切片均沿用既有复盘视觉语言，不新增全局 `DESIGN.md`。

## 云端交易复盘快照

- GitHub Pages 根入口同步本地「数据下钻」「盈亏复盘」「交易总结」三个复盘模块，支持模块切换、月份翻页、日期选择、时间范围、盈亏模式、矩阵维度、排序和分页。
- 云端数据由本地 committed fills、Review Journal、分钟归档证据与交易总结 read model 导出；统计口径与本地一致，但账号、原始 STP 行、批次追溯和内部调试字段不会进入公开快照。
- 静态快照带稳定 `source_hash` 并在浏览器内重新核对闭合交易数、交易股数与 PnL；文件缺失或校验失败时页面明确阻断，不会继续显示旧数字或空成功态。

## 最新交易总结更新

- 「交易复盘」下新增第三个子 tab「交易总结」，与「盈亏复盘」共享全部、本月、本周和特定时间段筛选；交易总结始终同时分析该范围的盈利、亏损和持平闭合交易，盈亏单单选仍只属于盈亏复盘。
- 个性化推荐采用严格样本门槛：至少 20 笔闭合交易，且盈利、亏损各至少 5 笔。未达标时只显示经典日内交易基线、样本缺口和准备进度，不允许生成 AI 摘要。
- 推荐规则、排序和证据由后端 `intraday_review_rule_catalog_v2` 确定；规则卡直接展示可执行参数，包括等待 K 线数、量能倍数、ATR 距离、单笔风险、分批止盈比例、R 倍数、时间止损和当日停手线。支持笔数、支持率和影响金额只保留在后端审计证据，不作为推荐规则主文案。
- AI 摘要由当前 Codex 会话基于脱敏聚合证据生成，并以 `codex_session` artifact 写入 `trade_summary_generations` 后由页面直接展示；浏览器不会自动或手动调用模型。摘要必须匹配当前 `summary_key`、提示词版本和全部规则 ID，不能新增数字、规则或交易结论；证据变化后旧摘要进入 `stale`。
- `POST /api/review/trade-summary/generations` 仍保留为可选的后端本地模型兼容入口，使用 `GRIT_REVIEW_LLM_BASE_URL`、`GRIT_REVIEW_LLM_MODEL` 和可选的 `GRIT_REVIEW_LLM_API_KEY`；地址只允许包含 `/v1` 的本机 loopback，前端交易总结页不主动调用该入口。

## 最新下钻复盘更新

- 「成交记录」模块新增「仅看亏损单」勾选项，并同步收窄上方分钟蜡烛图的买卖点；模块不再提供单独「复盘」操作按钮；已平仓亏损交易组可在 Trade Replay 弹层的订单明细下方选择开仓信号、平仓信号或误操作下的精简亏损原因；该记录进入 Review Journal，不会修改 STP 成交价格、数量或时间。
- 「数据下钻」tab 现在先展示全部、本月、本周或特定时间段筛选，再展示该时间范围内全部订单统计指标和月日历；「月日历下钻」可切换为每日表格，查看成交数、股数、PnL、胜率、盈亏比、单笔期望值、每股净收益、MFE 和 MAE，并把当前范围导出为同口径 Excel 兼容工作簿。列表不重复展示已平仓/未平仓列，桌面端自动贴合容器，窄屏改为逐日指标卡片，避免横向滚动。头部汇总、当前每日指标和成交记录均用 MFE/MAE 取代持仓最大回撤，并提供「?」名词解释。历史 MFE/MAE 会从 committed fills 与已保存分钟线重新计算，启动入口会拒绝缺少当前 excursion 合同的旧后端。日历仍按天展示股数与 PnL，点击有订单的日期方块即可选中该日并在右侧进入标的下钻，当前复盘日期、标的和指标位于月日历下方。
- 「下钻复盘」包含「数据下钻」「盈亏复盘」和「交易总结」三个模块 tab；热力时间矩阵位于「盈亏复盘」。盈亏复盘默认展示全部订单，也可切到仅看盈利单或仅看亏损单；所选时间段会统一控制统计指标、热力时间矩阵和订单列表，亏损视图额外展示一级/二级原因饼图联动筛选。全部订单热力时间矩阵可在 ATR 时间矩阵与股数时间矩阵之间切换：ATR 视图按开仓 1min K 振幅 / 前 20 根 ATR 分层，股数视图按每笔已平仓交易组的配对股数分档并在右侧展示 Y 轴收益、订单数和股数汇总；两种矩阵均保持只读，仍只写 Review Journal。

## 最新信号面板更新
- 「下单信号」模块展开当前监控窗口内后端 `signals[]` 的真实 BUY/SELL 信号订单，展示标的、订单意图、操作类型、信号价、股数、触发时间和 bar index；开仓单额外展示止损/止盈，股数由后端按策略初始本金和入场资金比例计算，关仓单不展示止损/止盈并显示后端平仓原因标签；HOLD、失败、完整策略动作、状态、版本、provider、原因码和 hash 证据保留在「原因与证据」模块。
- `Login-Grit-DayTrading.cmd` 会校验前端是否包含当前实时交易 UI 指纹，并在打开浏览器时携带版本参数，避免重登后继续看到旧实时交易模块。

## 最新实时交易监控更新
- 「实时交易」工作区支持标的下拉多选，行情源默认 Yahoo；点击「开启监控」后每 30 秒按所选策略和标的读取最新实时分钟线，并展示后端只读 BUY/SELL/HOLD 信号、原因码、最新策略版本和证据 hash。

## P2 交易策略配置、AI 推荐与历史信号复盘

- 复盘台顶层包含「交易复盘」「策略测试」「AI策略」和「实时交易」四个工作区；交易复盘只保留成交证据、分钟线、买卖点、Watchlist、交易组和批次证据，策略测试集中配置与历史测试，AI策略只读展示 Top 5 推荐，实时交易只做只读信号预览。
- 「AI策略」v2 以 100,000 USD 本金和单次 20% 入场资金为固定比较口径，推荐 5 分钟开盘区间突破、15 分钟开盘区间突破回踩、VWAP 开盘驱动、VWAP 趋势回踩和尾盘半小时动量五个新模板；同口径本地证据达标时展示每笔闭合信号期望 PnL、窗口总 PnL、胜率、Profit Factor、最大回撤、完成日和排除日，旧五模板仅保留历史追溯。
- 复盘台新增「实时交易」工作区，可下拉选择策略和标的，用 Futu、Yahoo 或 Fake provider 的实时分钟线生成只读 BUY/SELL/HOLD 信号、下单原因和证据 hash，并展示最新策略版本号；该工作区不自动下单，也不修改 STP 成交事实。
- 交易复盘工作区头部展示有记录以来的 committed fills 汇总，并支持按交易日或按标的下钻；选择具体日期+标的后进入分钟蜡烛和交易组复盘模块，成交组会展示按成交路径和分钟线最值追溯的持仓最大回撤。
- 策略测试工作区按「策略配置」「策略测试」「测试复盘（最近30天）」「策略优化」组织；测试复盘先展示策略整体指标，再按日期或按标的汇总下钻到单日复盘，避免把成交复盘和参数研究混在同一个操作面板。
- 复盘台提供「交易策略配置」操作按钮，可打开配置弹层，从模板添加策略、编辑参数、开启或关闭策略，并查看策略版本记录或回退到历史参数快照。
- `POST /api/strategies/{strategy_id}/test-runs` 会基于所选标的截至日期最近 30 天（自然日）内的本地已归档分钟线生成 strategy test batch；窗口内没有归档时保存可见失败状态，不自动拉行情，也不向更早交易日补足。
- 策略测试页可手工输入单个研究标的，也可输入逗号分隔的标的组；分钟线归档和 30 天测试会逐标的保存独立证据，策略优化会按输入标的组保存一个全局综合 run，该数据准备动作不会在策略 run 中自动触发。
- 策略配置新增初始本金和入场资金比例，默认初始本金为 100000、每次入场使用 20% 资金；单日复盘、30 天测试和优化候选的 PnL 都按后端资金模型换算。
- `POST /api/strategies/{strategy_id}/optimizations` 会用默认参数网格运行可追溯优化；传入 `symbols[]` 时会在同一 candidate 上汇总所有标的的逐日结果并选出全局综合最优，最佳候选只展示，必须由用户显式套用后才会更新策略配置、当前模板版本和配置变更历史。
- 当前内置策略包括 `1分钟布林带收缩突破策略 (BB Squeeze Breakout)`、`1分钟机构流动性掠夺策略 (Institutional Liquidity Sweep)`、`1分钟动能过滤均值回归策略 (Momentum Mean Reversion)`、`1分钟趋势中继策略 (Trend Rider)` 和 `PA-1min边缘狙击反转策略v1.1`。
- BB Squeeze 默认参数为 BB(20, 2)、RSI(14)、前 20 分钟均量、2 倍量能、10% 收缩分位、10 分钟 setup、ATR(14) 1.0 倍止损、ATR 1.5 倍第一目标、9 EMA 出场缓冲和最小绝对带宽 2.0。
- Liquidity Sweep 默认参数为 20 根局部窗口、0.6 影线占比、前 20 分钟均量、1.5 倍放量、BB(20, 2) 中轨目标、1.5:1 盈亏比、2 个 tick 止损偏移、最多持仓 3 根 K 和 `OCO_Immediate` 历史出场模式。
- Momentum Mean Reversion 默认只在美东 11:30 至 13:30 执行，要求 QQQ 与 SMH 同时在各自 VWAP 上方或下方；后端会用 ADX 区分趋势/震荡，趋势熔断时均值回归生成 0 信号，震荡恢复后才等待目标标的跌破或冲破 BB(20, 2) 并以 Pin Bar 或吞没形态收回布林带内入场；硬止损按 1 分钟 ATR 动态计算，并按中轨部分止盈、对侧外轨最终止盈和 break-even 止损建模。
- Trend Rider 默认使用 VWAP、20 EMA、9 EMA 和相对成交量识别 Always In 趋势突破；强突破后等待 H2/L2 二级回调、回调缩量和 20 EMA 收回/跌回确认入场，不设静态止盈，只用硬止损或 9 EMA 收盘破位退出。
- PA-1min边缘狙击反转策略v1.1 默认回看最近 45 根 1 分钟 K，要求震荡区间上下沿各至少 2 次触边、20 EMA 钝化、至少 8 根 K 穿越 EMA；只在区间顶部或底部 25% 边缘等待假突破反转，下一根 K 开盘入场；第一目标为区间中轴线并按 50% 分批止盈，触达后剩余仓位止损上移到保本价，第二目标为对侧区间边缘。
- 策略运行只读取已保存的 `market_minute_archives`，不会自动拉行情，也不会修改 STP 成交价格、数量或时间。
- Momentum Mean Reversion 额外读取同日已归档的 QQQ 和 SMH 分钟线作为动能过滤输入；缺任一归档时保存缺归档状态，不渲染成功信号。
- 启用 Momentum Mean Reversion 后，分钟线归档会把同日 QQQ 和 SMH 作为策略上下文目标一起归档；策略 run 仍然只读取已归档 artifact。
- 被动止盈和 `OCO_Immediate` 只在历史策略 run 中按 high/low 触达建模为出场信号，不会向券商或 STP 发送真实限价单。
- `POST /api/strategies/{strategy_id}/runs` 会生成可追溯的 strategy run，保存 `source_archive_id`、`bars_hash`、指标序列、`indicator_hash` 和开平仓信号。
- `GET /api/strategy-runs/{run_id}` 会返回按 entry/exit 配对的 `signal_groups`，每个订单组的资金 PnL 由后端 run read model 按初始本金和入场资金比例计算；旧详情响应缺少 `signal_groups` 时，前端只读取后端 signal metrics 里的收益证据做兼容展示，未闭合或缺证据时显示 N/A。
- 每次单日 run 会保存当时的 `params_json`，策略配置后续变更不会改写历史 run 的参数解释。
- 分钟蜡烛图会叠加 BB bands、策略 EMA、策略 VWAP 和策略开平仓 marker；实际成交 marker 仍只来自 committed fills。
- 缺分钟线归档、非可用行情或分钟线不足时会显示策略 run 状态，不渲染假信号。

## P1 本地分钟线归档与备选行情

- P1 从已提交成交记录推导有交易日的标的，优先用 Yahoo Finance 获取 1 分钟线；Yahoo 拒绝、失败、返回不完整数据、出现与前后行情不连续的孤立异常柱，或对有 committed fills 的目标返回空数据时，自动尝试 Futu 历史 1 分钟 K 线。
- 上传 STP TXT 成功后，会按本批 committed fills 的日期和标的检查本地分钟线；缺失时补写分钟线归档和逐 provider attempt，重复上传仍复用既有归档。
- 如果启用了需要动能过滤的均值回归策略，同日 QQQ/SMH 会作为零成交数的策略上下文目标纳入归档队列。
- 兼容归档入口仍是 `POST /api/market-data/yahoo-minute-archive`，读取入口是 `GET /api/market-data/minute-archives`；读取不限定 provider，按 `trade_date + symbol` 优先返回可用本地归档。
- 归档入口支持按已提交成交目标批量归档，也支持手工指定 `symbol + end_date + window_trading_days` 拉取研究标的最近自然日窗口分钟线；字段名为兼容旧 API 保留，业务语义是最近 N 天。
- 离线脚本入口是 `python scripts/archive-yahoo-minute-data.py --date YYYY-MM-DD`；不传日期时会扫描所有已提交成交涉及的交易日和标的。
- 本地研究标的组归档入口是 `python scripts/archive-local-minute-db.py --date YYYY-MM-DD --symbols MU,NVDA,SPY --window-trading-days 1`；该脚本把指定标的的 1 分钟线持久化到同一个 SQLite 本地库，供策略测试只读复用。
- 交易复盘页只读取本地已保存分钟线归档，分钟蜡烛图会自动缩放到该标的第一笔到最后一笔 committed fill，并把买卖点叠加到图上；打开 Replay 弹层不会自动触发行情 provider 拉取。
- 分钟蜡烛复盘主图、Trade Replay 弹层和复用同一图表的策略复盘支持鼠标悬浮查看对应分钟的中文开盘价、最高价、最低价、收盘价、归档 VWAP 和该分钟买入/卖出成交价；多笔同向成交显示价格区间与笔数，数值只读当前归档 bar 和 committed fills，鼠标离开或证据不可用时不会保留或伪造提示。
- 归档只写入 `market_minute_archives` 和 provider attempt 记录，不会修改 STP 成交价格、数量或时间。
- 每条归档保存 `bars_hash`、`bars_json`、VWAP、当日高低、成交量上下文、provider 状态和归档版本。
- 强制刷新仍会保存本次 provider attempt；如果新结果失败、为空或质量更差，既有 `available` / `partial` bars、hash 和归档时间保持不变，不会把日后可复查的成功蜡烛数据降级清空。
- 交易复盘中的「刷新本地分钟线」在归档完成后会同步刷新当前日期、当前标的、每日列表、全局汇总和成交组 read model；蜡烛图与 MFE/MAE 不会分别停留在新旧两份状态。
- 历史已保存归档也会在读取时执行同一价格质量门禁；异常 bars 和 hash 保留用于追溯，但有效状态投影为 `partial`，Trade Replay、MFE/MAE、交易评价和策略运行不得把它当成成功行情消费。
- Futu 备选源依赖本机 Futu OpenD 和历史 K 线额度；本机回退请求发现行情端口未连接时，会尝试启动已安装的 Futu OpenD GUI 并等待行情端口，且不会调用交易解锁。OpenD 未安装、未登录或 Futu 仍不可用时会保留两个 provider 的失败证据并显示分钟线不可用，不会渲染假成功图。

## P1 Market Context And Watchlist

P1 已接到当前 P0-only 基线。STP TXT 和 committed fills 仍是成交真相源，行情只作为复盘上下文进入 snapshot，不会改写成交价格、数量或时间。

- Market Context Replay：`POST /api/market-context/replay` 会按 `fill_id + provider + requested_start + requested_end` 固化 snapshot，并保存 `bars_hash`、VWAP、当日高低、成交量环境和数据状态。
- Market Context Read：`GET /api/fills/{fill_id}/market-context` 与 `GET /api/market-context/{snapshot_id}` 只读取已保存 snapshot。
- Watchlist：`POST /api/watchlist/generate` 与 `GET /api/watchlist?date=YYYY-MM-DD` 返回 provider summary 生成的关注列表，每个 symbol 都带 `reason_codes`、`metrics` 和 `metrics_hash`。
- 数据状态：`available`、`partial`、`missing`、`provider_failed`、`timezone_conflict` 都会进入 API/UI read model；provider failure 不会渲染成正常图表。
- 自动验收使用 fake provider；live Futu 和 Yahoo adapter 保持可替换行情源入口。

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
- 已支持按平仓 round-trip 计算 PnL、胜率、盈亏比、单笔期望值和每股净收益：每次 B&S 或 S&B 回到平仓状态才算一笔交易；复盘指标中的持仓最大回撤只读引用成交路径和已归档分钟线 high/low，不改写成交事实。
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
- [index.html](./index.html)：仓库根目录只读云端复盘入口，同步「数据下钻」「盈亏复盘」「交易总结」三个模块及日历交互。
- [scripts/export-review-snapshot.py](./scripts/export-review-snapshot.py)：从本地复盘 API 导出脱敏、可校验的 GitHub Pages read-model 快照。
- [scripts/archive-yahoo-minute-data.py](./scripts/archive-yahoo-minute-data.py)：从已提交成交目标准备 Yahoo 优先、Futu 备选的 1 分钟线归档。
- [scripts/archive-local-minute-db.py](./scripts/archive-local-minute-db.py)：按本地研究标的组准备 Yahoo 优先、Futu 备选的 1 分钟线归档。
- [scripts/run-ai-strategy-benchmark.py](./scripts/run-ai-strategy-benchmark.py)：显式运行 AI策略 v2 五模板的同口径本地历史回放并输出摘要报告；GET 推荐接口不会自动触发该脚本。
- [scripts/resolve-backend-python.ps1](./scripts/resolve-backend-python.ps1)：后端启动前选择同时具备 FastAPI、Uvicorn 和 Futu SDK 的 Python；可用 `GRIT_PYTHON` 显式指定环境。
- [docs/p0_acceptance.md](./docs/p0_acceptance.md)：P0 DB/API/UI read-model 一致性和验收证据。
- [designs/2026-06-03-review-desk-layout/spec.md](./designs/2026-06-03-review-desk-layout/spec.md)：复盘台主图优先、盘前工作栏和导入证据区布局规格。
- [designs/2026-07-14-ai-strategy-tab/spec.md](./designs/2026-07-14-ai-strategy-tab/spec.md)：AI策略 Top 5 榜单、详情台、窄屏堆叠和证据状态设计规格。
- [designs/2026-07-14-ai-strategy-tab/traceability-matrix.md](./designs/2026-07-14-ai-strategy-tab/traceability-matrix.md)：AI策略 v2 从需求、实现、自动化测试到桌面/移动端运行截图的追踪矩阵。
- [designs/2026-07-22-trade-summary-tab/spec.md](./designs/2026-07-22-trade-summary-tab/spec.md)：交易总结样本概览、AI 状态、双栏规则、经典方法依据和响应式设计规格。

## P0 API

- `POST /api/imports/stp-txt`：上传 STP TXT，返回 `batch_id`、`file_hash`、`status`、`accepted_rows`、`quarantined_rows`，提交成功时附带本批成交触发的分钟线归档结果。
- `GET /api/imports/{batch_id}`：查看批次状态、parser version、mapping version 和错误摘要。
- `GET /api/imports/{batch_id}/quarantine`：查看异常行、原始文本、失败字段、失败原因和修复建议。
- `GET /api/fills`：按日期、账号、symbol 查询 committed 成交 read-model；跨批重导的同一 fallback 成交只展示最新批次。
- `GET /api/review/daily-summary?date=YYYY-MM-DD`：查看只基于 committed 成交 read-model 计算的 PnL、胜率、盈亏比、单笔期望值、每股净收益、MFE、MAE、持仓最大回撤、成交数量和异常行数量；这些核心 KPI 按已平仓 round-trip、成交组实际持仓路径和分钟线追溯统计，缺少可用分钟归档时 MFE/MAE 保持不可用。
- `GET /api/review/summary`：按全局、日期或标的范围查看 committed fills 轻量汇总。
- `GET /api/review/summary-groups`：按交易日或标的返回轻量下钻汇总，供复盘页选择具体日期+标的；完整交易评价只在交易组详情路径读取。
- `GET /api/trade-groups?date=YYYY-MM-DD&include_details=false`：读取复盘页首屏交易组轻量列表，不携带组内 fills 和评价因子明细；不传 `date` 时返回全部日期的轻量交易组，供盈亏复盘下钻汇总；Replay 操作再用 `include_details=true` 拉取完整证据。

## P2 API

- `GET /api/ai-strategy-recommendations?end_date=YYYY-MM-DD&symbols=MU,NVDA&initial_capital=100000&window_calendar_days=30`：读取版本化 Top 5 推荐目录、研究或本地排名、建议参数、策略逻辑、资本模型、证据状态和来源；不触发策略测试，不返回逐日结果。
- `GET /api/strategy-templates`：查看可添加的策略模板和默认参数。
- `GET /api/strategies`：查看当前策略配置。
- `POST /api/strategies`：新增模板策略实例。
- `PATCH /api/strategies/{strategy_id}`：更新策略名称、参数或启停状态。
- `POST /api/strategies/{strategy_id}/runs`：对指定日期和标的运行历史策略复盘。
- `GET /api/strategy-runs?date=YYYY-MM-DD&symbol=SYMBOL&limit=20`：读取轻量策略 run 摘要，策略工作区激活后再加载，首屏不返回完整指标序列，并默认限制历史 run 数量。
- `GET /api/strategy-runs/{run_id}`：读取单条策略 run 的完整指标序列和信号，供图表与单日 drilldown 使用。
- `POST /api/strategies/{strategy_id}/test-runs`：按截至日期最近 30 天（自然日）内的本地已归档分钟线运行批量策略测试。
- `GET /api/strategy-test-runs?end_date=YYYY-MM-DD&symbol=SYMBOL`：读取策略测试批次和逐日结果。
- `POST /api/strategies/{strategy_id}/optimizations`：按默认参数网格运行策略优化。
- `GET /api/strategy-optimizations?end_date=YYYY-MM-DD&symbol=SYMBOL`：读取优化 run 列表。
- `GET /api/strategy-optimizations/{optimization_id}`：读取优化候选参数和逐日证据。
- `POST /api/strategies/{strategy_id}/optimization-candidates/{candidate_id}/apply`：显式套用合格优化候选，并保存前后模板版本、前后参数 hash、候选来源和变更原因。
- `GET /api/strategies/{strategy_id}/history`：读取策略配置版本、参数快照和参数变更历史。
- `POST /api/strategies/{strategy_id}/history/{history_id}/rollback`：从历史记录恢复变更前参数快照，并新增一条回退历史记录。
- `POST /api/strategies/{strategy_id}/live-signal`：用 Futu、Yahoo 或 Fake 实时分钟线生成只读信号预览，返回当前配置版本、最新策略版本、provider 状态和 hash 证据。

## P3 API

- `GET /api/review/trade-summary?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`：读取指定日期范围的确定性交易总结、样本门槛、覆盖率、量化 `condition/action_steps`、`summary_key` 和匹配的本会话 AI artifact。
- `POST /api/review/trade-summary/generations`：可选的本地模型兼容入口，只接收日期范围并由服务端重新计算规则证据；交易总结页面不调用该入口，任何客户端都不能提交或覆盖规则、证据数或交易结论。

## 登录快捷方式

Windows 下可双击根目录的 `Login-Grit-DayTrading.cmd` 进入本地复盘台。它会检查 Python、npm、复盘汇总 API、AI策略推荐 API、`ai_strategy_catalog_v2` 健康 sentinel、P2 必需 API 路由、策略 run 详情路由、亏损复盘保存路由和新策略模板，优先复用默认后端和前端端口，并自动打开 AI策略 v2；新启动的后端会优先使用 `GRIT_PYTHON` 或项目 `.venv`，否则从 PATH 中选择同时具备 FastAPI、Uvicorn 和 Futu SDK 的 Python。如果默认后端端口上已有旧服务但缺少当前合同，会自动切到备用后端和前端端口启动，并通过前端代理复查 OpenAPI 合同。

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
