# AI策略 v2 设计追踪矩阵

| 需求 | 实现证据 | 自动化证据 | 运行态证据 | 状态 |
| --- | --- | --- | --- | --- |
| AI 推荐目录替换为五个新日内策略 | `ai_strategy_catalog_v2` 仅返回 ORB 5m、ORB Retest 15m、VWAP Opening Drive、VWAP Pullback、Last-hour Momentum | `tests/test_ai_strategy.py` 固定 v2 顺序与旧目录退出名单 | `live-desktop.png` 榜单展示五个新策略 | PASS |
| 100k / 20% 同口径历史收益 | API 只聚合匹配资本与建议参数 hash 的 test artifacts | recommendation key、资本不匹配与排序门槛测试 | 首位显示 `$46.33/笔`、`$787.65`、17 笔闭合信号 | PASS |
| 非可用日期透明排除 | `non_available_archive` 保留逐日失败 artifact，不生成信号或 PnL | excluded day 可比排序与负向测试 | 页面显示 8/9 个排除日期及“不计入收益”说明 | PASS |
| 入场、出场、止盈、止损、仓位、品种、参数与理由 | 目录 v2 是唯一文案与参数事实源，前端只读渲染 | frontend contract 固定详情字段与只读 CTA | 桌面详情台展示完整策略逻辑和 100k 风险口径 | PASS |
| 桌面榜单 + 详情台 | 36% / 64% 双列布局 | TypeScript typecheck 与 production build | `live-desktop.png`，1440px 视口 | PASS |
| 移动端上下堆叠且无横向滚动 | `<=1080px` 单列、`<=560px` 控件与 Tab 纵排 | CSS/front-end contract | `live-mobile.png`；375px visual viewport，document scroll width 375px | PASS |
| 只读，不自动测试、不改配置、不下单 | GET 推荐接口无写操作；CTA 仅切换工作区 | API/frontend contract | 浏览器验收仅产生 GET，控制台 0 error | PASS |
| 风险透明 | API 返回样本内、未计佣金滑点、非未来盈利声明 | disclaimer contract | 桌面与移动端均显示风险条 | PASS |
| v2 静态设计 PNG | `spec.html` 已更新为 v2；现有 `spec.png` 仍是 v1 概念稿 | 不适用 | 本地 `file:` 页面受浏览器安全策略阻止，未能刷新 `spec.png` | BLOCKED |

## 截图口径

- `live-desktop.png`：当前运行态 1440 × 1000 首屏，截止日期 `2026-07-13`，18 个完成日、9 个排除日期，排名与 `2026-07-14` 基准一致。
- `live-mobile.png`：当前运行态 390px viewport，验证四个工作区 Tab 纵排、资本/日期/标的单列和本地回放排名。
- `spec.png`：被 v2 替代的 v1 概念稿，仅作历史追溯；v2 设计真相源为 `spec.html` 与两张 live 截图。
