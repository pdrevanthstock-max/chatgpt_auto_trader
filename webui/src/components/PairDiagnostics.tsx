import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { DiagnosticSnapshot } from "../api/types";
import { currency } from "../format";
import {
  formatIstTimestamp, globalRanking, independentRanking, latestRowsByIndex,
  rowIndex, rowNumber, type DiagnosticRow,
} from "./pairRanking";

interface Props { diagnostics: DiagnosticSnapshot; onStart: (top: 5 | 10) => void; onStop: () => void; }
type Row = DiagnosticRow;

function raw(row: Row, ...keys: string[]) { for (const key of keys) if (row[key] !== undefined && row[key] !== null) return row[key]; return undefined; }
function text(row: Row, ...keys: string[]) { const value = raw(row, ...keys); return value === undefined ? "" : String(value); }
function money(row: Row, ...keys: string[]) { const value = rowNumber(row, ...keys); return value === null ? "—" : currency(value); }
function percent(value: number | null) { return value === null ? "—" : `${value.toFixed(2)}%`; }
function seconds(value: number | null) { return value === null ? "—" : `${value.toFixed(1)}s`; }
function status(row: Row) { return text(row, "result", "verdict", "status", "signal") || "UNKNOWN"; }
function reason(row: Row) { return text(row, "reason", "rejection_reason", "selection_reason") || "—"; }
function pairName(row: Row) { return text(row, "pair", "pair_name", "pair_id") || `${text(row, "ce_strike") || "CE"} CE + ${text(row, "pe_strike") || "PE"} PE`; }
function strike(row: Row, side: "ce" | "pe") {
  const value = text(row, `${side}_strike`) || "—";
  const label = text(row, `${side}_moneyness`, `${side}_bucket`).replace(/^CE_|^PE_/, "");
  return label ? `${value} (${label})` : value;
}
function maxLots(row: Row) {
  const lots = rowNumber(row, "max_lots", "affordable_lots");
  if (lots !== 0) return lots === null ? "—" : String(lots);
  const shortfall = rowNumber(row, "capital_shortfall", "shortfall");
  return `0 — insufficient PAPER money${shortfall && shortfall > 0 ? ` (short ${currency(shortfall)})` : ""}`;
}

const COLUMNS: { label: string; value: (row: Row) => React.ReactNode }[] = [
  { label: "Rank", value: row => text(row, "rank", "position") || "—" },
  { label: "Time (IST)", value: row => formatIstTimestamp(raw(row, "timestamp", "captured_at")) },
  { label: "Pair", value: pairName },
  { label: "CE", value: row => strike(row, "ce") },
  { label: "PE", value: row => strike(row, "pe") },
  { label: "Result", value: status },
  { label: "Reason", value: reason },
  { label: "Divergence", value: row => percent(rowNumber(row, "divergence_pct", "divergence")) },
  { label: "Projected net", value: row => money(row, "projected_net", "projected_net_pnl") },
  { label: "Return", value: row => percent(rowNumber(row, "projected_return_pct", "projected_return")) },
  { label: "Combined ask", value: row => money(row, "combined_ask", "combined_premium") },
  { label: "One-lot cost", value: row => money(row, "one_lot_premium", "one_lot_cost") },
  { label: "Affordable lots", value: maxLots },
  { label: "Quote age", value: row => seconds(rowNumber(row, "quote_age_seconds", "quote_age")) },
  { label: "Details", value: () => null },
];

