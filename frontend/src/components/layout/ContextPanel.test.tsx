import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { UserIdentity } from "../../api";
import type { Message } from "../../types";
import { ContextPanel } from "./ContextPanel";

const identity: UserIdentity = { subject: "user", issuer: "test", roles: ["Employee"] };
const messages: Message[] = [{
  id: "answer-1",
  role: "assistant",
  text: "The policy is in the handbook.",
  createdAt: 1,
  sources: [{ id: "source-1", kind: "file", format: "PDF", title: "Policy.pdf" }],
}];

describe("ContextPanel", () => {
  it("keeps source and folder actions while simplifying secondary details", async () => {
    const user = userEvent.setup();
    const onOpenSource = vi.fn();
    const onOpenFolderPicker = vi.fn();
    render(
      <ContextPanel
        identity={identity}
        messages={messages}
        onOpenSource={onOpenSource}
        onClose={vi.fn()}
        folderPath="C:/CompanyData"
        folderName="CompanyData"
        folderFileCount={496}
        onOpenFolderPicker={onOpenFolderPicker}
      />,
    );

    expect(screen.getByRole("heading", { name: "Workspace details" })).toBeInTheDocument();
    const citationsSummary = screen.getByText("Cited documents");
    const citationsDisclosure = citationsSummary.closest("details") as HTMLDetailsElement;
    expect(citationsDisclosure.open).toBe(false);
    await user.click(citationsSummary);
    expect(citationsDisclosure.open).toBe(true);
    await user.click(screen.getByRole("button", { name: /Policy\.pdf/ }));
    expect(onOpenSource).toHaveBeenCalledWith(messages[0].sources?.[0]);

    const folderSummary = screen.getByText("Company files");
    const folderDisclosure = folderSummary.closest("details") as HTMLDetailsElement;
    expect(folderDisclosure.open).toBe(false);
    await user.click(folderSummary);
    expect(folderDisclosure.open).toBe(true);
    expect(screen.getByText("C:/CompanyData")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Change folder" }));
    expect(onOpenFolderPicker).toHaveBeenCalledOnce();

    expect(screen.queryByText("Session Identity")).not.toBeInTheDocument();
    expect(screen.queryByText("Workspace HUD")).not.toBeInTheDocument();
  });
});