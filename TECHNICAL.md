# Technical Plan

## 当前 P3 切片：交易回测

目标：在本地「交易复盘」的第四个「交易回测」tab 中，除固定基准/A/B/C 对比外，把 A 持仓上限和 B 每日组合亏损线参数化，通过完整组合回测寻找总盈亏最高的候选；不生成策略信号、不自动下单、不修改 P2 策略配置。GitHub Pages 静态快照保持现有三个模块。

范围：

- 存储版本升级到 v11：既有 `trade_backtest_runs` / `trade_backtest_scenario_results` 保留四场景结果，新增 `trade_backtest_optimization_runs` / `trade_backtest_optimization_candidates` 固化来源 run、搜索空间、目标、完整候选、排名、指标、聚合证据和 hash。
- 四场景合同升级为 `trade_backtest_contract_v5` / `trade_backtest_rule_catalog_v5`，计算算法保持 `trade_backtest_engine_v4`；固定预设为 A=200 股、B=1000 USD、C=A+B。组合优化维持 `trade_backtest_optimization_contract_v1` / `trade_backtest_optimization_engine_v1` 与回退后的 70 组范围，继续提供独立 presets、运行/复用、历史列表和详情 API，并纳入 `/api/healthz` 与 Windows 启动器的陈旧运行时检查。
- 默认优化搜索空间恢复为 A=`[50,100,150,200,300,500,1000]`、B=`[500,1000,1500,2000,2500,3000,3500,4000,4500,5000]`，共 70 组；自定义输入使用 A 不超过 100000 股、B 不超过 1000000 USD 的安全边界，规范化后去重排序，候选总数仍设 120 上限。`maximize_pnl_v1` 先按总盈亏降序，再按更低 A、更低 B 和参数 hash 稳定破平局。
- `trade_backtest_engine_v4` 接受每个候选的 A/B 参数，继续负责组合 PnL、分钟级阈值插值、开盘跳空、全部清仓、当日禁开、次日重置，以及覆盖缺口跳过和局部质量异常 target 隔离；不额外模拟佣金或滑点。
- 本地 UI 复用既有时间筛选。进入 tab 时只 GET 最近结果，点击主操作后才 POST；桌面显示四行对比表，移动端用 CSS 转为四张场景卡，指标只读取 API read model。
- 四场景设计包位于 `designs/2026-08-03-trade-backtest-tab/`；组合优化设计包位于 `designs/2026-08-03-trade-backtest-optimization/`，均包含 `spec.md`、`spec.html`、`spec.png` 和 `trace-matrix.md`。本切片沿用现有复盘设计系统，不新增全局 `DESIGN.md`。

事实源矩阵：

| 层次 | 来源/产物 | 约束 |
| --- | --- | --- |
| Canonical source | 去重后的 committed fills | 只读，不修改订单、成交或 Trade Groups |
| Market artifact source | `market_minute_archives` 的结构/hash、质量投影及覆盖状态 | 只读；覆盖缺口跳过、局部质量异常 target 隔离并留证，不在回测中拉行情 |
| Read model | 四场景 API 与优化 best/matrix/Top 10 | 前端不计算指标、排名或色阶 |
| Artifact source | 四场景与优化 run/candidate 四张表 | 版本化、hash 化、保留完整候选历史 |
| Idempotency key | 日期范围、规则/优化引擎/目标版本、精确来源 run、成交/归档/参数空间 hash | 相同证据复用，任一来源或搜索空间变化新建 |

Owner files：后端合同与引擎为 `storage.py`、`trade_backtest.py`、`api.py`；前端 read model 为 `types.ts`、`api.ts`、`App.tsx`、`styles.css`；focused test owner slice 为 trade-backtest/storage/API、review frontend 和 launcher contract 测试。

