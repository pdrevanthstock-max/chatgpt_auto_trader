import type { TradeRow } from "../api/types";
import { currency, dateTime } from "../format";

export function TradeJournal({ trades }: { trades: TradeRow[] }) {
  return <section className="panel" aria-labelledby="journal-title"><div className="panel-heading"><div><p className="eyebrow">History</p><h2 id="journal-title">Trade journal</h2></div><span className="status active">{trades.length} trades</span></div>
    {trades.length === 0 ? <p className="empty-state">No PAPER trades have been recorded.</p> : <div className="table-wrap"><table><thead><tr><th>Trade</th><th>Entry</th><th>Pair</th><th>Lots / Units</th><th>Exit reason</th><th>Gross</th><th>Costs</th><th>Net</th></tr></thead><tbody>{trades.map(trade => <tr key={trade.trade_id}><td>{trade.trade_id}</td><td>{dateTime(trade.entry_time)}</td><td>{trade.ce_strike} CE / {trade.pe_strike} PE</td><td>{trade.lots} / {trade.units_per_leg}</td><td>{trade.exit_reason ?? trade.phase}</td><td>{currency(trade.gross_pnl)}</td><td>{currency(trade.transaction_costs)}</td><td className={trade.net_pnl < 0 ? "negative" : "positive"}>{currency(trade.net_pnl)}</td></tr>)}</tbody></table></div>}
  </section>;
}
