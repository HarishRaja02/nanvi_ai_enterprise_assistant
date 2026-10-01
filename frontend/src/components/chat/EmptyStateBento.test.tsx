import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EmptyStateBento } from "./EmptyStateBento";
import { ROTATING_STARTERS } from "../../lib/prompts";

describe("EmptyStateBento", () => {
  afterEach(() => vi.useRealTimers());

  it("dissolves to one new suggested question every three seconds and keeps prompts clickable", () => {
    vi.useFakeTimers();
    const onPick = vi.fn();
    const visiblePrompts = ROTATING_STARTERS.slice(0, 5);
    render(<EmptyStateBento starters={visiblePrompts} onPick={onPick} />);

    const promptList = screen.getByRole("region", { name: "Suggested questions" });
    expect(within(promptList).getAllByRole("button")).toHaveLength(4);
    expect(within(promptList).getByRole("button", { name: visiblePrompts[0].prompt })).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(2500); });
    expect(within(promptList).getByRole("button", { name: visiblePrompts[0].prompt })).toHaveClass("is-dissolving");

    act(() => { vi.advanceTimersByTime(500); });
    expect(within(promptList).queryByRole("button", { name: visiblePrompts[0].prompt })).not.toBeInTheDocument();
    expect(within(promptList).getByRole("button", { name: visiblePrompts[4].prompt })).toBeInTheDocument();

    fireEvent.click(within(promptList).getByRole("button", { name: visiblePrompts[4].prompt }));
    expect(onPick).toHaveBeenCalledWith(visiblePrompts[4].prompt);
  });
});