负向路径：日期范围非法返回 422，run 不存在返回 404；优化参数为空、非正数、A 非整数、A 超过 100000、B 超过 1000000 或组合超过 120 返回 422；缺失、provider 不可用或 hash/JSON 无效归档不得让规则 B/C 或组合优化成功；结构/hash 有效但覆盖不足时跳过缺失分钟，局部质量异常时隔离整个日期/标的，继续运行并令最差日内组合 PnL 为 N/A；跨日持仓和未闭合轮次返回明确不支持状态且优化不生成最佳值。parser version 与 field mapper version 不变，但来源版本集合随四场景和优化 run 保存。

## 当前 P3 切片：GitHub Pages 交易复盘一致性

目标：把本地交易复盘的「数据下钻」「盈亏复盘」「交易总结」同步到 GitHub Pages 根入口，保留三模块切换、月份/日期选择和本地样式语义，同时严格保持公开页面只读和证据脱敏。

范围：

- 通过 repo-owned 导出脚本读取本地 trade group、review summary、日期/标的聚合与 trade summary API，生成 `review-snapshot.json`。
- 根入口只加载脱敏快照并复用本地复盘样式；数据下钻支持全部/本月/本周/特定时间段与日历，盈亏复盘支持全部/盈利/亏损、矩阵、排序和分页，交易总结展示当前快照的规则和生成状态。
- 云端根入口的共享壳层必须与本地 `App.tsx` DOM 合同一致：标题文案、工作区与复盘 tab 使用同一组 Lucide SVG，导航和复盘面板之间不得插入可见的云端专属元信息，日历详情沿用 `compactFacts summaryMiniFacts` 布局；合同测试和同视口截图负责防回归。
- Canonical source 仍为 committed fills、Review Journal、分钟归档证据和规则目录；静态 JSON 只是部署 read model，artifact source 为 GitHub Pages 根入口资产。
- 幂等口径为去除导出时间后的排序 JSON SHA-256；parser version 和 field mapper version 不变。

Focused test owner slice：根入口合同、脱敏快照聚合、交易复盘前端合同、交易总结合同；通过后再执行 web typecheck/build、全量 pytest 和 Windows 启动入口检查。

负向路径：快照缺失、schema 无效或 closed group 数、`traded_quantity`、PnL 任一不一致时阻断全部复盘内容，不使用硬编码旧数字或空成功态。

## 当前 P3 切片：交易总结混合推荐

目标：在「交易复盘」下新增「交易总结」，把指定日期范围的盈利、亏损和持平闭合交易转成证据可追溯、参数明确的执行规则与规避错误；后端确定规则、排序和量化动作，当前 Codex 会话负责生成受约束的摘要表达。

范围：

- 「盈亏复盘」和「交易总结」共用全部、本月、本周和特定时间段 state；盈亏单单选仍属于盈亏复盘。
- 新增 `GET /api/review/trade-summary` 和 `POST /api/review/trade-summary/generations`。
- 存储版本升级到 v9，新增 `trade_summary_generations` 保存脱敏聚合快照、确定性规则、AI 文案、失败和重试证据。
- `intraday_review_rule_catalog_v2` 覆盖突破回踩、VWAP/趋势一致、量能确认、结构/时间止损、盈利保护和执行纪律，并为每条规则固化 `condition` 与 `action_steps`；参数包含 K 线数、量能倍数、ATR、风险百分比、R 倍数、分批比例和停手线。
- 本地模型只允许 loopback `/v1` 地址，`temperature=0`、非流式、60 秒超时；服务端读取模型配置和可选密钥。
- `trade_summary_contract_v3` 优先读取当前 `summary_key + prompt_version + codex_session + session_model + model_config_hash` 匹配的本会话 artifact；前端只 GET 展示，不自动或手动 POST 模型请求。
- 当前会话 narrative 必须覆盖后端给出的全部规则 ID，且不能新增数字；服务层重新计算证据后才写入 `trade_summary_generations`。可选本地模型入口沿用相同校验和脱敏边界。
- 支持率、命中率和影响金额继续作为后端 `quantification` 审计字段保存，但 UI 推荐卡只展示目录确定的量化条件与动作，不把相关性证据误写成执行参数。
- 设计包位于 `designs/2026-07-22-trade-summary-tab/`；本切片不新增全局 `DESIGN.md`。

