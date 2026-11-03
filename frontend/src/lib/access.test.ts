import { describe, expect, it } from "vitest";
import { permissionsFor, visibleNav } from "./access";

const ids = (perms: ReturnType<typeof permissionsFor>) => visibleNav(perms).flatMap((g) => g.items.map((i) => i.id));

describe("access (UX-only visibility)", () => {
  it("shows only modules a role has permission for, hiding Knowledge, Finance, HR, and Audit by default", () => {
    expect(ids(permissionsFor(["Employee"]))).toEqual(["Chat"]);
    expect(ids(permissionsFor(["Project Engineer"]))).toEqual(["Chat"]);
    expect(ids(permissionsFor(["Supervisor"]))).toEqual(["Chat", "Email", "Data", "Reports", "Settings"]);
    expect(ids(permissionsFor(["Superior"]))).toEqual(["Chat", "Email", "Data", "Reports", "Settings", "Logs"]);
  });
  it("unions permissions when the backend reports several roles", () => {
    expect(ids(permissionsFor(["Employee", "Supervisor"]))).toContain("Reports");
  });
  it("can include hidden modules when includeHidden is true", () => {
    const superiorAll = visibleNav(permissionsFor(["Superior"]), false, true).flatMap((g) => g.items.map((i) => i.id));
    expect(superiorAll).toEqual(["Chat", "Knowledge", "Email", "Data", "Reports", "Finance", "HR", "Audit", "Settings", "Logs"]);
  });
  it("ignores unknown roles and grants nothing for them", () => {
    expect(permissionsFor(["Hacker", "__proto__", "constructor"])).toEqual([]);
    expect(ids([])).toEqual(["Chat"]);
  });
  it("drops empty groups", () => {
    expect(visibleNav([]).map((g) => g.id)).toEqual(["assistant"]);
  });
});
