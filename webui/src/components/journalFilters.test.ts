import { describe, expect, it } from "vitest";
import type { TradeRow } from "../api/types";
import { filterTradesByPeriod } from "./journalFilters";

const trade = (id: string, entry_time: string | null): TradeRow => ({
  trade_id: id, execution_mode: "PAPER", index_symbol: "NIFTY", direction: "LONG_CE",
  regime: "DIRECTIONAL", phase: "CLOSED", ce_strike: 24200, pe_strike: 24250,
  ce_entry: 100, pe_entry: 95, ce_exit: 110, pe_exit: 90, lots: 1, lot_size: 65,
  units_per_leg: 65, entry_time, exit_time: entry_time, exit_reason: "TARGET_HIT",
  gross_pnl: 300, transaction_costs: 50, net_pnl: 250, hard_stop_loss: 450,
  post_daily_sl: false,
});

describe("journal filters in IST", () => {
  const now = new Date("2026-07-17T06:30:00Z");
  const rows = [
    trade("today", "2026-07-16T19:00:00Z"),
    trade("yesterday", "2026-07-16T10:00:00Z"),
    trade("week", "2026-07-13T04:00:00Z"),
    trade("month", "2026-07-02T04:00:00Z"),
    trade("old", "2026-06-30T04:00:00Z"),
    trade("missing", null),
  ];

  it("uses IST calendar boundaries for each period", () => {
    expect(filterTradesByPeriod(rows, "today", now).map(row => row.trade_id)).toEqual(["today"]);
    expect(filterTradesByPeriod(rows, "yesterday", now).map(row => row.trade_id)).toEqual(["yesterday"]);
    expect(filterTradesByPeriod(rows, "week", now).map(row => row.trade_id)).toEqual(["today", "yesterday", "week"]);
    expect(filterTradesByPeriod(rows, "month", now).map(row => row.trade_id)).toEqual(["today", "yesterday", "week", "month"]);
    expect(filterTradesByPeriod(rows, "all", now)).toHaveLength(6);
  });
});
