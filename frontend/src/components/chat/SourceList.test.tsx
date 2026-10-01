import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SourceList } from "./SourceList";

describe("SourceList", () => {
  it("lets the user hide and show source cards without losing their actions", async () => {
    const user = userEvent.setup();
    render(
      <SourceList
        sources={[{ id: "source-1", kind: "email", format: "MAIL", title: "Project update" }]}
        onOpen={vi.fn()}
      />,
    );

    const cards = screen.getByText("Project update").closest(".source-cards-grid");
    expect(cards).not.toHaveAttribute("hidden");

    await user.click(screen.getByRole("button", { name: "Hide sources" }));
    expect(cards).toHaveAttribute("hidden");

    await user.click(screen.getByRole("button", { name: "Show sources (1)" }));
    expect(cards).not.toHaveAttribute("hidden");
    expect(screen.getByRole("button", { name: "Open File" })).toBeInTheDocument();
  });
});