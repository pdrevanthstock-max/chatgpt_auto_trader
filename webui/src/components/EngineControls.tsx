import type { RuntimeSnapshot } from "../api/types";

interface Props { runtime: RuntimeSnapshot; onStart: () => void; onStop: () => void; busy?: boolean; }

export function EngineControls({ runtime, onStart, onStop, busy = false }: Props) {
  const running = runtime.state === "RUNNING";
  return <section className="panel engine-controls" aria-labelledby="engine-title">
    <div className="panel-heading"><div><p className="eyebrow">Engine</p><h2 id="engine-title">PAPER runtime</h2></div><span className={running ? "status active" : "status paused"}>{runtime.state}</span></div>
    <p className="hint">This web runtime is locked to PAPER. It cannot construct a LIVE broker executor.</p>
    <div className="session-banner"><strong>{runtime.market_phase.replaceAll("_", " ")}</strong><span>{runtime.market_status}</span></div>
    {!running ? <button className="primary" disabled={busy} onClick={onStart}>Start PAPER engine</button> : <button className="danger" disabled={busy || runtime.has_active_position} onClick={onStop}>Stop engine</button>}
    {running && runtime.has_active_position && <p className="warning">Stop is disabled while a position is active; risk and exits must continue.</p>}
  </section>;
}
