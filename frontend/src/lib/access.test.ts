import { describe, expect, it } from "vitest";
import { permissionsFor, visibleNav } from "./access";

const ids = (perms: ReturnType<typeof permissionsFor>) => visibleNav(perms).flatMap((g) => g.items.map((i) => i.id));

describe("access (UX-only visibility)", () => {
  it("shows only modules a role has permission for", () => {
    expect(ids(permissionsFor(["Employee"]))).toEqual(["Chat", "Knowledge"]);
    expect(ids(permissionsFor(["Project Engineer"]))).toEqual(["Chat", "Knowledge"]);
    expect(ids(permissionsFor(["Supervisor"]))).toEqual(["Chat", "Knowledge", "Email", "Data", "Reports", "Finance", "HR", "Settings"]);
    expect(ids(permissionsFor(["Superior"]))).toEqual(["Chat", "Knowledge", "Email", "Data", "Reports", "Finance", "HR", "Audit", "Settings"]);
  });
  it("unions permissions when the backend reports several roles", () => {
    expect(ids(permissionsFor(["Employee", "Supervisor"]))).toContain("Finance");
  });
  it("ignores unknown roles and grants nothing for them", () => {
    expect(permissionsFor(["Hacker", "__proto__", "constructor"])).toEqual([]);
    expect(ids([])).toEqual(["Chat"]);
  });
  it("drops empty groups", () => {
    expect(visibleNav([]).map((g) => g.id)).toEqual(["assistant"]);
  });
});
