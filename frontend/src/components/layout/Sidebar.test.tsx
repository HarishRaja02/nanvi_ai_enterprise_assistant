import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { NavGroup } from "../../lib/access";
import { Sidebar } from "./Sidebar";

const groups: NavGroup[] = [
  { id: "assistant", items: [{ id: "Chat", label: "Assistant" }] },
  { id: "sources", label: "Sources", items: [{ id: "Knowledge", label: "Knowledge" }] },
];

describe("Sidebar More tools", () => {
  it("opens the flyout and preserves route selection behavior", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onCloseDrawer = vi.fn();
    render(
      <Sidebar
        groups={groups}
        active="Chat"
        onNavigate={onNavigate}
        onNewConversation={vi.fn()}
        history={[]}
        historyLoading={false}
        historyError=""
        onRetryHistory={vi.fn()}
        onOpenHelp={vi.fn()}
        onSelectConversation={vi.fn()}
        userName="Test User"
        userRole="Employee"
        onSignOut={vi.fn()}
        onCloseDrawer={onCloseDrawer}
      />,
    );

    const toggle = screen.getByRole("button", { name: "More tools" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "More workspace tools" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    expect(onNavigate).toHaveBeenCalledWith("Knowledge");
    expect(onCloseDrawer).toHaveBeenCalledOnce();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});