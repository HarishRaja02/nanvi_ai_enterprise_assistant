import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Modal } from "./Modal";

function Harness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && <Modal title="Details" onClose={() => setOpen(false)}><button>Inside</button></Modal>}
    </>
  );
}

describe("Modal", () => {
  it("is labelled, traps focus, closes on Escape and restores focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Open" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Details" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    for (let i = 0; i < 5; i++) await user.tab();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("closes when the backdrop is pressed but not when the dialog is", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(screen.getByRole("dialog"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.pointer({ target: document.querySelector(".modal-backdrop")!, keys: "[MouseLeft]" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
