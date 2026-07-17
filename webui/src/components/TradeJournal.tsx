import { useMemo, useState } from "react";
import type { TradeRow } from "../api/types";
import { currency, dateTime } from "../format";
import { filterTradesByPeriod, type JournalPeriod } from "./journalFilters";

const PERIODS: { value: JournalPeriod; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
  { value: "all", label: "All" },
];

export function TradeJournal({ trades, now }: { trades: TradeRow[]; now?: Date }) {
  const [period, setPeriod] = useState<JournalPeriod>("today");
  const visible = useMemo(() => filterTradesByPeriod(trades, period, now ?? new Date()), [now, period, trades]);
  const selectedLabel = PERIODS.find(item => item.value === period)?.label ?? "Today";
  return <section className="panel" aria-labelledby="journal-title">
    <div className="panel-heading"><div><p className="eyebrow">History</p><h2 id="journal-title">Trade journal</h2><p className="panel-subtitle">{selectedLabel} · {visible.length} visible {visible.length === 1 ? "trade" : "trades"}</p></div><span className="status active">{trades.length} total</span></div>
    <div className="segmented journal-periods" aria-label="Trade journal period">{PERIODS.map(item => <button key={item.value} className={period === item.value ? "selected" : ""} onClick={() => setPeriod(item.value)}>{item.label}</button>)}</div>
    {visible.length === 0 ? <p className="empty-state">No PAPER trades were recorded for {selectedLabel.toLowerCase()}.</p> : <div className="table-wrap"><table><thead><tr><th>Index</th><th>Trade</th><th>Entry</th><th>Pair</th><th>Lots / Units</th><th>Exit reason</th><th>Gross</th><th>Costs</th><th>Net</th></tr></thead><tbody>{visible.map(trade => <tr key={trade.trade_id}><td>{trade.index_symbol}</td><td>{trade.trade_id}</td><td>{dateTime(trade.entry_time)}</td><td>{trade.ce_strike} CE / {trade.pe_strike} PE</td><td>{trade.lots} / {trade.units_per_leg}</td><td>{trade.exit_reason ?? trade.phase}</td><td>{currency(trade.gross_pnl)}</td><td>{currency(trade.transaction_costs)}</td><td className={trade.net_pnl < 0 ? "negative" : "positive"}>{currency(trade.net_pnl)}</td></tr>)}</tbody></table></div>}
  </section>;
}
