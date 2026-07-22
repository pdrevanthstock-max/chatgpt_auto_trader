import { useEffect, useMemo, useState } from "react";
import type { CapitalSnapshot } from "../api/types";
import { currency, dateTime } from "../format";

interface Props {
  capital: CapitalSnapshot;
  engineRunning?: boolean;
  hasOpenPosition?: boolean;
  onAdjust?: (target: number, note: string) => void;
}

type AdjustmentMode = "deposit" | "withdraw";

export function CapitalPanel({
  capital,
  engineRunning = false,
  hasOpenPosition = false,
  onAdjust,
}: Props) {
  const available = Number(capital.equity ?? 0);
  const [mode, setMode] = useState<AdjustmentMode>("deposit");
  const [amountText, setAmountText] = useState("");
  const [note, setNote] = useState("PAPER test money adjustment");
  useEffect(() => setAmountText(""), [capital.equity]);
  const amount = Number(amountText);
  const signedAmount = mode === "deposit" ? amount : -amount;
  const result = available + (Number.isFinite(amount) ? signedAmount : 0);
  const locked = engineRunning || hasOpenPosition;
  const validation = useMemo(() => {
    if (locked) return engineRunning
      ? "Stop the PAPER engine before changing simulated money."
      : "Close the active PAPER position before changing simulated money.";
    if (!Number.isFinite(amount) || amount <= 0) return "Enter a positive amount.";
    if (!note.trim()) return "Enter an audit note.";
    if (mode === "withdraw" && result < 0) return "Withdrawal cannot exceed available PAPER money.";
    return "";
  }, [amount, engineRunning, hasOpenPosition, locked, mode, note, result]);

  const submit = () => {
    if (validation || !onAdjust) return;
    onAdjust(result, note.trim());
  };

  return <section className="panel capital-panel" aria-labelledby="capital-title">
    <div className="panel-heading"><div><p className="eyebrow">Simulated capital</p><h2 id="capital-title">PAPER money &amp; ledger</h2><p className="panel-subtitle">Local test money only. Deposits and withdrawals never touch Dhan or real funds.</p></div><span className="paper-lock">PAPER only</span></div>
    <div className="metric-grid">
      <div><span>Available PAPER Money</span><strong>{currency(available)}</strong></div>
      <div><span>Today PAPER P&amp;L</span><strong className={(capital.today_realized_pnl ?? 0) < 0 ? "negative" : "positive"}>{currency(capital.today_realized_pnl ?? 0)}</strong></div>
      <div><span>Month PAPER P&amp;L</span><strong className={(capital.month_realized_pnl ?? 0) < 0 ? "negative" : "positive"}>{currency(capital.month_realized_pnl ?? 0)}</strong></div>
      <div><span>Net Deposits / Withdrawals</span><strong>{currency(capital.cash_adjustments)}</strong></div>
    </div>
    <div className="capital-adjustment">
      <div className="segmented" aria-label="PAPER money adjustment type">
        <button className={mode === "deposit" ? "selected" : ""} onClick={() => setMode("deposit")}>Deposit</button>
        <button className={mode === "withdraw" ? "selected" : ""} onClick={() => setMode("withdraw")}>Withdraw</button>
      </div>
      <div className="capital-form">
        <label>Amount (₹)<input aria-label="Amount" type="text" inputMode="decimal" disabled={locked} value={amountText} onChange={event => setAmountText(event.target.value)} placeholder="Example: 5000" /></label>
        <label>Audit note<input aria-label="Audit note" disabled={locked} value={note} onChange={event => setNote(event.target.value)} placeholder="Why are you changing PAPER money?" /></label>
        <button className="primary" disabled={Boolean(validation) || !onAdjust} onClick={submit}>Apply PAPER {mode}</button>
      </div>
      <div className="adjustment-preview" aria-label="PAPER money preview">
        <span>Current {currency(available)}</span><span>{mode === "deposit" ? "+" : "−"} {currency(Number.isFinite(amount) ? amount : 0)}</span><strong>Resulting available money {currency(result)}</strong>
      </div>
      {validation && <p className={locked || (amount > 0 && note.trim()) ? "warning" : "hint"}>{validation}</p>}
    </div>
    <h3>Recent PAPER ledger activity</h3>
    {capital.transactions.length === 0 ? <p className="empty-state">No PAPER deposits, withdrawals, or P&amp;L records.</p> : <div className="table-wrap"><table><thead><tr><th>Time</th><th>Type</th><th>Amount</th><th>Note</th></tr></thead><tbody>{capital.transactions.slice(0, 10).map(item => <tr key={item.id}><td>{dateTime(item.timestamp)}</td><td>PAPER {item.type}</td><td>{currency(item.amount)}</td><td>{item.note}</td></tr>)}</tbody></table></div>}
  </section>;
}
