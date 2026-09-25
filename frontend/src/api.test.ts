import { describe, expect, it, vi } from "vitest";
import { ApiError, NanviApiClient } from "./api";

describe("NanviApiClient", () => {
  it("attaches bearer authentication without putting credentials in request bodies", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ subject: "u1", roles: ["Employee"] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = new NanviApiClient({ getAccessToken: async () => "test-token" });
    await api.me();
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Headers).get("Authorization")).toBe("Bearer test-token");
    expect(init?.body).toBeUndefined();
  });

  it("turns backend errors into safe typed errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Forbidden" }), { status: 403, headers: { "Content-Type": "application/json" } }));
    const api = new NanviApiClient();
    await expect(api.history()).rejects.toMatchObject({ status: 403, message: "Forbidden" });
  });

  it("handles rate limiting and Retry-After", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Rate limit exceeded" }), { status: 429, headers: { "Retry-After": "12", "Content-Type": "application/json" } }));
    const api = new NanviApiClient();
    await expect(api.history()).rejects.toMatchObject({ status: 429, retryAfter: 12, message: "Too many requests. Please try again in 12s." });
  });

  it("invokes the unauthorized callback on 401", async () => {
    const onUnauthorized = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Invalid" }), { status: 401, headers: { "Content-Type": "application/json" } }));
    const api = new NanviApiClient({ onUnauthorized });
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("encodes opaque source references", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ reference_id: "x" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const api = new NanviApiClient();
    await api.source("a/b?c");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/sources/a%2Fb%3Fc");
  });
});
