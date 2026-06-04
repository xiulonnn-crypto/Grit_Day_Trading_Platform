# 日内复盘台布局规格

## 目标用户

个人日内交易者，在收盘后用 STP TXT、分钟线归档、盘前 watchlist 和策略 run 复查当天执行质量。

## 视觉方向

采用交易 journal 和 trade replay 工具常见的信息层级：顶部日期和指标过滤，主图优先，右侧放盘前工作栏，交易回放作为成交行的动作，导入批次和隔离行沉到底部证据区。参考方向来自 TradeZella 的 Dashboard / Trade Page、Tradervue 的 trading journal 能力说明，以及 TradesViz 的导入故障语义说明。

参考链接：

- [TradeZella Getting Started](https://help.tradezella.com/en/articles/13863136-getting-started-with-tradezella)
- [TradeZella Trade Page](https://help.tradezella.com/en/articles/5860216-understanding-the-trade-page)
- [Tradervue Trading Journal Template](https://www.tradervue.com/trading-journal-template)
- [TradesViz Import Guide](https://tradesviz.crisp.help/en/article/how-to-import-trades-from-tradersync-to-tradesviz-step-by-step-guide-shdn2w/)

## 页面结构

- 顶部：产品名、P2 阶段标签、STP 上传入口。
- KPI 行：复盘日期、复盘标的、成交数、成交股数、PnL、胜率、盈亏比、隔离行。
- 首屏工作区：左侧分钟蜡烛复盘，右侧盘前 Watchlist 和操作入口。
- 成交记录：全宽交易组表格；Trade Replay 入口为行内 `查看` 按钮。
- 底部证据区：左侧导入批次与批次证据，右侧隔离行。
- 弹层：策略配置和 Trade Replay 维持现有合同。

## 响应式

- 桌面宽屏：`reviewWorkspace` 为主图加右侧工作栏，右侧工作栏 sticky。
- 中等宽度：主图独占一行，Watchlist 和操作入口两列并排。
- 移动：所有区块单列；批次详情、最新批次和表头操作纵向排列。

## 事实源合同

- 当前切片：P2 UI Parity。
- Canonical source：STP TXT、`import_batches`、`fills`、`watchlist_runs`、`watchlist_items`、`market_minute_archives`、`strategy_signal_runs`。
- Read model：`GET /api/fills`、`GET /api/trade-groups`、`GET /api/watchlist`、`GET /api/market-data/minute-archives`、`GET /api/strategy-runs`。
- Artifact source：`file_hash`、`raw_line`、`parser_version`、`field_mapper_version`、`bars_hash`、`metrics_hash`、`indicator_hash`。
- Idempotency key：批次 `file_hash`；watchlist `trade_date + provider + rules_version`；strategy run 使用既有 P2 幂等合同。
- Parser version 和 field mapper version：本次只重新布局展示，不改变保存口径。

## 负向验收

- 缺分钟线归档时，主图显示缺失状态，不渲染成功蜡烛图。
- Watchlist provider failure 或零结果时，右侧 Watchlist 保留失败或空状态。
- 未清仓交易组不提供 Trade Replay 按钮，只显示未清仓状态。
- 无导入批次时，底部证据区显示空状态，不伪造 file hash 或 parser version。

## 实现映射

- `web/src/App.tsx`：重排 JSX 信息架构，保留 API 和状态计算。
- `web/src/styles.css`：新增 `reviewWorkspace`、`reviewRail`、`tradeLedgerPanel`、`evidenceGrid`、`importEvidenceLayout` 等布局样式。
- `CHANGELOG.md`：记录复盘台布局结果。
- `README.md`：补充设计包导航。

## 可见文案

- `盘前 Watchlist`
- `操作入口`
- `交易组`
- `批次证据`
- `导入批次与证据`
- `分钟蜡烛复盘`
- `成交记录`
- `隔离行`

## Handoff Contract

- Canonical page：复盘台首页。
- Canonical viewport：桌面 1440px、平板 1080px、移动 390px。
- Canonical sections：KPI 行、首屏工作区、成交记录、底部证据区。
- Legacy fragment：旧 `p1Grid` 中独立 Trade Replay 面板不再作为目标布局。
- Allowed live-data substitutions：所有数字、symbol、状态、hash、reason code 和 metrics 值均来自现有 API read model。
- Deferred：不新增 Review Journal 入口，不新增自动下单，不新增前端指标计算。