事实源：

- Canonical source：committed fills 构成的 closed Trade Groups。
- Subjective source：Review Journal 亏损原因。
- Market evidence：已保存分钟归档、archive id 和 `bars_hash`。
- Knowledge source：版本化经典规则目录。
- Read model：交易总结 GET。
- Artifact source：`trade_summary_generations`。
- Idempotency：`summary_key + prompt_version + provider + model + model_config_hash` 稳定 hash。

验收：

- 至少 20 笔闭合交易且盈利、亏损各至少 5 笔才允许个性化生成；未达标展示经典基线和缺口。
- 因子统一归一化为 `score / max_score`；盈利支持 `>= 0.70`，亏损弱项 `< 0.40`。
- 执行规则至少 3 笔盈利支持和 3 笔亏损反证；规避规则至少 3 笔亏损命中。
- 缺归档和缺 Journal 不被当成反向证据。
- 模型未配置、不可连接、超时、非成功响应、非法 JSON、规则 ID 篡改或新增数字时保存失败，确定性规则仍可见。
- 证据、规则目录或提示词变化后旧会话 artifact 必须标记 `stale`；页面不得继续把旧文案展示为当前结论。
- 模型外发不包含账号、原始 STP 行、fill/order id、原始 payload、Journal 自由文本或本机路径。
- Windows 启动器和 `/api/healthz` 检查 `trade_summary_contract_v3` 与两条新路由，不暴露模型地址或密钥。

负向路径：无交易不创建 artifact；样本不足拒绝生成；规则 ID 缺失、篡改或摘要新增数字时拒绝写入；证据变化后旧文案显示 `stale`；摘要失败不能显示成功或伪造建议，确定性量化规则仍可见。

## 当前 P3 切片：亏损交易组 Review Journal

目标：在 Trade Replay 弹层内为已平仓亏损交易组提供精简原因下拉，记录本次亏损的主观归因；「成交记录」模块提供「仅看亏损单」勾选项但不提供单独「复盘」操作按钮；「下钻复盘」保留「数据下钻」和「盈亏复盘」能力，并由当前交易总结切片增加第三个「交易总结」tab。数据下钻用月日历选择每日下钻，盈亏复盘集中承接热力时间矩阵、全部订单/盈利单/亏损单列表和亏损原因分类。

范围：

- 新增 `trade_reviews` 作为 Review Journal canonical source。
- `GET /api/trade-groups` 返回每个交易组已有的 `review`，`date` 可省略以读取全部日期的轻量交易组。
- `PUT /api/trade-groups/{trade_group_id}/review` 保存或更新亏损交易组复盘原因。
- 原因分类固定为开仓信号、平仓信号和误操作；原因码由后端校验。
- 复盘记录保存 `trade_group_id`、交易组 PnL、parser versions、field mapper versions、source batch ids 和 raw line numbers。

验收：

