# Technical Plan

本文档记录当前技术计划、阶段切片、接口草案、测试策略和开放问题。

## 当前技术真相

- 项目目标是 STP 日内交易闭环 Web 系统。
- STP TXT 是订单和成交真相源。
- P0 不接富途行情。
- P0 不做 Trade Plan。
- 首版只做提醒和复盘，不自动下单。
- 首个真实 STP TXT 样例将决定 parser fixture 和字段合同。
- 当前实现前建议先跑工程方案复审，确认数据模型、Web 栈和验收命令。
- 当前已完成 P0 scaffold：FastAPI、SQLite、STP TXT parser、导入 API、React 复盘台和测试 fixture。

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

### P0.5 Trade Plan

目标：

- 支持交易前或交易中录入计划。
- 自动匹配 STP fills。
- 计算计划与执行偏差。

验收：

- 一笔计划匹配多笔成交。
- 多笔计划同 symbol 进入冲突处理。
- 未匹配成交可见。
- 超计划仓位可见。
- 成交导入不会改写计划原文。

### P1 Market Context Replay

目标：

- 接入富途分钟线和日内摘要。
- 为每笔 fill 生成 market context snapshot。
- 在复盘页展示成交时刻、VWAP、当日高低、成交量环境和缺数据状态。

验收：

- 分钟线缺失显示 `缺数据`。
- 富途接口失败显示 provider failure。
- 时区错位进入诊断状态。
- 盘前和盘后成交按独立 session 语义展示。

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
```

### Trade Plans

```text
POST /api/trade-plans
GET  /api/trade-plans
GET  /api/trade-plans/{plan_id}
PUT  /api/trade-plans/{plan_id}
POST /api/trade-plans/{plan_id}/match
GET  /api/trade-plans/{plan_id}/deviation
```

### Market Context

```text
POST /api/market-context/replay
GET  /api/fills/{fill_id}/market-context
GET  /api/watchlist
PUT  /api/watchlist
```

这些 API 是 P0 合同。P0 不能移除证据账本、quarantine、幂等导入和 committed-only KPI 语义。

## Parser 合同

Parser 必须输出：

- `parser_version`
- `field_mapper_version`
- `raw_line`
- `row_number`
- `raw_line_sha256`
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

## Matching 合同

计划匹配使用分层规则：

1. `account_scope`、symbol、方向、计划有效窗口完全匹配。
2. 如果一笔计划对应多笔成交，全部记录到 match 表。
3. 如果多个计划同 symbol 且时间窗口重叠，生成冲突候选，不自动选择。
4. 如果成交方向与计划方向不一致，保留成交并记录 deviation。
5. 如果成交数量超过计划仓位，记录 over-plan deviation。

## Market Context 合同

每笔 fill 的 replay 请求应记录：

- provider。
- 请求开始和结束时间。
- provider timezone。
- 返回 bar 数量。
- bars hash。
- VWAP。
- 当日高低。
- 成交量环境。
- failure reason。

`available` 以外的状态都必须在 UI 可见。

## 测试计划

当前固定验证命令：

```powershell
python -m pytest -q
npm.cmd --prefix web run typecheck
npm.cmd --prefix web run build
```

当前 P0 集成测试覆盖 24 个 Python 用例，包含 parser、storage contract、import API 和 DB/API/UI read-model 一致性。

### P0 Tests

- 真实 STP TXT 样例。
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

### P0.5 Tests

- 一笔计划匹配多笔成交。
- 多笔计划同 symbol。
- 未匹配成交。
- 超计划仓位。
- 方向不一致。
- 手工覆盖 match。

### P1 Tests

- 分钟线缺失。
- 时区错位。
- 盘前成交。
- 盘后成交。
- 富途接口失败。
- provider 返回 partial bars。

### UI Acceptance

- 上传后能看到批次状态。
- 失败行显示字段和修复建议。
- 30 秒内找到一笔交易。
- 交易详情展示证据 row、计划偏差、market context 状态。
- 用户可以打标签并写复盘结论。

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
- Trade Plan 匹配是否需要人工确认队列。
- Market Context Replay 的数据缓存策略。
- UI 是否先做导入和详情页薄切片。
