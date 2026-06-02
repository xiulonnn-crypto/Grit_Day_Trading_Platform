import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Clock3,
  FileText,
  FileUp,
  Hash,
  ListChecks,
  RefreshCw,
  TableProperties
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchBatches, fetchDailySummary, fetchFills, fetchQuarantine, uploadStpTxt } from "./api";
import type { DailySummary, FillRow, ImportBatch, QuarantineRow } from "./types";
import "./styles.css";

const today = new Date().toISOString().slice(0, 10);

const statusMeta: Record<
  ImportBatch["status"],
  { label: string; detail: string; tone: "info" | "ok" | "warn" | "danger" }
> = {
  uploaded: { label: "已上传", detail: "等待解析确认", tone: "info" },
  parsing: { label: "解析中", detail: "批次仍在处理", tone: "warn" },
  committed: { label: "已入账", detail: "可用于复盘 KPI", tone: "ok" },
  failed: { label: "导入失败", detail: "需要查看异常行", tone: "danger" },
  retry_requested: { label: "待重试", detail: "等待重新解析", tone: "warn" }
};

const sourceLabel: Record<DailySummary["source"], string> = {
  committed_fills_only: "只基于 committed fills"
};

const releaseHighlights = [
  {
    title: "无表头 TXT",
    detail: "按默认成交字段合同解析，缺价格等问题进入异常行。"
  },
  {
    title: "修正重导",
    detail: "证据批次保留，成交列表和 KPI 不重复计算重叠成交。"
  },
  {
    title: "Fallback 成交",
    detail: "缺 execution id 的成交在表格中明确标识 fallback key。"
  },
  {
    title: "Round-trip KPI",
    detail: "PnL、胜率和盈亏比只按已平仓交易分组计算。"
  }
];

const integerFormatter = new Intl.NumberFormat("en-US");
const decimalFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2
});

