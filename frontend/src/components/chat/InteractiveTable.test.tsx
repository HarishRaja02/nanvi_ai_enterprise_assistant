import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { InteractiveTable } from "./InteractiveTable";

describe("InteractiveTable", () => {
  it("starts collapsed and keeps filter, sort, and CSV controls available when expanded", async () => {
    const user = userEvent.setup();
    render(
      <InteractiveTable
        headers={["Contract ID", "Account"]}
        rows={[
          ["CTR-01", "Acme"],
          ["CTR-02", "Apex"],
          ["CTR-03", "Globex"],
        ]}
        metadata={{ filename: "contracts.csv", sheet: "Renewals" }}
      />,
    );

    const summary = screen.getByText("Show table").closest("summary");
    const disclosure = summary?.closest("details") as HTMLDetailsElement;
    expect(disclosure.open).toBe(false);
    expect(screen.getByText("contracts.csv")).toBeInTheDocument();

    await user.click(summary!);
    expect(disclosure.open).toBe(true);
    expect(screen.getByRole("textbox", { name: "Filter table records" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Contract ID" })).toHaveAttribute("title", "Sort by Contract ID");
    expect(screen.getByRole("button", { name: "Copy table as CSV" })).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });
});