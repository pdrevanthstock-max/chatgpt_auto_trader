import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SystemHealth } from "./SystemHealth";

describe("SystemHealth", () => {
  it("shows real percentages, status and threshold explanation", () => {
    render(<SystemHealth health={{ cpu_percent: 81.2, memory_percent: 72.5, status: "WARNING", explanation: "Warning: CPU is at or above 75%." }} />);
    expect(screen.getByText("81.2%")).toBeInTheDocument();
    expect(screen.getByText("72.5%")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getByText(/CPU is at or above 75%/i)).toBeInTheDocument();
  });

  it("does not invent zero values when metrics are unavailable", () => {
    render(<SystemHealth health={{ cpu_percent: null, memory_percent: null, status: "UNAVAILABLE", explanation: "System metrics are unavailable." }} />);
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
});
