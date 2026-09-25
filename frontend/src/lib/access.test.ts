import { describe, expect, it } from "vitest";
import { permissionsFor, visibleNav } from "./access";

const ids = (perms: ReturnType<typeof permissionsFor>) => visibleNav(perms).flatMap((g) => g.items.map((i) => i.id));

describe("access (UX-only visibility)", () => {
  it("shows only modules a role has permission for", () => {
    expect(ids(permissionsFor(["Employee"]))).toEqual(["Chat", "Knowledge", "Email", "Data", "Reports", "Settings"]);
    expect(ids(permissionsFor(["IT Admin"]))).toContain("Audit");
    expect(ids(permissionsFor(["IT Admin"]))).not.toContain("Finance");
    expect(ids(permissionsFor(["CEO"]))).toEqual(["Chat", "Knowledge", "Email", "Data", "Reports", "Finance", "HR", "Audit", "Settings"]);
  });
  it("unions permissions when the backend reports several roles", () => {
    expect(ids(permissionsFor(["Employee", "HR"]))).toContain("HR");
  });
  it("ignores unknown roles and grants nothing for them", () => {
    expect(permissionsFor(["Hacker", "__proto__", "constructor"])).toEqual([]);
    expect(ids([])).toEqual(["Chat", "Settings"]);
  });
  it("drops empty groups", () => {
    expect(visibleNav([]).map((g) => g.id)).toEqual(["assistant", "governance"]);
  });
});
