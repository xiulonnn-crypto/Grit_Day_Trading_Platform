# AI策略 Top 5 推荐台设计规格

## 页面目标

- 面向个人日内交易者，在不触发 GET 自动运行、不修改配置、不下单的前提下，比较研究后新增的五个 P2 策略模板及同口径本地回放收益。
- 页面只展示后端推荐 read model；研究排序与本地回放证据必须分层表达。
- Canonical page key：`ai-strategy-recommendation-v2`。
- Canonical URL query：`?grit_ui=ai-strategy-recommendation-v2`。
- Frozen direction：证据优先的“左侧 Top 5 榜单 + 右侧策略详情台”。

## 视觉方向

仓库没有全局 `DESIGN.md`。本页面沿用现有日内复盘台的浅灰背景、白色面板、青绿色主操作色、8px 圆角、紧凑中文信息密度，不新增全局 token。

design-shotgun 原计划比较“证据优先、风险优先、紧凑分析台”三个方向；本机位图生成器缺少生成服务凭据，按降级规则使用 HTML wireframe。批准计划中的默认方向“证据优先”作为实施基线。当前 v2 验收以 `spec.html`、`live-desktop.png` 与 `live-mobile.png` 为准；`spec.png` 仅保留被 v2 替代的 v1 概念稿，不作为实现验收依据。

## 布局与响应式

- 桌面宽度：最大 1440px。控制条在上，主体为 `36% / 64%` 两列。
- 左侧榜单固定展示五项：排名、策略名、研究家族、证据状态和盈利期望摘要。
- 右侧按“证据摘要、交易逻辑、风险与仓位、推荐品种、建议参数、推荐理由、研究来源”排序。
- `<=1080px`：主体改为单列，榜单在前、详情在后。
- `<=560px`：工作区 Tab 纵向排列；控制项、指标和双列详情全部改为单列。

## Design tokens

```css
--ai-bg: #f4f6f8;
--ai-panel: #ffffff;
--ai-ink: #1f2933;
--ai-muted: #607080;
--ai-accent: #1f6f67;
--ai-accent-soft: #edf7f5;
--ai-border: #dce3e8;
--ai-warn: #ad6800;
--ai-danger: #a8071a;
--ai-radius: 8px;
--ai-gap: 12px;
```

- 字体：`Inter, Segoe UI, Microsoft YaHei, sans-serif`。
- 标题：16px/700；正文：13px/1.55；说明：12px/1.45；关键指标：20px/700。
- 边框：1px；阴影只用于当前 Tab 和选中榜单项。

## 组件与状态

| 组件 | 必须状态 | 合同 |
|---|---|---|
| 顶部控制条 | loading、ready、error | 本金固定 `$100,000`；可修改截止日期与标的；不提供运行按钮 |
| 排名依据 | research、local | 只有五个策略全部达到可比证据门槛才显示“本地回放排序” |
| 榜单项 | selected、research_only、partial、backtested | v2 只展示五个新模板；缺数据时不得显示推算或占位盈利数字 |
| 详情证据卡 | insufficient、partial、verified | `expected_pnl_per_closed_trade` 只来自闭合信号；显示 completed days、closed groups 和参数一致性 |
| 逻辑区 | ready | 入场、出场、止盈、止损文案均来自后端目录 |
| 参数区 | ready、config_mismatch | 展示建议参数；当前配置偏离时显示明确警告，不自动套用 |
| CTA | enabled、disabled | “去策略测试”只切换 Tab 并带入策略、日期、标的 |

## 数据与格式

- 金额使用 `USD`，两位小数；百分比使用一位小数；profit factor 使用两位小数。
- `null` 盈利指标显示“尚未通过本地归档验证”，不得显示 `0` 或 `--` 冒充已测结果。
- 推荐品种按“流动性画像 + 示例 ticker + 原因”展示，不作为实时选股。
- 多标的汇总只累加独立回放 PnL；最大回撤取单标的最大值；明确提示未建模并发资金占用。
- 收益证据同时展示每笔闭合信号期望 PnL、窗口总 PnL、胜率、Profit Factor、最大回撤、完成归档日、闭合信号和排除日期。
- `non_available_archive` 日期保持失败日 artifact，不生成信号或收益；若五个策略共享同一 archive scope 且各自达到至少 10 个完成日和 10 笔闭合信号，该日期可作为“明确排除日”而不阻止可比排序。
- 研究来源使用可访问链接；免责声明固定说明“本地回放是样本内历史结果，未计佣金与滑点，不代表未来盈利”。

## Accessibility

- 榜单使用原生 `button`，提供 `aria-pressed`；状态不能只靠颜色区分。
- 详情区使用语义标题层级；外链带清晰名称并在新窗口打开。
- 键盘焦点使用 3px 半透明青绿色 focus ring。
- 移动端不得产生页面级横向滚动。

## Implementation handoff

- 后端 canonical catalog：`ai_strategy_catalog_v2`。
- 前端只消费 `GET /api/ai-strategy-recommendations`，不得复制指标计算或排名逻辑。
- 目标组件：`AiStrategyWorkspace`；App 只负责 Tab、共享日期/标的与“去策略测试”跳转。
- 允许 live 替代：策略配置名、证据指标、状态和 recommendation key。
- 不允许偏离：自动运行测试、自动修改参数、自动应用候选、展示虚构盈利数字、删除免责声明。
- Desktop screenshot：1440px；mobile screenshot：390px。最终截图与 trace matrix 必须逐项验收。

## 当前本地回放基准

固定口径：`MU`、截止 `2026-07-14`、最近 30 个自然日、初始本金 `$100,000`、单次入场 `20%`。18 个完成归档日进入收益统计，8 个非可用日期保留失败 artifact 并明确排除。结果为样本内历史回放，未计佣金、滑点和多策略并发资本。

| 排名 | 新策略 | 每笔闭合信号期望 PnL | 窗口总 PnL | 胜率 | Profit Factor | 最大回撤 | 闭合信号 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5分钟开盘区间突破 | `$46.33` | `$787.65` | `47.1%` | `2.05` | `$439.77` | 17 |
| 2 | 15分钟开盘区间突破回踩 | `$35.80` | `$357.99` | `50.0%` | `1.88` | `$106.20` | 10 |
| 3 | 尾盘半小时动量 | `$23.76` | `$356.47` | `66.7%` | `3.21` | `$57.75` | 15 |
| 4 | VWAP 开盘驱动延续 | `$9.47` | `$151.56` | `43.8%` | `1.14` | `$396.68` | 16 |
| 5 | VWAP 趋势回踩 | `$2.29` | `$38.89` | `41.2%` | `1.05` | `$278.01` | 17 |

## v2 Superseded

- 原 v1 的“不新增独立 ORB/VWAP 引擎”已被本次需求覆盖；v2 新增 5 分钟 ORB、15 分钟 ORB 回踩、VWAP 开盘驱动、VWAP 趋势回踩和尾盘动量五个独立模板。
- Trend Rider、BB Squeeze、Momentum Mean Reversion、Liquidity Sweep 和 Range Fader 退出 AI Top 5，但历史配置、run、test batch 和 artifact 保留追溯。

## Deferred

- 不新增全局 `DESIGN.md`；只有后续确认本页 token 可复用时再提升为系统规则。
- 不建模多策略并发组合资本曲线。
