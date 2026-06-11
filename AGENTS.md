# AGENTS

本文档是本项目的 agent 操作规则。所有 Codex、工程 agent 和后续自动化 worker 在改动本项目时必须先读本文档。

## 工作顺序

1. 先读 [README.md](./README.md)，确认当前产品范围。
2. 再读 [ARCHITECTURE.md](./ARCHITECTURE.md)，确认事实源和数据流。
3. 再读 [TECHNICAL.md](./TECHNICAL.md)，确认当前阶段、切片和测试策略。
4. 修改用户可见结果或阶段记录时同步 [CHANGELOG.md](./CHANGELOG.md)。
5. 如果新增设计稿、UI 规格、fixture 或脚本，必须在对应根文档里补导航。

## 当前项目状态

- 当前目录已经包含 P0 STP 导入、P1 行情上下文、分钟线归档、watchlist 和 trade replay 代码。
- 当前交付目标是 P2 交易策略配置与历史策略信号复盘，不继承相邻项目代码。
- 当前 P0 事实源仍是 STP TXT 订单导出到可追溯复盘数据；P2 只做复盘信号，不做自动下单。
- 可以参考 Grit Strategy Lab 的文档组织方式和 TradeGPT 的 STP 证据链经验，但不得复制旧项目运行时假设到本项目。
- 首个真实 STP TXT 样例将成为 parser fixture 和字段合同来源。

## 编码与文档规则

- Markdown 文件保存为 UTF-8。
- 用户可见文档默认使用中文。
- 命令、字段名、状态枚举、表名和产品名可以保留英文。
- 不在公开文档中写真实账号、真实本机路径、密钥、token、localhost URL、原始 STP 行、原始 payload 或内部调试 id。
- `CHANGELOG.md` 只写用户可理解的产品结果，不写测试命令、文件清单或实现流水账。

## 事实源纪律

- STP TXT 是订单和成交真相源。
- 富途是 P0 之后的行情和市场上下文来源。
- Review Journal 是主观复盘结论来源。
- 这些来源只能互相引用，不能互相覆盖。

## 实施门禁

任何实现 STP 导入、行情上下文、策略复盘或复盘展示的改动，都必须在计划或最终报告中说明：

- 当前切片属于 P0、P1、P2 还是 P3。
- 本次改动的 canonical source、read model 和 artifact source。
- 幂等 key。
- parser version 和 field mapper version 是否随记录保存。
- 至少一个负向验收路径。
- 文档和 changelog 是否已同步。

## 耗时复盘与加速规则

当一次实现或 review 超过 30 分钟，或用户明确要求复盘耗时时，必须先判断耗时属于必要验收还是可压缩流程成本。优先把 repo-local 规则写回本文档或 [TECHNICAL.md](./TECHNICAL.md)，只有跨项目通用时才建议修改 shared skill。

针对事实源、窗口口径、单个 tab 或单个弹层的小切片，实施前先冻结：

- 当前 lane：`Functional`、`UI` 或 `Functional then UI`。
- 当前阶段：P0、P1、P2 或 P3。
- owner files：后端合同、前端 read model、测试和文档的最小文件集合。
- source matrix：canonical source、read model、artifact source 和幂等 key。
- focused test owner slice：先跑直接覆盖的后端/API/frontend contract 测试；通过后再决定是否跑 full suite。

如果工作树已有大量未提交改动，先用 `git status --short --branch` 和针对性 `rg` 定位本次 owner files，不做全仓 diff 复盘；不得回退不属于本次请求的改动。文档同步要在测试前后各检查一次，避免最后才发现 README、ARCHITECTURE、TECHNICAL、CHANGELOG 或 AGENTS 口径冲突。

## P0 Agent 要求

P0 改动必须覆盖：

- STP TXT 上传批次。
- 原始文件 hash。
- 原始行保留。
- parser version。
- field mapper version。
- 账号 `strip().upper()` canonicalization。
- quarantine 行。
- normalized orders/fills。
- 重复导入幂等。
- PnL、胜率和盈亏比只使用 committed fills。

禁止行为：

- 导入失败后只在终端报错，不给 UI 或导入历史留状态。
- 丢弃未知列。
- 用默认空值把失败行写成成功记录。
- parser 升级后直接覆盖历史解析结果。

## P1 Agent 要求

