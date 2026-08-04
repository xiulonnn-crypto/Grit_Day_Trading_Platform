# 交易回测 UI Artifact Trace Matrix

| 设计规格区域 | 实现映射 | 状态与证据 | 响应式验收 | 状态 | 验收证据 |
| --- | --- | --- | --- | --- | --- |
| `spec.html` · 第四子 Tab | `ReviewDrillSurfaceTab` 与「交易回测」按钮 | React state 切换，不影响前三个子 Tab | 桌面单行；390px 为 2×2 | PASS | frontend contract 通过；真实 DOM 显示四个子 Tab，390px computed columns 为 `163px 163px` |
| `spec.html` · 标题与主操作 | `TradeBacktestPanel` header 与「运行四组回测」 | 进入只 GET；按钮显式 POST，运行时 disabled | 窄屏 header 纵向排列、按钮全宽 | PASS | 真实浏览器进入 Tab 读取最新 v5 run；全历史四组均为 completed |
| `spec.html` · 规则说明 | A/B/C 规则卡 | 文案只读取 `trade_backtest_rule_catalog_v5` presets API | 桌面三列；移动端单列 | PASS | presets API 与真实 DOM 均显示 A=200 股、B=1000 USD、C=200+1000 |
| `spec.html` · 运行状态 | 最近匹配范围的 run 元数据 | 覆盖 loading、empty、completed、partial_failed、failed/no_trades | 状态块在窄屏改为单列 | PASS | 覆盖缺口与局部质量异常 target 允许 B/C 隔离后完成；缺失、provider 不可用或结构/hash 无效归档仍为 partial_failed |
| `spec.html` · 四场景结果 | `TradeBacktestScenarioRow` | 所有指标直接读取 API；显示忽略不完整时段数量，失败场景显示 N/A 与原因 | 桌面四行表；移动端四张场景卡 | PASS | 真实 DOM 为 4 rows；移动端 table=`block`、row=`grid`，四个场景均显示 `2 个日期/标的` |
| 页面级响应式与错误检查 | 既有 review shell + 新回测样式 | 不修改 committed fills/策略配置；无浏览器 console warning/error | 1280×720 与 390×844 均无页面横向溢出 | PASS | 两个 viewport 均为 `scrollWidth == clientWidth`；移动端 table=`block`、row=`grid`、Tab 为 2×2；console error/warning 为 0 |

设计方向沿用既有本地交易复盘视觉语言；该切片不新增或修改全局 `DESIGN.md`。
