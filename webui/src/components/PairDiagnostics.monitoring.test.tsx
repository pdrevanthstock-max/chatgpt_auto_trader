import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PairDiagnostics } from "./PairDiagnostics";
import type { DiagnosticSnapshot } from "../api/types";

const row = (index: string, pair: string, projectedNet: number, rank: number, extra: Record<string, unknown> = {}) => ({
  cycle_id: "scan-42", timestamp: "2026-07-17T10:01:02+05:30", index_symbol: index, rank, pair, pair_class: "ATM_ITM",
  ce_moneyness: "ATM", pe_moneyness: "ITM1", ce_strike: 25100, pe_strike: 25050,
  divergence_pct: 4.2, verdict: "PASS", rejection_reason: "", projected_net: projectedNet,
  projected_return_pct: .72, combined_ask: 300, lot_size: index === "BANKNIFTY" ? 30 : index === "FINNIFTY" ? 60 : 65,
  one_lot_premium: index === "BANKNIFTY" ? 9000 : 19500, deployable_capital: 40500,
  max_lots: 2, charges_estimate: 122, capital_shortfall: 0, quote_age_seconds: .8,
  spot: 25072, atm_strike: 25100, expiry: "2026-07-23", maximum_premium_at_risk: 39000,
  generated_count: 29, quotable_count: 27, signal_count: 12, economic_count: 4, final_count: 2,
  ce_universe: [{ strike: 25100, moneyness: "ATM" }, { strike: 25050, moneyness: "ITM1" }],
  pe_universe: [{ strike: 25100, moneyness: "ATM" }, { strike: 25150, moneyness: "ITM1" }],
  research_ce_universe: [{ strike: 25150, moneyness: "OTM1" }],
  research_pe_universe: [{ strike: 25050, moneyness: "OTM1" }],
  prefilter_rejection_reasons: { DUAL_DECAY: 9, STALE_PRICE: 2 }, internal_debug_value: "drawer-only",
  ...extra,
});

describe("PairDiagnostics strategy monitoring", () => {
  it("explains that deployable money is the available balance after the safety reserve", () => {
    const diagnostics: DiagnosticSnapshot = {
      capturing: true,
      top_count: 5,
      rows: [row("BANKNIFTY", "57200 CE + 57000 PE", 410, 1)],
    };
    render(<PairDiagnostics diagnostics={diagnostics} onStart={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByText("Available after 10% safety reserve")).toBeInTheDocument();
  });

  it("shows independent index views, bounded matrices, funnel, capital and global comparison", async () => {
    const diagnostics: DiagnosticSnapshot = {
      capturing: true,
      top_count: 5,
      rows: [
        row("NIFTY", "25100 CE + 25050 PE", 260, 1),
        row("BANKNIFTY", "57200 CE + 57000 PE", 410, 1, { ce_moneyness: "OTM1", pe_moneyness: "OTM2", pair_class: "OTM_RESEARCH", displacement_reason: "Higher projected net after costs" }),
        row("FINNIFTY", "26300 CE + 26200 PE", 330, 1),
      ],
    };
    render(<PairDiagnostics diagnostics={diagnostics} onStart={vi.fn()} onStop={vi.fn()} />);

    expect(screen.getByRole("heading", { name: /Global candidate comparison/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Global Top pairs/i })).toBeInTheDocument();

    const niftyTab = screen.getByRole("tab", { name: /^NIFTY/i });
    const bankTab = screen.getByRole("tab", { name: /^BANKNIFTY/i });
    expect(niftyTab).toHaveAttribute("aria-selected", "true");
    await userEvent.click(bankTab);
    expect(bankTab).toHaveAttribute("aria-selected", "true");
    const capitalSection = screen.getByRole("heading", { name: /BANKNIFTY capital/i }).closest("section")!;
    expect(within(capitalSection).getByText("₹9,000.00")).toBeInTheDocument();
    expect(screen.queryByText(/Established 5/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("25100 (ATM)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("25050 (ITM1)").length).toBeGreaterThan(0);
    expect(screen.getByText("Generated")).toBeInTheDocument();
    expect(screen.getByText("DUAL DECAY · 9")).toBeInTheDocument();

    const table = screen.getByRole("table", { name: /BANKNIFTY Top pairs/i });
    expect(within(table).getByRole("columnheader", { name: /Time \(IST\)/i })).toBeInTheDocument();
    expect(within(table).getByText("17 Jul 2026, 10:01:02 am")).toBeInTheDocument();
    await userEvent.click(within(table).getByRole("button", { name: /Inspect 57200 CE/i }));
    expect(screen.getByRole("dialog", { name: /Pair details/i })).toHaveTextContent("drawer-only");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: /Pair details/i })).not.toBeInTheDocument();
  });

  it("remains useful with the current flat API and empty snapshots", () => {
    const { rerender } = render(<PairDiagnostics diagnostics={{ capturing: false, top_count: 5, rows: [{ index: "NIFTY", pair: "ATM CE + ATM PE", projected_net: 220 }] }} onStart={vi.fn()} onStop={vi.fn()} />);
    expect(screen.getByRole("tab", { name: /^NIFTY/i })).toBeInTheDocument();
    expect(screen.getByText("ATM CE + ATM PE")).toBeInTheDocument();

    rerender(<PairDiagnostics diagnostics={{ capturing: false, top_count: 5, rows: [] }} onStart={vi.fn()} onStop={vi.fn()} />);
    expect(screen.getByText(/No captured scan rows/i)).toBeInTheDocument();
  });
});
