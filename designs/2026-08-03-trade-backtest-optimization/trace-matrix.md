# 交易回测组合优化 UI Artifact Trace Matrix

| 设计规格区域 | 实现目标 | 状态/数据映射 | 桌面/移动验收 | 状态 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 参数输入 | `TradeBacktestOptimizationWorkbench` A/B 候选输入 | API 返回恢复后的 7×10 默认参数空间与宽范围安全边界 | 2 列 / 1 列 | PASS | 真实页面载入 A 7 值、B 10 值，组成 70 个候选 |
| 主操作与状态 | “运行组合优化”、loading/empty/error | POST 显式运行；GET 只选择当前优化引擎的匹配范围结果 | 按钮右对齐 / 全宽 | PASS | 页面在较新的 v2 artifact 存在时仍选择 v1 的 70/70 结果；POST 复用原 artifact |
| 最佳组合摘要 | 后端 `best_candidate` | PnL、delta、A/B 参数、rank 全部只读 | 单行 KPI / 2 列 | PASS | API、DB artifact 与页面均显示 A=500、B=1000、rank=1、PnL=-1623.818756 |
| 完整候选矩阵 | 后端完整 `matrix` | cell rank/tone/metrics 由 API 提供 | 内部滚动 / 内部滚动 | PASS | DOM 为 10 行×7 列，宽内容限制在矩阵容器内部 |
| Top 10 排名 | 后端 `top_candidates` | `total_candidates` 来自 batch ledger，Top 10 不是 canonical total | 表格 / 卡片 | PASS | manifest 为 70/70，DOM 展示 10 个排名候选 |
| 失败与边界 | invalid params、missing evidence、open/cross-day | 不生成伪最佳值；不显示应用按钮 | 中文可见状态 | PASS | focused 测试覆盖 422、404、硬归档失败、覆盖不完整继续和宽范围恢复 |
| 页面级响应式 | 现有 review shell + optimization styles | 页面无横向溢出 | 1280×900、390×844 | PASS | 桌面 documentWidth=1265≤1280；移动 documentWidth=375≤390，四个子 Tab 为 2×2 |

批准偏离：矩阵内容允许容器内部横向滚动；页面级横向滚动仍不允许。