- 成交记录行不显示单独「复盘」操作按钮。
- 成交记录可勾选「仅看亏损单」只查看当前范围内 closed 且 PnL 小于 0 的交易组，并同步让上方分钟蜡烛图只显示这些交易组对应的买卖点；该筛选不重新计算 KPI 或修改事实源。
- 「数据下钻」tab 按全部、本月、本周和特定时间段筛选当前下钻 read model；展示顺序固定为时间筛选、该时间范围内全部订单统计指标、月日历下钻和月历下方的当前复盘上下文。「月日历下钻」默认保持日历视图，也可切到覆盖完整所选时间范围的每日表格；表格与导出固定为日期、成交数、股数、PnL、胜率、盈亏比、单笔期望值、每股净收益、MFE、MAE 十列，不重复展示已平仓/未平仓计数。桌面表格自适应容器，窄屏转换为逐日指标卡片，不产生横向滚动。月日历按日展示股数与 PnL，点击有订单的日期方块只更新当前复盘日期并显示该日标的入口，不写入 `trade_reviews`、STP 成交或行情归档。
- 每个 closed trade group 的 MFE/MAE 由后端按实际 open position、移动均价和已保存 `market_minute_archives` 窗口 high/low 计算；头部汇总、当前每日指标、成交记录行和每日表格只投影后端 excursion read model，并统一提供可悬浮、可键盘聚焦的「?」名词解释，不在浏览器读取 bars 自算。历史日期按同一确定性路径回溯计算，启动器必须验证 `trade_group_excursion_v2`，避免复用尚未提供 MFE/MAE 的旧后端。缺归档时 MFE/MAE 为 N/A，无每日数据时导出不可用。
- 工作区启动查询参数只用于确定首次打开的工作区；React 初始化完成后删除 `grit_ui`，保留其他查询参数和 hash，避免地址栏长期暴露渠道标记。
- Canonical source 为 committed fills；market evidence 为 `market_minute_archives`；read model 为轻量 trade groups、review summary 与每日分组；artifact source 为原成交证据与 archive id / `bars_hash`。沿用既有 `trade_group_id` 和成交幂等口径，不新增持久化幂等 key；parser version 与 field mapper version 不变。
- 「下钻复盘」默认展示「数据下钻」；切到「盈亏复盘」后读取所有日期 closed 且 PnL 可计算的交易组，单选默认选中「全部订单」，可切到「仅看盈利单」或「仅看亏损单」。
- 盈亏复盘时间筛选提供全部、本月、本周和特定时间段；当前单选和时间范围统一控制统计指标、热力矩阵和订单列表。亏损视图额外展示一级/二级原因分类汇总并支持联动多选筛选订单明细；盈利和全部视图的原因模块展示为空。
- 盈亏复盘统计指标整理在一行；订单明细默认按时间倒序，也可按盈亏绝对值、盈利金额或亏损金额倒序，每页 20 笔。
- 「盈亏复盘」展示只读热力时间矩阵，横轴固定为 09:30-10:30、10:30-11:30、11:30-13:30、13:30-15:00、15:00-16:00 五个美股常规盘微观结构窗口。全部订单视图默认展示 ATR 时间矩阵，并可切换为股数时间矩阵；ATR 纵轴读取后端 `position_drawdown.entry_atr_multiple`，由本地 `market_minute_archives` 计算开仓 1min K 振幅 / 前 20 根 ATR，缺历史分钟线时显示缺 ATR 证据；股数纵轴只读使用轻量交易组 `total_quantity`，按 `≤50`、`51-100`、`101-200`、`201-500`、`>500` 股分档，异常非正数进入缺股数证据，并在右侧 Y 轴汇总每档收益、订单数和股数。全部订单两种矩阵均展示最大盈利区、最大亏损区和每个时间窗口收益合计；盈利视图和亏损视图继续使用 ATR 时间矩阵，分别展示最大盈利区或最大亏损区。矩阵格不筛选订单明细，不用已实现盈亏或美元回撤回退 ATR，也不新增前端行情指标计算。
- 只有 closed 且 PnL 小于 0 的交易组在 Trade Replay 弹层订单明细模块下方展示亏损原因下拉。
- 保存原因后成交记录行显示已选亏损原因。
- 盈利、持平、未清仓或不存在的交易组不能写入亏损复盘。
- 复盘原因只写 `trade_reviews`，不修改 STP committed fills、行情归档或策略 artifact。

## 当前补充：实时交易信号面板
目标：收敛「实时交易」中的「下单信号」模块，展开后端 `signals[]` 中真实 BUY/SELL 订单层面的信号明细。HOLD、失败、策略动作、策略版本、provider 状态、最新行情、原因码、指标和 hash 证据继续展示在「原因与证据」模块。

