import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ChatResponse, NanviApiClient, UserIdentity } from "../api";
import { useChat } from "./useChat";

const identity: UserIdentity = { subject: "u", issuer: "i", roles: ["Employee"] };
const reply = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  conversation_id: "c1", answer: "Answer", capability: "knowledge_search", trace: ["step"], history: [],
  sources: [{ reference_id: "s1", source_type: "file", display_name: "a.pdf", sheet: "S1" }], ...over,
});
const last = <T,>(items: T[]): T | undefined => items[items.length - 1];
const apiWith = (chat: NanviApiClient["chat"]) => ({ chat }) as unknown as NanviApiClient;

describe("useChat", () => {
  it("keeps backend trace, capability and sources on the answer", async () => {
    const api = apiWith(vi.fn().mockResolvedValue(reply()));
    const { result } = renderHook(() => useChat(api, identity));
    await act(async () => { await result.current.send("hello"); });
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    const answer = result.current.messages[1];
    expect(answer).toMatchObject({ capability: "knowledge_search", trace: ["step"] });
    expect(answer.sources?.[0].sheet).toBe("S1");
  });

  it("continues the same conversation and ignores empty input", async () => {
    const chat = vi.fn().mockResolvedValue(reply());
    const { result } = renderHook(() => useChat(apiWith(chat), identity));
    expect(await result.current.send("   ")).toBe(false);
    await act(async () => { await result.current.send("one"); });
    await waitFor(() => expect(result.current.busy).toBe(false));
    await act(async () => { await result.current.send("two"); });
    await waitFor(() => expect(chat).toHaveBeenCalledTimes(2));
    expect(chat.mock.calls[1]).toEqual(["two", "c1"]);
  });

  it("retry re-sends the failed query without duplicating the user turn", async () => {
    const chat = vi.fn().mockRejectedValueOnce(new ApiError("Too many requests.", 429, 5)).mockResolvedValueOnce(reply());
    const { result } = renderHook(() => useChat(apiWith(chat), identity));
    await act(async () => { await result.current.send("q"); });
    await waitFor(() => expect(last(result.current.messages)?.error).toBe(true));
    expect(last(result.current.messages)?.retryAfter).toBe(5);
    await act(async () => { result.current.retry(last(result.current.messages)!.id); });
    await waitFor(() => expect(last(result.current.messages)?.error).toBeUndefined());
    expect(chat).toHaveBeenCalledTimes(2);
    expect(chat.mock.calls[1][0]).toBe("q");
    expect(result.current.messages.some((m) => m.error)).toBe(false); // the failed bubble is replaced, not left behind
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
  });

  it("discards a reply that arrives after the conversation was reset", async () => {
    let resolve!: (r: ChatResponse) => void;
    const chat = vi.fn().mockReturnValue(new Promise<ChatResponse>((r) => { resolve = r; }));
    const { result } = renderHook(() => useChat(apiWith(chat), identity));
    await act(async () => { await result.current.send("slow"); });
    act(() => result.current.reset());
    await act(async () => { resolve(reply({ answer: "LATE" })); });
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.conversationId).toBeUndefined();
    expect(result.current.busy).toBe(false);
  });

  it("clears the conversation when the identity goes away (sign-out / 401)", async () => {
    const api = apiWith(vi.fn().mockResolvedValue(reply()));
    const { result, rerender } = renderHook(({ id }) => useChat(api, id), { initialProps: { id: identity as UserIdentity | null } });
    await act(async () => { await result.current.send("hello"); });
    await waitFor(() => expect(result.current.messages).toHaveLength(2));
    rerender({ id: null });
    await waitFor(() => expect(result.current.messages).toHaveLength(0));
  });
});