function CapitalCards({ row, index }: { row: Row; index: string }) {
  const cards = [
    ["Spot", rowNumber(row, "spot", "spot_price")?.toLocaleString("en-IN") ?? "—"],
    ["ATM", text(row, "atm", "atm_strike") || "—"], ["Expiry", text(row, "expiry", "expiry_date") || "—"],
    ["Lot size", text(row, "lot_size") || "—"], ["Combined premium", money(row, "combined_ask", "combined_premium")],
    ["One-lot cost", money(row, "one_lot_premium", "one_lot_cost")], ["Deployable equity", money(row, "deployable_capital", "deployable_equity")],
    ["Affordable lots", maxLots(row)], ["Charges", money(row, "charges_estimate", "estimated_charges")],
    ["Shortfall", money(row, "capital_shortfall", "shortfall")], ["Premium at risk", money(row, "maximum_premium_at_risk", "premium_at_risk")],
    ["Quote age", seconds(rowNumber(row, "quote_age_seconds", "quote_age"))],
  ];
  return <section className="monitor-section" aria-labelledby={`${index}-capital`}><div className="section-heading"><div><p className="eyebrow">Affordability</p><h3 id={`${index}-capital`}>{index} capital</h3></div></div>
    <div className="capital-card-grid">{cards.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
  </section>;
}

interface StrikeItem { strike: number; moneyness: string; }
function universe(row: Row, key: string): StrikeItem[] {
  const value = row[key];
  if (!Array.isArray(value)) return [];
  return value.filter(item => item && typeof item === "object" && Number.isFinite(Number((item as Record<string, unknown>).strike))).map(item => ({
    strike: Number((item as Record<string, unknown>).strike),
    moneyness: String((item as Record<string, unknown>).moneyness ?? ""),
  }));
}

function StrikeUniverse({ row }: { row: Row }) {
  const ce = universe(row, "ce_universe"); const pe = universe(row, "pe_universe");
  const researchCe = universe(row, "research_ce_universe"); const researchPe = universe(row, "research_pe_universe");
  const items = (values: StrikeItem[]) => values.length
    ? values.map(item => <span key={`${item.strike}-${item.moneyness}`}>{item.strike} ({item.moneyness})</span>)
    : <em>Waiting for the next completed scan.</em>;
  return <section className="monitor-section strike-universe" aria-labelledby="strike-universe-title">
    <div className="section-heading"><div><p className="eyebrow">Dynamic option-chain universe</p><h3 id="strike-universe-title">Current ATM / ITM strikes</h3></div><span className="cycle-id">Cycle {text(row, "cycle_id") || "—"}</span></div>
    <div className="strike-row"><strong>CE</strong><div>{items(ce)}</div></div>
    <div className="strike-row"><strong>PE</strong><div>{items(pe)}</div></div>
    {(researchCe.length > 0 || researchPe.length > 0) && <div className="research-strikes"><strong>Guarded OTM research</strong><div className="strike-row"><b>CE</b><div>{items(researchCe)}</div></div><div className="strike-row"><b>PE</b><div>{items(researchPe)}</div></div></div>}
  </section>;
}

function RejectionFunnel({ row }: { row: Row }) {
  const stages = [["Generated", "generated_count"], ["Quotable", "quotable_count"], ["Signal", "signal_count"], ["Economic", "economic_count"], ["Final", "final_count"]];
  const reasons = raw(row, "prefilter_rejection_reasons", "rejection_reasons");
  return <section className="monitor-section" aria-labelledby="funnel-title"><div className="section-heading"><div><p className="eyebrow">Scan funnel</p><h3 id="funnel-title">Why pairs fell away</h3></div></div>
    <div className="funnel" aria-label="Rejection funnel">{stages.map(([label, key], index) => <div key={key} style={{ "--funnel-inset": `${index * 3}%` } as React.CSSProperties}><span>{label}</span><strong>{text(row, key) || "—"}</strong></div>)}</div>
    {reasons && typeof reasons === "object" && <div className="reason-chips">{Object.entries(reasons).map(([item, count]) => <span key={item}>{item.replaceAll("_", " ")} · {String(count)}</span>)}</div>}
  </section>;
}

function GlobalComparison({ rows }: { rows: Row[] }) {
  const ranking = globalRanking(rows);
  if (!ranking.rows.length) return null;
  const winner = ranking.rows[0]; const runnerUp = ranking.rows[1];
  const gap = runnerUp ? (rowNumber(winner, "projected_net", "projected_net_pnl") ?? 0) - (rowNumber(runnerUp, "projected_net", "projected_net_pnl") ?? 0) : null;
  return <section className="global-comparison" aria-labelledby="global-comparison-title">
    <div className="section-heading"><div><p className="eyebrow">Across tradable indices · Top 5</p><h3 id="global-comparison-title">Global candidate comparison</h3></div><span className={ranking.hasExecutableWinner ? "status active" : "status paused"}>{ranking.hasExecutableWinner ? "Executable winner available" : "No executable global winner"}</span></div>
    <p className="comparison-reason">{ranking.hasExecutableWinner ? `${rowIndex(winner)} leads by projected net after all recorded gates${gap === null ? "." : `, ${currency(gap)} ahead of the runner-up.`}` : "No pair passed every gate. The table shows each index’s strongest rejection and exact reason."}</p>
    <div className="table-wrap"><table aria-label="Global Top pairs"><thead><tr><th>Global rank</th><th>Time (IST)</th><th>Index</th><th>CE</th><th>PE</th><th>Result</th><th>Reason</th><th>Confidence</th><th>Projected net</th><th>Return</th><th>Lots</th><th>Why ranked here</th></tr></thead><tbody>{ranking.rows.map((row, index) => <tr key={`${rowIndex(row)}-${pairName(row)}-${index}`}><td>{index + 1}</td><td>{formatIstTimestamp(raw(row, "timestamp", "captured_at"))}</td><td>{rowIndex(row)}</td><td>{strike(row, "ce")}</td><td>{strike(row, "pe")}</td><td>{status(row)}</td><td>{reason(row)}</td><td>{percent(rowNumber(row, "confidence", "strategy_confidence"))}</td><td>{money(row, "projected_net", "projected_net_pnl")}</td><td>{percent(rowNumber(row, "projected_return_pct", "projected_return"))}</td><td>{maxLots(row)}</td><td>{index === 0 && ranking.hasExecutableWinner ? "Best eligible projected net after costs." : status(row) === "PASS" ? "Eligible, ranked below stronger projected economics." : `Observed only: ${reason(row)}.`}</td></tr>)}</tbody></table></div>
  </section>;
}

export function PairDiagnostics({ diagnostics, onStart, onStop }: Props) {
  const [captureTop, setCaptureTop] = useState<5 | 10>(diagnostics.top_count);
  const rowsByIndex = useMemo(() => latestRowsByIndex(diagnostics.rows), [diagnostics.rows]);
  const indices = Object.keys(rowsByIndex);
  const [selected, setSelected] = useState(indices[0] ?? "");
  const [limits, setLimits] = useState<Record<string, 5 | 10>>({});
  const [detail, setDetail] = useState<Row | null>(null);
  const detailTrigger = useRef<HTMLButtonElement | null>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => { if (!rowsByIndex[selected] && indices[0]) setSelected(indices[0]); }, [indices, rowsByIndex, selected]);
  useEffect(() => { if (!detail) return; const close = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape") { setDetail(null); detailTrigger.current?.focus(); } }; window.addEventListener("keydown", close); return () => window.removeEventListener("keydown", close); }, [detail]);
  const selectByArrow = (event: KeyboardEvent<HTMLButtonElement>, index: number) => { if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return; event.preventDefault(); const next = (index + (event.key === "ArrowRight" ? 1 : -1) + indices.length) % indices.length; setSelected(indices[next]); tabs.current[next]?.focus(); };
  const selectedRows = rowsByIndex[selected] ?? [];
  const limit = limits[selected] ?? diagnostics.top_count;
  const visibleRows = independentRanking(selectedRows, limit);
  const best = visibleRows[0] ?? selectedRows[0] ?? {};

  return <section className="panel monitoring-panel" aria-labelledby="diagnostic-title">
    <div className="panel-heading"><div><p className="eyebrow">Diagnostics</p><h2 id="diagnostic-title">Pair inspector</h2><p className="panel-subtitle">Latest completed scan per index, dynamic strikes, visible IST timestamps, and exact rejection evidence.</p></div><span className={diagnostics.capturing ? "status active" : "status paused"}>{diagnostics.capturing ? "Capturing" : "Capture off"}</span></div>
    <div className="toolbar"><label>Capture Top <select value={captureTop} disabled={diagnostics.capturing} onChange={event => setCaptureTop(Number(event.target.value) as 5 | 10)}><option value={5}>5</option><option value={10}>10</option></select></label>{!diagnostics.capturing ? <button className="primary" onClick={() => onStart(captureTop)}>Start capture</button> : <button className="danger" onClick={onStop}>Stop capture</button>}<a className="button-link" href="/api/diagnostics/download?format=csv">CSV</a><a className="button-link" href="/api/diagnostics/download?format=json">JSON</a></div>
    {diagnostics.rows.length === 0 ? <p className="empty-state">No captured scan rows. Start capture to collect subsequent completed-candle scans.</p> : <>
      <GlobalComparison rows={Object.values(rowsByIndex).flat()} />
      <div className="index-tabs" role="tablist" aria-label="Index pair rankings">{indices.map((index, position) => <button key={index} ref={element => { tabs.current[position] = element; }} role="tab" id={`tab-${index}`} aria-controls={`panel-${index}`} aria-selected={selected === index} tabIndex={selected === index ? 0 : -1} onKeyDown={event => selectByArrow(event, position)} onClick={() => setSelected(index)}>{index}<small>{independentRanking(rowsByIndex[index], diagnostics.top_count).length} pairs</small></button>)}</div>
      <div role="tabpanel" id={`panel-${selected}`} aria-labelledby={`tab-${selected}`} className="index-workspace">
        <div className="monitoring-split"><CapitalCards row={best} index={selected} /><RejectionFunnel row={best} /></div>
        <StrikeUniverse row={best} />
        <section className="monitor-section" aria-labelledby={`${selected}-pairs`}><div className="section-heading"><div><p className="eyebrow">Independent ranking</p><h3 id={`${selected}-pairs`}>{selected} Top {limit}</h3></div><div className="compact-segmented" aria-label={`${selected} pair limit`}><button className={limit === 5 ? "selected" : ""} onClick={() => setLimits(current => ({ ...current, [selected]: 5 }))}>Top 5</button><button className={limit === 10 ? "selected" : ""} onClick={() => setLimits(current => ({ ...current, [selected]: 10 }))}>Top 10</button></div></div>
          <div className="table-wrap"><table aria-label={`${selected} Top pairs`}><thead><tr>{COLUMNS.map(column => <th key={column.label}>{column.label}</th>)}</tr></thead><tbody>{visibleRows.map((row, index) => <tr key={`${text(row, "cycle_id")}-${pairName(row)}-${index}`}>{COLUMNS.map(column => <td key={column.label}>{column.label === "Details" ? <button ref={element => { if (detail === row) detailTrigger.current = element; }} className="inspect-button" aria-label={`Inspect ${pairName(row)}`} onClick={event => { detailTrigger.current = event.currentTarget; setDetail(row); }}>Inspect</button> : column.value(row)}</td>)}</tr>)}</tbody></table></div>
        </section>
      </div>
    </>}
    {detail && <div className="drawer-backdrop" onMouseDown={() => setDetail(null)}><aside className="details-drawer" role="dialog" aria-modal="true" aria-labelledby="pair-detail-title" onMouseDown={event => event.stopPropagation()}><div className="section-heading"><div><p className="eyebrow">Full diagnostic record</p><h3 id="pair-detail-title">Pair details</h3></div><button autoFocus onClick={() => { setDetail(null); detailTrigger.current?.focus(); }} aria-label="Close pair details">Close</button></div><dl>{Object.entries(detail).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</dd></div>)}</dl></aside></div>}
  </section>;
}