验收：
- 「下单信号」每个真实 BUY/SELL 信号订单只展示标的、订单意图、操作类型、信号价、股数、触发时间和 bar index；开仓单额外展示止损/止盈，股数由后端按策略资金参数和开仓价计算，关仓单不展示止损/止盈并展示平仓原因标签；操作类型由后端策略动作派生为「开仓」或「关仓」，同一标的窗口内的开仓和关仓都要展示。
- 「下单信号」不展示 HOLD、失败状态、状态徽标、状态摘要、完整策略动作、provider、bar count、latest strategy version、config version、latest_bar 最新行情或 hash 证据。
- 「原因与证据」按每个标的展示后端 `latest_bar` 的最新分钟 K 时间、收盘、OHLC、成交量和 bars 数；provider 未返回分钟线时显示暂无最新行情，不渲染假价格。
- `Login-Grit-DayTrading.cmd --check` 会检查前端 `App.tsx` 是否包含当前信号面板指纹，避免旧前端进程被误判为可用。
- provider failure、策略未开启或无信号时仍保留状态和失败原因，不渲染假订单。

## 当前补充：实时交易监控
目标：将「实时交易」从单次刷新改为多标的监控。用户下拉多选标的后，默认使用 Yahoo 实时行情；点击「开启监控」会立即读取一次最新行情，并每 30 秒继续调用后端 live-signal read model 输出只读下单信号和原因。

验收：
- 标的选择支持多选，同一轮监控按每个 symbol 独立调用 `POST /api/strategies/{strategy_id}/live-signal`。
- 前端默认 provider 为 Yahoo，后端请求未显式传 provider 时也默认 Yahoo。
- 切换策略、标的、行情源或分钟线窗口会停止监控并清空旧结果，避免旧行情覆盖新选择。
- 实时监控刷新只更新实时交易工作区结果，不得改写交易复盘工作区的当前复盘日期或当前复盘标的。
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
- 策略模板 registry 当前保留五个历史模板，并新增 `five_minute_opening_range_breakout_v1`、`fifteen_minute_opening_range_retest_v1`、`vwap_opening_drive_v1`、`vwap_trend_pullback_v1` 和 `last_hour_intraday_momentum_v1`；十个模板均 seed 默认禁用配置，旧模板只退出 AI v2 推荐目录，不删除历史配置或 run。
- 新增策略 API：模板、配置、启停、参数保存、历史 run 和 run 查询。
- 新增策略测试 API：截至日期最近 30 天（自然日）本地归档窗口的 test batch、逐日结果、优化 run、候选参数和稳定性排序。
- 新增策略配置历史合同：模板 registry 升级、手工参数保存、显式套用优化候选和历史回退时保存前后模板版本、前后参数 hash、参数 JSON 快照、候选来源、来源历史记录和变更原因。
- 策略计算只读取 `market_minute_archives`，不自动归档分钟线，不修改 STP 成交事实。
- 顶层 UI 拆为「交易复盘」「策略测试」「AI策略」和「实时交易」四个 tab；交易复盘保留成交证据与买卖点，策略测试集中展示配置、单日测试、30 天测试复盘和策略优化，AI策略展示只读 Top 5 推荐，实时交易只展示只读下单信号预览。
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

## 当前 P2 切片：AI策略 Top 5 推荐

目标：用版本化研究目录和本地策略测试 artifact，为五个新策略模板提供确定性、可解释、只读的 Top 5 推荐；盈利期望只表示每笔闭合信号的样本内历史回放期望 PnL。

范围：

- `ai_strategy_catalog_v2` 和 `GET /api/ai-strategy-recommendations` 统一返回五个新模板的研究顺序、策略逻辑、建议参数、品种画像、100,000 USD / 20% 资本模型、推荐理由和来源；v1 旧目录仅保留历史追溯。
- 默认使用研究顺序；仅当五个策略在相同日期、最近 30 个自然日、相同标的集合、相同资本和建议参数 hash 下都满足至少 10 个完成归档交易日与 10 个闭合信号时，整体切换为本地回放排序。`non_available_archive` 日期保留逐日失败 artifact，在共享 scope 且其余门槛达标时作为明确排除日，不生成信号或收益。
- 本地排序依次比较每笔闭合信号期望 PnL、profit factor、max drawdown、闭合信号数和研究排名，不使用优化候选 composite score。
- 前端采用桌面端左侧榜单、右侧详情台，窄屏上下堆叠；所有指标、参数 label、证据状态和来源都读取后端 read model。
- 「去策略测试」只把策略、截止日期和标的带入现有策略测试工作区，不发起 POST，不自动应用参数。

