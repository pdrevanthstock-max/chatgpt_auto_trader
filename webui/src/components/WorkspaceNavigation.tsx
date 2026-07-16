export type WorkspaceView = "paper" | "backtest" | "live";

interface Props { current: WorkspaceView; onChange: (view: WorkspaceView) => void; }

export function WorkspaceNavigation({ current, onChange }: Props) {
  return <nav className="workspace-nav" aria-label="Trading workspaces">
    <button className={current === "paper" ? "active" : ""} onClick={() => onChange("paper")}>PAPER operations</button>
    <button className={current === "backtest" ? "active" : ""} onClick={() => onChange("backtest")}>Backtesting</button>
    <button className={current === "live" ? "active" : ""} onClick={() => onChange("live")}>LIVE readiness</button>
  </nav>;
}
