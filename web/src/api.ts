import type { DailySummary, FillRow, ImportBatch, QuarantineRow } from "./types";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`API ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function uploadStpTxt(file: File): Promise<ImportBatch> {
  const body = new FormData();
  body.append("file", file);
  return readJson<ImportBatch>(await fetch("/api/imports/stp-txt", { method: "POST", body }));
}

export async function fetchBatches(): Promise<ImportBatch[]> {
  const payload = await readJson<{ items: ImportBatch[] }>(await fetch("/api/imports"));
  return payload.items;
}

export async function fetchQuarantine(batchId: string): Promise<QuarantineRow[]> {
  const payload = await readJson<{ items: QuarantineRow[] }>(await fetch(`/api/imports/${batchId}/quarantine`));
  return payload.items;
}

export async function fetchFills(date?: string): Promise<FillRow[]> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  const payload = await readJson<{ items: FillRow[] }>(await fetch(`/api/fills${query}`));
  return payload.items;
}

export async function fetchDailySummary(date: string): Promise<DailySummary> {
  return readJson<DailySummary>(await fetch(`/api/review/daily-summary?date=${encodeURIComponent(date)}`));
}

