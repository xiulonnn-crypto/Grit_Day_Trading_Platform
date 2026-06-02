# P0 Acceptance Evidence

本文档记录 A5 QA / Evidence 对 P0 STP TXT 导入链路的验收矩阵。当前切片只补测试与证据，不修改 backend source、API source 或 web source。

## 阶段切片

- 当前阶段：P0。
- 当前切片：QA / Evidence。
- Canonical source：STP TXT 原始文件、`import_batches`、`import_rows`、`quarantine_rows`、`orders`、`fills`。
- Read model：导入批次、成交列表、异常行列表、daily summary API payload。
- Artifact source：`tests/fixtures/stp_sample.tsv`、`tests/fixtures/stp_p0_edge_cases.tsv`、`tests/fixtures/stp_missing_required.tsv`、`tests/test_e2e_p0.py`。
- 幂等 key：批次使用 `file_hash`；原始行使用 `batch_id + raw_line_number + raw_line_hash`；订单使用 `account_canonical + order_id`；成交优先使用 `account_canonical + execution_id`，缺失 execution id 时使用 fallback key。
- Parser version：`PARSER_VERSION` 随批次和原始行保存。
- Field mapper version：`FIELD_MAPPER_VERSION` 随批次和原始行保存。

## Fixture Matrix

| Fixture | 用途 | 覆盖点 | 验收口径 |
| --- | --- | --- | --- |
| `stp_sample.tsv` | 当前固定 STP 参考样例 | 账号 canonicalization、取消单、quarantine、PnL | 作为 parser 和 import API 回归样例 |
| `stp_p0_edge_cases.tsv` | 模拟边界样例 | partial fill、缺 execution id fallback、取消单、跨日成交、未知列、缺价格 quarantine | 作为 P0 e2e QA 主样例 |
| `stp_missing_required.tsv` | 负路径样例 | 缺 order id、缺 symbol、无成功行 | 批次失败可见，不写 committed fills |

说明：当前仓库没有可验证的真实券商原始 STP TXT。现有样例均为去敏或人工样例，最终 parser 验收仍需回到首个真实 STP TXT 样例。

## Acceptance Matrix

| 验收项 | DB 证据 | API 证据 | UI read-model 证据 | 结论 |
| --- | --- | --- | --- | --- |
| STP TXT 上传批次 | `import_batches.file_hash` 唯一 | `POST /api/imports/stp-txt` 返回 `batch_id`、`file_hash`、`status` | 上传后批次卡片可显示状态和计数 | PASS |
| 原始文件 hash | `file_hash` 长度为 64 | 上传响应返回同一 hash | 批次 trace 使用该批次响应 | PASS |
| 原始行保留 | `import_rows.raw_text` 和 `raw_line_hash` 非空 | 成交和 quarantine payload 追溯 raw line number | 成交行 trace 显示 `line + parser version` | PASS |
| parser version | 批次和原始行保存 `PARSER_VERSION` | fills payload 返回 parser version | 成交 trace 可见 parser version | PASS |
| field mapper version | 批次和原始行保存 `FIELD_MAPPER_VERSION` | fills payload 返回 field mapper version | 与成交 read-model 一起可追溯 | PASS |
| 账号 canonicalization | `account_raw` 保留，`account_canonical = strip().upper()` | fills payload 返回 canonical account | 成交列表显示 canonical account | PASS |
| quarantine 行 | `quarantine_rows` 保存失败字段和修复提示 | quarantine API 返回 reason code、failed field、review status | 异常行卡片可显示 line、reason、failed field | PASS |
| normalized orders/fills | `orders` 和 `fills` 只写 accepted 语义 | fills API 按日期返回 committed fills | 成交列表使用 committed fills | PASS |
| 重复导入幂等 | 重复上传后 DB 表计数不增加 | 第二次上传返回同一 `batch_id` 且 `duplicate=true` | UI 应复用同一批次响应 | PASS |
| KPI committed-only | daily summary 从 `fills` 计算 | API 返回 `source=committed_fills_only` | KPI 卡片使用 daily summary | PASS |
| 纯失败批次 | 无 orders/fills 写入 | failed batch 和 quarantine rows 可查 | 失败状态可由批次 read-model 显示 | PASS |
| 批次列表选择字段 | `import_batches.id` 存在 | `GET /api/imports` 返回 `batch_id` alias | React 批次列表读取 `batch_id` | PASS |

## DB / API / UI Consistency Report

| 对象 | DB 值 | API 值 | UI read-model 值 | Source of truth | Preview | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| Batch status | `committed` | `committed` | 批次卡片 `committed` | `import_batches` | 否 | PASS |
| Accepted rows | `5` | `5` | 批次卡片 accepted `5` | `import_rows.row_status` | 否 | PASS |
| Quarantine rows | `1` | `1` | 批次卡片 quarantine `1` | `quarantine_rows` | 否 | PASS |
| Day 1 fills | `3` | `3` | 成交列表 `3` 行 | `fills` | 否 | PASS |
| Day 2 fills | `1` | `1` | 成交列表可按日期查询 | `fills` | 否 | PASS |
| Fallback execution id | `execution_id IS NULL` | `execution_id=null` | Exec ID 显示 `fallback` | `fills.idempotency_key` | 否 | PASS |
| Daily summary source | committed fills only | `source=committed_fills_only` | KPI 卡片读取同一 summary | `fills` | 否 | PASS |
| Batch list id alias | `id` | 返回 `batch_id` alias | 批次列表读取 `batch_id` | `import_batches.id` | 否 | PASS |

## Negative Acceptance

- 空文件：批次状态为 `failed`，`status_reason=empty_file`，无 committed fills。
- 缺关键字段：批次状态为 `failed`，quarantine 行保留失败字段，orders/fills 不写入。
- 未知列：保存在 parsed payload 的 `_unknown_columns`，不静默丢弃。
- 取消单：写入 order，不写入 fill。
- 缺 execution id 成交：写入 fill，并在 UI read-model 中显示 fallback。

## Remaining Risks

- 当前没有可验证的真实 STP 原始样例；需要真实样例后补 broker-format fixture 并复跑 parser 验收。
- `GET /api/imports` 已返回前端消费的 `batch_id` alias，并进入硬验收。
- 本次没有启动浏览器做 DOM 几何或截图验收；UI 证据限定为当前 React 页面消费的 API read model。
- `CHANGELOG.md` 由 A0 集成 owner 统一同步，worker handoff 不直接写公开变更记录。
