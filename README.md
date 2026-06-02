# Grit Day Trading Platform

Grit Day Trading Platform 是个人日内交易闭环 Web 系统。首版目标不是做自动下单，也不是做漂亮但不可追溯的报表，而是稳定回答四个问题：

- 交易前我计划了什么？
- STP 最终实际成交了什么？
- 成交当时市场环境给了什么信号？
- 计划与执行之间的偏差在哪里？

当前项目处于文档基线阶段。本文档把 2026-06-02 的 CEO Review 补强版确认为第一版产品和工程事实源，后续实现必须同步更新 [ARCHITECTURE.md](./ARCHITECTURE.md)、[TECHNICAL.md](./TECHNICAL.md)、[AGENTS.md](./AGENTS.md) 和 [CHANGELOG.md](./CHANGELOG.md)。

## 当前范围

- 使用 STP TXT 作为订单、委托和成交真相源。
- P0 只支持导入证据账本、异常隔离、幂等导入、解析版本留痕和基础复盘指标。
- P0 前端只做复盘台：上传、批次状态、异常行、成交列表、PnL、胜率和盈亏比。
- Trade Plan、富途行情和成交市场上下文重建保留在 P0 之后。

## 当前实现状态

- 已初始化 FastAPI + SQLite + React/Vite scaffold。
- 已实现 `POST /api/imports/stp-txt`、批次查询、quarantine 查询、fills 查询和 daily summary。
- 已实现 STP TXT parser、字段映射诊断、账号 canonicalization、parser/mapping version 留痕。
- 已支持无表头成交 TXT 按 `日期、时间、标的、买卖、股数、价格、账号、通道` 自动补字段合同；第 9 列存在时作为 `order_id`。
- 已支持旧 parser 造成的零行 file-level 失败批次在新 parser 下重解析，避免同一文件永远返回旧失败状态。
- 已支持缺 execution id 的重复成交行逐行入账，并在 daily summary 中展示配对交易股数。
- 已支持跨批次重导的成交 read-model 去重：原始批次和 evidence rows 保留，成交列表和 KPI 不重复计算同一批修正重导。
- 已支持按平仓 round-trip 计算 PnL、胜率和盈亏比：每次 B&S 或 S&B 回到平仓状态才算一笔交易。
- 已实现 storage migration marker、唯一索引、账号 canonicalization trigger 和幂等写入。
- 已实现 P0 复盘台骨架，展示上传、批次、异常行、成交表和基础 KPI。

## 不在首版范围

- 不自动下单。
- 不做期权链。
- 不做多用户或商业化权限体系。
- 不做全市场实时扫描。
- 不让富途行情覆盖 STP 成交真相。
- 不让 STP TXT 覆盖 Trade Plan 的原始计划意图。

## 事实源边界

| 领域 | 事实源 | 用途 | 禁止行为 |
| --- | --- | --- | --- |
| 订单与成交 | STP TXT 原始文件和证据账本 | 订单、成交、取消、部分成交、跨日成交的最终真相 | 用富途或 UI 手工数据覆盖成交 |
| 计划意图 | Trade Plan | 入场理由、setup、止损、目标、失效条件、计划仓位 | 成交导入后反写篡改计划原文 |
| 市场上下文 | 富途行情 | 分钟线、VWAP、当日高低、成交量环境、watchlist 信号 | 行情缺失时展示空图冒充成功 |
| 复盘结论 | Review Journal | 标签、错误分类、改进结论 | 把主观复盘当作成交真相 |

## 路线图

### P0

- STP TXT 导入。
- STP Evidence Ledger。
- 异常行 quarantine。
- 订单和成交标准化。
- 基础复盘指标。

### P0.5

- Trade Plan 录入。
- 计划与实际成交自动匹配。
- 执行偏差分析。

### P1

- 盘前 watchlist。
- Market Context Replay。
- 图表化复盘。

### P2

- 只对 watchlist 做盘中信号提醒。
- 信号只做提示，不触发下单。

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
- 交易计划可以匹配一笔或多笔成交。
- 未匹配成交、超计划仓位和方向不一致必须显式提示。
- 行情缺失必须显示为 `缺数据`，不能渲染成正常图表。
- 导入后 30 秒内，用户应能找到一笔交易、看到计划偏差、打标签并写复盘结论。

## 文档导航

- [ARCHITECTURE.md](./ARCHITECTURE.md)：系统边界、事实源矩阵、数据流、存储合同和失败语义。
- [TECHNICAL.md](./TECHNICAL.md)：当前技术计划、阶段切片、接口草案、测试策略和开放问题。
- [AGENTS.md](./AGENTS.md)：Codex 和后续工程 agent 的操作规则、交付门禁和变更纪律。
- [CHANGELOG.md](./CHANGELOG.md)：公开变更记录。
- [docs/p0_acceptance.md](./docs/p0_acceptance.md)：P0 DB/API/UI read-model 一致性和验收证据。

## P0 API

- `POST /api/imports/stp-txt`：上传 STP TXT，返回 `batch_id`、`file_hash`、`status`、`accepted_rows`、`quarantined_rows`。
- `GET /api/imports/{batch_id}`：查看批次状态、parser version、mapping version 和错误摘要。
- `GET /api/imports/{batch_id}/quarantine`：查看异常行、原始文本、失败字段、失败原因和修复建议。
- `GET /api/fills`：按日期、账号、symbol 查询 committed 成交 read-model；跨批重导的同一 fallback 成交只展示最新批次。
- `GET /api/review/daily-summary?date=YYYY-MM-DD`：查看只基于 committed 成交 read-model 计算的 PnL、胜率、盈亏比、成交数量和异常行数量；PnL、胜率和盈亏比按已平仓 round-trip 统计。

## 登录快捷方式

Windows 下可双击根目录的 `Login-Grit-DayTrading.cmd` 进入本地复盘台。它会检查 Python 和 npm，按需启动默认后端端口、默认前端端口，并自动打开浏览器。

```powershell
.\Login-Grit-DayTrading.cmd
```

只做快捷方式自检、不启动服务：

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
