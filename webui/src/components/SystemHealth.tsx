import type { SystemHealthSnapshot } from "../api/types";

export function SystemHealth({ health }: { health: SystemHealthSnapshot }) {
  const metric = (value: number | null) => value === null ? "Unavailable" : `${value.toFixed(1)}%`;
  return <section className={`system-health health-${health.status.toLowerCase()}`} aria-label="Server system health">
    <div className="health-heading"><strong>System health</strong><span>{health.status}</span></div>
    <div className="health-metrics"><div><small>CPU</small><strong>{metric(health.cpu_percent)}</strong></div><div><small>Memory</small><strong>{metric(health.memory_percent)}</strong></div></div>
    <p>{health.explanation}</p>
  </section>;
}
