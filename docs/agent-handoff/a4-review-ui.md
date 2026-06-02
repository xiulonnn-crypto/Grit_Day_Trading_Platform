# A4 Review UI Handoff

## 任务边界

- 阶段切片：P0 Review UI。
- Ownership：`web/src/App.tsx`、`web/src/styles.css`、本 handoff。
- 禁止修改：`web/src/types.ts`、`web/src/api.ts`、`src/` 后端文件、`api.py`。
- 事实源：STP TXT 导入批次和 evidence ledger。
- Read model：`/api/imports`、`/api/imports/{batch_id}/quarantine`、`/api/fills`、`/api/review/daily-summary`。
- Artifact source：上传文件 hash、原始行、parser version、field mapper version。
- 幂等 key：批次使用 `file_hash`；成交优先 `account_canonical + execution_id`，缺 execution id 时 UI 显示 fallback。
- KPI 口径：PnL、胜率和盈亏比只展示 `committed_fills_only` summary。

## UI Trace Matrix

| 验收项 | 来源 | 实现目标 | 负向路径 | 验收证据 |
| --- | --- | --- | --- | --- |
| 上传入口 | README P0 API | 上传按钮、busy、错误提示、重复导入状态 | 上传失败不能只在终端报错 | `npm.cmd --prefix web run typecheck`、`npm.cmd --prefix web run build` |
| 批次状态 | AGENTS P0 | 批次列表展示 status、row count、file hash、parser 和 mapper version | 失败批次仍必须可见 | 同上 |
| 异常行 | TECHNICAL UI Acceptance | failed field、reason、repair hint、raw evidence preview | quarantine 行不得进入 fills | 同上 |
| 成交表 | ARCHITECTURE P0 data contract | 长 symbol、长账号、side、quantity、price、execution id、追溯字段 | 缺 execution id 显示 fallback，不伪装成成功 id | 同上 |
| 基础 KPI | README 当前范围 | 成交数、PnL、胜率、盈亏比、异常行、summary source | 零成交显示空态，不显示误导性指标 | 同上 |
| 空状态 | AGENTS 测试纪律 | 无批次、无成交、无异常行都有用户可见解释 | 空文件或无成交不得渲染成正常成交表 | 同上 |
| 响应式和长文本 | 用户目标 | 长账号、长 symbol、长文件名、长 repair hint 不撑破布局 | 移动视口不可互相覆盖 | 同上 |

## Changelog Candidate

- **P0 复盘台体验**: 强化上传、批次状态、异常行、成交表和空状态展示，让导入结果和基础复盘指标更容易核对。

## Integration Update

- A0 later synced `web/src/types.ts` with `batch_id`, `trade_group_count`, `traded_quantity`, and fallback execution-id fields.
- Current validation passed `npm.cmd --prefix web run typecheck`.
- Current validation passed `npm.cmd --prefix web run build`.
- Current full backend validation passed `python -m pytest -q` with `35 passed`.
