import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { IndexSelector } from "./IndexSelector";

const indices = [
  { symbol: "NIFTY", display_name: "NIFTY 50", lot_size: 65, permission: "TRADABLE" as const, metadata_requires_runtime_validation: true, runtime_connected: true },
  { symbol: "MIDCPNIFTY", display_name: "NIFTY Midcap Select", lot_size: 120, permission: "OBSERVE_ONLY" as const, metadata_requires_runtime_validation: true, runtime_connected: false }
];

describe("IndexSelector", () => {
  it("unchecking All requests the explicit pause state", async () => {
    const onChange = vi.fn();
    render(<IndexSelector indices={indices} selection={{ symbols: ["NIFTY", "MIDCPNIFTY"], version: 0, is_all: true, pause_new_entries: false }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText(/All indices/i));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("shows observe-only permission and active-position safety text", () => {
    render(<IndexSelector indices={indices} selection={{ symbols: [], version: 1, is_all: false, pause_new_entries: true }} onChange={() => undefined} />);
    expect(screen.getByText("Pause New Entries")).toBeInTheDocument();
    expect(screen.getByText("Observe only · feed pending")).toBeInTheDocument();
    expect(screen.getByText("Connected · tradable")).toBeInTheDocument();
    expect(screen.getByText(/Existing positions remain/i)).toBeInTheDocument();
  });
});