验收：

- 100,000 USD 本金和 20% 单次入场稳定换算为 20,000 USD 名义仓位，并提示多标的并发资金占用尚未建模。
- 零归档、样本不足、参数 hash 过期、archive scope 不一致、null profit factor 或单策略引擎失败都保留研究排名，不显示伪造盈利期望；非可用日期数量和原因必须展示。
- response 不包含逐日大对象；相同输入与证据生成稳定 recommendation key。
- 本切片不新增推荐持久化表；GET 推荐接口不运行策略、不修改配置、不触发自动下单。
- 显式 benchmark 脚本只读取本地归档并写入现有测试 artifact；当前 MU 30 自然日样本得到 18 个完成日和至少 10 个闭合信号/策略，五策略达到 `verified`。这些结果未计佣金、滑点与组合并发资本，不代表未来盈利。
- benchmark 报告保存 `job_id`、`source_job_id`、`artifact_id`、策略数、结果数、稳定 `hash`、批次 id、archive scope hash 和 recommendation key，UI/API/DB 口径可追溯且不把首屏预览当成全量结果。

## 当前 P1 切片：Trade Replay Groups

目标：成交记录从单笔 fill 改为“每一次开仓至清仓”的交易组，并在 replay 弹层中展示该次交易的分钟蜡烛图、成交量、关键指标和可审计智能评价。

范围：

- 新增 `GET /api/trade-groups?date=YYYY-MM-DD&account=&symbol=`，从 committed `fills` read model 构建交易组，不新增持久化表。
- 交易组按 `account_canonical + symbol`、成交时间和 fill id 顺序配对，支持多头、空头、加仓、部分平仓和未清仓状态。
- Daily summary 的 `trade_group_count`、PnL、胜率、盈亏比、单笔期望值、每股净收益和持仓最大回撤复用 closed trade groups，避免 UI 分组和 KPI 口径漂移。
- Replay 弹层只读取本地已归档 `market_minute_archives`，默认按开仓到清仓窗口自动缩放并保留首尾各 10 分钟；勾选「查看半小时」时只把可见蜡烛图窗口扩大到开平仓前后各 30 分钟，叠加组内所有成交点，并展示按组内成交路径和窗口分钟 high/low 追溯的持仓最大回撤；打开弹层不会自动触发行情 provider 拉取。
- 分钟蜡烛复盘主图、Trade Replay 弹层和共享组件下的策略蜡烛图支持鼠标悬浮查看对应分钟的中文开盘价、最高价、最低价、收盘价、归档 VWAP 与买入/卖出成交价；OHLC/VWAP 只读当前 archive，成交价只读映射到该分钟的 committed `fills`，多笔同向成交显示价格区间与笔数，不新增前端行情、成交均价或策略计算。
- 智能评价采用 `trade_eval_intraday_v1` 规则模型，只读计算 VWAP 执行质量、趋势配合、成交量确认、MFE/MAE、清仓效率和 PnL 结果；评分 payload 以结构化 `recommendations` 返回后续开仓和平仓建议；持仓最大回撤是交易组 read model 字段，不由前端自行重算。
- 交易复盘 tab 头部展示有记录以来汇总；随后按交易日和按标的两个下钻 tab 展示次级汇总，选择具体日期+标的后进入分钟蜡烛和交易组复盘模块。

验收：

