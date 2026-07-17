export type IndexPermission = "TRADABLE" | "OBSERVE_ONLY";

export interface IndexInfo {
  symbol: string;
  display_name: string;
  lot_size: number;
  permission: IndexPermission;
  metadata_requires_runtime_validation: boolean;
  runtime_connected: boolean;
}

export interface IndexSelection {
  symbols: string[];
  version: number;
  is_all: boolean;
  pause_new_entries: boolean;
}

export interface IndexUniverseResponse {
  indices: IndexInfo[];
  selection: IndexSelection;
}

export type PerformancePeriod = "today" | "week" | "month" | "year" | "all_time";

export interface PerformanceSnapshot {
  period: PerformancePeriod;
  mode: "PAPER" | "LIVE";
  realized_pnl: number;
  active_pnl: number;
  total_pnl: number;
  daily_risk_pnl: number;
  period_start: string | null;
  period_end: string;
}

export interface TradeRow {
  trade_id: string; execution_mode: string; index_symbol: string; direction: string; regime: string; phase: string;
  ce_strike: number; pe_strike: number; ce_entry: number; pe_entry: number;
  ce_exit: number | null; pe_exit: number | null; lots: number; lot_size: number;
  units_per_leg: number; entry_time: string | null; exit_time: string | null;
  exit_reason: string | null; gross_pnl: number; transaction_costs: number; net_pnl: number;
  hard_stop_loss: number; post_daily_sl: boolean;
}

export interface ActivePositionView extends TradeRow {
  ce_current: number | null; pe_current: number | null;
  mark_to_market_available: boolean; active_pnl: number | null;
}

export interface CapitalTransaction {
  id: string; timestamp: string; mode: string; type: string; amount: number; note: string;
  reference_id: string | null; broker_balance: number | null; allocation_after: number | null;
}

export interface CapitalSnapshot {
  mode: "PAPER" | "LIVE"; base_capital: number | null; realized_pnl: number | null;
  cash_adjustments: number | null; equity: number | null; live_allocation: number | null;
  transactions: CapitalTransaction[]; read_only: boolean;
}

export interface DiagnosticSnapshot {
  capturing: boolean;
  top_count: 5 | 10;
  /** Flat rows remain the compatibility contract; monitoring fields are additive and optional. */
  rows: Record<string, unknown>[];
}

export interface RuntimeSnapshot {
  state: "STOPPED" | "RUNNING";
  execution_mode: "PAPER";
  has_active_position: boolean;
  activity: string[];
  market_phase: string;
  market_status: string;
  seconds_to_next_phase: number;
  system_health?: SystemHealthSnapshot;
}

export interface SystemHealthSnapshot {
  cpu_percent: number | null;
  memory_percent: number | null;
  status: "NORMAL" | "WARNING" | "CRITICAL" | "UNAVAILABLE";
  explanation: string;
}

export interface RuntimeEvent {
  type: "runtime_snapshot";
  runtime: RuntimeSnapshot;
  position: ActivePositionView | null;
  diagnostics: DiagnosticSnapshot;
}