Market Context Replay 改动必须支持：

- 分钟线。
- VWAP。
- 当日高低。
- 成交量环境。
- provider attempt 状态。
- 缺数据状态。
- 盘前和盘后成交。
- 时区错位诊断。
- 盘前 watchlist run。
- 每个 watchlist symbol 的入选原因和指标。
- watchlist provider failure 和零结果状态。
- 手工指定标的和自然日窗口的分钟线归档，只能写行情归档和 provider attempt，不能改成交事实。

禁止行为：

- 富途失败时渲染正常图表。
- 缺分钟线时用静态空图表示成功。
- 用行情数据修改成交价格、成交数量或成交时间。
- 前端自行计算 VWAP 或 watchlist 入选原因。

## P2 Agent 要求

Strategy Replay 改动必须支持：

- 策略配置保存到 `strategy_configs`。
- 策略 run 保存到 `strategy_signal_runs`。
- 策略开平仓信号保存到 `strategy_signals`。
- 策略测试批次保存到 `strategy_test_batches` 和 `strategy_test_day_results`。
- 策略优化 run 和候选保存到 `strategy_optimization_runs` 和 `strategy_optimization_candidates`。
- 策略输入只读取已归档 `market_minute_archives`。
- 每次 run 保存 `source_archive_id`、`bars_hash`、`params_hash`、`indicator_engine_version` 和 `indicator_hash`。
- 单日 run、30 天测试和优化候选必须保存运行时 `params_json` 或 candidate 参数证据。
- 缺归档、非 available 归档、分钟线不足、策略未开启和引擎失败状态。
- 截止日前最近 30 天自然日窗口内没有本地归档时保存 `insufficient_archive_coverage`，不得自动拉行情、补假日期或向更早交易日补足。
- UI 可以提供显式“拉取最近 30 天数据”作为数据准备动作，但策略 run、test batch 和 optimization 仍只能读取已保存归档。
- 优化 candidate 默认上限为 120；最佳候选只能展示，必须由用户显式套用后才更新策略配置。
- BB Squeeze 指标序列和信号由后端计算，UI 只读 API read model。
- 9 EMA 出场缓冲、绝对带宽过滤和被动止盈触达只能由后端策略 run 计算。

禁止行为：

- 策略运行时自动下单。
- 用策略信号修改 STP 成交价格、成交数量或成交时间。
- 前端自行计算 BB、RSI、VWAP、relative volume、9 EMA、absolute bandwidth 或开平仓信号。
- 缺归档或行情不可用时渲染成功信号。
- 策略升级后直接覆盖历史 run 的 artifact source。
- 优化结束后自动覆盖策略配置。

## 测试纪律

实现前优先固定真实 STP TXT fixture。没有真实样例时，可以先写 contract skeleton 和人工 fixture 结构，但最终 parser 验收必须回到真实样例。

最低测试切片：

- STP TXT：真实样例、重复导入、空文件、缺字段、未知列、部分成交、取消单、跨日成交。
- Evidence Ledger：原始行可追溯、quarantine 可复查、parser version 可重跑。
- Market Context：分钟线缺失、时区错位、盘前盘后成交、富途接口失败。
- Watchlist：稳定排序、入选理由、零结果、provider failure。
- Strategy Replay：缺归档、非 available 归档、分钟线不足、disabled run、重复运行、force 重跑、无未来函数、持仓中不重复 entry。
- UI：导入后 30 秒内能找到一笔交易、看到证据追溯字段、查看行情上下文和 watchlist 状态。
- Windows `.cmd` 启动入口：修改后必须保持 CRLF，并运行 `Login-Grit-DayTrading.cmd` 或 `Login-Grit-DayTrading.cmd --check` 的真实路径验证。

## 交付报告格式

最终报告至少包含：

- Changed files。
- 本次阶段切片。
- 事实源和幂等口径。
- Commands run。
- Test results。
- 未完成风险。
- 文档和 changelog 同步结果。

如果没有运行测试，必须明确说明原因。

## Changelog 候选写法

使用以下形状：

```text
- **主题**: 用户可理解的结果或风险降低。
```

不要写：

- 本机路径。
- 内部 URL。
- 真实账号。
- 原始 STP 行。
- stack trace。
- worker 过程描述。
- 测试命令。
- 源码文件清单。
