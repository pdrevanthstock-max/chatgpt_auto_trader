import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceNavigation } from "./WorkspaceNavigation";

describe("workspace navigation", () => {
  it("switches views without implying LIVE is enabled", async () => {
    const onChange = vi.fn();
    render(<WorkspaceNavigation current="paper" onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /LIVE readiness/i }));

    expect(onChange).toHaveBeenCalledWith("live");
    expect(screen.queryByRole("button", { name: /Start LIVE engine/i })).not.toBeInTheDocument();
  });
});
