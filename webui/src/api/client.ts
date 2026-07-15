import type {
  ActivePositionView, CapitalSnapshot, DiagnosticSnapshot, IndexSelection,
  IndexUniverseResponse, PerformancePeriod, PerformanceSnapshot, TradeRow
  , RuntimeSnapshot
} from "./types";

async function checked<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  indices: () => fetch("/api/indices").then(checked<IndexUniverseResponse>),
  updateSelection: (symbols: string[], expectedVersion: number) =>
    fetch("/api/indices/selection", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols, expected_version: expectedVersion })
    }).then(checked<IndexSelection>),
  performance: (period: PerformancePeriod, mode = "PAPER") =>
    fetch(`/api/performance?period=${period}&mode=${mode}`).then(checked<PerformanceSnapshot>),
  activePosition: (mode = "PAPER") =>
    fetch(`/api/positions/active?mode=${mode}`).then(checked<ActivePositionView | null>),
  trades: (mode = "PAPER") => fetch(`/api/trades?mode=${mode}`).then(checked<TradeRow[]>),
  capital: (mode = "PAPER") => fetch(`/api/capital?mode=${mode}`).then(checked<CapitalSnapshot>),
  diagnostics: () => fetch("/api/diagnostics").then(checked<DiagnosticSnapshot>),
  startDiagnostics: (topCount: 5 | 10) => fetch("/api/diagnostics/start", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ top_count: topCount })
  }).then(checked<DiagnosticSnapshot>),
  stopDiagnostics: () => fetch("/api/diagnostics/stop", { method: "POST" }).then(checked<DiagnosticSnapshot>)
  ,runtime: () => fetch("/api/runtime").then(checked<RuntimeSnapshot>),
  startEngine: () => fetch("/api/engine/start", { method: "POST" }).then(checked<RuntimeSnapshot>),
  stopEngine: () => fetch("/api/engine/stop", { method: "POST" }).then(checked<RuntimeSnapshot>),
  adjustPaperTarget: (targetEquity: number, note: string) => fetch("/api/capital/paper/target", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_equity: targetEquity, note })
  }).then(checked<CapitalSnapshot>)
};
