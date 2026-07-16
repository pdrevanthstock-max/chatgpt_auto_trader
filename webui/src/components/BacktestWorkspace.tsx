export function BacktestWorkspace() {
  return <section className="panel" aria-labelledby="backtest-title">
    <div className="panel-heading"><div><p className="eyebrow">Historical validation</p><h2 id="backtest-title">Backtesting workspace</h2></div><span className="status paused">API migration pending</span></div>
    <p>The page boundary is established, but historical-data loading and run controls are not yet exposed by FastAPI. No backtest can be started from this page today.</p>
    <div className="safety-list">
      <p><strong>Required before activation:</strong> server-side date validation, isolated backtest state, progress and cancel controls, deterministic exports, and regression comparison with the existing engine.</p>
      <p>The configured historical dates remain unchanged. Backtests will never reuse PAPER or LIVE runtime state.</p>
    </div>
  </section>;
}
