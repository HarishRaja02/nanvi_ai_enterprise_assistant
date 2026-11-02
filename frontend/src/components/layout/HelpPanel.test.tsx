import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { HelpPanel } from "./HelpPanel";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open help</button>
      {open && <HelpPanel onClose={() => setOpen(false)} />}
    </>
  );
}

describe("HelpPanel", () => {
  it("filters existing help and closes on Escape, restoring focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open help" });
    await user.click(opener);

    const dialog = screen.getByRole("dialog", { name: "Nanvi help" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const search = screen.getByRole("searchbox", { name: "Search help" });
    await user.type(search, "sources");
    expect(screen.getByRole("heading", { name: "Sources and answers" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ask Nanvi" })).not.toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("navigates to that page and closes when a specific help topic is clicked", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onClose = vi.fn();
    render(<HelpPanel onClose={onClose} onNavigate={onNavigate} />);

    // Click on "Connections Hub"
    const connectionsTopic = screen.getByRole("heading", { name: "Connections Hub" });
    await user.click(connectionsTopic);

    expect(onNavigate).toHaveBeenCalledWith("Settings", "connections");
    expect(onClose).toHaveBeenCalled();
  });
});