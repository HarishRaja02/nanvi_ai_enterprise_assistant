import { describe, expect, it } from "vitest";
import { parseSsoUrl } from "./config";

describe("parseSsoUrl", () => {
  it("accepts absolute https URLs", () => {
    expect(parseSsoUrl("https://login.example.com/authorize?x=1")).toBe("https://login.example.com/authorize?x=1");
  });
  it("accepts http only for localhost development", () => {
    expect(parseSsoUrl("http://localhost:9000/auth")).toContain("localhost");
    expect(parseSsoUrl("http://sso.example.com/auth")).toBeNull();
  });
  it("rejects dangerous or malformed values because this becomes a navigation target", () => {
    for (const v of ["javascript:alert(1)", "data:text/html,x", "//evil.example", "/relative", "not a url", "", "   ", undefined]) {
      expect(parseSsoUrl(v)).toBeNull();
    }
  });
});
