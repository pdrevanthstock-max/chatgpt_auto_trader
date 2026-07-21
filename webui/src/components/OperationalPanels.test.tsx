import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ActivePosition } from "./ActivePosition";
import { CapitalPanel } from "./CapitalPanel";
import { PairDiagnostics } from "./PairDiagnostics";
import { PerformanceCards } from "./PerformanceCards";
import { TradeJournal } from "./TradeJournal";
import { EngineControls } from "./EngineControls";


describe("operational dashboard panels", () => {
  it("starts and stops only the server-authoritative PAPER runtime", async () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(<EngineControls runtime={{ state: "STOPPED", execution_mode: "PAPER", has_active_position: false, activity: [], market_phase: "PREMARKET_IDLE", market_status: "Premarket idle.", seconds_to_next_phase: 2200 }} onStart={onStart} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: /Start PAPER engine/i }));
    expect(onStart).toHaveBeenCalledTimes(1);

    rerender(<EngineControls runtime={{ state: "RUNNING", execution_mode: "PAPER", has_active_position: false, activity: [], market_phase: "ENTRY_WINDOW", market_status: "PAPER entry window is active.", seconds_to_next_phase: 20400 }} onStart={onStart} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: /Stop engine/i }));
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/PAPER entry window is active/i)).toBeInTheDocument();
  });
  it("changes the P&L period and displays separate realized and active values", async () => {
    const onPeriodChange = vi.fn();
    render(<PerformanceCards snapshot={{
      period: "today", mode: "PAPER", realized_pnl: 250, active_pnl: -50,
      total_pnl: 200, daily_risk_pnl: 200, period_start: null, period_end: "2026-07-15T11:00:00"
    }} period="today" onPeriodChange={onPeriodChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Week" }));

    expect(onPeriodChange).toHaveBeenCalledWith("week");
    expect(screen.getByText("₹250.00")).toBeInTheDocument();
    expect(screen.getByText("-₹50.00")).toBeInTheDocument();
  });

  it("makes lots and units prominent and does not invent unavailable marks", () => {
    render(<ActivePosition position={{
      trade_id: "paper-1", execution_mode: "PAPER", index_symbol: "BANKNIFTY", direction: "LONG_CE", regime: "DIRECTIONAL",
      phase: "PHASE_1_BOTH_LEGS", ce_strike: 24200, pe_strike: 24200, ce_entry: 100, pe_entry: 98,
      ce_exit: null, pe_exit: null, lots: 2, lot_size: 65, units_per_leg: 130,
      entry_time: "2026-07-15T10:00:00", exit_time: null, exit_reason: null, gross_pnl: 0,
      transaction_costs: 0, net_pnl: 0, hard_stop_loss: 900, post_daily_sl: false,
      ce_current: null, pe_current: null, mark_to_market_available: false, active_pnl: null
    }} />);

    expect(screen.getByText("2 lots")).toBeInTheDocument();
    expect(screen.getByText("BANKNIFTY")).toBeInTheDocument();
    expect(screen.getByText("130 units / leg")).toBeInTheDocument();
    expect(screen.getByText(/Live mark unavailable/i)).toBeInTheDocument();
  });

  it("starts and stops diagnostics explicitly", async () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const { rerender } = render(<PairDiagnostics diagnostics={{ capturing: false, top_count: 5, rows: [] }} onStart={onStart} onStop={onStop} />);

    expect(screen.getByText(/No captured scan rows.*completed-candle scans/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Start capture/i }));
    expect(onStart).toHaveBeenCalledWith(5);

    rerender(<PairDiagnostics diagnostics={{ capturing: true, top_count: 5, rows: [] }} onStart={onStart} onStop={onStop} />);
    await userEvent.click(screen.getByRole("button", { name: /Stop capture/i }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("renders journal quantity, net result, and period filters", async () => {
    render(<TradeJournal trades={[{
      trade_id: "closed-1", execution_mode: "PAPER", index_symbol: "FINNIFTY", direction: "LONG_CE", regime: "DIRECTIONAL",
      phase: "CLOSED", ce_strike: 24200, pe_strike: 24200, ce_entry: 100, pe_entry: 98,
      ce_exit: 110, pe_exit: 97, lots: 3, lot_size: 65, units_per_leg: 195,
      entry_time: "2026-07-15T10:00:00", exit_time: "2026-07-15T10:05:00", exit_reason: "TARGET_HIT",
      gross_pnl: 1755, transaction_costs: 120, net_pnl: 1635, hard_stop_loss: 900, post_daily_sl: false
    }]} />);
    expect(screen.getByRole("button", { name: "Today" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByText("3 / 195")).toBeInTheDocument();
    expect(screen.getByText("FINNIFTY")).toBeInTheDocument();
    expect(screen.getByText(/1 visible trade/i)).toBeInTheDocument();
    expect(screen.getByText("₹1,635.00")).toBeInTheDocument();
  });

  it("uses a clear simulated deposit and withdrawal workflow", async () => {
    const onAdjust = vi.fn();
    render(<CapitalPanel onAdjust={onAdjust} engineRunning={false} capital={{
      mode: "PAPER", base_capital: 45000, realized_pnl: -1000, cash_adjustments: 6000,
      today_realized_pnl: 0, month_realized_pnl: -1000,
      equity: 50000, live_allocation: null, read_only: true,
      transactions: [{ id: "tx", timestamp: "2026-07-15T10:00:00", mode: "PAPER", type: "DEPOSIT", amount: 6000, note: "Test refill", reference_id: null, broker_balance: null, allocation_after: null }]
    }} />);
    expect(screen.getByText("₹50,000.00")).toBeInTheDocument();
    expect(screen.getByText("Test refill")).toBeInTheDocument();
    expect(screen.getByText("Available PAPER Money")).toBeInTheDocument();
    expect(screen.getByText("Today PAPER P&L")).toBeInTheDocument();
    expect(screen.getByText("Month PAPER P&L")).toBeInTheDocument();
    expect(screen.getByText("Net Deposits / Withdrawals")).toBeInTheDocument();
    expect(screen.queryByText("Base capital")).not.toBeInTheDocument();
    expect(screen.queryByText("Read only")).not.toBeInTheDocument();
    const amountInput = screen.getByRole("textbox", { name: /Amount/i });
    expect(amountInput).toHaveAttribute("inputmode", "decimal");
    await userEvent.type(amountInput, "5000");
    const noteInput = screen.getByRole("textbox", { name: /Audit note/i });
    expect(noteInput).toHaveValue("PAPER test money adjustment");
    await userEvent.clear(noteInput);
    await userEvent.type(noteInput, "Paper refill");
    expect(screen.getByText(/Resulting available money/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Apply PAPER deposit/i }));
    expect(onAdjust).toHaveBeenCalledWith(55000, "Paper refill");
  });
});
