export function LiveReadinessWorkspace() {
  return <section className="panel" aria-labelledby="live-title">
    <div className="panel-heading"><div><p className="eyebrow">Broker safety boundary</p><h2 id="live-title">LIVE readiness</h2></div><span className="status danger-status">LOCKED</span></div>
    <p>LIVE execution is unavailable in this web process. There is no LIVE start endpoint and this page cannot construct a broker executor.</p>
    <div className="safety-list">
      <p><strong>Planned authentication:</strong> a server-side hashed PIN, rate-limited attempts, a short-lived session, and an audit record that never stores the PIN.</p>
      <p><strong>Required execution gates:</strong> stopped PAPER engine, zero unresolved positions, explicit allocation within broker-confirmed funds, readiness thresholds, typed confirmation, and another authorization check at order time.</p>
      <p>Opening this view is informational only. It cannot submit, modify, or cancel a Dhan order.</p>
    </div>
  </section>;
}