export default function App() {
  const [date, setDate] = useState(today);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [fills, setFills] = useState<FillRow[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineRow[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(nextBatchId = selectedBatch) {
    setLoading(true);
    setError(null);
    try {
      const [nextBatches, nextFills, nextSummary] = await Promise.all([
        fetchBatches(),
        fetchFills(date),
        fetchDailySummary(date)
      ]);
      setBatches(nextBatches);
      setFills(nextFills);
      setSummary(nextSummary);
      const requestedBatch = nextBatchId
        ? nextBatches.find((batch) => batch.batch_id === nextBatchId)?.batch_id ?? null
        : null;
      const batchToLoad = requestedBatch ?? nextBatches[0]?.batch_id ?? null;
      setSelectedBatch(batchToLoad);
      setQuarantine(batchToLoad ? await fetchQuarantine(batchToLoad) : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [date]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const batch = await uploadStpTxt(file);
      await refresh(batch.batch_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  const selected = useMemo(
    () => batches.find((batch) => batch.batch_id === selectedBatch) ?? null,
    [batches, selectedBatch]
  );
  const selectedStatus = selected ? statusMeta[selected.status] : null;
  const hasFills = fills.length > 0;
  const hasBatches = batches.length > 0;
  const summaryNote = summary ? sourceLabel[summary.source] : "等待 summary";

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">P0 Review Desk</p>
          <h1>STP TXT 复盘台</h1>
          <p>订单和成交真相只来自已提交的 STP TXT 证据账本。</p>
        </div>
        <label className={busy ? "uploadButton busy" : "uploadButton"} aria-busy={busy}>
          <FileUp size={18} />
          <span>{busy ? "导入中" : "上传 TXT"}</span>
          <input
            type="file"
            accept=".txt,.tsv,.csv"
            disabled={busy}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0] ?? null;
              event.currentTarget.value = "";
              void onUpload(file);
            }}
          />
        </label>
      </section>

      {error ? (
        <div className="error" role="alert">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      <section className="releasePanel" aria-label="本次更新点">
        <header>
          <div>
            <h2>
              <ListChecks size={18} />
              本次更新点
            </h2>
            <p className="panelNote">P0 复盘真相源已完成集成验证。</p>
          </div>
          <span className="sourcePill">P0 已验证</span>
        </header>
        <div className="releaseGrid">
          {releaseHighlights.map((item) => (
            <article className="releaseItem" key={item.title}>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="kpis" aria-label="P0 复盘指标">
        <label className="dateControl">
          <span>复盘日期</span>
          <input value={date} onChange={(event) => setDate(event.target.value)} type="date" />
        </label>
        <Metric label="成交数" value={formatInteger(summary?.fill_count ?? 0)} note={summaryNote} />
        <Metric label="交易股数" value={formatInteger(summary?.traded_quantity ?? 0)} note="BUY/SELL 配对股数" />
        <Metric label="PnL" value={formatPnl(summary?.pnl ?? 0)} tone={summaryTone(summary?.pnl ?? 0)} />
        <Metric label="胜率" value={formatWinRate(summary)} />
        <Metric label="盈亏比" value={formatProfitFactor(summary)} />
        <Metric
          label="异常行"
          value={formatInteger(summary?.quarantine_row_count ?? 0)}
          tone={(summary?.quarantine_row_count ?? 0) > 0 ? "warn" : "ok"}
        />
      </section>

      <section className="layout">
        <aside className="panel">
          <header>
            <div>
              <h2>
                <FileText size={18} />
                导入批次
              </h2>
              <p className="panelNote">file_hash 是批次幂等 key。</p>
            </div>
            <button className="iconButton" onClick={() => void refresh()} title="刷新" aria-label="刷新批次和复盘数据">
              <RefreshCw className={loading ? "spin" : undefined} size={16} />
            </button>
          </header>

          {hasBatches ? (
            <div className="batchList">
              {batches.map((batch) => {
                const meta = statusMeta[batch.status];
                return (
                  <button
                    className={batch.batch_id === selectedBatch ? "batch active" : "batch"}
                    key={batch.batch_id}
                    onClick={() => void refresh(batch.batch_id)}
                  >
                    <span className="batchRow">
                      <span className="batchFile" title={batch.file_name}>
                        {batch.file_name}
                      </span>
                      <span className={`statusPill ${meta.tone}`}>{meta.label}</span>
                    </span>
                    <small>
                      rows {formatInteger(batch.row_count)} · accepted {formatInteger(batch.accepted_rows)} · quarantine{" "}
                      {formatInteger(batch.quarantined_rows)}
                    </small>
                    {batch.duplicate ? <span className="duplicateNote">重复文件，沿用既有批次</span> : null}
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<CircleSlash size={18} />}
              title="还没有导入批次"
              detail="上传 STP TXT 后，这里会显示批次状态、幂等结果和异常行数量。"
            />
          )}
        </aside>

        <section className="panel mainPanel">
          <header>
            <div>
              <h2>
                <TableProperties size={18} />
                成交列表
              </h2>
              <p className="panelNote">PnL、胜率和盈亏比只使用 committed fills。</p>
            </div>
            <span className="sourcePill">{summaryNote}</span>
          </header>

          {hasFills ? (
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>账号</th>
                    <th>Symbol</th>
                    <th>方向</th>
                    <th>数量</th>
                    <th>价格</th>
                    <th>Exec ID</th>
                    <th>追溯</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.map((fill) => (
                    <tr key={fill.id}>
                      <td className="timeCell">{formatDateTime(fill.filled_at)}</td>
                      <td className="textCell">
                        <span className="monoWrap" title={fill.account_canonical}>
                          {fill.account_canonical}
                        </span>
                        {fill.account_raw && fill.account_raw !== fill.account_canonical ? (
                          <small title={fill.account_raw}>raw {fill.account_raw}</small>
                        ) : null}
                      </td>
                      <td className="textCell">
                        <span className="symbolText" title={fill.symbol}>
                          {fill.symbol}
                        </span>
                      </td>
                      <td>
                        <span className={fill.side === "BUY" ? "sidePill buy" : "sidePill sell"}>{fill.side}</span>
                      </td>
                      <td>{formatInteger(fill.quantity)}</td>
                      <td>{decimalFormatter.format(fill.price)}</td>
                      <td className="textCell">
                        {fill.execution_id ? (
                          <span className="monoWrap" title={fill.execution_id}>
                            {fill.execution_id}
                          </span>
                        ) : (
                          <span className="fallbackPill" title="缺 execution id 时使用组合幂等 key">
                            fallback key
                          </span>
                        )}
                      </td>
                      <td className="traceCell">
                        <span>line {fill.raw_line_number}</span>
                        <small>
                          {fill.parser_version} · {fill.field_mapper_version}
                        </small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={<CircleSlash size={18} />}
              title="当前日期没有 committed 成交"
              detail="KPI 保持 0 或 N/A；请检查复盘日期或导入批次状态。"
            />
          )}
        </section>
      </section>

      <section className="panel batchDetailPanel">
        <header>
          <div>
            <h2>
              <Hash size={18} />
              批次证据
            </h2>
            <p className="panelNote">展示 parser version、field mapper version 和原始文件 hash 摘要。</p>
          </div>
          {selectedStatus ? <span className={`statusPill ${selectedStatus.tone}`}>{selectedStatus.label}</span> : null}
        </header>

        {selected ? (
          <>
            <dl className="batchFacts">
              <div>
                <dt>文件名</dt>
                <dd className="wrapValue" title={selected.file_name}>
                  {selected.file_name}
                </dd>
              </div>
              <div>
                <dt>file_hash</dt>
                <dd className="monoWrap" title={selected.file_hash}>
                  {shortHash(selected.file_hash)}
                </dd>
              </div>
              <div>
                <dt>parser version</dt>
                <dd>{selected.parser_version}</dd>
              </div>
              <div>
                <dt>field mapper version</dt>
                <dd>{selected.field_mapper_version}</dd>
              </div>
              <div>
                <dt>批次状态</dt>
                <dd>{selectedStatus?.detail}</dd>
              </div>
              <div>
                <dt>异常行</dt>
                <dd>{formatInteger(selected.quarantined_rows)}</dd>
              </div>
            </dl>
            {selected.status_reason ? (
              <div className="statusReason">
                <AlertTriangle size={16} />
                <span>{selected.status_reason}</span>
              </div>
            ) : null}
          </>
        ) : (
          <EmptyState icon={<Clock3 size={18} />} title="未选择批次" detail="导入 STP TXT 或选择一个历史批次后查看证据字段。" />
        )}
      </section>

      <section className="panel">
        <header>
          <div>
            <h2>
              <AlertTriangle size={18} />
              异常行
            </h2>
            <p className="panelNote">失败字段、失败原因和修复建议必须可复查。</p>
          </div>
          {selected ? (
            <span className={selected.quarantined_rows > 0 ? "warningPill" : "okPill"}>
              {selected.quarantined_rows > 0 ? "本批次存在未解析行" : "无异常行"}
            </span>
          ) : null}
        </header>
        <div className="quarantineGrid">
          {selected && quarantine.length > 0
            ? quarantine.map((row) => (
                <article key={row.id} className="quarantineItem">
                  <div className="quarantineHeader">
                    <strong>line {row.raw_line_number}</strong>
                    <span className="failedField">{row.failed_field}</span>
                    <span className="reasonCode">{row.reason_code}</span>
                  </div>
                  <p>{row.reason}</p>
                  <code>{row.raw_text}</code>
                  <small>{row.repair_hint}</small>
                </article>
              ))
            : null}
          {selected && quarantine.length === 0 ? (
            <EmptyState icon={<CheckCircle2 size={18} />} title="当前批次没有异常行" detail="所有可解析行都已进入 normalized orders/fills 或批次仍无异常记录。" />
          ) : null}
          {!selected ? <EmptyState icon={<Clock3 size={18} />} title="等待批次" detail="选择导入批次后查看 quarantine 行。" /> : null}
        </div>
      </section>
    </main>
  );
}

function Metric(props: { label: string; value: number | string; note?: string; tone?: "neutral" | "ok" | "warn" | "bad" }) {
  return (
    <div className={`metric ${props.tone ?? "neutral"}`}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
      {props.note ? <small>{props.note}</small> : null}
    </div>
  );
}

function EmptyState(props: { icon: ReactNode; title: string; detail: string }) {
  return (
    <div className="emptyState">
      {props.icon}
      <div>
        <strong>{props.title}</strong>
        <p>{props.detail}</p>
      </div>
    </div>
  );
}

function formatInteger(value: number) {
  return integerFormatter.format(value);
}

function formatPnl(value: number) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${decimalFormatter.format(value)}`;
}

function summaryTone(value: number): "neutral" | "ok" | "bad" {
  if (value > 0) return "ok";
  if (value < 0) return "bad";
  return "neutral";
}

function formatWinRate(summary: DailySummary | null) {
  if (!summary || summary.trade_group_count === 0) return "N/A";
  return `${decimalFormatter.format(summary.win_rate * 100)}%`;
}

function formatProfitFactor(summary: DailySummary | null) {
  if (!summary || summary.trade_group_count === 0 || summary.profit_factor === null) return "N/A";
  return decimalFormatter.format(summary.profit_factor);
}

function formatDateTime(value: string) {
  return value.replace("T", " ").replace("Z", " UTC");
}

function shortHash(value: string) {
  if (value.length <= 18) return value;
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}
