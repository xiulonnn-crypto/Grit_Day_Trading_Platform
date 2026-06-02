# AGENTS

本文档是本项目的 agent 操作规则。所有 Codex、工程 agent 和后续自动化 worker 在改动本项目时必须先读本文档。

## 工作顺序

1. 先读 [README.md](./README.md)，确认当前产品范围。
2. 再读 [ARCHITECTURE.md](./ARCHITECTURE.md)，确认事实源和数据流。
3. 再读 [TECHNICAL.md](./TECHNICAL.md)，确认当前阶段、切片和测试策略。
4. 修改用户可见结果或阶段记录时同步 [CHANGELOG.md](./CHANGELOG.md)。
5. 如果新增设计稿、UI 规格、fixture 或脚本，必须在对应根文档里补导航。

## 当前项目状态

- 当前目录是新的空项目基线。
- 当前交付目标是补齐项目文档，不继承相邻项目代码。
- 当前 P0 交付目标是 STP TXT 订单导出到可追溯复盘数据，不做 Trade Plan、富途行情或自动下单。
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
- Trade Plan 是 P0 之后的交易前意图真相源。
- 富途是 P0 之后的行情和市场上下文来源。
- Review Journal 是主观复盘结论来源。
- 这些来源只能互相引用，不能互相覆盖。

## 实施门禁

任何实现 STP 导入、交易计划、行情上下文或复盘展示的改动，都必须在计划或最终报告中说明：

- 当前切片属于 P0、P0.5、P1、P2 还是 P3。
- 本次改动的 canonical source、read model 和 artifact source。
- 幂等 key。
- parser version 和 field mapper version 是否随记录保存。
- 至少一个负向验收路径。
- 文档和 changelog 是否已同步。

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

## P0.5 Agent 要求

Trade Plan 改动必须支持：

- symbol。
- 方向。
- setup。
- 入场理由。
- 止损。
- 目标。
- 失效条件。
- 计划仓位。
- 一笔计划匹配多笔成交。
- 多笔计划同 symbol 的冲突处理。
- 未匹配成交。
- 超计划仓位。

禁止行为：

- 成交导入后改写计划原始文本。
- 把未匹配成交隐藏起来。
- 用 symbol 单字段直接匹配所有计划。

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

禁止行为：

- 富途失败时渲染正常图表。
- 缺分钟线时用静态空图表示成功。
- 用行情数据修改成交价格、成交数量或成交时间。

## 测试纪律

实现前优先固定真实 STP TXT fixture。没有真实样例时，可以先写 contract skeleton 和人工 fixture 结构，但最终 parser 验收必须回到真实样例。

最低测试切片：

- STP TXT：真实样例、重复导入、空文件、缺字段、未知列、部分成交、取消单、跨日成交。
- Evidence Ledger：原始行可追溯、quarantine 可复查、parser version 可重跑。
- Trade Plan：一计划多成交、多计划同 symbol、未匹配成交、超计划仓位。
- Market Context：分钟线缺失、时区错位、盘前盘后成交、富途接口失败。
- UI：导入后 30 秒内能找到一笔交易、看到计划偏差、打标签并写复盘结论。

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
