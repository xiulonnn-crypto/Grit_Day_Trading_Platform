# P3「交易总结」设计规格

## 设计结论

- 批准时间：2026-07-22。
- 批准方向：证据优先的紧凑双栏复盘面板。
- 目标用户：需要把历史日内闭合交易转成可执行复盘纪律的个人交易者。
- 核心任务：在不改写成交事实、不伪造交易结论的前提下，快速识别应该重复执行的条件和应该规避的错误。
- 设计语言来源：项目当前浅灰页面背景、白色面板、青绿色主强调、红棕风险强调和紧凑信息密度。仓库没有 `DESIGN.md`，本切片不新增全局设计文件。

## Canonical artifacts

- `spec.md`：设计与实现交接合同。
- `spec.html`：批准方向的静态 HTML 预览。
- `spec.png`：以 1440 × 1000 桌面视口从最终实现截取的批准方向截图；`spec.html` 保留同方向静态预览。
- UI 验收矩阵：`output/ui-artifact-trace/trade-summary-tab/trace-matrix.md`。

## 页面和路由

- 页面 key：`trade-review.trade-summary`。
- 用户入口：根应用 query `grit_ui=ai-strategy-recommendation-v2`。
- 工作区：顶层「交易复盘」。
- 子 tab 顺序：`数据下钻`、`盈亏复盘`、`交易总结`。
- 目标视口：桌面 1440 × 1000；移动 390 × 844。

## 布局结构

1. 子 tab 导航：保持既有紧凑分段控件，激活项使用青绿色底色。
2. 标题区：`交易总结`、混合模式说明、规则目录版本 pill。
3. 共享日期筛选：`全部 / 本月 / 本周 / 特定时间段`。该状态与「盈亏复盘」共用；盈亏单单选不进入本页。
4. 样本概览：一行八项指标。桌面 8 列，1080px 以下 4 列，560px 以下单列。
5. AI 摘要：独立状态卡，状态 badge 位于右上；当前 Codex 会话基于脱敏聚合证据生成 narrative，服务层校验后写入 artifact，页面只 GET 并标注“摘要来源：本次会话”。浏览器不提供模型生成按钮，也不自动 POST。
6. 个性化规则：桌面左右双栏，左为「推荐执行规则」，右为「推荐规避错误」；900px 以下改为单列。
7. 样本不足：用三条进度条替换个性化双栏，并展示六条经典基线卡。
8. 经典方法依据：默认折叠；展开后显示研究和风险来源链接。
9. 免责声明：底部浅灰提示条。

## 状态合同

### Evidence

- `no_trades`：无闭合交易；展示零样本、经典基线和准备进度，禁用生成。
- `insufficient_sample`：闭合交易不足 20，或盈利/亏损任一不足 5；展示缺口，禁用生成。
- `eligible`：门槛满足；展示个性化规则和可用生成动作。

### Generation

- `not_requested`：当前范围尚无本会话摘要；量化规则照常显示。
- `unconfigured`：没有本会话 artifact 且可选本地模型未配置；UI 仍统一显示等待会话摘要。
- `pending`：artifact 正在生成或写入；规则照常显示。
- `completed`：通过 JSON、规则 ID 和无新增数字校验。
- `failed`：摘要不可用或响应无效；保留确定性量化规则。
- `stale`：证据、规则目录或提示词变化；旧文案不能代表当前范围，不自动调用模型。

## 组件合同

| 组件 | 必填内容 | 行为 |
| --- | --- | --- |
| `ReviewSharedTimeFilter` | 四种范围、可选自定义起止日期、当前范围标签 | 父层持有状态，两个子 tab 共用 |
| `TradeSummaryPanel` | 标题、样本、AI 状态、摘要来源、规则、来源、免责声明 | 进入时只 GET；有匹配 `codex_session` artifact 时直接展示，否则显示等待会话摘要 |
| `TradeSummaryProgress` | 名称、缺口、进度百分比 | 不允许超过 100% |
| `TradeSummaryRuleColumn` | 标题、规则卡、空态 | 桌面双栏、移动单列 |
| 规则卡 | 家族、标题、量化适用条件、量化执行步骤、可选会话点评 | 固定展示 K 线数、量能倍数、ATR、风险百分比、R 倍数、分批比例、跟踪退出或停手线；支持笔数/支持率不得作为推荐内容 |

## 数据映射

- 所有指标、覆盖率、规则、排序和证据金额只读 `GET /api/review/trade-summary`。
- 页面只调用 `GET /api/review/trade-summary`；当前会话生成摘要时由受信任服务层重新计算证据并写入 `trade_summary_generations`，浏览器不提交规则 ID、证据、模型文案或生成请求。
- AI narrative 只能作为对应规则卡的“会话点评”，不能修改卡片标题、量化条件或动作步骤。
- `trade_summary_contract_v3` 返回 `provider=codex_session` 的匹配 artifact 和目录 v2 的 `condition/action_steps`。支持/命中证据仍在后端审计字段中，但不进入主视觉推荐。
- 比例分母只统计具备对应评价因子或 Journal 归因的可观察交易；缺分钟线或缺 Journal 不得计作未命中。
- 缺分钟线只降低分钟线评价覆盖；缺 Journal 只降低亏损 Journal 覆盖，不当作“没有错误”。

## 视觉 tokens

```css
:root {
  --review-bg: #fbfcfd;
  --review-surface: #ffffff;
  --review-border: #dce3e8;
  --review-text: #1f2933;
  --review-muted: #607080;
  --review-accent: #1f6f67;
  --review-accent-soft: #eef8f6;
  --review-risk: #b4533e;
  --review-risk-soft: #fff6f5;
  --review-radius: 8px;
  --review-gap: 14px;
}
```

- 字体：项目现有系统无衬线 stack。
- 正文：12–13px，`line-height: 1.55`。
- 标题：14–18px，`font-weight: 800–900`。
- 阴影：不新增浮夸阴影，依靠边框、浅底色和 3px 顶边强调层级。

## 可访问性

- 子 tab 和日期范围按钮必须保留 `aria-pressed`。
- AI 状态区使用 `aria-live="polite"`。
- 所有链接使用可辨识文字，并在新窗口打开时保留 `rel="noreferrer"`。
- 完成态必须显示“摘要来源：本次会话”；没有匹配 artifact 时清楚说明页面不会自动调用模型。
- 390px 下不得横向溢出；主按钮和子 tab 变为全宽。

## 验收与允许偏离

- 桌面必须显示八项样本指标和双栏规则。
- 移动端必须按单列顺序显示，不隐藏量化动作或免责声明。
- loading、无数据、样本不足、等待会话摘要、生成中、完成、失败、stale 均需自动化或人工证据。
- 规则卡必须可读地展示量化条件与逐项动作；桌面双列、移动单列均不得截断 R、ATR、百分比或 K 线参数。
- 没有匹配本会话 artifact 是正式负向路径，不得用静态文案冒充完成；确定性量化规则始终可见。
- 批准偏离：无。
- 延后事项：不在本切片引入异步后台队列、多模型选择器或 Review Journal 自由文本分析。
