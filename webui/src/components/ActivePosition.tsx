import type { ActivePositionView } from "../api/types";
import { currency, dateTime } from "../format";

export function ActivePosition({ position }: { position: ActivePositionView | null }) {
  return <section className="panel" aria-labelledby="position-title">
    <div className="panel-heading"><div><p className="eyebrow">Position</p><h2 id="position-title">Active position</h2></div>{position && <span className="status active">{position.phase}</span>}</div>
    {!position ? <div className="empty-state"><strong>No active position</strong><p>Risk monitoring remains independent of browser state.</p></div> : <>
      <div className="quantity-banner"><strong>{position.lots} lots</strong><strong>{position.units_per_leg.toLocaleString("en-IN")} units / leg</strong></div>
      <div className="detail-grid">
        <div><span>Trade</span><strong>{position.trade_id}</strong></div><div><span>Direction</span><strong>{position.direction}</strong></div>
        <div><span>CE</span><strong>{position.ce_strike} @ {currency(position.ce_entry)}</strong></div><div><span>PE</span><strong>{position.pe_strike} @ {currency(position.pe_entry)}</strong></div>
        <div><span>Hard stop</span><strong>{currency(position.hard_stop_loss)}</strong></div><div><span>Entry</span><strong>{dateTime(position.entry_time)}</strong></div>
      </div>
      {position.mark_to_market_available ? <p className="position-pnl">Active P&amp;L: {currency(position.active_pnl)}</p> : <p className="warning">Live mark unavailable. The UI will not invent prices or P&amp;L from persisted entry data.</p>}
    </>}
  </section>;
}