- closed group 才进入已实现 PnL、胜率、盈亏比、单笔期望值、每股净收益、持仓最大回撤和正常评价；open group 必须显示未清仓。
- `trade_group_id` 只暴露 hash 后 ID，不暴露原始 fill idempotency key。
- 缺分钟线、provider failure、时区冲突或无 bars 时，持仓最大回撤和评价必须返回 `insufficient_market_data`，不能生成正常评分。
- Replay 弹层不能用行情数据改写成交价格、数量或时间。
- 鼠标离开价格绘图区、切换归档或改变可见窗口后必须清空旧浮层；缺归档、无 bars 或失败状态不得显示悬浮行情，没有映射成交或 VWAP 时必须显示缺值，不得合成价格或伪造成交。
- 「查看半小时」只改变 Trade Replay 可见分钟线范围；缺归档、provider failure 或无 bars 时仍显示不可用状态，不渲染成功图。
- 无 committed fills 时，全局汇总为 0、日期/标的下钻为空，UI 不展示假日期、假标的或成功复盘。
- 文档和 changelog 必须同步 P1 事实源、read model、artifact source 和负向路径。

## 当前 P1 切片：本地分钟线归档与备选行情

目标：从 committed fills 推导有交易日的标的，使用 Yahoo 主源与 Futu 备选源获取 1 分钟线，并保存为长期可复查的本地归档。

范围：

- Yahoo provider adapter 负责主源分钟线获取和错误状态映射；Yahoo 拒绝、失败、返回不完整数据、出现与前后行情不连续且显著超过典型分钟振幅的孤立异常柱，或对有 committed fills 的目标返回空数据时，再调用 Futu 历史 K 线 adapter。
- 新增 `market_minute_archives` 存储合同，保存 symbol/day 级别的 bars、hash、VWAP、当日高低、成交量上下文和归档版本。
- 新增 `POST /api/market-data/yahoo-minute-archive`、`GET /api/market-data/minute-archives`、`scripts/archive-yahoo-minute-data.py` 和 `scripts/archive-local-minute-db.py` 作为操作入口。
- `POST /api/imports/stp-txt` 导入 committed 后会按本批 `source_batch_id` 下的成交日期和标的触发缺失分钟线归档，并在上传响应中返回归档摘要。
- `POST /api/market-data/yahoo-minute-archive` 可按已提交成交目标归档，也可按手工 `symbol + date + window_trading_days` 归档研究标的最近自然日窗口；`window_trading_days` 是兼容字段名，当前业务语义为最近 N 天；`archive-local-minute-db.py` 可按 `symbols + date + window_trading_days` 批量归档本地研究标的组。
- 复盘页新增日期和标的选择器，按 `trade_date + symbol` 读取归档分钟线，默认显示当前标的第一笔到最后一笔 committed fill 的时间范围，并用 committed fills 标注买卖点。
- 归档目标来自已提交 `fills`，不读取 quarantine 行，不修改 STP 成交事实。
- 启用 Momentum Mean Reversion 时，归档目标还包括同日 QQQ/SMH 策略上下文标的；这些上下文归档的 `source_fill_count` 为 0，策略 run 仍只读取已归档 artifact。
- 兼容 API 名称保留 `yahoo-minute-archive`，但响应会返回 `provider_chain`、备选尝试数和备选成功数；读取端不限定 Yahoo，按可用状态和 provider 顺序选择本地归档。
- Futu 仅在本地分钟线归档回退路径启用 OpenD 自动启动；只允许连接本机行情端口，只启动已安装的 `Futu_OpenD` GUI 并等待行情通道，不执行 `unlock_trade` 或任何交易动作；可用 `FUTU_AUTO_START_OPEND=0` 显式关闭。
- Version boundary: 本切片不涉及 STP parser 或 field mapper，相关版本保持不变；`market_minute_archive_v1`、provider、bars hash 和逐次 attempt 继续随原记录保存。

验收：

