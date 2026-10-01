import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("sends the entered question with the selected search setting and preserves Voice entry", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn().mockResolvedValue(true);
    const onToggleRag = vi.fn();
    const onOpenVoiceMode = vi.fn();
    const { rerender } = render(
      <Composer
        busy={false}
        onSend={onSend}
        focusToken={0}
        ragEnabled
        onToggleRag={onToggleRag}
        onOpenVoiceMode={onOpenVoiceMode}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Company file search: On" }));
    expect(onToggleRag).toHaveBeenCalledWith(false);
    await user.click(screen.getByRole("button", { name: "Open Voice Assistant Mode" }));
    expect(onOpenVoiceMode).toHaveBeenCalledOnce();

    rerender(
      <Composer
        busy={false}
        onSend={onSend}
        focusToken={0}
        ragEnabled={false}
        onToggleRag={onToggleRag}
        onOpenVoiceMode={onOpenVoiceMode}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: "Ask Nanvi" }), "Find the current travel policy");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSend).toHaveBeenCalledWith("Find the current travel policy", false, undefined);
  });
});