import { AlertTriangle, CheckCircle2, FileUp, RefreshCw, TableProperties } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { fetchBatches, fetchDailySummary, fetchFills, fetchQuarantine, uploadStpTxt } from "./api";
import type { DailySummary, FillRow, ImportBatch, QuarantineRow } from "./types";
import "./styles.css";

const today = new Date().toISOString().slice(0, 10);

export default function App() {
  const [date, setDate] = useState(today);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [fills, setFills] = useState<FillRow[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineRow[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh(nextBatchId = selectedBatch) {
    setError(null);
    const [nextBatches, nextFills, nextSummary] = await Promise.all([
      fetchBatches(),
      fetchFills(date),
      fetchDailySummary(date)
    ]);
    setBatches(nextBatches);
    setFills(nextFills);
    setSummary(nextSummary);
    const batchToLoad = nextBatchId ?? nextBatches[0]?.batch_id ?? null;
    setSelectedBatch(batchToLoad);
    setQuarantine(batchToLoad ? await fetchQuarantine(batchToLoad) : []);
  }

  useEffect(() => {
    refresh().catch((err: unknown) => setError(err instanceof Error ? err.message : "加载失败"));
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

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <h1>STP TXT 复盘台</h1>
          <p>订单和成交真相只来自已提交的 STP TXT 证据账本。</p>
        </div>
        <label className="uploadButton">
          <FileUp size={18} />
          <span>{busy ? "导入中" : "上传 TXT"}</span>
          <input type="file" accept=".txt,.tsv,.csv" disabled={busy} onChange={(event) => onUpload(event.target.files?.[0] ?? null)} />
        </label>
      </section>

      {error ? <div className="error"><AlertTriangle size={16} />{error}</div> : null}

      <section className="kpis">
        <label>
          复盘日期
          <input value={date} onChange={(event) => setDate(event.target.value)} type="date" />
        </label>
        <Metric label="成交数" value={summary?.fill_count ?? 0} />
        <Metric label="PnL" value={summary?.pnl ?? 0} />
        <Metric label="胜率" value={`${Math.round((summary?.win_rate ?? 0) * 100)}%`} />
        <Metric label="盈亏比" value={summary?.profit_factor ?? "N/A"} />
        <Metric label="异常行" value={summary?.quarantine_row_count ?? 0} warn={(summary?.quarantine_row_count ?? 0) > 0} />
      </section>

      <section className="layout">
        <aside className="panel">
          <header>
            <h2>导入批次</h2>
            <button onClick={() => refresh()} title="刷新">
              <RefreshCw size={16} />
            </button>
          </header>
          <div className="batchList">
            {batches.map((batch) => (
              <button
                className={batch.batch_id === selectedBatch ? "batch active" : "batch"}
                key={batch.batch_id}
                onClick={() => refresh(batch.batch_id)}
              >
                <span>{batch.file_name}</span>
                <small>{batch.status} · accepted {batch.accepted_rows} · quarantine {batch.quarantined_rows}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="panel mainPanel">
          <header>
            <h2><TableProperties size={18} />成交列表</h2>
            <span className="sourcePill">committed fills only</span>
          </header>
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
                    <td>{fill.filled_at}</td>
                    <td>{fill.account_canonical}</td>
                    <td>{fill.symbol}</td>
                    <td>{fill.side}</td>
                    <td>{fill.quantity}</td>
                    <td>{fill.price}</td>
                    <td>{fill.execution_id ?? "fallback"}</td>
                    <td>line {fill.raw_line_number} · {fill.parser_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section className="panel">
        <header>
          <h2><AlertTriangle size={18} />异常行</h2>
          {selected ? <span className={selected.quarantined_rows > 0 ? "warningPill" : "okPill"}>{selected.quarantined_rows > 0 ? "本批次存在未解析行" : "无异常行"}</span> : null}
        </header>
        <div className="quarantineGrid">
          {quarantine.map((row) => (
            <article key={row.id} className="quarantineItem">
              <strong>line {row.raw_line_number} · {row.reason_code}</strong>
              <p>{row.reason}</p>
              <code>{row.raw_text}</code>
              <small>{row.repair_hint}</small>
            </article>
          ))}
          {quarantine.length === 0 ? <p className="empty"><CheckCircle2 size={16} />当前批次没有异常行。</p> : null}
        </div>
      </section>
    </main>
  );
}

function Metric(props: { label: string; value: number | string; warn?: boolean }) {
  return (
    <div className={props.warn ? "metric warn" : "metric"}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

