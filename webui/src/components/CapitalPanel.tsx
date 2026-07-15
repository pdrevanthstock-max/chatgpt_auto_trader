import { useState } from "react";
import type { CapitalSnapshot } from "../api/types";
import { currency, dateTime } from "../format";

interface Props { capital: CapitalSnapshot; engineRunning?: boolean; onAdjust?: (target: number, note: string) => void; }

export function CapitalPanel({ capital, engineRunning = false, onAdjust }: Props) {
  const [target, setTarget] = useState(capital.equity ?? capital.base_capital ?? 0);
  const [note, setNote] = useState("PAPER test capital adjustment");
  return <section className="panel" aria-labelledby="capital-title"><div className="panel-heading"><div><p className="eyebrow">Capital</p><h2 id="capital-title">PAPER equity &amp; ledger</h2></div><span className="status paused">Read only</span></div>
    <div className="metric-grid"><div><span>Current equity</span><strong>{currency(capital.equity)}</strong></div><div><span>Base capital</span><strong>{currency(capital.base_capital)}</strong></div><div><span>Deposits / withdrawals</span><strong>{currency(capital.cash_adjustments)}</strong></div></div>
    <h3>Recent ledger activity</h3>{capital.transactions.length === 0 ? <p className="empty-state">No PAPER deposits, withdrawals, or adjustments recorded.</p> : <div className="table-wrap"><table><thead><tr><th>Time</th><th>Type</th><th>Amount</th><th>Note</th></tr></thead><tbody>{capital.transactions.slice(0, 10).map(item => <tr key={item.id}><td>{dateTime(item.timestamp)}</td><td>{item.type}</td><td>{currency(item.amount)}</td><td>{item.note}</td></tr>)}</tbody></table></div>}
    <div className="capital-form"><label>Target PAPER equity<input type="number" min="0" value={target} onChange={event => setTarget(Number(event.target.value))} /></label><label>Audit note<input value={note} onChange={event => setNote(event.target.value)} /></label><button className="primary" disabled={engineRunning || !onAdjust || !note.trim()} onClick={() => onAdjust?.(target, note)}>Apply PAPER target</button></div>
    <p className="hint">Adjustments are append-only and accepted only while the engine is stopped with no open position.</p>
  </section>;
}