- 重复运行默认不新增 archive 或 provider attempt。
- 重复上传同一 STP TXT 默认复用既有批次和既有分钟线归档，不新增重复 provider attempt。
- `force=true` 可以刷新已有 archive，但失败、空数据或质量更差的新结果不得覆盖既有 `available` / `partial` bars、hash 和归档时间；失败 attempt 仍必须保存。
- Yahoo 失败后必须尝试 Futu；两个 provider 的 attempt 独立留痕，Futu 成功后保存为独立本地 archive。
- Yahoo 和 Futu 都失败、Futu OpenD 未运行或历史 K 线额度不可用时，必须保留可见失败状态，不得伪造成功归档。
- 历史已保存的异常 Yahoo bars/hash 保留追溯，但读取端必须把孤立价格断层投影为 `partial`；有可用 Futu 归档时优先读取 Futu，没有可用备选时 Trade Replay、MFE/MAE、交易评价和新策略 run 均不得渲染成功。
- 用户显式刷新本地分钟线并获得可用归档后，交易复盘必须同步重读当前日期/标的汇总、全局汇总、日期/标的分组和轻量交易组，确保蜡烛图、MFE/MAE、每日列表和成交记录使用同一次刷新后的 read model。
- 复盘页缺归档或缺分钟线时必须显示缺失状态，不能用空蜡烛图表示成功。
- 负向路径覆盖无成交目标、双 provider failure、孤立价格断层、历史异常归档降级、失败强刷保护、重复归档、缺 QQQ/SMH 动能上下文和 STP fill 不被行情数据改写。

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
- 当前 daily summary 的 PnL、胜率、盈亏比、单笔期望值和每股净收益按已平仓 round-trip 统计，持仓最大回撤按 closed trade group 的成交路径和已归档分钟线 high/low 追溯统计；前端只展示 API read model，不自行重算核心 KPI。
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
GET /api/review/trade-summary?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
POST /api/review/trade-summary/generations
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
GET   /api/ai-strategy-recommendations?end_date=YYYY-MM-DD&symbols=MU,NVDA&initial_capital=100000&window_calendar_days=30
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

当前 Python 集成测试覆盖 P0、P1 和 P2，包含 parser、storage contract、import API、market context、watchlist、strategy replay、AI策略推荐和 DB/API/UI read-model 一致性。

## 本地登录入口

根目录提供 `Login-Grit-DayTrading.cmd` 作为 Windows 双击入口：

- 后端默认端口：`8001`。
- 前端默认端口：`5173`。
- 后端备用端口从 `8011` 起选择，前端备用端口从 `5183` 起选择。
- 前端 API 代理默认指向当前选中的后端端口；只有用户显式设置 `VITE_API_PROXY` 时才保留外部指定值。
- `scripts/resolve-backend-python.ps1` 按 `GRIT_PYTHON`、项目 `.venv`、PATH 候选顺序选择同时具备 FastAPI、Uvicorn 和 Futu SDK 的 Python；找不到合格环境时后端启动必须失败并显示修复提示，不能以缺少 Futu SDK 的环境继续提供会导致回补失败的服务。
- 启动前会验证后端 `healthz`、`trade_eval_recommendation_v1` 评分建议合同、`ai_strategy_catalog_v2` 目录 sentinel、复盘汇总 API、AI策略推荐 API、P2 必需 API 路由、`GET /api/strategy-runs/{run_id}` 详情路由、亏损复盘保存路由和新策略模板；前端 ready 还必须通过 Vite 代理读取 `/openapi.json` 并命中同一合同，同时在短暂可用后用不依赖 stdin 的等待路径复查一次。如果默认端口上是旧后端，正常启动会自动切到备用后端和前端端口，避免前端连到旧目录或失效 fallback 页面。
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
- 分钟线强制刷新后，蜡烛图和所有依赖行情的复盘汇总同步失效并重读。
- Replay 幂等和 force replay。
- Watchlist 稳定排序、入选理由、零结果、provider failure。
- API 404/422、fill 不存在、日期格式错误、watchlist 重跑。

### P2 Tests

- AI Strategy Recommendation：v2 新五模板固定目录顺序、建议参数、100k/20% 仓位、稳定 recommendation key、全榜单证据门槛、本地排序 tie-break、参数过期、明确排除非可用日期、null profit factor、响应不含逐日大对象和只读 CTA。
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
