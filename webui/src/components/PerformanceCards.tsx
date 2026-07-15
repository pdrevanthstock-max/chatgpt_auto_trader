import type { PerformancePeriod, PerformanceSnapshot } from "../api/types";
import { currency } from "../format";

const periods: { value: PerformancePeriod; label: string }[] = [
  { value: "today", label: "Today" }, { value: "week", label: "Week" },
  { value: "month", label: "Month" }, { value: "year", label: "Year" },
  { value: "all_time", label: "All time" }
];

interface Props { snapshot: PerformanceSnapshot; period: PerformancePeriod; onPeriodChange: (period: PerformancePeriod) => void; }

export function PerformanceCards({ snapshot, period, onPeriodChange }: Props) {
  return <section className="panel" aria-labelledby="performance-title">
    <div className="panel-heading"><div><p className="eyebrow">Performance</p><h2 id="performance-title">Period P&amp;L</h2></div><span className="status active">{snapshot.mode}</span></div>
    <div className="segmented" aria-label="P&L period">{periods.map(item => <button key={item.value} className={period === item.value ? "selected" : ""} onClick={() => onPeriodChange(item.value)}>{item.label}</button>)}</div>
    <div className="metric-grid">
      <div><span>Realized</span><strong className={snapshot.realized_pnl < 0 ? "negative" : "positive"}>{currency(snapshot.realized_pnl)}</strong></div>
      <div><span>Active</span><strong className={snapshot.active_pnl < 0 ? "negative" : "positive"}>{currency(snapshot.active_pnl)}</strong></div>
      <div><span>Total</span><strong className={snapshot.total_pnl < 0 ? "negative" : "positive"}>{currency(snapshot.total_pnl)}</strong></div>
    </div>
  </section>;
}
